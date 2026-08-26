"""
Builds a labeling worksheet for the news -> feed classification eval. Pulls real,
already-classified ticker_news rows and their current top-1 common_feed_templates
match, and writes a CSV with a blank `correct_feed` column for a human to fill in
(the candidate name if it's right, a different template name, or literally "none").

This script does NOT fabricate labels - it only builds the worksheet. Run
score_classification.py against the filled-in CSV to get precision/recall/false-skip
metrics.

Scoped to common_feed_templates (ticker-agnostic, shared across users) rather than
per-user custom feeds, to avoid picking one arbitrary user's feed set.

Usage:
    python -m agent.eval.export_labels --limit 100 --output agent/eval/labeling_worksheet.csv
"""

import argparse
import csv

from db.queries import get_classified_ticker_news_sample, match_common_feed_template_for_embedding

FIELDNAMES = [
    "ticker_news_id",
    "ticker",
    "title",
    "publisher",
    "source_url",
    "published_at",
    "candidate_feed_name",
    "candidate_similarity",
    "candidate_threshold",
    "correct_feed",
]


def export_labels(limit: int, output_path: str) -> int:
    rows = get_classified_ticker_news_sample(limit)
    worksheet_rows = []
    for row in rows:
        matches = match_common_feed_template_for_embedding(row["content_embedding"], match_count=1)
        top = matches[0] if matches else None
        worksheet_rows.append(
            {
                "ticker_news_id": row["id"],
                "ticker": row["ticker"],
                "title": row["title"],
                "publisher": row.get("publisher"),
                "source_url": row.get("source_url"),
                "published_at": row.get("published_at"),
                "candidate_feed_name": top["name"] if top else "",
                "candidate_similarity": round(top["similarity"], 4) if top else "",
                "candidate_threshold": top["match_threshold"] if top else "",
                "correct_feed": "",
            }
        )

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(worksheet_rows)

    return len(worksheet_rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", default="agent/eval/labeling_worksheet.csv")
    args = parser.parse_args()

    n = export_labels(args.limit, args.output)
    print(f"Wrote {n} rows to {args.output}. Fill in the 'correct_feed' column, then run score_classification.py.")
