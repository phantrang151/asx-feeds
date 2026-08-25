import calendar
from datetime import datetime, timezone

from langchain_anthropic import ChatAnthropic
from langgraph.types import Command

from config import ANALYSIS_MODEL, ANTHROPIC_API_KEY
from db.queries import (
    get_feeds_for_user,
    get_custom_feed_items,
    get_common_feed_items,
    match_document_chunks_for_embedding,
    match_ticker_news_for_embedding,
    get_company_sector,
    get_peer_tickers,
    insert_ticker_insight,
)
from agent.shared.synthesize import synthesize_insight

from .insight_schemas import FeedSummary, FeedSourceDecision, FeedSourcePlan

def _six_months_ago(now: datetime) -> datetime:
    month_index = now.year * 12 + now.month - 1 - 6
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    day = min(now.day, calendar.monthrange(year, month)[1])
    return now.replace(year=year, month=month, day=day)

FEED_SUMMARY_PROMPT = """You are a financial analyst. You are given several items that were
classified as relevant to one specific feed/topic for a stock.

Summarize what these items say about this topic in 1-3 sentences. Look across all of them
together rather than listing each one separately.

Also judge whether these items actually give a real, on-topic signal about this specific
topic. Thin evidence is still sufficient as long as it's genuinely on-topic - even a single
relevant item can be worth surfacing as an early signal (e.g. one article about a new AI
investment can signal a company is starting to move in that direction). Only mark the
evidence insufficient if the items are off-topic, too vague, or don't genuinely address what
this feed is meant to track - not merely because there's little of it.

If the evidence is thin (e.g. a single item, or items that only hint at something rather
than confirm it), say so plainly in the summary itself - e.g. "Based on limited information
(a single article), ..." - rather than stating it with the same confidence as a
well-supported trend.

Never recommend buying, selling, or holding the stock, and never state or imply whether now
is a good or bad time to invest."""


def summarize_feed_items(feed_name: str, ticker: str, items: list[dict]) -> FeedSummary:
    """One LLM call per feed that passed planner_node's cheap item-count floor. Returns a
    structured judgment, not just prose: `sufficient` is the model's own qualitative call on
    whether these items actually support a conclusion about this topic - a feed can have
    items and still come back `sufficient=False` (e.g. the one matched item isn't really
    about what the feed tracks). Only ever summarizes this one feed's own items - never
    asked to connect across feeds, that's synthesize_node's job via synthesize_insight()."""
    items_text = "\n".join(f"- {item['content_summary']}" for item in items)
    llm = ChatAnthropic(model=ANALYSIS_MODEL, api_key=ANTHROPIC_API_KEY)
    prompt = f"{FEED_SUMMARY_PROMPT}\n\nTicker: {ticker}\nFeed: {feed_name}\n\nItems:\n{items_text}"
    return llm.with_structured_output(FeedSummary).invoke(prompt)


SOURCE_DECISION_PROMPT = """You are a financial analyst deciding what EXTRA data sources
should be pulled in for each feed/topic being tracked for a stock, beyond that feed's own
matched news items.

For each feed below, decide two independent yes/no questions:

1. needs_reports - would official financial-report content (uploaded filings, earnings
   reports, financial statements) materially help answer this feed's topic? Say yes for a
   feed like "Revenue trend", where a news headline rarely breaks down WHERE the revenue is
   actually coming from (product lines, subscriptions vs one-off sales, geographic mix) -
   only the company's own financial statements reliably show that. Say no for feeds about
   sentiment, management commentary, competitors, scandals, or a single self-contained
   initiative (e.g. "Investment in AI" - the company's own announcements and news coverage
   of it are already sufficient; a financial report won't add anything a headline hasn't).

2. needs_peer_news - would news about OTHER companies in the same industry materially help
   judge this feed's topic? Say yes whenever the real question is "is this specific to this
   company, or is it happening industry-wide" - which is exactly what a feed like "Business
   strategy" needs to answer. For example: if ANZ cuts its home-loan rate, that's only a
   meaningful competitive move if OTHER banks aren't doing the same - if mortgage
   applications are down across Australia and every bank is cutting rates, ANZ's move isn't
   actually "outstanding," it's just following the industry. Likewise, Telstra announcing 5G
   network expansion isn't a distinguishing strategic signal if every telco is doing the same
   thing - only comparing against peers reveals whether it's genuinely competitive
   positioning or just keeping pace. Say no for feeds that are purely about this company's
   own internal matters, numbers, or self-contained events with no "is this normal for the
   industry" question to answer (e.g. "Investment in AI" again - no need to check whether
   other companies are also investing in AI to summarize what THIS company announced).

A feed can be yes/yes, yes/no, no/yes, or no/no - the two questions are independent, and
most feeds should be no/no (their own matched news is enough). Only say yes when the extra
source would genuinely add signal, not merely because it's tangentially related.

When needs_peer_news is yes, the system will automatically limit the lookup to at most four
other ASX 200 companies in the same industry, then keep only semantically similar news from
the last six months. You only decide whether that bounded comparison would add signal; do not
request peers merely to broaden coverage.

Return one decision per feed listed below, using the exact feed name given.

Ticker: {ticker}

Feeds:
{feed_list}
"""


