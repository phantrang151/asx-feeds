"""
Shared evidence reconstruction for a ticker_insights row - used by both
agent/eval/runners/run_insight_eval.py (fixed-limit manual Evaluation trigger) and
monitoring/quality_sampling.py (continuous production sampling), so the two don't
maintain separate, potentially-drifting copies of this logic.
"""


def build_insight_evidence(feed_summaries: list[dict]) -> list[dict]:
    """Evidence for grounding/completeness is reconstructed from a ticker_insights row's
    own persisted feed_summaries (the same {feed_name, summary} shape synthesize_node
    itself builds the "evidence" list from before calling synthesize_insight() - see
    agent/pipelines/insight_nodes.py) rather than re-querying custom_feed_items - what the judge
    sees should match what synthesis actually had.

    Also includes a note naming which OTHER feeds had no/insufficient evidence,
    mirroring synthesize_insight()'s own skipped_block (see agent/shared/synthesize.py)
    - without it, a legitimate gap-callout in the insight text (e.g. "Revenue Trend
    evidence was too thin") looks unsupported to the judge, since it has no way to know
    that context was actually given to the model that wrote it."""
    evidence = [
        {"source": fs["feed_name"], "content": fs["summary"]}
        for fs in feed_summaries
        if fs["status"] == "sufficient" and fs.get("summary")
    ]

    no_evidence_feeds = [fs["feed_name"] for fs in feed_summaries if fs["status"] == "insufficient" and not fs["item_count"]]
    insufficient_evidence_feeds = [
        fs["feed_name"] for fs in feed_summaries if fs["status"] == "insufficient" and fs["item_count"]
    ]
    if no_evidence_feeds:
        evidence.append({
            "source": "pipeline note",
            "content": f"No evidence was found this run for: {', '.join(no_evidence_feeds)}.",
        })
    if insufficient_evidence_feeds:
        evidence.append({
            "source": "pipeline note",
            "content": f"Evidence was found but judged too thin or off-topic for: {', '.join(insufficient_evidence_feeds)}.",
        })

    return evidence
