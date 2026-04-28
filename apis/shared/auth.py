"""Helpers for extracting caller identity from API Gateway events.

API Gateway with a Cognito authorizer puts the JWT claims into
`event.requestContext.authorizer.claims`. This module isolates that lookup.
"""

from __future__ import annotations

from typing import Any


def extract_email(event: dict[str, Any]) -> str:
    """Return the caller's email claim, or empty string if absent."""
    rc = event.get("requestContext") or {}
    authz = rc.get("authorizer") or {}
    claims = authz.get("claims") or {}
    return claims.get("email") or claims.get("cognito:username") or ""
