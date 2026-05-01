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
# Precedence: REQUESTQUEUE_AWS_* in .env OVERRIDES any AWS_* values already
# in the shell environment. The .env file is the authoritative source for
# THIS project — without override, a stale `AWS_PROFILE=other-account` in
# the user's shell would silently misroute deploys. To deploy to a
# different account, edit .env (don't `export AWS_PROFILE=…` in the shell).
# When REQUESTQUEUE_AWS_* is unset, any existing AWS_* values pass through
# unchanged.

# shellcheck disable=SC2120
load_env() {
  local env_file="${1:-${REPO_ROOT}/.env}"
  if [[ -f "${env_file}" ]]; then
    # shellcheck source=/dev/null
    set -a; source "${env_file}"; set +a
  fi

  # Translate REQUESTQUEUE_AWS_* → AWS_* — .env values OVERRIDE shell env.
  # Use `if [[ ]]; then ...; fi` (NOT `[[ ]] && export`) — under `set -e`
  # in the calling script, a `[[ ]] && cmd` chain returns the failed [[ ]]
  # exit code when the variable is empty, which propagates as a function
  # return code of 1 and silently kills the caller.
  if [[ -n "${REQUESTQUEUE_AWS_REGION:-}" ]]; then
    export AWS_REGION="${REQUESTQUEUE_AWS_REGION}"
    export AWS_DEFAULT_REGION="${REQUESTQUEUE_AWS_REGION}"
  fi
  if [[ -n "${REQUESTQUEUE_AWS_PROFILE:-}" ]]; then
    export AWS_PROFILE="${REQUESTQUEUE_AWS_PROFILE}"
  fi
  if [[ -n "${REQUESTQUEUE_AWS_ACCESS_KEY_ID:-}" ]]; then
    export AWS_ACCESS_KEY_ID="${REQUESTQUEUE_AWS_ACCESS_KEY_ID}"
  fi
  if [[ -n "${REQUESTQUEUE_AWS_SECRET_ACCESS_KEY:-}" ]]; then
    export AWS_SECRET_ACCESS_KEY="${REQUESTQUEUE_AWS_SECRET_ACCESS_KEY}"
  fi
  if [[ -n "${REQUESTQUEUE_AWS_SESSION_TOKEN:-}" ]]; then
    export AWS_SESSION_TOKEN="${REQUESTQUEUE_AWS_SESSION_TOKEN}"
  fi

  return 0
}
