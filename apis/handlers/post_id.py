"""POST /id — create a new request.

Server generates `reqid` (uuid v7); any client-supplied reqid is silently
ignored. `reqcreator` is set from the JWT email claim.
"""

from __future__ import annotations

import json
from typing import Any

from uuid6 import uuid7

from shared import ddb, responses
from shared.auth import extract_email
from shared.models import (
    DEFAULT_REQAREA,
    Status,
    make_timelog_entry,
)

_MUTABLE_FIELDS = {"reqstatus", "reqarea", "reqpr", "request", "response"}


def _service_user_email() -> str:
    import os

    return os.environ.get("SERVICE_USER_EMAIL", "service-local-monitor@requestqueue.internal")


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    body = _parse_body(event)
    if body is None:
        return responses.bad_request("invalid JSON body")

    creator = extract_email(event) or _service_user_email()
    reqid = str(uuid7())

    item: dict[str, Any] = {
        "reqid": reqid,
        "reqstatus": body.get("reqstatus") or Status.PENDING_REVIEW.value,
        "reqarea": body.get("reqarea") or DEFAULT_REQAREA,
        "reqcreator": creator,
        "reqpr": body.get("reqpr") or "",
        "request": body.get("request") or "",
        "response": body.get("response") or "",
        "timelog": [make_timelog_entry(body.get("reqstatus") or Status.PENDING_REVIEW.value)],
    }

    # Drop any unknown / not-allowed fields silently (incl. client-supplied reqid).
    for k in list(item.keys()):
        if k not in {"reqid", "reqcreator", "timelog"} and k not in _MUTABLE_FIELDS:
            del item[k]

    ddb.put_item(item)
    return responses.created(item)


def _parse_body(event: dict[str, Any]) -> dict[str, Any] | None:
    raw = event.get("body")
    if raw is None:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None
