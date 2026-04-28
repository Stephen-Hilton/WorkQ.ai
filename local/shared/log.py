"""Rotating file loggers for the monitor and build processes.

Application telemetry only — never per-request output. See spec DECISION 11.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from .config import repo_root

_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup(name: str, *, also_stdout: bool = True) -> logging.Logger:
    """Configure a logger that writes to local/logs/<name>.log + (optionally) stdout.

    Daily rotation, 14 backups kept.
    """
    logs_dir: Path = repo_root() / "local" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()  # root, so submodule loggers also flow
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if setup() runs twice in the same process.
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter(_FORMAT)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(logs_dir / f"{name}.log"),
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    if also_stdout:
        stream_handler = logging.StreamHandler(stream=sys.stdout)
        stream_handler.setFormatter(fmt)
        logger.addHandler(stream_handler)

    return logging.getLogger(name)
