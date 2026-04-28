"""Prompt assembly from `prompt_parts.yaml` + a DDB record.

Final shape (per spec):
    <all.pre>
    <status.<mapped>.pre>
    <areas.<reqarea>.pre>

    <request text, plus existing response prepended as "# Previous AI Responses">

    <all.post>
    <status.<mapped>.post>
    <areas.<reqarea>.post>

The DDB → prompt_parts.status mapping:
    "queued for build"    -> "build"
    "queued for planning" -> "planning"
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

DEFAULT_AREA = "General"

_STATUS_TO_ACTION: dict[str, str] = {
    "queued for build": "build",
    "queued for planning": "planning",
    # Allow re-running an in-progress record (e.g., manual re-queue without
    # going through "queued for X" first).
    "building": "build",
    "planning": "planning",
}


class PromptParts:
    def __init__(self, raw: dict[str, Any]) -> None:
        self._all = raw.get("all") or {}
        self._status = raw.get("status") or {}
        self._areas = dict(raw.get("areas") or {})
        # Auto-inject "General" with empty pre/post if the project didn't
        # define one. See spec DECISION 22.
        self._areas.setdefault(DEFAULT_AREA, {"pre": "", "post": ""})

    def areas(self) -> list[str]:
        return sorted(self._areas.keys())

    def render(self, *, reqstatus: str, reqarea: str, request: str, prior_response: str = "") -> str:
        action = _STATUS_TO_ACTION.get(reqstatus.lower())
        status_block = self._status.get(action) if action else None
        area_block = self._areas.get(reqarea) or self._areas.get(DEFAULT_AREA) or {}

        pre = "\n\n".join(
            s
            for s in (
                _get(self._all, "pre"),
                _get(status_block, "pre"),
                _get(area_block, "pre"),
            )
            if s
        )
        post = "\n\n".join(
            s
            for s in (
                _get(self._all, "post"),
                _get(status_block, "post"),
                _get(area_block, "post"),
            )
            if s
        )

        body = request or ""
        if prior_response:
            body = (
                f"{body}\n\n"
                "# Previous AI Responses\n\n"
                f"{prior_response}"
            ).strip()

        return f"{pre}\n\n---\n\n{body}\n\n---\n\n{post}".strip() + "\n"


def _get(block: dict[str, Any] | None, key: str) -> str:
    if not block:
        return ""
    v = block.get(key, "")
    if v is None:
        return ""
    return str(v).strip()


def load(path: Path) -> PromptParts:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"prompt_parts.yaml at {path} is not a mapping")
    return PromptParts(raw)
