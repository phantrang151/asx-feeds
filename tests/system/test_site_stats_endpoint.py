"""API-level tests for the public front-page statistics endpoint. The snapshot read is faked.
Marked slow: imports the whole app."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.slow


def test_returns_the_latest_snapshot_without_login():
    import api.main as main

    snapshot = {"computed_at": "2026-10-25T20:05:00+00:00", "active_researchers": 3,
                "feeds_created": 12, "articles_matched": 34, "insights_generated": 30}
    with patch.object(main, "latest_site_stats", return_value=snapshot):
        resp = TestClient(main.app).get("/api/public/site-stats")   # no Authorization header

    assert resp.status_code == 200
    assert resp.json() == snapshot


def test_404_before_the_first_weekly_run():
    import api.main as main

    with patch.object(main, "latest_site_stats", return_value=None):
        resp = TestClient(main.app).get("/api/public/site-stats")

    assert resp.status_code == 404
