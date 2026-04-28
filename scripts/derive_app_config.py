#!/usr/bin/env python3
"""Build the webapp's runtime `app.json` from `config/prompt_parts.yaml` + env.

The webapp consumes a tiny payload at runtime:
  - display_timezone: from $REQUESTQUEUE_DISPLAY_TIMEZONE (default UTC)
  - prompt_areas:    derived from prompt_parts.yaml `areas:` keys
                     (always includes "General")

The full prompt_parts.yaml never reaches the webapp — the pre/post text
stays on the local-build server only.

Outputs JSON to stdout.

Usage:
  derive_app_config.py [path-to-prompt_parts.yaml]
  default path: config/prompt_parts.yaml
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml


def derive(path: Path, timezone: str) -> dict:
    raw = yaml.safe_load(path.read_text()) if path.exists() else {}
    if not isinstance(raw, dict):
        raw = {}
    areas_block = raw.get("areas") or {}
    if not isinstance(areas_block, dict):
        areas_block = {}
    area_names = list(areas_block.keys())
    if "General" not in area_names:
        area_names.insert(0, "General")
    return {
        "display_timezone": timezone,
        "prompt_areas": area_names,
    }


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config/prompt_parts.yaml")
    tz = os.environ.get("REQUESTQUEUE_DISPLAY_TIMEZONE", "UTC")
    payload = derive(path, tz)
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
