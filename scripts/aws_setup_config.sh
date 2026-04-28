#!/usr/bin/env bash
# scripts/aws_setup_config.sh — configure an AWS CLI profile from a CSV file
# or the system clipboard, without exposing the keys to anything that captures
# stdout (e.g. Claude Code's `!` bash mode).
#
# Three modes:
#   --csv <path>       Read AWS-downloaded "Access keys" CSV. Single
#                      invocation; sets ID + secret + region + output.
#   --clip-id          Read Access Key ID from clipboard.
#                      Run this first, then copy the secret and run --clip-secret.
#   --clip-secret      Read Secret Access Key from clipboard. Sets region +
#                      output and runs `aws sts get-caller-identity` to verify.
#
# Args after the mode:
#   [profile]          AWS profile name (default: requestqueue)
#   [region]           AWS region (default: us-east-1)
#
# Output is intentionally minimal: only success messages and the
# `aws sts get-caller-identity` JSON (which contains account ID + user ARN —
# non-secret). Key values are NEVER printed.
#
# Idempotent: re-running overwrites the same profile fields. Safe.

set -euo pipefail

DEFAULT_PROFILE="requestqueue"
DEFAULT_REGION="us-east-1"

usage() {
  cat <<EOF
Usage:
  $0 --csv <path> [profile] [region]
  $0 --clip-id [profile]
  $0 --clip-secret [profile] [region]

Modes:
  --csv          Read keys from AWS-downloaded "Access keys" CSV file.
                 Single invocation; sets ID + secret + region + output.
  --clip-id      Read Access Key ID from system clipboard. Run first.
  --clip-secret  Read Secret Access Key from clipboard. Run after --clip-id.
                 Also sets region + output and verifies via sts.

Defaults: profile=$DEFAULT_PROFILE region=$DEFAULT_REGION
EOF
}

# Read clipboard into stdout. Detects platform and clipboard tool.
read_clipboard() {
  local val=""
  case "$(uname -s)" in
    Darwin)
      val=$(pbpaste 2>/dev/null || true)
      ;;
    Linux)
      if [[ -n "${WAYLAND_DISPLAY:-}" ]] && command -v wl-paste >/dev/null 2>&1; then
        val=$(wl-paste -n 2>/dev/null || true)
      elif command -v xclip >/dev/null 2>&1; then
        val=$(xclip -o -selection clipboard 2>/dev/null || true)
      elif command -v xsel >/dev/null 2>&1; then
        val=$(xsel --clipboard --output 2>/dev/null || true)
      else
        echo "ERROR: no clipboard tool found." >&2
        echo "  On Linux, install one of: wl-clipboard, xclip, xsel" >&2
        echo "  On WSL2, run with WSLg or use --csv mode instead." >&2
        exit 2
      fi
      ;;
    *)
      echo "ERROR: clipboard mode is not supported on $(uname -s). Use --csv mode." >&2
      exit 2
      ;;
  esac
  # Strip whitespace (especially trailing newlines from copy operations).
  printf '%s' "$val" | tr -d '[:space:]'
}

verify_profile() {
  local profile="$1"
  echo
  echo "Verifying profile '$profile' with aws sts get-caller-identity..."
  if aws sts get-caller-identity --profile "$profile"; then
    echo
    echo "✓ Profile '$profile' is configured and authenticates successfully."
  else
    echo
    echo "✗ Verification failed. Possible causes:" >&2
    echo "  - Wrong Access Key ID or Secret pasted" >&2
    echo "  - IAM user lacks sts:GetCallerIdentity (extremely rare)" >&2
    echo "  - Access key was deactivated in the AWS console" >&2
    return 1
  fi
}

