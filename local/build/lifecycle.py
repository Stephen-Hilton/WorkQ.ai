"""Status transitions + response writeback for a single build.

Centralizes the "always try to record back to DDB" principle from spec
DECISION 15: every API call retries 3x with exponential backoff.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from shared.api_client import ApiClient, ApiError

log = logging.getLogger(__name__)

_MAX_RETRIES = 3
_INITIAL_BACKOFF = 1.0


class Lifecycle:
    """Reads, mutates, and writes one DDB record across the build lifecycle."""

    def __init__(self, client: ApiClient, reqid: str) -> None:
        self._client = client
        self._reqid = reqid
        self._record: dict[str, Any] | None = None

    @property
    def reqid(self) -> str:
        return self._reqid

    def load(self) -> dict[str, Any]:
        self._record = _retry(lambda: self._client.get_id(self._reqid))
        return self._record

    @property
    def record(self) -> dict[str, Any]:
        if self._record is None:
            return self.load()
        return self._record

    def transition(self, *, status: str, reqpr: str | None = None,
                   prepend_response: str = "") -> None:
        """Set status (and optionally update reqpr / prepend response).

        Doesn't use optimistic concurrency — local/build is the only writer
        once the record is in `building`/`planning`, so conflicts here would
        signal a real problem. We let the API serialize.
        """
        body: dict[str, Any] = {"reqstatus": status}
        if reqpr is not None:
            body["reqpr"] = reqpr
        if prepend_response:
            existing = (self._record or {}).get("response") or ""
            body["response"] = _prepend(existing, prepend_response)
        updated = _retry(lambda: self._client.put(self._reqid, body))
        self._record = updated
        log.info("reqid=%s → status=%s", self._reqid, status)


def _prepend(existing: str, new: str) -> str:
    if not existing:
        return new
    return f"{new}\n\n---\n\n{existing}"


def _retry[T](fn) -> T:  # type: ignore[no-untyped-def, valid-type]
    backoff = _INITIAL_BACKOFF
    last: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return fn()
        except ApiError as e:
            last = e
            log.warning("API call failed (attempt %d/%d): %s", attempt + 1, _MAX_RETRIES, e)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(backoff)
                backoff *= 2
    assert last is not None
    raise last
