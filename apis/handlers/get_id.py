"""GET /id/{reqid} — single record by uuid."""

from __future__ import annotations

from typing import Any

from shared import ddb, responses


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    reqid = (event.get("pathParameters") or {}).get("reqid")
    if not reqid:
        return responses.bad_request("missing reqid")

    item = ddb.get_item(reqid)
    if item is None:
        return responses.not_found()
    return responses.ok(item)
