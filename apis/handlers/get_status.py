"""GET /status/{status} — list records filtered by reqstatus.

Special path values:
  /status/all     → return everything
  /status/queued  → return queued for build OR queued for planning
  /status/<exact> → return exact status (URL-decoded by API Gateway)
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from shared import ddb, responses
from shared.models import Status


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    status_param = (event.get("pathParameters") or {}).get("status", "")
    status = unquote(status_param)

    if not status or status == "all":
        items = ddb.scan_all()
    elif status == "queued":
        items = ddb.scan_by_status(
            [Status.QUEUED_FOR_BUILD.value, Status.QUEUED_FOR_PLANNING.value]
        )
    else:
        items = ddb.scan_by_status([status])

    return responses.ok({"items": items, "count": len(items)})
