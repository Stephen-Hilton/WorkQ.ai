"""Main poll loop for local/monitor.

Responsibilities:
  1. Poll `GET /status/queued`. For each queued record, in `reqid` order
     (uuid v7 = create-order), spawn `python -m build <reqid>` as a child
     subprocess and wait for it to exit. Strict serial.
  2. Detect stuck builds (records in `building`/`planning` whose latest
     `timelog.ts` is older than `REQUESTQUEUE_BUILD_TIMEOUT_SECONDS + 60s`) and
     force-mark them `failed`.
  3. Sleep `polling_seconds` between cycles.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time

from shared.api_client import ApiClient
from shared.config import Config

from .stuck_detector import find_stuck, mark_failed

log = logging.getLogger(__name__)


def run(config: Config) -> None:
    log.info(
        "starting monitor: api=%s polling=%ds timeout=%ds",
        config.api_url,
        config.polling_seconds,
        config.build_timeout_seconds,
    )
    client = ApiClient(config)

    while True:
        try:
            _drain_stuck(client, config)
            _drain_queue(client, config)
        except Exception as e:  # noqa: BLE001 - never let the monitor die
            log.exception("poll cycle failed: %s", e)

        log.debug("sleeping %ds", config.polling_seconds)
        time.sleep(config.polling_seconds)


def _drain_stuck(client: ApiClient, config: Config) -> None:
    """Force-fail any record stuck in building/planning past the timeout."""
    try:
        all_items = client.list_all()
    except Exception as e:  # noqa: BLE001
        log.warning("could not list_all for stuck-detection: %s", e)
        return

    for item in find_stuck(all_items, timeout_seconds=config.build_timeout_seconds):
        log.warning("stuck-build detected: reqid=%s status=%s", item.get("reqid"), item.get("reqstatus"))
        try:
            mark_failed(client, item)
        except Exception as e:  # noqa: BLE001
            log.error("could not mark stuck reqid=%s as failed: %s", item.get("reqid"), e)


def _drain_queue(client: ApiClient, config: Config) -> None:
    queued = client.list_queued()
    queued.sort(key=lambda r: r.get("reqid", ""))  # uuid v7 = create-order
    if not queued:
        return
    log.info("queue: %d record(s) to process", len(queued))

    for record in queued:
        reqid = record.get("reqid")
        if not reqid:
            log.warning("skipping queued record with no reqid: %r", record)
            continue
        _run_build(reqid, config)


def _run_build(reqid: str, config: Config) -> None:
    log.info("dispatching reqid=%s to build subprocess", reqid)
    cmd = [sys.executable, "-m", "build", reqid]
    try:
        # Wait for completion. Subprocess timeout is its problem (build enforces
        # REQUESTQUEUE_BUILD_TIMEOUT_SECONDS internally on the claude run); we add a
        # generous outer cap here just in case.
        outer_cap = config.build_timeout_seconds + 120
        result = subprocess.run(
            cmd,
            cwd=str(config.repo_root / "local"),
            timeout=outer_cap,
            check=False,
        )
        if result.returncode == 0:
            log.info("reqid=%s build subprocess exited cleanly", reqid)
        else:
            log.warning("reqid=%s build subprocess exited code=%d", reqid, result.returncode)
    except subprocess.TimeoutExpired:
        log.error("reqid=%s build subprocess exceeded outer cap %ds — kill", reqid, outer_cap)
    except FileNotFoundError as e:
        log.error("could not exec build subprocess: %s", e)
    except Exception as e:  # noqa: BLE001
        log.exception("reqid=%s build subprocess failed unexpectedly: %s", reqid, e)
