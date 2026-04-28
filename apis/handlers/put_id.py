"""PUT /id/{reqid} — update an existing record.

Body may include any subset of mutable fields plus an optional
`expected_timelog_len` for optimistic concurrency. Returns 409 with the
current record if the timelog length has changed since load.

`reqcreator` is immutable and silently stripped.
"""

from __future__ import annotations

import json
from typing import Any

from shared import ddb, responses
from shared.models import make_timelog_entry

_MUTABLE_FIELDS = {"reqstatus", "reqarea", "reqpr", "request", "response"}


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    reqid = (event.get("pathParameters") or {}).get("reqid")
    if not reqid:
        return responses.bad_request("missing reqid")

    body = _parse_body(event)
    if body is None:
        return responses.bad_request("invalid JSON body")

    fields: dict[str, Any] = {
        k: body[k] for k in body if k in _MUTABLE_FIELDS and body[k] is not None
    }

    expected_len = body.get("expected_timelog_len")
    if expected_len is not None and not isinstance(expected_len, int):
        return responses.bad_request("expected_timelog_len must be an integer")

    new_status = fields.get("reqstatus")
    # Always log a timelog entry. If reqstatus didn't change, log the existing
    # one so the audit trail still records the update.
    if new_status is None:
        current = ddb.get_item(reqid)
        if current is None:
            return responses.not_found()
        new_status = current.get("reqstatus", "unknown")

    new_log_entry = make_timelog_entry(new_status)

    try:
        updated = ddb.update_item(
            reqid=reqid,
            fields=fields,
            new_timelog_entry=new_log_entry,
            expected_timelog_len=expected_len,
        )
    except ddb.ConcurrencyConflict:
        # Return the current record so the client can show a diff.
        current = ddb.get_item(reqid)
        return responses.conflict(current or {"reqid": reqid})

    return responses.ok(updated)


def _parse_body(event: dict[str, Any]) -> dict[str, Any] | None:
    raw = event.get("body")
    if raw is None:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None
