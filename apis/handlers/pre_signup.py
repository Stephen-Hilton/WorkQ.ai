"""Cognito pre-signup trigger — gates sign-up against the SSM whitelist.

Permits sign-up if the email matches any whitelist entry:
  - Exact: `user@example.com` matches `user@example.com`
  - Domain wildcard: `@example.com` matches any `*@example.com`

Auto-confirms the user on success so they can log in immediately.

Whitelist source: SSM Parameter Store at $WHITELIST_PARAM_NAME (comma-separated).
"""

from __future__ import annotations

import os
import time
from typing import Any

import boto3

# Module-level cache so warm Lambdas don't fetch SSM on every invocation.
_CACHE_TTL_SECONDS = 60
_cached: tuple[float, list[str]] | None = None


def _whitelist() -> list[str]:
    global _cached
    now = time.time()
    if _cached is not None and now - _cached[0] < _CACHE_TTL_SECONDS:
        return _cached[1]

    name = os.environ["WHITELIST_PARAM_NAME"]
    ssm = boto3.client("ssm")
    resp = ssm.get_parameter(Name=name)
    raw = resp["Parameter"]["Value"]
    entries = [e.strip().lower() for e in raw.split(",") if e.strip()]
    _cached = (now, entries)
    return entries


def _matches(email: str, whitelist: list[str]) -> bool:
    email = email.strip().lower()
    if not email:
        return False
    for entry in whitelist:
        if entry.startswith("@"):
            if email.endswith(entry):
                return True
        elif entry == email:
            return True
    return False


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    email = (event.get("request") or {}).get("userAttributes", {}).get("email", "")
    whitelist = _whitelist()
    if not _matches(email, whitelist):
        # Cognito treats a raised exception as a sign-up rejection.
        raise Exception(f"email {email!r} not in whitelist")

    # Auto-confirm so users skip the email-verification step.
    response = event.setdefault("response", {})
    response["autoConfirmUser"] = True
    response["autoVerifyEmail"] = True
    return event
