"""Pure-logic test for _parse_published_at - no I/O, no mocks needed."""

from datetime import datetime, timezone

from agent.pipelines.ingestion_steps import _parse_published_at


def test_iso_string_passes_through_unchanged():
    assert _parse_published_at("2026-01-15T10:30:00") == "2026-01-15T10:30:00"


def test_unix_timestamp_converts_to_iso():
    result = _parse_published_at(1700000000)
    assert result == datetime.fromtimestamp(1700000000, tz=timezone.utc).isoformat()


def test_none_returns_none():
    assert _parse_published_at(None) is None


def test_empty_string_returns_none():
    assert _parse_published_at("") is None


def test_unix_epoch_zero_is_treated_as_absent_not_1970():
    # Documents current behavior: `if not published` is truthy for 0, so an epoch-zero
    # timestamp is indistinguishable from "no timestamp" rather than converted to
    # 1970-01-01T00:00:00Z. Locking this in so a future refactor doesn't silently change it
    # without the change being deliberate.
    assert _parse_published_at(0) is None
