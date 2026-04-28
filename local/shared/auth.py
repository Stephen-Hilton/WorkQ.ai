"""Cognito authentication helper for the local server.

Implements `USER_PASSWORD_AUTH` (initial login) + refresh-token flow.
Refreshes proactively before each API call when access token has <5 minutes
left. Falls back to password login if the refresh token is rejected.

The local server has no AWS IAM credentials at runtime. The only thing it
talks to AWS-wise is the public Cognito IDP endpoint, which doesn't require
AWS auth — Cognito is its own auth domain.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import boto3
from botocore import UNSIGNED
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

log = logging.getLogger(__name__)

# Don't refresh until within this many seconds of expiry (and don't send
# a token that's about to expire mid-flight).
_REFRESH_BUFFER_SECONDS = 300


class AuthenticatedSession:
    """Maintains a Cognito access token and refreshes on demand.

    Thread-unsafe — designed for single-threaded use within local/monitor and
    local/build. The two processes maintain independent sessions.
    """

    def __init__(self, *, region: str, client_id: str, email: str, password: str):
        self._region = region
        self._client_id = client_id
        self._email = email
        self._password = password
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        # Wall-clock unix seconds at which the access token expires.
        self._expires_at: float = 0.0
        # Cognito IDP doesn't require AWS auth — use anonymous client.
        self._cog = boto3.client(
            "cognito-idp",
            region_name=region,
            config=BotoConfig(signature_version=UNSIGNED),
        )

    def access_token(self) -> str:
        if self._access_token is None or self._expires_in() < _REFRESH_BUFFER_SECONDS:
            self._ensure_fresh()
        assert self._access_token is not None
        return self._access_token

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _expires_in(self) -> float:
        return self._expires_at - time.time()

    def _ensure_fresh(self) -> None:
        if self._refresh_token:
            try:
                self._refresh()
                return
            except ClientError as e:
                log.warning("refresh failed (%s); falling back to password login", e.response["Error"]["Code"])
        self._login_with_password()

    def _login_with_password(self) -> None:
        log.info("authenticating service user %s via USER_PASSWORD_AUTH", self._email)
        resp = self._cog.initiate_auth(
            ClientId=self._client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": self._email,
                "PASSWORD": self._password,
            },
        )
        self._absorb(resp)

    def _refresh(self) -> None:
        log.info("refreshing Cognito access token")
        resp = self._cog.initiate_auth(
            ClientId=self._client_id,
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": self._refresh_token or ""},
        )
        self._absorb(resp, keep_refresh=True)

    def _absorb(self, resp: dict[str, Any], *, keep_refresh: bool = False) -> None:
        result = resp.get("AuthenticationResult") or {}
        access = result.get("AccessToken")
        if not access:
            raise RuntimeError(f"unexpected Cognito response: {resp}")
        self._access_token = access
        # Refresh tokens come back only on initial login.
        new_refresh = result.get("RefreshToken")
        if new_refresh:
            self._refresh_token = new_refresh
        elif not keep_refresh:
            self._refresh_token = None
        # ExpiresIn is seconds from now.
        ttl = int(result.get("ExpiresIn") or 3600)
        self._expires_at = time.time() + ttl - 1  # paranoia 1s
