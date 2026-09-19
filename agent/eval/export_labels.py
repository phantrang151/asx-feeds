"""
Builds a labeling worksheet for the news -> feed classification eval. Pulls real,
already-classified ticker_news rows and writes a CSV with blank `correct_feed` and
`explanation` columns for a human to fill in (the correct common-feed-template name,
or literally "none", plus a short note on why).

Input only - deliberately does NOT compute or store the classifier's own candidate
match here. run_classification_eval.py computes that fresh, every run, by calling the
live classifier (see its own docstring for why storing it as a static column here was
the wrong design). This script's only job is sampling real articles and giving a human
something to label.

This script does NOT fabricate labels - it only builds the worksheet. Run
run_classification_eval.py against the filled-in CSV to get precision/recall/false-skip
metrics.

Scoped to common_feed_templates (ticker-agnostic, shared across users) rather than
per-user custom feeds, to avoid picking one arbitrary user's feed set.

Usage:
    python -m agent.eval.export_labels --limit 100 --output agent/eval/fixtures/labeling_worksheet.csv
"""

import argparse
import csv

from db.queries import get_classified_ticker_news_sample

FIELDNAMES = [
    "ticker_news_id",
    "ticker",
    "title",
    "snippet",
    "publisher",
    "source_url",
    "published_at",
    "correct_feed",
    "explanation",
]


def export_labels(limit: int, output_path: str) -> int:
    rows = get_classified_ticker_news_sample(limit)
    worksheet_rows = [
        {
            "ticker_news_id": row["id"],
            "ticker": row["ticker"],
            "title": row["title"],
            "snippet": row.get("snippet"),
            "publisher": row.get("publisher"),
            "source_url": row.get("source_url"),
            "published_at": row.get("published_at"),
            "correct_feed": "",
            "explanation": "",
        }
        for row in rows
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(worksheet_rows)

    return len(worksheet_rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", default="agent/eval/fixtures/labeling_worksheet.csv")
    args = parser.parse_args()

    n = export_labels(args.limit, args.output)
    print(f"Wrote {n} rows to {args.output}. Fill in 'correct_feed' (and 'explanation'), then run run_classification_eval.py.")
