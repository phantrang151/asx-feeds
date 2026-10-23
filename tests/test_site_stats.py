"""Tests for stats/site_stats.py and the weekly job (scripts/run_weekly_job.py). The database
and the pipeline are faked; the SQL definitions themselves are in scripts/migration_site_stats.sql."""
from unittest.mock import patch

import scripts.run_weekly_job as job
import stats.site_stats as site_stats

COMPUTED = {"active_researchers": 3, "feeds_created": 12, "articles_matched": 34, "insights_generated": 30}


def test_refresh_stores_exactly_the_four_numbers():
    with patch.object(site_stats, "compute_site_stats", return_value={**COMPUTED, "unexpected": 1}), \
         patch.object(site_stats, "insert_site_stats", side_effect=lambda row: {"id": "s1", **row}) as insert:
        row = site_stats.refresh_site_stats()

    insert.assert_called_once_with(COMPUTED)
    assert row["articles_matched"] == 34


def _pipeline(status="success"):
    return {"run_id": "r1", "status": status, "errors": []}


def test_weekly_job_runs_pipeline_then_stats():
    calls = []
    with patch.object(job, "run_ingestion_for_all_watchlisted_tickers",
                      side_effect=lambda: calls.append("pipeline") or _pipeline()), \
         patch.object(job, "refresh_site_stats", side_effect=lambda: calls.append("stats")):
        assert job.run_weekly_job() == 0
    assert calls == ["pipeline", "stats"]


def test_stats_still_refresh_when_the_pipeline_fails_and_the_job_reports_failure():
    with patch.object(job, "run_ingestion_for_all_watchlisted_tickers", return_value=_pipeline("failed")), \
         patch.object(job, "refresh_site_stats") as refresh:
        assert job.run_weekly_job() == 1
    refresh.assert_called_once()


def test_pipeline_crash_still_refreshes_stats():
    with patch.object(job, "run_ingestion_for_all_watchlisted_tickers", side_effect=RuntimeError("boom")), \
         patch.object(job, "refresh_site_stats") as refresh:
        assert job.run_weekly_job() == 1
    refresh.assert_called_once()


def test_stats_failure_fails_the_job():
    with patch.object(job, "run_ingestion_for_all_watchlisted_tickers", return_value=_pipeline()), \
         patch.object(job, "refresh_site_stats", side_effect=RuntimeError("db down")):
        assert job.run_weekly_job() == 1
