"""Stuck-build detector: zombie records that need force-failing.

A build is "stuck" if its `reqstatus` is `building` or `planning` and the
latest `timelog.ts` is older than `WORKQ_BUILD_TIMEOUT_SECONDS + 60s`.
This catches:
  - local server reboot mid-build,
  - local/build segfault before status writeback,
  - any failure that bypasses the normal failure path.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from shared.api_client import ApiClient

log = logging.getLogger(__name__)

_IN_FLIGHT = {"building", "planning"}
_GRACE_SECONDS = 60


def find_stuck(items: Iterable[dict[str, Any]], *, timeout_seconds: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc).timestamp() - (timeout_seconds + _GRACE_SECONDS)
    out: list[dict[str, Any]] = []
    for item in items:
        if item.get("reqstatus") not in _IN_FLIGHT:
            continue
        ts = _latest_timelog_ts(item)
        if ts is None:
            continue
        if ts < cutoff:
            out.append(item)
    return out


def _latest_timelog_ts(item: dict[str, Any]) -> float | None:
    log_entries = item.get("timelog") or []
    if not log_entries:
        return None
    last = log_entries[-1]
    raw = last.get("ts") if isinstance(last, dict) else None
    if not raw:
        return None
    try:
        # Accept both `2026-04-27T...Z` and `+00:00`.
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def mark_failed(client: ApiClient, item: dict[str, Any]) -> None:
    reqid = item["reqid"]
    explanation = (
        "Build appears to have died — no status update within the timeout window.\n\n"
        "# Recommended Next Step\n\n"
        f"- Inspect `local/logs/build.log` for entries about `{reqid}`.\n"
        "- If the work product looks salvageable, edit this record and "
        "`Save and Queue for Build` again, or `Save and Complete` if already merged.\n"
        "- Otherwise, `Delete` the record."
    )
    body = {
        "reqstatus": "failed",
        "response": _prepend(item.get("response", ""), explanation),
    }
    client.put(reqid, body)
    log.warning("marked reqid=%s failed (stuck-build sweep)", reqid)


def _prepend(existing: str, new_section: str) -> str:
    if not existing:
        return new_section
    return f"{new_section}\n\n---\n\n{existing}"
