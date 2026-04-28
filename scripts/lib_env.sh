#!/usr/bin/env bash
# scripts/lib_env.sh — shared helper for .env loading + AWS credential
# normalization. Source this from any script that talks to AWS:
#
#   # shellcheck source=lib_env.sh
#   source "$(dirname "${BASH_SOURCE[0]}")/lib_env.sh"
#   load_env "${REPO_ROOT}/.env"
#
# After load_env returns, the standard `aws` CLI / `sam` env vars are set
# from the REQUESTQUEUE_* equivalents in .env (if present), so the user
# doesn't need to also `aws configure` or `export AWS_PROFILE=...` separately.
#
# Lookup precedence: existing AWS_* env var > REQUESTQUEUE_AWS_* from .env >
# unset (let aws CLI fall back to ~/.aws/credentials, instance role, etc.).

# shellcheck disable=SC2120
load_env() {
  local env_file="${1:-${REPO_ROOT}/.env}"
  if [[ -f "${env_file}" ]]; then
    # shellcheck source=/dev/null
    set -a; source "${env_file}"; set +a
  fi

  # Translate REQUESTQUEUE_AWS_* → AWS_* if the standard one isn't already set.
  : "${AWS_REGION:=${REQUESTQUEUE_AWS_REGION:-}}"
  : "${AWS_DEFAULT_REGION:=${REQUESTQUEUE_AWS_REGION:-}}"
  : "${AWS_PROFILE:=${REQUESTQUEUE_AWS_PROFILE:-}}"
  : "${AWS_ACCESS_KEY_ID:=${REQUESTQUEUE_AWS_ACCESS_KEY_ID:-}}"
  : "${AWS_SECRET_ACCESS_KEY:=${REQUESTQUEUE_AWS_SECRET_ACCESS_KEY:-}}"
  : "${AWS_SESSION_TOKEN:=${REQUESTQUEUE_AWS_SESSION_TOKEN:-}}"

  # Don't export empty values — some AWS SDKs treat empty AWS_PROFILE as a
  # profile named "" and break.
  [[ -n "${AWS_REGION}" ]] && export AWS_REGION
  [[ -n "${AWS_DEFAULT_REGION}" ]] && export AWS_DEFAULT_REGION
  [[ -n "${AWS_PROFILE}" ]] && export AWS_PROFILE
  [[ -n "${AWS_ACCESS_KEY_ID}" ]] && export AWS_ACCESS_KEY_ID
  [[ -n "${AWS_SECRET_ACCESS_KEY}" ]] && export AWS_SECRET_ACCESS_KEY
  [[ -n "${AWS_SESSION_TOKEN}" ]] && export AWS_SESSION_TOKEN
}
