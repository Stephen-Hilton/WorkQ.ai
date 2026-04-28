"""Git worktree + branch + PR operations for `local/build`.

Per-build flow:
  1. Ensure a bare clone exists at `local/workspace/.git-bare/` (clone-once).
  2. `git worktree add local/workspace/<reqid> -b workq/<reqid> <base-branch>`
     to get an isolated working tree on a fresh branch.
  3. Claude operates inside that directory.
  4. After claude exits:
     - If commits exist: push, open PR via `gh`, optionally auto-merge.
     - If no commits: just clean up the worktree.
  5. `git worktree remove --force` regardless.

Uses `gh` for PR creation (auth via `WORKQ_GITHUB_TOKEN` env var).
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class WorktreeResult:
    path: Path
    branch: str


@dataclass
class PrResult:
    url: str
    number: int
    auto_merged: bool
    notes: list[str]


class GitError(Exception):
    pass


def _run(cmd: list[str], *, cwd: Path | None = None, env_extra: dict[str, str] | None = None) -> str:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    log.debug("$ %s (cwd=%s)", " ".join(cmd), cwd)
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise GitError(
            f"command failed: {' '.join(cmd)}\nstderr:\n{proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def ensure_bare_clone(*, repo_url: str, bare_dir: Path) -> None:
    if (bare_dir / "HEAD").exists():
        # Already cloned; just fetch latest.
        _run(["git", "fetch", "--all", "--prune"], cwd=bare_dir)
        return
    bare_dir.parent.mkdir(parents=True, exist_ok=True)
    log.info("cloning bare repo to %s …", bare_dir)
    _run(["git", "clone", "--bare", repo_url, str(bare_dir)])


def add_worktree(
    *, bare_dir: Path, worktree_dir: Path, base_branch: str, new_branch: str
) -> WorktreeResult:
    if worktree_dir.exists():
        log.warning("worktree %s already exists; removing first", worktree_dir)
        try:
            _run(["git", "worktree", "remove", "--force", str(worktree_dir)], cwd=bare_dir)
        except GitError:
            pass
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "git",
            "worktree",
            "add",
            "-b",
            new_branch,
            str(worktree_dir),
            f"origin/{base_branch}",
        ],
        cwd=bare_dir,
    )
    return WorktreeResult(path=worktree_dir, branch=new_branch)


def remove_worktree(*, bare_dir: Path, worktree_dir: Path, branch: str | None = None) -> None:
    try:
        _run(["git", "worktree", "remove", "--force", str(worktree_dir)], cwd=bare_dir)
    except GitError as e:
        log.warning("worktree remove failed (continuing): %s", e)
    # Branch cleanup: only if no commits / not pushed (prune unused branches).
    if branch:
        try:
            _run(["git", "branch", "-D", branch], cwd=bare_dir)
        except GitError:
            pass


def has_new_commits(*, worktree_dir: Path, base_branch: str) -> bool:
    """True if the worktree has commits that aren't already in `origin/<base>`."""
    try:
        out = _run(
            ["git", "rev-list", "--count", f"origin/{base_branch}..HEAD"],
            cwd=worktree_dir,
        )
        return int(out) > 0
    except (GitError, ValueError):
        return False


def push_branch(*, worktree_dir: Path, branch: str, token: str) -> None:
    _run(
        ["git", "push", "-u", "origin", branch],
        cwd=worktree_dir,
        env_extra={"GITHUB_TOKEN": token, "GH_TOKEN": token},
    )


def create_pr(
    *,
    worktree_dir: Path,
    base_branch: str,
    branch: str,
    title: str,
    body: str,
    token: str,
) -> PrResult:
    notes: list[str] = []
    url = _run(
        ["gh", "pr", "create", "--base", base_branch, "--head", branch, "--title", title, "--body", body],
        cwd=worktree_dir,
        env_extra={"GITHUB_TOKEN": token, "GH_TOKEN": token},
    )
    # `gh pr create` returns the PR URL on stdout. Parse the number off the end.
    number = _parse_pr_number(url)
    return PrResult(url=url, number=number, auto_merged=False, notes=notes)


def _parse_pr_number(url: str) -> int:
    try:
        return int(url.rstrip("/").rsplit("/", 1)[-1])
    except (ValueError, IndexError):
        return 0


def auto_merge_pr(*, worktree_dir: Path, pr_number: int, method: str, token: str) -> None:
    flag = {"squash": "--squash", "merge": "--merge", "rebase": "--rebase"}.get(method, "--squash")
    _run(
        ["gh", "pr", "merge", str(pr_number), flag, "--delete-branch", "--admin"],
        cwd=worktree_dir,
        env_extra={"GITHUB_TOKEN": token, "GH_TOKEN": token},
    )
