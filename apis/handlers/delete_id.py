"""DELETE /id/{reqid}."""

from __future__ import annotations

from typing import Any

from shared import ddb, responses


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    reqid = (event.get("pathParameters") or {}).get("reqid")
    if not reqid:
        return responses.bad_request("missing reqid")

    ddb.delete_item(reqid)
    return responses.ok({"reqid": reqid, "deleted": True})
