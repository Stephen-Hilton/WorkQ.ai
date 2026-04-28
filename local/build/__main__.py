"""`python -m build <reqid>` — single-request build lifecycle.

Spawned by local/monitor for each queued record. See spec DECISION 11 + 15.

High-level flow:
  1. Load the record via the API.
  2. Transition status: `queued for build` → `building` (or planning).
  3. Set up a git worktree on `workq/<reqid>` (build only; planning skips git).
  4. Assemble the prompt from `prompt_parts.yaml`.
  5. Run `claude code` headlessly with a 45-min wall-clock timeout.
  6. Capture claude's stdout; prepend to DDB `response`.
  7. For build: if claude made commits, push + open PR + optional auto-merge.
  8. Final status from: status fence > zero-commit detection > exit code > default `complete`.
  9. Always: every failure response includes a `# Recommended Next Step` section.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from shared.config import load
from shared.log import setup

from . import claude_runner, git_ops
from .lifecycle import Lifecycle
from .prompt import load as load_prompt_parts


def main() -> int:
    setup("build")
    log = logging.getLogger("build")

    if len(sys.argv) != 2:
        log.error("usage: python -m build <reqid>")
        return 2

    reqid = sys.argv[1]
    config = load()

    if not config.api_url or not config.service_user_password:
        log.error("local/build is not bootstrapped — run `scripts/bootstrap_local.sh`")
        return 2

    from shared.api_client import ApiClient

    client = ApiClient(config)
    lifecycle = Lifecycle(client, reqid)

    try:
        record = lifecycle.load()
    except Exception as e:  # noqa: BLE001
        log.exception("could not load record %s: %s", reqid, e)
        return 1

    initial_status = (record.get("reqstatus") or "").lower()
    is_build = initial_status == "queued for build"
    is_planning = initial_status == "queued for planning"

    if not (is_build or is_planning):
        log.warning("reqid=%s is not in a queued state (status=%s); refusing to run", reqid, initial_status)
        return 0

    in_progress_status = "building" if is_build else "planning"
    lifecycle.transition(status=in_progress_status)

    worktree_dir: Path | None = None
    branch: str | None = None
    bare_dir = config.repo_root / "local" / "workspace" / ".git-bare"

    try:
        if is_build:
            git_ops.ensure_bare_clone(repo_url=config.github_repo_url, bare_dir=bare_dir)
            worktree_dir = config.repo_root / "local" / "workspace" / reqid
            branch = f"workq/{reqid}"
            git_ops.add_worktree(
                bare_dir=bare_dir,
                worktree_dir=worktree_dir,
                base_branch=config.github_branch,
                new_branch=branch,
            )
            cwd = worktree_dir
        else:
            # Planning: still hand claude the codebase as a read-only context,
            # but no commits / push / PR.
            try:
                git_ops.ensure_bare_clone(repo_url=config.github_repo_url, bare_dir=bare_dir)
                worktree_dir = config.repo_root / "local" / "workspace" / reqid
                branch = f"workq-plan/{reqid}"
                git_ops.add_worktree(
                    bare_dir=bare_dir,
                    worktree_dir=worktree_dir,
                    base_branch=config.github_branch,
                    new_branch=branch,
                )
                cwd = worktree_dir
            except git_ops.GitError as e:
                log.warning("could not set up planning worktree (continuing without): %s", e)
                cwd = config.repo_root

        prompt_parts = load_prompt_parts(config.prompt_parts_path)
        prompt = prompt_parts.render(
            reqstatus=initial_status,
            reqarea=record.get("reqarea") or "General",
            request=record.get("request") or "",
            prior_response=record.get("response") or "",
        )

        result = claude_runner.run(
            prompt=prompt,
            cwd=cwd,
            timeout_seconds=config.build_timeout_seconds,
        )

        # Final status decision tree.
        final_status, footer, reqpr = _decide_outcome(
            result=result,
            is_build=is_build,
            worktree_dir=worktree_dir,
            branch=branch,
            config=config,
            log=log,
            record=record,
        )

        prepended = _format_response(result.output, footer)
        lifecycle.transition(status=final_status, reqpr=reqpr, prepend_response=prepended)

    except Exception as e:  # noqa: BLE001
        log.exception("build for reqid=%s failed unexpectedly: %s", reqid, e)
        try:
            recommended = _next_steps_for_unexpected(reqid, branch, str(e))
            lifecycle.transition(
                status="failed",
                prepend_response=f"Build failed unexpectedly: `{e}`.\n\n{recommended}",
            )
        except Exception as e2:  # noqa: BLE001
            log.exception("could not even mark reqid=%s as failed: %s", reqid, e2)
        return 1
    finally:
        if worktree_dir and bare_dir.exists():
            try:
                git_ops.remove_worktree(bare_dir=bare_dir, worktree_dir=worktree_dir, branch=branch)
            except Exception as e:  # noqa: BLE001
                log.warning("worktree cleanup failed for reqid=%s: %s", reqid, e)

    return 0


def _decide_outcome(
    *,
    result: claude_runner.ClaudeResult,
    is_build: bool,
    worktree_dir: Path | None,
    branch: str | None,
    config,  # type: ignore[no-untyped-def]
    log: logging.Logger,
    record: dict,
) -> tuple[str, str, str | None]:
    """Compute final (status, response_footer, reqpr) for this build."""
    reqpr: str | None = None

    # Timeout always wins.
    if result.timed_out:
        footer = _next_steps_timeout(record.get("reqid", ""), branch, config.build_timeout_seconds)
        return "failed", footer, reqpr

    # Fence override (if claude explicitly signaled).
    if result.fence_status == "failed":
        footer = _next_steps_claude_failed(record.get("reqid", ""), branch)
        return "failed", footer, reqpr
    if result.fence_status == "pending_review":
        return "pending review", "", reqpr

    # Non-zero exit (and no fence override) → failed.
    if result.exit_code != 0:
        footer = _next_steps_nonzero_exit(record.get("reqid", ""), branch, result.exit_code)
        return "failed", footer, reqpr

    # Build only: try to push + open PR.
    if is_build and worktree_dir and branch:
        try:
            if not git_ops.has_new_commits(
                worktree_dir=worktree_dir, base_branch=config.github_branch
            ):
                # Claude did the planning thinking but produced no commits.
                footer = _next_steps_no_commits(record.get("reqid", ""))
                return "pending review", footer, reqpr
            git_ops.push_branch(worktree_dir=worktree_dir, branch=branch, token=config.github_token)
            pr = git_ops.create_pr(
                worktree_dir=worktree_dir,
                base_branch=config.github_branch,
                branch=branch,
                title=_pr_title(record),
                body=_pr_body(record),
                token=config.github_token,
            )
            reqpr = pr.url
            if config.github_auto_merge:
                try:
                    git_ops.auto_merge_pr(
                        worktree_dir=worktree_dir,
                        pr_number=pr.number,
                        method=config.github_auto_merge_method,
                        token=config.github_token,
                    )
                except git_ops.GitError as e:
                    footer = _next_steps_auto_merge_failed(pr.url, str(e))
                    return "pending review", footer, reqpr
        except git_ops.GitError as e:
            log.warning("git/PR step failed: %s", e)
            footer = _next_steps_git_failed(record.get("reqid", ""), branch, str(e))
            return "pending review", footer, reqpr

    return "complete", "", reqpr


# ---------------------------------------------------------------------------
# Recommended-next-step builders
# ---------------------------------------------------------------------------


def _format_response(output: str, footer: str) -> str:
    if not footer:
        return output
    return f"{output}\n\n---\n\n{footer}"


def _next_steps_timeout(reqid: str, branch: str | None, timeout: int) -> str:
    return (
        f"# Recommended Next Step\n\n"
        f"Build was killed after {timeout}s ({timeout // 60} min). Last 100 lines of "
        f"claude output are shown above.\n\n"
        f"- Inspect `local/logs/build.log` for the entries about `{reqid}`.\n"
        f"- If the request is solvable but needs more time, increase "
        f"`WORKQ_BUILD_TIMEOUT_SECONDS` in `.env` (max ~24h, but most of "
        f"that requires also extending the Cognito access-token TTL).\n"
        f"- If the work product is recoverable from the worktree at "
        f"`local/workspace/{reqid}/`, you may inspect or push manually.\n"
    )


def _next_steps_claude_failed(reqid: str, branch: str | None) -> str:
    branch_hint = (
        f"- Worktree may exist at `local/workspace/{reqid}/`; inspect or remove with "
        f"`git -C local/workspace/.git-bare worktree remove --force local/workspace/{reqid}`.\n"
        if branch
        else ""
    )
    return (
        f"# Recommended Next Step\n\n"
        f"Claude self-reported failure (status fence). Read its response above for the "
        f"reason, then:\n\n"
        f"- Edit the `request` text to address claude's complaint and click "
        f"`Save and Queue for Build` (or Planning).\n"
        f"- Or `Mark for Review` and answer the question manually, then re-queue.\n"
        f"{branch_hint}"
    )


def _next_steps_nonzero_exit(reqid: str, branch: str | None, exit_code: int) -> str:
    return (
        f"# Recommended Next Step\n\n"
        f"Claude exited with code {exit_code}. Common causes:\n\n"
        f"- The headless `claude code` binary itself crashed — check `claude --version`.\n"
        f"- The prompt was malformed — inspect `config/prompt_parts.yaml` and the "
        f"  rendered prompt by running `local/build` with `LOG_LEVEL=DEBUG`.\n"
        f"- Worktree at `local/workspace/{reqid}/` may have partial state; remove or "
        f"  inspect.\n"
    )


def _next_steps_no_commits(reqid: str) -> str:
    return (
        f"# Recommended Next Step\n\n"
        f"Claude reported success but made no commits. Either it decided no change was "
        f"needed (read the response above), or it forgot to commit. To follow up:\n\n"
        f"- If response is satisfactory, click `Save and Complete` to close this out.\n"
        f"- If you want a different result, edit `request` and click "
        f"  `Save and Queue for Build` again.\n"
        f"- Worktree at `local/workspace/{reqid}/` may still have uncommitted changes; "
        f"  inspect with `git -C local/workspace/{reqid} status` before it gets cleaned up.\n"
    )


def _next_steps_git_failed(reqid: str, branch: str | None, err: str) -> str:
    return (
        f"# Recommended Next Step\n\n"
        f"Claude succeeded, but the post-build git/PR step failed: `{err}`\n\n"
        f"Manual recovery (branch `{branch}` may already be pushed):\n\n"
        f"```sh\n"
        f"cd local/workspace/{reqid}\n"
        f"git status\n"
        f"git push origin {branch}\n"
        f"gh pr create --base <base> --head {branch} --title '<title>' --body '<body>'\n"
        f"```\n"
        f"Once recovered, paste the PR URL into `reqpr` and click `Save and Complete`.\n"
    )


def _next_steps_auto_merge_failed(pr_url: str, err: str) -> str:
    return (
        f"# Recommended Next Step\n\n"
        f"PR was created at {pr_url} but auto-merge failed: `{err}`\n\n"
        f"- Verify your `WORKQ_GITHUB_TOKEN` has admin rights on the repo.\n"
        f"- Or merge the PR manually in the GitHub UI, then click `Save and Complete`.\n"
    )


def _next_steps_for_unexpected(reqid: str, branch: str | None, err: str) -> str:
    return (
        f"# Recommended Next Step\n\n"
        f"Unexpected failure outside the normal build flow: `{err}`\n\n"
        f"- Check `local/logs/build.log` for the stack trace.\n"
        f"- Worktree at `local/workspace/{reqid}/` (if any) will be cleaned up; "
        f"  any partial work is in the branch `{branch or '(none)'}`.\n"
        f"- Re-queueing the request is usually safe.\n"
    )


def _pr_title(record: dict) -> str:
    req = (record.get("request") or "").strip().splitlines()
    first = req[0].strip() if req else f"WorkQ build {record.get('reqid', '')}"
    if len(first) > 70:
        first = first[:67] + "…"
    return f"workq: {first}"


def _pr_body(record: dict) -> str:
    return (
        f"Generated by WorkQ.ai for request `{record.get('reqid', '')}`.\n\n"
        f"**Original request:**\n\n"
        f"```\n{(record.get('request') or '').strip()}\n```\n\n"
        f"_See the WorkQ webapp for the full conversation and AI response._"
    )


if __name__ == "__main__":
    sys.exit(main())
