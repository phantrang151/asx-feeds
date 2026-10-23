"""Public marketing statistics for the TickerThesis front page: active researchers, investment
feeds created, news articles matched and insights generated.

The numbers are calculated by the compute_site_stats SQL function (definitions in
scripts/migration_site_stats.sql) and stored as a snapshot, once a week after the pipeline run
(scripts/run_weekly_job.py). The front page reads the latest snapshot through
GET /api/public/site-stats, so a visit never runs the counts itself.
"""
from db.queries import compute_site_stats, get_latest_site_stats, insert_site_stats
from tools.logger import get_logger

logger = get_logger(__name__)

STAT_FIELDS = ("active_researchers", "feeds_created", "articles_matched", "insights_generated")


def refresh_site_stats() -> dict:
    """Calculates the four numbers now and stores them as a new snapshot. Returns the stored row."""
    stats = compute_site_stats()
    row = insert_site_stats({field: stats[field] for field in STAT_FIELDS})
    logger.info("Site stats refreshed: %s", {field: row[field] for field in STAT_FIELDS})
    return row


def latest_site_stats() -> dict | None:
    """The most recent snapshot, or None if the weekly job has never run."""
    return get_latest_site_stats()
