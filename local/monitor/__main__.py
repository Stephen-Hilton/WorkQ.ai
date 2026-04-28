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
        print("ERROR: api_url not set. Run `make publish` on the deploy machine first.", file=sys.stderr)
        return 2
    if not config.service_user_password:
        print(
            "ERROR: REQUESTQUEUE_SERVICE_USER_PASSWORD missing from .env. "
            "Run `scripts/refresh_creds.sh` (deploy machine) and copy the two "
            "REQUESTQUEUE_SERVICE_USER_* lines into this server's .env.",
            file=sys.stderr,
        )
        return 2
    run(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