[[ $# -ge 1 ]] || { usage; exit 1; }
MODE="$1"; shift

case "$MODE" in
  --csv)
    [[ $# -ge 1 ]] || { usage; exit 1; }
    CSV="$1"
    PROFILE="${2:-$DEFAULT_PROFILE}"
    REGION="${3:-$DEFAULT_REGION}"

    [[ -f "$CSV" ]] || { echo "ERROR: CSV file not found: $CSV" >&2; exit 1; }

    # AWS CSV format: header row + one data row.
    # Common headers: "Access key ID,Secret access key" (legacy) or
    # "User name,Password,Access key ID,Secret access key,Console login link"
    HEADER=$(head -n1 "$CSV" | tr -d '\r')
    DATA=$(sed -n '2p' "$CSV" | tr -d '\r')
    [[ -n "$DATA" ]] || { echo "ERROR: CSV has no data row: $CSV" >&2; exit 1; }

    # Find column positions (case-insensitive) for the ID and Secret columns.
    ID_COL=$(printf '%s\n' "$HEADER" | awk -F',' '{
      for (i=1; i<=NF; i++) {
        v=tolower($i); gsub(/[ "]/,"",v)
        if (v ~ /accesskeyid/) { print i; exit }
      }
    }')
    SECRET_COL=$(printf '%s\n' "$HEADER" | awk -F',' '{
      for (i=1; i<=NF; i++) {
        v=tolower($i); gsub(/[ "]/,"",v)
        if (v ~ /secretaccesskey/ || v ~ /secretkey/) { print i; exit }
      }
    }')
    if [[ -z "$ID_COL" || -z "$SECRET_COL" ]]; then
      echo "ERROR: could not find 'Access key ID' and 'Secret access key' columns." >&2
      echo "Header was: $HEADER" >&2
      exit 1
    fi

    KEY_ID=$(printf '%s\n' "$DATA"   | awk -F',' -v c="$ID_COL"     '{print $c}' | tr -d '"\r ')
    SECRET=$(printf '%s\n' "$DATA"   | awk -F',' -v c="$SECRET_COL" '{print $c}' | tr -d '"\r ')
    if [[ -z "$KEY_ID" || -z "$SECRET" ]]; then
      echo "ERROR: empty key or secret in CSV." >&2
      exit 1
    fi

    aws configure set aws_access_key_id     "$KEY_ID" --profile "$PROFILE"
    aws configure set aws_secret_access_key "$SECRET" --profile "$PROFILE"
    aws configure set region                "$REGION" --profile "$PROFILE"
    aws configure set output                "json"    --profile "$PROFILE"

    verify_profile "$PROFILE"
    echo
    echo "Tip: securely delete the CSV file now:"
    echo "  rm \"$CSV\""
    ;;

  --clip-id)
    PROFILE="${1:-$DEFAULT_PROFILE}"
    KEY_ID=$(read_clipboard)
    if [[ -z "$KEY_ID" ]]; then
      echo "ERROR: clipboard is empty. Copy the Access Key ID first." >&2
      exit 1
    fi
    if [[ ! "$KEY_ID" =~ ^[A-Z0-9]{16,128}$ ]]; then
      echo "ERROR: clipboard does not look like an AWS Access Key ID." >&2
      echo "  Expected: 16-128 uppercase alphanumeric chars (typically AKIA…)." >&2
      echo "  Got: ${#KEY_ID} chars, starting with '${KEY_ID:0:4}…'" >&2
      exit 1
    fi
    aws configure set aws_access_key_id "$KEY_ID" --profile "$PROFILE"
    echo "✓ Set aws_access_key_id for profile '$PROFILE' (length: ${#KEY_ID}, prefix: ${KEY_ID:0:4})."
    echo
    echo "Next: copy the Secret Access Key to your clipboard, then run:"
    echo "  ./scripts/aws_setup_config.sh --clip-secret $PROFILE"
    ;;

  --clip-secret)
    PROFILE="${1:-$DEFAULT_PROFILE}"
    REGION="${2:-$DEFAULT_REGION}"
    SECRET=$(read_clipboard)
    if [[ -z "$SECRET" ]]; then
      echo "ERROR: clipboard is empty. Copy the Secret Access Key first." >&2
      exit 1
    fi
    if [[ ${#SECRET} -lt 20 ]]; then
      echo "ERROR: clipboard content too short to be a Secret Access Key (${#SECRET} chars)." >&2
      echo "  AWS Secret Access Keys are typically 40 chars." >&2
      exit 1
    fi

    aws configure set aws_secret_access_key "$SECRET" --profile "$PROFILE"
    aws configure set region                "$REGION" --profile "$PROFILE"
    aws configure set output                "json"    --profile "$PROFILE"

    verify_profile "$PROFILE"
    ;;

  -h|--help)
    usage
    ;;

  *)
    echo "ERROR: unknown mode: $MODE" >&2
    usage
    exit 1
    ;;
esac
