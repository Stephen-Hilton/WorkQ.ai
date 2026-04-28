"""`python -m monitor` — entry point for the long-running poll loop."""

from __future__ import annotations

import sys

from shared.config import load
from shared.log import setup

from .poller import run


def main() -> int:
    setup("monitor")
    config = load()
    if not config.api_url:
        print("ERROR: api_url not set. Run `make publish` first, then `bootstrap_local.sh`.", file=sys.stderr)
        return 2
    if not config.service_user_password:
        print("ERROR: service-user password missing. Run `scripts/bootstrap_local.sh` once.", file=sys.stderr)
        return 2
    run(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
