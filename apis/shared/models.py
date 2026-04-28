"""Record schema and status enum for WorkQ work requests.

Authoritative schema. Any field-level change must be reflected in:
- the SAM template (DDB attribute defs only matter for keys/GSI),
- the webapp TypeScript types (`ui/webapp/src/types.ts`),
- the spec (`prompts/reqv1.md`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, TypedDict


class Status(StrEnum):
    """Permissible reqstatus values.

    DDB stores `reqstatus` as a free-form string but the webapp + API constrain
    saves to this set. New values added here must also appear in the webapp
    selector.
    """

    QUEUED_FOR_BUILD = "queued for build"
    QUEUED_FOR_PLANNING = "queued for planning"
    PENDING_REVIEW = "pending review"
    BUILDING = "building"
    PLANNING = "planning"
    COMPLETE = "complete"
    FAILED = "failed"


# Statuses the local monitor will pick up and dispatch.
DISPATCHABLE_STATUSES = frozenset({Status.QUEUED_FOR_BUILD, Status.QUEUED_FOR_PLANNING})

# Statuses that indicate a build is currently in flight.
IN_FLIGHT_STATUSES = frozenset({Status.BUILDING, Status.PLANNING})

# DDB → prompt_parts.status key mapping. See spec DECISION 3.
STATUS_TO_ACTION: dict[str, str] = {
    Status.QUEUED_FOR_BUILD: "build",
    Status.QUEUED_FOR_PLANNING: "planning",
}

DEFAULT_REQAREA = "General"

# Statuses claude can request via the HTML-comment fence at the end of its
# response. Anything else is silently ignored. See spec DECISION 14.
FENCE_OVERRIDE_STATUSES: dict[str, Status] = {
    "pending_review": Status.PENDING_REVIEW,
    "complete": Status.COMPLETE,
    "failed": Status.FAILED,
}


class TimelogEntry(TypedDict):
    """Single timelog entry. Stored in DDB as a Map within a List."""

    status: str
    ts: str  # ISO 8601 UTC, e.g. "2026-04-27T18:32:01.123Z"


@dataclass
class Record:
    """Full work-request record. Mirrors the DDB item shape 1:1."""

    reqid: str
    reqstatus: str = Status.PENDING_REVIEW.value
    reqarea: str = DEFAULT_REQAREA
    reqcreator: str = ""
    reqpr: str = ""
    request: str = ""
    response: str = ""
    timelog: list[TimelogEntry] = field(default_factory=list)

    def to_ddb(self) -> dict[str, Any]:
        """Serialize for boto3 `put_item` / equivalents."""
        return {
            "reqid": self.reqid,
            "reqstatus": self.reqstatus,
            "reqarea": self.reqarea,
            "reqcreator": self.reqcreator,
            "reqpr": self.reqpr,
            "request": self.request,
            "response": self.response,
            "timelog": [dict(e) for e in self.timelog],
        }

    @classmethod
    def from_ddb(cls, item: dict[str, Any]) -> Record:
        return cls(
            reqid=item["reqid"],
            reqstatus=item.get("reqstatus", Status.PENDING_REVIEW.value),
            reqarea=item.get("reqarea", DEFAULT_REQAREA),
            reqcreator=item.get("reqcreator", ""),
            reqpr=item.get("reqpr", ""),
            request=item.get("request", ""),
            response=item.get("response", ""),
            timelog=list(item.get("timelog", [])),
        )


def utc_now_iso() -> str:
    """Standard UTC timestamp for timelog entries."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def make_timelog_entry(status: str, ts: str | None = None) -> TimelogEntry:
    return {"status": status, "ts": ts or utc_now_iso()}
