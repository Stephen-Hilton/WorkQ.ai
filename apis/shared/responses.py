"""HTTP response helpers for API Gateway proxy integrations."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

# CORS headers (origin "*" is fine — Cognito JWT is the actual gate).
DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Authorization,Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}


def _default(o: Any) -> Any:
    if isinstance(o, Decimal):
        # DDB Numbers come back as Decimal — emit as int if integer, else float.
        return int(o) if o == int(o) else float(o)
    raise TypeError(f"not serializable: {type(o)}")


def respond(status_code: int, body: Any) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": DEFAULT_HEADERS,
        "body": json.dumps(body, default=_default),
    }


def ok(body: Any) -> dict[str, Any]:
    return respond(200, body)


def created(body: Any) -> dict[str, Any]:
    return respond(201, body)


def bad_request(message: str) -> dict[str, Any]:
    return respond(400, {"error": message})


def not_found(message: str = "not found") -> dict[str, Any]:
    return respond(404, {"error": message})


def conflict(body: Any) -> dict[str, Any]:
    """409 — used for optimistic-concurrency mismatches. Body is the current record."""
    return respond(409, body)


def server_error(message: str = "internal error") -> dict[str, Any]:
    return respond(500, {"error": message})
