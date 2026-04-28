"""Headless `claude code` invocation, with timeout + status-fence parsing.

Runs:
    claude --dangerously-skip-permissions -p '<prompt>'

Captures stdout, returns exit code + stdout text. Honors
`REQUESTQUEUE_BUILD_TIMEOUT_SECONDS` via `subprocess.run(timeout=…)`.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# HTML comment fence claude can write at the end of its response, per spec
# DECISION 14. Tolerant of surrounding whitespace.
_FENCE_RE = re.compile(
    r"<!--\s*requestqueue:status\s*=\s*([a-z_]+)\s*-->",
    re.IGNORECASE,
)
_VALID_FENCE_VALUES = {"pending_review", "complete", "failed"}


@dataclass
class ClaudeResult:
    exit_code: int
    output: str
    timed_out: bool
    fence_status: str | None  # one of: pending_review, complete, failed (or None)


def run(
    *,
    prompt: str,
    cwd: Path,
    timeout_seconds: int,
    extra_args: list[str] | None = None,
) -> ClaudeResult:
    """Run claude in `cwd` with the given prompt.

    Returns even on failure — the caller is responsible for mapping exit code
    + timeout to a final status.
    """
    cmd = ["claude", "--dangerously-skip-permissions", "-p", prompt]
    if extra_args:
        cmd.extend(extra_args)

    log.info("running claude in %s (timeout=%ds, prompt %d chars)", cwd, timeout_seconds, len(prompt))

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        partial = (e.stdout or "") if isinstance(e.stdout, str) else ""
        log.warning("claude timeout after %ds; captured %d chars of partial output", timeout_seconds, len(partial))
        return ClaudeResult(
            exit_code=-1,
            output=partial or "(no output captured before timeout)",
            timed_out=True,
            fence_status=None,
        )
    except FileNotFoundError:
        log.error("claude binary not found on PATH")
        return ClaudeResult(
            exit_code=127,
            output="`claude` binary not found on PATH. Install Claude Code on the local server.",
            timed_out=False,
            fence_status="failed",
        )

    output = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
    fence = parse_fence(output)
    return ClaudeResult(
        exit_code=proc.returncode,
        output=output,
        timed_out=False,
        fence_status=fence,
    )


def parse_fence(text: str) -> str | None:
    """Find the LAST requestqueue:status fence in the output.

    We only inspect the last 2 KB so a stray comment in the middle of a long
    response can't accidentally trigger the fence.
    """
    tail = text[-2048:]
    last: str | None = None
    for m in _FENCE_RE.finditer(tail):
        v = m.group(1).lower()
        if v in _VALID_FENCE_VALUES:
            last = v
    return last
