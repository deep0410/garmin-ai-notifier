#!/usr/bin/env bash
# Upload local ~/.garminconnect tokens to AWS Secrets Manager (one-time after mint_token.py).
# Requires: AWS CLI configured locally, tokens in GARMINTOKENS (default ~/.garminconnect).
# Env: AWS_REGION, GARMIN_TOKEN_SECRET_NAME (or set in .env).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

AWS_REGION="${AWS_REGION:-us-east-1}"
GARMIN_TOKEN_SECRET_NAME="${GARMIN_TOKEN_SECRET_NAME:-garmin-ai-notifier/garmin-tokens}"
export AWS_REGION GARMIN_TOKEN_SECRET_NAME

if ! aws sts get-caller-identity --region "$AWS_REGION" >/dev/null 2>&1; then
  echo "AWS CLI not configured — run: aws configure" >&2
  exit 1
fi

B64="$("$SCRIPT_DIR/token_aws.sh" pack)"
aws secretsmanager put-secret-value \
  --secret-id "$GARMIN_TOKEN_SECRET_NAME" \
  --secret-string "$B64" \
  --region "$AWS_REGION" \
  --output text >/dev/null

echo "Seeded $GARMIN_TOKEN_SECRET_NAME in $AWS_REGION"
echo "Verify: bash scripts/token_aws.sh restore"
