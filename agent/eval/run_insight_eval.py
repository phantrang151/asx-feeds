"""
Quality eval for the insight-synthesis pipeline (agent/pipelines/insight_nodes.py's
synthesize_node), the pipeline-side counterpart to run_generation_eval.py's chat-answer
scoring. Samples recent REAL ticker_insights rows (not a fixture set - unlike chat
questions, there's no fixed list of "tickers to ask about", the pipeline runs on whatever
the current watchlist is) and reuses the exact same judge functions run_generation_eval.py
uses, so both surfaces are graded by the same standard.

Evidence for grounding/completeness is reconstructed from each row's own persisted
feed_summaries (the same {feed_name, summary} shape synthesize_node itself builds the
"evidence" list from before calling synthesize_insight()) rather than re-querying
feed_items - what the judge sees should match what synthesis actually had. This also
includes a note naming which OTHER feeds had no/insufficient evidence, mirroring
synthesize_insight()'s own skipped_block (see agent/shared/synthesize.py) - without it,
a legitimate gap-callout in the insight text (e.g. "Revenue Trend evidence was too
thin") looks unsupported to the judge, since it has no way to know that context was
actually given to the model that wrote it.

Usage:
    python -m agent.eval.run_insight_eval --limit 20 --output agent/eval/results/insight_eval.json
"""

import argparse
import json

from db.queries import get_recent_ticker_insights, insert_eval_run
from agent.eval.judge import judge_groundedness, judge_relevance, judge_completeness


def run_one(row: dict) -> dict:
    ticker = row["ticker"]
    insight_text = row["insight_text"]
    question = f"What's happening with {ticker} and why?"

    evidence = [
        {"source": fs["feed_name"], "content": fs["summary"]}
        for fs in row["feed_summaries"]
        if fs["status"] == "sufficient" and fs.get("summary")
    ]

    # synthesize_insight() is explicitly told which feeds had no evidence at all vs.
    # evidence that was too thin (see agent/shared/synthesize.py's skipped_block), and
    # instructed to name those gaps in the insight - so a sentence like "Revenue Trend
    # evidence was too thin" is a legitimate, grounded statement, not a hallucination.
    # Without surfacing that same context here, the judge has no way to tell the two
    # apart and flags every gap-feed mention as unsupported.
    no_evidence_feeds = [fs["feed_name"] for fs in row["feed_summaries"] if fs["status"] == "insufficient" and not fs["item_count"]]
    insufficient_evidence_feeds = [
        fs["feed_name"] for fs in row["feed_summaries"] if fs["status"] == "insufficient" and fs["item_count"]
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

    groundedness = judge_groundedness(insight_text, evidence)
    relevance = judge_relevance(question, insight_text)

    result = {
        "ticker_insight_id": row["id"],
        "ticker": ticker,
        "created_at": row["created_at"],
        "n_sufficient_feeds": len(evidence),
        "groundedness": {
            "grounded": groundedness.grounded,
            "unsupported_claims": groundedness.unsupported_claims,
        },
        "relevance": {"score": relevance.score, "reasoning": relevance.reasoning},
    }

    # Same guard as run_generation_eval.py: no evidence makes "% of it covered" vacuous.
    if evidence:
        completeness = judge_completeness(question, insight_text, evidence)
        result["completeness"] = {
            "coverage_pct": completeness.coverage_pct,
            "omitted_points": completeness.omitted_points,
        }
    else:
        result["completeness"] = None

    return result


def summarize(results: list[dict]) -> dict:
    n = len(results)
    completeness_judged = [r for r in results if r["completeness"] is not None]
    return {
        "n_total": n,
        "avg_relevance": round(sum(r["relevance"]["score"] for r in results) / n, 2) if n else None,
        "pct_grounded": round(100 * sum(1 for r in results if r["groundedness"]["grounded"]) / n, 1) if n else None,
        "avg_completeness_pct": (
            round(sum(r["completeness"]["coverage_pct"] for r in completeness_judged) / len(completeness_judged), 1)
            if completeness_judged
            else None
        ),
    }


def _print_summary(summary: dict) -> None:
    print(f"Total insights judged:  {summary['n_total']}")
    print(f"Avg relevance (1-5):    {summary['avg_relevance']}")
    print(f"% grounded:             {summary['pct_grounded']}")
    print(f"Avg evidence coverage:  {summary['avg_completeness_pct']}%")


def run_insight_eval(limit: int = 20, persist: bool = True) -> dict:
    """Runs the sample and returns {"summary", "results"} - the one function both this
    script's __main__ block AND POST /api/admin/eval/insight/trigger call. Makes real,
    live JUDGE_MODEL calls per sampled insight - not free, not instant."""
    rows = get_recent_ticker_insights(limit=limit)
    results = [run_one(row) for row in rows]
    summary = summarize(results)

    if persist:
        insert_eval_run("insight_quality", {"limit": limit, "summary": summary, "results": results})

    return {"summary": summary, "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", default="agent/eval/results/insight_eval.json")
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing this run to the eval_runs table (used by the admin page) - useful for a local dry run.",
    )
    args = parser.parse_args()

    output = run_insight_eval(args.limit, persist=not args.no_persist)
    _print_summary(output["summary"])

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote full detail to {args.output}")
    if not args.no_persist:
        print("Logged this run to eval_runs (visible on the admin page).")
