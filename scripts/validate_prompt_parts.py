#!/usr/bin/env python3
"""Validate `config/prompt_parts.yaml` against the WorkQ schema.

Run as part of `scripts/publish.sh` and as a CI step on PRs that touch the file.

Schema:
  - top-level keys: `all`, `status`, `areas` (each optional but recommended).
  - `all`: object with optional string `pre`/`post`.
  - `status`: map; values are objects with optional string `pre`/`post`.
  - `areas`: map; values are objects with optional string `pre`/`post`.
  - All `pre`/`post` values must be strings (or empty).

Exits 0 on success, non-zero on schema violations.

Usage:
  scripts/validate_prompt_parts.py [path]
  default path: config/prompt_parts.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


def _err(path: str, msg: str) -> None:
    print(f"\033[1;31mERROR\033[0m {path}: {msg}", file=sys.stderr)


def _validate_block(name: str, block: Any, path: str) -> int:
    if block is None or block == "":
        return 0
    if not isinstance(block, dict):
        _err(path, f"{name}: expected mapping, got {type(block).__name__}")
        return 1
    errs = 0
    for key in ("pre", "post"):
        if key in block:
            v = block[key]
            if v is None or v == "":
                continue
            if not isinstance(v, str):
                _err(path, f"{name}.{key}: expected string, got {type(v).__name__}")
                errs += 1
    extra = set(block.keys()) - {"pre", "post"}
    if extra:
        _err(path, f"{name}: unexpected keys {sorted(extra)}; only 'pre' and 'post' allowed")
        errs += 1
    return errs


def validate(path: Path) -> int:
    if not path.exists():
        _err(str(path), "file does not exist")
        return 2
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        _err(str(path), f"yaml parse error: {e}")
        return 2
    if raw is None:
        _err(str(path), "file is empty")
        return 2
    if not isinstance(raw, dict):
        _err(str(path), f"top-level must be a mapping, got {type(raw).__name__}")
        return 2

    errs = 0
    extra = set(raw.keys()) - {"all", "status", "areas"}
    if extra:
        _err(str(path), f"unexpected top-level keys {sorted(extra)}; allowed: all, status, areas")
        errs += 1

    errs += _validate_block("all", raw.get("all"), str(path))

    for kind in ("status", "areas"):
        block = raw.get(kind)
        if block is None:
            continue
        if not isinstance(block, dict):
            _err(str(path), f"{kind}: expected mapping, got {type(block).__name__}")
            errs += 1
            continue
        for k, v in block.items():
            if not isinstance(k, str):
                _err(str(path), f"{kind}: keys must be strings, found {k!r} ({type(k).__name__})")
                errs += 1
                continue
            errs += _validate_block(f"{kind}.{k}", v, str(path))

    if errs == 0:
        print(f"\033[1;32mOK\033[0m {path}")
        return 0
    print(f"\033[1;31m{errs} error(s)\033[0m in {path}", file=sys.stderr)
    return 1


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config/prompt_parts.yaml")
    return validate(path)


if __name__ == "__main__":
    sys.exit(main())
