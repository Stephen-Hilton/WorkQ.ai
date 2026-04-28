"""Thin REST client for the RequestQueue API, using a Cognito JWT.

Wraps `requests` with automatic token refresh via AuthenticatedSession.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import quote

import requests

from .auth import AuthenticatedSession
from .config import Config

log = logging.getLogger(__name__)

_RETRY_STATUSES = {500, 502, 503, 504}
_MAX_RETRIES = 3
_RETRY_INITIAL_BACKOFF = 1.0


class ApiError(Exception):
    """Non-retryable API error (4xx, or 5xx after retries exhausted)."""

    def __init__(self, status: int, body: Any):
        super().__init__(f"API {status}: {body}")
        self.status = status
        self.body = body


class ConflictError(ApiError):
    """409 Conflict — optimistic-concurrency mismatch."""

    def __init__(self, body: Any):
        super().__init__(409, body)


class ApiClient:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._session = AuthenticatedSession(
            region=config.cognito_region,
            client_id=config.cognito_client_id,
            email=config.service_user_email,
            password=config.service_user_password,
        )
        self._http = requests.Session()

    # ------------------------------------------------------------------
    # high-level methods
    # ------------------------------------------------------------------

    def get_id(self, reqid: str) -> dict[str, Any]:
        return self._request("GET", f"/id/{quote(reqid, safe='')}")

    def list_status(self, status: str) -> list[dict[str, Any]]:
        path = f"/status/{quote(status, safe='')}"
        resp = self._request("GET", path)
        return list(resp.get("items", []))

    def list_queued(self) -> list[dict[str, Any]]:
        return self.list_status("queued")

    def list_all(self) -> list[dict[str, Any]]:
        return self.list_status("all")

    def post(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/id", json=body)

    def put(self, reqid: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/id/{quote(reqid, safe='')}", json=body)

    def delete(self, reqid: str) -> dict[str, Any]:
        return self._request("DELETE", f"/id/{quote(reqid, safe='')}")

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, *, json: Any = None) -> Any:
        url = self._config.api_url.rstrip("/") + path
        backoff = _RETRY_INITIAL_BACKOFF
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                token = self._session.access_token()
                resp = self._http.request(
                    method,
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=json,
                    timeout=30,
                )
            except requests.RequestException as e:
                last_exc = e
                log.warning("HTTP %s %s failed: %s (attempt %d)", method, path, e, attempt + 1)
                time.sleep(backoff)
                backoff *= 2
                continue

            if resp.status_code == 409:
                raise ConflictError(_safe_body(resp))
            if resp.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES - 1:
                log.warning("API %s %s → %d (attempt %d)", method, path, resp.status_code, attempt + 1)
                time.sleep(backoff)
                backoff *= 2
                continue
            if not resp.ok:
                raise ApiError(resp.status_code, _safe_body(resp))
            return _safe_body(resp)

        raise ApiError(0, f"exhausted retries: {last_exc}")


def _safe_body(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text