def decide_feed_sources(ticker: str, feeds: list[dict]) -> dict[str, FeedSourceDecision]:
    """ONE batched LLM call across every feed for this (user, ticker) pair, not one call per
    feed, to control cost. `feeds` is the same feed rows planner_node already fetched via
    get_feeds_for_user - only feed_name/feed_description are used. Returns a dict keyed by
    feed_name; any feed name the LLM doesn't echo back exactly falls back to
    needs_reports=False, needs_peer_news=False rather than crashing or silently over-fetching."""
    if not feeds:
        return {}

    feed_list = "\n".join(f"- {f['feed_name']}: {f['feed_description']}" for f in feeds)
    llm = ChatAnthropic(model=ANALYSIS_MODEL, api_key=ANTHROPIC_API_KEY)
    prompt = SOURCE_DECISION_PROMPT.format(ticker=ticker, feed_list=feed_list)
    plan = llm.with_structured_output(FeedSourcePlan).invoke(prompt)
    by_name = {d.feed_name: d for d in plan.decisions}

    return {
        f["feed_name"]: by_name.get(
            f["feed_name"],
            FeedSourceDecision(feed_name=f["feed_name"], needs_reports=False, needs_peer_news=False),
        )
        for f in feeds
    }


def _get_peer_tickers_for(ticker: str, limit: int = 4) -> list[str]:
    """DB-only peer lookup for execute_step_node - reads this ticker's cached industry
    (ensure_company_sector_cached in ingestion_steps.py populates it during phase 1) and
    finds other tickers sharing it. Returns [] (never raises) if this ticker has no cached
    sector yet - e.g. a brand-new watchlist add whose first pipeline run hasn't reached
    phase 1 for it yet."""
    company = get_company_sector(ticker)
    if not company or not company.get("industry"):
        return []
    return get_peer_tickers(company["industry"], exclude_ticker=ticker, limit=min(limit, 4))


def planner_node(state):
    """
    Fetches every feed's own items once, up front - into items_by_feed, which
    execute_step_node reads from instead of re-querying the DB on every step. Feeds with no
    own classified news are discarded before the LLM source-decision call, so they consume
    neither planner tokens nor supplementary-source queries. For the remaining feeds, one
    batched LLM call decides whether reports or peer-industry news would materially help.

    A feed therefore needs at least one own classified news item before any supplementary
    source is considered. Empty feeds go straight to synthesis as insufficient evidence.
    """
    user_id, ticker = state["user_id"], state["ticker"]
    feeds = get_feeds_for_user(user_id, ticker)

    items_by_feed = {
        f["feed_name"]: (
            get_common_feed_items(f["common_feed_template_id"], ticker)
            if f["feed_type"] == "common"
            else get_custom_feed_items(f["id"])
        )
        for f in feeds
    }
    eligible_feeds = [f for f in feeds if items_by_feed[f["feed_name"]]]
    feed_embeddings = {f["feed_name"]: f["description_embedding"] for f in eligible_feeds}
    source_decisions = decide_feed_sources(ticker, eligible_feeds)
    plan = [f["feed_name"] for f in eligible_feeds]

    return Command(
        goto="execute_step" if plan else "synthesize",
        update={
            "items_by_feed": items_by_feed,
            "feed_embeddings": feed_embeddings,
            "source_decisions": source_decisions,
            "supplementary_items_by_feed": {},
            "plan": plan,
            "step_results": [],
        },
    )


