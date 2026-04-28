"""Config loader for local components.

Reads, in order:
  1. `.env` at repo root (deploy inputs + Cognito service-user password).
  2. `.requestqueue.outputs.json` at repo root (deploy outputs from `sam deploy`).

Provides typed accessors so the rest of the codebase doesn't sprinkle
`os.environ.get(...)` calls everywhere.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)


def repo_root() -> Path:
    """Walk up from this file to find the repo root (where `.env.example` lives)."""
    p = Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if (parent / ".env.example").exists():
            return parent
    return Path.cwd()


@dataclass(frozen=True)
class Config:
    api_url: str
    cognito_user_pool_id: str
    cognito_client_id: str
    cognito_region: str
    service_user_email: str
    service_user_password: str
    polling_seconds: int
    build_timeout_seconds: int
    prompt_parts_path: Path
    github_repo_url: str
    github_branch: str
    github_token: str
    github_auto_merge: bool
    github_auto_merge_method: str
    repo_root: Path


def _load_outputs(root: Path) -> dict[str, str]:
    p = root / ".requestqueue.outputs.json"
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text())
    except (OSError, ValueError) as e:
        log.warning("could not read %s: %s", p, e)
        return {}
    aliases = {
        "WebappUrl": "webapp_url",
        "ApiUrl": "api_url",
        "CognitoUserPoolId": "cognito_user_pool_id",
        "CognitoClientId": "cognito_client_id",
        "CognitoDomain": "cognito_domain",
        "CognitoRegion": "cognito_region",
        "S3WebappBucket": "s3_webapp_bucket",
        "CloudfrontDistributionId": "cloudfront_distribution_id",
        "ServiceUserEmail": "service_user_email",
    }
    out: dict[str, str] = dict(raw)
    for pascal, snake in aliases.items():
        if pascal in raw and snake not in out:
            out[snake] = raw[pascal]
    return out


def load() -> Config:
    root = repo_root()
    load_dotenv(root / ".env", override=False)

    outputs = _load_outputs(root)

    def env_or(key: str, fallback: str = "") -> str:
        return os.environ.get(key, fallback)

    api_url = env_or("REQUESTQUEUE_API_URL") or outputs.get("api_url", "")
    pool_id = outputs.get("cognito_user_pool_id", "") or env_or("REQUESTQUEUE_COGNITO_USER_POOL_ID")
    client_id = outputs.get("cognito_client_id", "") or env_or("REQUESTQUEUE_COGNITO_CLIENT_ID")
    region = outputs.get("cognito_region", "") or env_or("REQUESTQUEUE_AWS_REGION", "us-east-1")
    service_email = (
        env_or("REQUESTQUEUE_SERVICE_USER_EMAIL")
        or outputs.get("service_user_email", "")
        or "service-local-monitor@requestqueue.internal"
    )
    service_password = env_or("REQUESTQUEUE_SERVICE_USER_PASSWORD")

    return Config(
        api_url=api_url,
        cognito_user_pool_id=pool_id,
        cognito_client_id=client_id,
        cognito_region=region,
        service_user_email=service_email,
        service_user_password=service_password,
        polling_seconds=int(env_or("REQUESTQUEUE_POLLING_SECONDS", "30")),
        build_timeout_seconds=int(env_or("REQUESTQUEUE_BUILD_TIMEOUT_SECONDS", "2700")),
        prompt_parts_path=Path(
            env_or("REQUESTQUEUE_PROMPT_PARTS_PATH", str(root / "config" / "prompt_parts.yaml"))
        ).expanduser(),
        github_repo_url=env_or("REQUESTQUEUE_GITHUB_REPO_URL"),
        github_branch=env_or("REQUESTQUEUE_GITHUB_BRANCH", "main"),
        github_token=env_or("REQUESTQUEUE_GITHUB_TOKEN"),
        github_auto_merge=env_or("REQUESTQUEUE_GITHUB_AUTO_MERGE", "false").lower() == "true",
        github_auto_merge_method=env_or("REQUESTQUEUE_GITHUB_AUTO_MERGE_METHOD", "squash"),
        repo_root=root,
    )
