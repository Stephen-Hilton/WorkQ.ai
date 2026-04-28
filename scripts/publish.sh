#!/usr/bin/env bash
# scripts/publish.sh — full WorkQ.ai deploy pipeline.
#
# Phases:
#   1. (--prompts-only or full) validate prompt_parts.yaml.
#   2. (--prompts-only or full) sam build + sam deploy
#      Writes .workq.outputs.json (snake_case keys mapped from CFN PascalCase).
#   3. (--infra-only: stop here)
#   4. pnpm/npm build the webapp using .workq.outputs.json.
#   5. aws s3 sync ui/webapp/dist/ s3://<bucket>/.
#   6. Upload prompts/prompt_parts.yaml + generated app.json to s3://<bucket>/config/.
#   7. CloudFront invalidation.
#
# Usage:
#   publish.sh                 # full pipeline
#   publish.sh --infra-only    # SAM deploy only (skip webapp + uploads)
#   publish.sh --prompts-only  # skip SAM, just upload prompt_parts + app.json + invalidate

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
OUTPUTS_FILE="${REPO_ROOT}/.workq.outputs.json"

INFRA_ONLY=0
PROMPTS_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --infra-only) INFRA_ONLY=1 ;;
    --prompts-only) PROMPTS_ONLY=1 ;;
    -h|--help) sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

err() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

[[ -f "${ENV_FILE}" ]] || err ".env not found at ${ENV_FILE} (copy from .env.example and fill in)"
# shellcheck source=/dev/null
set -a; source "${ENV_FILE}"; set +a

command -v aws >/dev/null || err "aws CLI not installed"
command -v jq >/dev/null || err "jq not installed (brew install jq)"

REGION="${WORKQ_AWS_REGION:-us-east-1}"
STACK="${WORKQ_STACK_NAME:-workq}"

# Pick package manager: prefer pnpm, fall back to npm.
if command -v pnpm >/dev/null 2>&1; then PM="pnpm"; else PM="npm"; fi

# ---------------------------------------------------------------------------
# 1) Validate prompts/prompt_parts.yaml
# ---------------------------------------------------------------------------
info "validating prompts/prompt_parts.yaml"
PYBIN="$(command -v python3 || command -v python)"
[[ -n "${PYBIN}" ]] || err "python3 not found"
"${PYBIN}" "${REPO_ROOT}/scripts/validate_prompt_parts.py" "${REPO_ROOT}/prompts/prompt_parts.yaml"

