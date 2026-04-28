#!/usr/bin/env bash
# scripts/bootstrap_local.sh — one-time fetch of the Cognito service-user
# password from Secrets Manager into ~/.config/requestqueue/credentials.
#
# Run this on the local server (or wherever local/monitor will run) ONCE,
# using AWS credentials that can read the secret. After this, the local
# server has zero AWS IAM credentials at runtime — only the Cognito password.
#
# Reads:
#   .requestqueue.outputs.json     (for ServiceUserSecretArn / ServiceUserEmail)
#   .env                    (for REQUESTQUEUE_AWS_REGION + AWS creds for the bootstrap)
#
# Writes:
#   ~/.config/requestqueue/credentials   (mode 0600, JSON: {email, password})
#
# Usage:
#   scripts/bootstrap_local.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUTS_FILE="${REPO_ROOT}/.requestqueue.outputs.json"
ENV_FILE="${REPO_ROOT}/.env"
CRED_DIR="${REQUESTQUEUE_CREDENTIALS_DIR:-${HOME}/.config/requestqueue}"
CRED_FILE="${CRED_DIR}/credentials"

err() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

[[ -f "${OUTPUTS_FILE}" ]] || err "${OUTPUTS_FILE} not found — run 'make publish' first"
[[ -f "${ENV_FILE}" ]] || err "${ENV_FILE} not found — copy from .env.example and fill in"

# shellcheck source=/dev/null
set -a; source "${ENV_FILE}"; set +a

command -v aws >/dev/null || err "aws CLI not installed"
command -v jq >/dev/null || err "jq not installed (brew install jq)"

REGION="${REQUESTQUEUE_AWS_REGION:-us-east-1}"
SECRET_ARN="$(jq -r '.ServiceUserSecretArn // .service_user_secret_arn // empty' "${OUTPUTS_FILE}")"
EMAIL="$(jq -r '.ServiceUserEmail // .service_user_email // empty' "${OUTPUTS_FILE}")"

[[ -n "${SECRET_ARN}" ]] || err "ServiceUserSecretArn missing from ${OUTPUTS_FILE}"
[[ -n "${EMAIL}" ]] || err "ServiceUserEmail missing from ${OUTPUTS_FILE}"

info "fetching service-user password from Secrets Manager…"
PASSWORD="$(aws secretsmanager get-secret-value \
  --region "${REGION}" \
  --secret-id "${SECRET_ARN}" \
  --query SecretString \
  --output text)"

[[ -n "${PASSWORD}" ]] || err "secret value was empty"

mkdir -p "${CRED_DIR}"
chmod 700 "${CRED_DIR}"
umask 077
jq -n --arg e "${EMAIL}" --arg p "${PASSWORD}" '{email: $e, password: $p}' > "${CRED_FILE}"
chmod 600 "${CRED_FILE}"

info "wrote ${CRED_FILE} (mode 0600, owner-only)"
info "you can now remove AWS credentials from .env on this machine — they are not needed at runtime"
info "next step: 'make monitor' to start the long-running poll loop"
