"""
One-off script to seed the fixed set of common feed templates. Run schema.sql against
your Supabase project first. Safe to re-run - upserts on template name.

Usage:
    python -m scripts.seed_common_feed_templates
"""

from tools.embeddings import embed
from db.queries import upsert_common_feed_template

TEMPLATE_DEFINITIONS = [
    (
        "Revenue Trend",
        "News and signals about the company's revenue performance, growth drivers, and composition, "
        "including business segments, products, services, customers, geographic markets, pricing, "
        "volumes, acquisitions, and other factors affecting revenue.",
    ),
    (
        "Business Strategy",
        "News about the company's strategic moves - partnerships, expansions, new "
        "products, acquisitions, or shifts in direction.",
    ),
    (
        "Red Flags",
        "Controversies, scandals, outages, regulatory issues, lawsuits, or other "
        "reputational or operational risks affecting the company.",
    ),
]


def seed_common_feed_templates():
    for name, description in TEMPLATE_DEFINITIONS:
        embedding = embed(description)
        upsert_common_feed_template(name, description, embedding)
        print(f"Upserted common feed template '{name}'.")


if __name__ == "__main__":
    seed_common_feed_templates()