# ---------------------------------------------------------------------------
# 2) SAM deploy (skipped for --prompts-only)
# ---------------------------------------------------------------------------
if (( PROMPTS_ONLY == 0 )); then
  command -v sam >/dev/null || err "sam CLI not installed (brew install aws-sam-cli)"

  PARAM_OVERRIDES="StackName=${STACK}"
  if [[ -n "${WORKQ_EMAIL_WHITELIST:-}" ]]; then
    PARAM_OVERRIDES+=" EmailWhitelistSeed=${WORKQ_EMAIL_WHITELIST}"
  fi
  if [[ -n "${WORKQ_CUSTOM_DOMAIN:-}" ]]; then
    PARAM_OVERRIDES+=" CustomDomain=${WORKQ_CUSTOM_DOMAIN}"
    [[ -n "${WORKQ_CUSTOM_DOMAIN_CERT_ARN:-}" ]] || err "WORKQ_CUSTOM_DOMAIN is set but WORKQ_CUSTOM_DOMAIN_CERT_ARN is not"
    PARAM_OVERRIDES+=" CustomDomainCertArn=${WORKQ_CUSTOM_DOMAIN_CERT_ARN}"
  fi
  if [[ -n "${WORKQ_COGNITO_DOMAIN_PREFIX:-}" ]]; then
    PARAM_OVERRIDES+=" CognitoDomainPrefix=${WORKQ_COGNITO_DOMAIN_PREFIX}"
  fi

  SAMCONFIG="${REPO_ROOT}/infra/samconfig.toml"
  GUIDED_FLAG=""
  if [[ ! -f "${SAMCONFIG}" ]]; then
    info "first deploy detected — running 'sam deploy --guided'"
    GUIDED_FLAG="--guided"
  fi

  info "sam build"
  (cd "${REPO_ROOT}/infra" && sam build)

  info "sam deploy"
  # shellcheck disable=SC2086
  (cd "${REPO_ROOT}/infra" && sam deploy \
    --stack-name "${STACK}" \
    --region "${REGION}" \
    --capabilities CAPABILITY_IAM \
    --no-fail-on-empty-changeset \
    --parameter-overrides ${PARAM_OVERRIDES} \
    ${GUIDED_FLAG})

  info "fetching stack outputs"
  raw="$(aws cloudformation describe-stacks --region "${REGION}" --stack-name "${STACK}" --query 'Stacks[0].Outputs')"
  echo "${raw}" | jq '
    [.[] | {key: .OutputKey, value: .OutputValue}]
    | reduce .[] as $o ({}; .[$o.key] = $o.value)
    | . + {
        api_url: (.ApiUrl // .api_url // ""),
        webapp_url: (.WebappUrl // .webapp_url // ""),
        cognito_user_pool_id: (.CognitoUserPoolId // ""),
        cognito_client_id: (.CognitoClientId // ""),
        cognito_domain: (.CognitoDomain // ""),
        cognito_region: (.CognitoRegion // ""),
        s3_webapp_bucket: (.S3WebappBucket // ""),
        cloudfront_distribution_id: (.CloudfrontDistributionId // ""),
        service_user_email: (.ServiceUserEmail // ""),
        service_user_secret_arn: (.ServiceUserSecretArn // "")
      }
  ' > "${OUTPUTS_FILE}"
  info "wrote ${OUTPUTS_FILE}"

  if (( INFRA_ONLY == 1 )); then
    info "infra-only: stopping after sam deploy"
    exit 0
  fi
fi

# ---------------------------------------------------------------------------
# 3) Webapp build (skipped for --prompts-only)
# ---------------------------------------------------------------------------
[[ -f "${OUTPUTS_FILE}" ]] || err "${OUTPUTS_FILE} missing — run a full publish first"

BUCKET="$(jq -r '.s3_webapp_bucket // .S3WebappBucket // empty' "${OUTPUTS_FILE}")"
DIST_ID="$(jq -r '.cloudfront_distribution_id // .CloudfrontDistributionId // empty' "${OUTPUTS_FILE}")"
[[ -n "${BUCKET}" ]] || err "s3_webapp_bucket missing from ${OUTPUTS_FILE}"
[[ -n "${DIST_ID}" ]] || err "cloudfront_distribution_id missing from ${OUTPUTS_FILE}"

if (( PROMPTS_ONLY == 0 )); then
  info "${PM} install (webapp)"
  (cd "${REPO_ROOT}/ui/webapp" && "${PM}" install)
  info "${PM} run build (webapp)"
  (cd "${REPO_ROOT}/ui/webapp" && "${PM}" run build)
  info "syncing webapp bundle to s3://${BUCKET}/"
  aws s3 sync "${REPO_ROOT}/ui/webapp/dist/" "s3://${BUCKET}/" --delete --exclude 'config/*'
fi

# ---------------------------------------------------------------------------
# 4) Runtime config upload
# ---------------------------------------------------------------------------
info "uploading runtime config (prompt_parts.yaml + app.json)"
TZ_VAL="${WORKQ_DISPLAY_TIMEZONE:-UTC}"
TMP_APP_JSON="$(mktemp)"
trap 'rm -f "${TMP_APP_JSON}"' EXIT
jq -n --arg tz "${TZ_VAL}" '{display_timezone: $tz}' > "${TMP_APP_JSON}"

aws s3 cp "${REPO_ROOT}/prompts/prompt_parts.yaml" "s3://${BUCKET}/config/prompt_parts.yaml" \
  --content-type 'text/yaml' --cache-control 'public,max-age=60'
aws s3 cp "${TMP_APP_JSON}" "s3://${BUCKET}/config/app.json" \
  --content-type 'application/json' --cache-control 'public,max-age=60'

# ---------------------------------------------------------------------------
# 5) CloudFront invalidation
# ---------------------------------------------------------------------------
info "creating CloudFront invalidation"
aws cloudfront create-invalidation --distribution-id "${DIST_ID}" --paths '/*' >/dev/null

WEBAPP_URL="$(jq -r '.webapp_url // .WebappUrl // empty' "${OUTPUTS_FILE}")"
API_URL="$(jq -r '.api_url // .ApiUrl // empty' "${OUTPUTS_FILE}")"

info "done!"
info "  webapp: ${WEBAPP_URL}"
info "  api:    ${API_URL}"
