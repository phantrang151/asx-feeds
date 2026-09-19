"""
One-off script to seed the fixed set of common feed templates. Run schema.sql against
your Supabase project first. Safe to re-run - upserts on template name.

Usage:
    python -m scripts.seed_common_feed_templates
"""

from tools.embeddings import embed
from db.queries import upsert_common_feed_template
from agent.shared.news_text import format_feed_content

TEMPLATE_DEFINITIONS = [
    (
        "Revenue Trend",
        "News reporting the company's actual financial results and what's driving them - "
        "quarterly or annual revenue/profit/earnings figures, segment or product-line revenue "
        "breakdowns, subscriber or customer growth numbers, pricing or sales-volume changes, "
        "margin or cost trends, or the reported financial impact of a past deal (e.g. added "
        "revenue from a completed acquisition). About financial RESULTS, not the strategic "
        "decision itself - a newly announced acquisition or partnership belongs to Business "
        "Strategy instead, even though it will eventually affect revenue.",
    ),
    (
        "Business Strategy",
        "News about a specific corporate action or strategic decision - acquisitions, "
        "mergers, divestitures, partnerships, joint ventures, expansion into a new market or "
        "product line, restructuring, leadership or executive changes, or a pricing decision "
        "(e.g. cutting or raising prices). About WHAT the company decided to do, not the "
        "financial outcome of it - the resulting revenue/profit impact belongs to Revenue "
        "Trend instead.",
    ),
    (
        "Red Flags",
        "News about a controversy, scandal, service or network outage, regulatory "
        "investigation or fine, lawsuit or class action, executive misconduct, data breach, "
        "or other reputational or operational risk to the company.",
    ),
]


def seed_common_feed_templates():
    for name, description in TEMPLATE_DEFINITIONS:
        embedding = embed(format_feed_content(name, description))
        upsert_common_feed_template(name, description, embedding)
        print(f"Upserted common feed template '{name}'.")


if __name__ == "__main__":
    seed_common_feed_templates()
