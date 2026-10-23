"""Weekly job: runs the ingestion pipeline (news fetch, feed matching, insights) for every
watchlisted ticker, then refreshes the front-page statistics so they reflect that run.
Scheduled every Sunday by .github/workflows/weekly-pipeline.yml; can also be run by hand.

The statistics are refreshed even if the pipeline fails - they count what is in the database,
which is still correct, just not updated by this week's run. Exits non-zero if either step
fails, so the scheduled run shows as failed.

Usage:
    python -m scripts.run_weekly_job
"""
import sys

from agent.pipelines.orchestrator import run_ingestion_for_all_watchlisted_tickers
from stats.site_stats import refresh_site_stats
from tools.logger import get_logger

logger = get_logger(__name__)


def run_weekly_job() -> int:
    ok = True

    try:
        result = run_ingestion_for_all_watchlisted_tickers()
        logger.info("Pipeline run %s finished with status %s", result["run_id"], result["status"])
        if result["status"] != "success":
            logger.error("Pipeline errors: %s", result["errors"])
            ok = False
    except Exception:
        logger.exception("Pipeline run crashed")
        ok = False

    try:
        refresh_site_stats()
    except Exception:
        logger.exception("Site stats refresh failed")
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run_weekly_job())
