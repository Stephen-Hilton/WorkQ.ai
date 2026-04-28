#!/usr/bin/env bash
# scripts/refresh_creds.sh — generate a fresh Cognito service-user password
# and write it into the local .env (with backup).
#
# Run this:
#   - Once at install, to generate the initial REQUESTQUEUE_SERVICE_USER_PASSWORD.
#   - Whenever you want to rotate the password (after which: `make publish`
#     to push to Cognito, then copy the same line to your local server's .env).
#
# Behavior:
#   1. Backs up the existing .env to backups/env/.env_<timestamp>
#      (mode 0600, gitignored).
#   2. Generates a new 32-char URL-safe password.
#   3. Removes any existing REQUESTQUEUE_SERVICE_USER_{EMAIL,PASSWORD} lines
#      from .env, then appends fresh ones.
#   4. Tightens .env to mode 0600.
#   5. Echoes the two new lines so you can paste them into your local
#      server's .env.
#
# Notes:
#   - This script ONLY writes to the local .env. It does NOT call AWS.
#   - To apply the new password to the Cognito user pool, run `make publish`
#     after this script. The CloudFormation NoEcho parameter
#     (ServiceUserPassword) is what propagates the value.
#   - If you've never run `make publish` before, this is the right first
#     step — it gives you the password .env needs before deploy.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
ENV_EXAMPLE="${REPO_ROOT}/.env.example"
BACKUP_DIR="${REPO_ROOT}/backups/env"

err() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

SERVICE_EMAIL="service-local-monitor@requestqueue.internal"

# Bootstrap .env from .env.example if missing — friendlier first-run UX.
if [[ ! -f "${ENV_FILE}" ]]; then
  if [[ -f "${ENV_EXAMPLE}" ]]; then
    info "${ENV_FILE} not found — creating from .env.example"
    cp "${ENV_EXAMPLE}" "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
  else
    err "${ENV_FILE} not found and no .env.example to bootstrap from"
  fi
fi

# Generate a new password. base64 from openssl gives us upper, lower, digits,
# plus +/= which Cognito accepts as symbols. Strip = padding and any embedded
# newlines so it copy-pastes cleanly into a single .env line.
if ! command -v openssl >/dev/null 2>&1; then
  err "openssl not installed (required for password generation)"
fi
NEW_PASSWORD="$(openssl rand -base64 32 | tr -d '=\n' | head -c 40)"
[[ -n "${NEW_PASSWORD}" ]] || err "failed to generate password"
[[ ${#NEW_PASSWORD} -ge 16 ]] || err "generated password too short (${#NEW_PASSWORD})"

# Backup
mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/.env_${TIMESTAMP}"
cp "${ENV_FILE}" "${BACKUP_FILE}"
chmod 600 "${BACKUP_FILE}"
info "backed up to ${BACKUP_FILE}"

# Strip existing service-user lines, then append fresh ones.
TMP_ENV="$(mktemp "${REPO_ROOT}/.env.refresh.XXXXXX")"
trap 'rm -f "${TMP_ENV}"' EXIT

# Drop any prior service-user lines AND any preceding marker comment so we
# don't accumulate stale comments on repeated runs.
awk '
  /^# Cognito service-user credentials \(set\/refreshed by scripts\/refresh_creds\.sh\)$/ { skip=1; next }
  /^REQUESTQUEUE_SERVICE_USER_(EMAIL|PASSWORD)=/ { skip=1; next }
  skip && /^$/ { skip=0; next }
  skip && /^#/ { next }
  { skip=0; print }
' "${ENV_FILE}" > "${TMP_ENV}"

# Trim trailing blank lines, then append the marker block.
# (We append rather than overwrite so the user keeps their other settings.)
{
  # Strip trailing blank lines
  sed -e :a -e '/^$/{$d;N;ba' -e '}' "${TMP_ENV}"
  echo ""
  echo "# Cognito service-user credentials (set/refreshed by scripts/refresh_creds.sh)"
  echo "REQUESTQUEUE_SERVICE_USER_EMAIL=${SERVICE_EMAIL}"
  echo "REQUESTQUEUE_SERVICE_USER_PASSWORD=${NEW_PASSWORD}"
} > "${TMP_ENV}.final"

mv "${TMP_ENV}.final" "${ENV_FILE}"
rm -f "${TMP_ENV}"
chmod 600 "${ENV_FILE}"

info "updated ${ENV_FILE} with fresh service-user credentials"
echo ""
info "Next steps:"
info "  1. (deploy machine)  make publish     — applies the new password to Cognito"
info "  2. If your local server is a different machine, paste these two lines"
info "     into the local server's .env (replacing any existing copies):"
echo ""
printf '       REQUESTQUEUE_SERVICE_USER_EMAIL=%s\n' "${SERVICE_EMAIL}"
printf '       REQUESTQUEUE_SERVICE_USER_PASSWORD=%s\n' "${NEW_PASSWORD}"
echo ""
info "  3. (local server)    restart the monitor process (or wait for next"
info "                       JWT refresh, which auto-falls-back to password login)"