def execute_step_node(state):
    """Executes the next un-run step of the plan: fetches this feed's supplementary
    sources (if decide_feed_sources flagged any), then summarizes its own items together
    with them in ONE combined LLM call. `.get(feed_name, [])` rather than direct indexing
    so a plan entry with no matching fetched feed degrades to an empty summary instead of
    crashing.

    Supplementary items (report chunks, peer-ticker news) are deliberately kept OUT of
    `items`/step_results["items"] and stored separately in supplementary_items_by_feed -
    they have no "id" field at all, so there's nothing for synthesize_node's id-collection
    loop (which only ever reads items_by_feed) to accidentally pick up. That's what keeps
    based_on_feed_item_ids strictly real feed_items/common_feed_items ids even though the
    summary itself was informed by other tables.

    Once the plan is exhausted, routes directly to synthesize. Missing or insufficient
    evidence is reported by the feed summary rather than triggering another retrieval pass.
    """
    step_index = len(state["step_results"])
    feed_name = state["plan"][step_index]
    ticker = state["ticker"]
    own_items = state["items_by_feed"].get(feed_name, [])
    decision = state["source_decisions"].get(feed_name)
    embedding = state["feed_embeddings"].get(feed_name)

    supplementary_items = []
    if decision and embedding:
        if decision.needs_reports:
            matches = match_document_chunks_for_embedding(ticker, embedding, match_count=5)
            supplementary_items += [{"content_summary": m["content"]} for m in matches]
        if decision.needs_peer_news:
            peer_tickers = _get_peer_tickers_for(ticker)
            news_since = _six_months_ago(datetime.now(timezone.utc)).isoformat()
            matches = match_ticker_news_for_embedding(
                peer_tickers,
                embedding,
                match_count=5,
                similarity_threshold=0.6,
                news_since=news_since,
            )
            # Labeled with the source ticker so the summarizing LLM doesn't misattribute a
            # peer company's news to the subject ticker.
            supplementary_items += [{"content_summary": f"[{m['ticker']}] {m['title']}"} for m in matches]

    result = summarize_feed_items(feed_name, ticker, own_items + supplementary_items)
    new_results = state["step_results"] + [
        {"step": feed_name, "items": own_items, "summary": result.summary, "sufficient": result.sufficient}
    ]
    new_supplementary = {**state["supplementary_items_by_feed"], feed_name: supplementary_items}

    if len(new_results) < len(state["plan"]):
        next_node = "execute_step"
    else:
        next_node = "synthesize"

    return Command(
        goto=next_node,
        update={"step_results": new_results, "supplementary_items_by_feed": new_supplementary},
    )

def synthesize_node(state):
    """Builds a 'God summary' from each sufficient feed's own sub-summary (not raw items),
    and explicitly flags gap feeds rather than letting them silently drag down the whole
    insight - split into no_evidence_feeds (zero items) and insufficient_evidence_feeds
    (items came back but summarize_feed_items judged them too thin/off-topic), so
    synthesize_insight can say "no evidence was found" only where that's actually true,
    rather than lumping a feed with one weak item in with a feed that had nothing at all.
    Status is driven by the qualitative `sufficient` judgment (via step_results), not raw
    item count - a feed with one weak/off-topic item is correctly "insufficient" even
    though items_by_feed shows item_count=1. A feed that ran but was judged insufficient
    keeps its summary here (it explains WHY it's a gap); a feed that never ran at all
    (0 items, no step_results entry) gets summary=None.

    Reuses the SAME synthesize_insight() function conduct_analysis (ReAct) uses; only the
    evidence-gathering differs between the two patterns."""
    step_by_feed = {r["step"]: r for r in state["step_results"]}

    evidence = []
    feed_summaries = []
    item_ids = []
    no_evidence_feeds = []
    insufficient_evidence_feeds = []

    for feed_name, items in state["items_by_feed"].items():
        step = step_by_feed.get(feed_name)
        sufficient = bool(step and step["sufficient"])
        ids = [item["id"] for item in items] if sufficient else []

        if sufficient:
            evidence.append({"source": feed_name, "content": step["summary"]})
            item_ids.extend(ids)
        elif items:
            # Ran and had items, but summarize_feed_items judged them too thin/off-topic -
            # distinct from a feed that had zero items at all (see below), so the insight
            # text doesn't claim "no evidence" for a feed that actually had some.
            insufficient_evidence_feeds.append(feed_name)
        else:
            no_evidence_feeds.append(feed_name)

        feed_summaries.append(
            {
                "feed_name": feed_name,
                "status": "sufficient" if sufficient else "insufficient",
                "summary": step["summary"] if step else None,
                "item_count": len(items),
                "item_ids": ids,
            }
        )

    insight_text = synthesize_insight(
        state["ticker"],
        evidence,
        no_evidence_feeds=no_evidence_feeds or None,
        insufficient_evidence_feeds=insufficient_evidence_feeds or None,
    )
    insert_ticker_insight(state["user_id"], state["ticker"], insight_text, item_ids, feed_summaries)

    return Command(update={"insight_text": insight_text, "based_on_feed_item_ids": item_ids})
