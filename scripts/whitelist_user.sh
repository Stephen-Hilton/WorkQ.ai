#!/usr/bin/env bash
# scripts/whitelist_user.sh — manage the SSM email whitelist.
#
# Usage:
#   whitelist_user.sh -a user@example.com    # add exact email
#   whitelist_user.sh -a @example.com        # add domain wildcard
#   whitelist_user.sh -r user@example.com    # remove
#   whitelist_user.sh -l                     # list
#   whitelist_user.sh -h | --help | ?        # help
#
# Reads .env for REQUESTQUEUE_AWS_REGION + REQUESTQUEUE_STACK_NAME.
# Requires: aws CLI, jq.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

err() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

usage() {
  cat <<EOF
Usage:
  $0 -a <email_or_@domain>     Add to whitelist
  $0 --add <email_or_@domain>

  $0 -r <email_or_@domain>     Remove from whitelist
  $0 --remove <email_or_@domain>

  $0 -l                        List current whitelist
  $0 --list

  $0 -h | --help | ?           Show this help

Examples:
  $0 -a alice@example.com
  $0 -a @example.com           # whole-domain wildcard
  $0 -r alice@example.com
  $0 -l
EOF
}

ACTION=""
VALUE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -a|--add) ACTION="add"; VALUE="${2:-}"; shift 2 ;;
    -r|--remove) ACTION="remove"; VALUE="${2:-}"; shift 2 ;;
    -l|--list) ACTION="list"; shift ;;
    -h|--help|"?") usage; exit 0 ;;
    *) err "unknown option: $1 (use -h for help)" ;;
  esac
done

[[ -n "${ACTION}" ]] || { usage; exit 1; }

if [[ "${ACTION}" != "list" && -z "${VALUE}" ]]; then
  err "missing email/domain for --${ACTION}"
fi

[[ -f "${ENV_FILE}" ]] || err ".env not found at ${ENV_FILE}"
# shellcheck source=lib_env.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib_env.sh"
load_env "${ENV_FILE}"

REGION="${REQUESTQUEUE_AWS_REGION:-us-east-1}"
STACK="${REQUESTQUEUE_STACK_NAME:-requestqueue}"
PARAM="/${STACK}/email_whitelist"

command -v aws >/dev/null || err "aws CLI not installed"
command -v jq >/dev/null || err "jq not installed (brew install jq)"

current="$(aws ssm get-parameter --region "${REGION}" --name "${PARAM}" --query 'Parameter.Value' --output text 2>/dev/null || echo '')"
# Normalize to lowercase, comma-separated, trim whitespace, drop empties.
to_array() {
  echo "$1" | tr ',' '\n' | sed -E 's/^[[:space:]]+|[[:space:]]+$//g' | tr '[:upper:]' '[:lower:]' | awk 'NF'
}
to_csv() { paste -sd, -; }

mapfile -t entries < <(to_array "${current}")

contains() {
  local needle="$1"
  for e in "${entries[@]}"; do
    [[ "${e}" == "${needle}" ]] && return 0
  done
  return 1
}

case "${ACTION}" in
  list)
    if (( ${#entries[@]} == 0 )); then
      info "(empty whitelist at ${PARAM})"
    else
      info "current ${PARAM}:"
      for e in "${entries[@]}"; do printf '  %s\n' "${e}"; done
    fi
    ;;

  add)
    needle="$(echo "${VALUE}" | tr '[:upper:]' '[:lower:]')"
    if contains "${needle}"; then
      info "already in whitelist: ${needle}"
      exit 0
    fi
    entries+=("${needle}")
    new="$(printf '%s\n' "${entries[@]}" | to_csv)"
    aws ssm put-parameter --region "${REGION}" --name "${PARAM}" --type String --value "${new}" --overwrite >/dev/null
    info "added ${needle}; whitelist now has ${#entries[@]} entries"
    ;;

  remove)
    needle="$(echo "${VALUE}" | tr '[:upper:]' '[:lower:]')"
    new_arr=()
    for e in "${entries[@]}"; do
      [[ "${e}" == "${needle}" ]] && continue
      new_arr+=("${e}")
    done
    if (( ${#new_arr[@]} == ${#entries[@]} )); then
      info "not in whitelist: ${needle}"
      exit 0
    fi
    new="$(printf '%s\n' "${new_arr[@]}" | to_csv)"
    aws ssm put-parameter --region "${REGION}" --name "${PARAM}" --type String --value "${new}" --overwrite >/dev/null
    info "removed ${needle}; whitelist now has ${#new_arr[@]} entries"
    ;;
esac
