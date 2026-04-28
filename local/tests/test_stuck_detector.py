"""Unit tests for the stuck-build detector."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from monitor.stuck_detector import find_stuck


def _ts(seconds_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat().replace("+00:00", "Z")


def test_stuck_building_record_found() -> None:
    items = [
        {"reqid": "stuck", "reqstatus": "building", "timelog": [{"status": "building", "ts": _ts(3000)}]},
    ]
    out = find_stuck(items, timeout_seconds=2700)
    assert [i["reqid"] for i in out] == ["stuck"]


def test_recent_building_record_not_found() -> None:
    items = [
        {"reqid": "fresh", "reqstatus": "building", "timelog": [{"status": "building", "ts": _ts(60)}]},
    ]
    assert find_stuck(items, timeout_seconds=2700) == []


def test_complete_record_ignored_even_if_old() -> None:
    items = [
        {"reqid": "old-complete", "reqstatus": "complete", "timelog": [{"status": "complete", "ts": _ts(99999)}]},
    ]
    assert find_stuck(items, timeout_seconds=2700) == []


def test_planning_status_also_detected() -> None:
    items = [
        {"reqid": "p", "reqstatus": "planning", "timelog": [{"status": "planning", "ts": _ts(3000)}]},
    ]
    out = find_stuck(items, timeout_seconds=2700)
    assert [i["reqid"] for i in out] == ["p"]


def test_grace_period_respected() -> None:
    """Within `timeout + 60s grace`, the record is NOT yet stuck."""
    items = [
        {"reqid": "boundary", "reqstatus": "building", "timelog": [{"status": "building", "ts": _ts(2710)}]},
    ]
    assert find_stuck(items, timeout_seconds=2700) == []
    items = [
        {"reqid": "past-grace", "reqstatus": "building", "timelog": [{"status": "building", "ts": _ts(2800)}]},
    ]
    out = find_stuck(items, timeout_seconds=2700)
    assert [i["reqid"] for i in out] == ["past-grace"]


def test_record_with_no_timelog_not_detected() -> None:
    items = [{"reqid": "x", "reqstatus": "building", "timelog": []}]
    assert find_stuck(items, timeout_seconds=2700) == []
