#!/usr/bin/env bash
# Pack, restore, or persist Garmin tokens via AWS Secrets Manager.
# Subcommands: pack | restore | persist
# Env: AWS_REGION (default us-east-1), GARMIN_TOKEN_SECRET_NAME (required for restore/persist),
#      GARMINTOKENS (default ~/.garminconnect), AWS_PROFILE (optional).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

load_env() {
  if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT_DIR/.env"
    set +a
  fi
}

AWS_REGION="${AWS_REGION:-us-east-1}"
TOKEN_DIR="${GARMINTOKENS:-$HOME/.garminconnect}"
TOKEN_DIR="${TOKEN_DIR/#\~/$HOME}"
if [[ -d "$TOKEN_DIR" ]]; then
  TOKEN_DIR="$(cd "$TOKEN_DIR" && pwd)"
fi

cmd_pack() {
  if [[ ! -d "$TOKEN_DIR" ]] || [[ -z "$(ls -A "$TOKEN_DIR" 2>/dev/null)" ]]; then
    echo "No tokens in $TOKEN_DIR — run: python scripts/mint_token.py" >&2
    exit 1
  fi
  OUT="$(mktemp -t garmin-tokens.XXXXXX.tar)"
  trap 'rm -f "$OUT"' RETURN
  tar -cf "$OUT" -C "$TOKEN_DIR" .
  base64 < "$OUT" | tr -d '\n\r '
}

cmd_restore() {
  load_env
  : "${GARMIN_TOKEN_SECRET_NAME:?Set GARMIN_TOKEN_SECRET_NAME}"

  B64="$(aws secretsmanager get-secret-value \
    --secret-id "$GARMIN_TOKEN_SECRET_NAME" \
    --region "$AWS_REGION" \
    --query SecretString \
    --output text)"

  if [[ -z "$B64" || "$B64" == "UNINITIALIZED" ]]; then
    echo "Secret not seeded — run: bash scripts/seed_aws_secret.sh" >&2
    exit 1
  fi

  mkdir -p "$TOKEN_DIR"
  TMP_TAR="$(mktemp -t garmin-tokens.XXXXXX.tar)"
  trap 'rm -f "$TMP_TAR"' EXIT
  printf '%s' "$B64" | tr -d '\n\r\t ' | base64 -d > "$TMP_TAR"
  tar -tf "$TMP_TAR" >/dev/null
  tar -xf "$TMP_TAR" -C "$TOKEN_DIR"

  if [[ ! -f "$TOKEN_DIR/garmin_tokens.json" ]]; then
    echo "Token file missing after extract — re-run scripts/seed_aws_secret.sh" >&2
    ls -la "$TOKEN_DIR" >&2 || true
    exit 1
  fi
  echo "Restored tokens to $TOKEN_DIR"
}

cmd_persist() {
  load_env
  : "${GARMIN_TOKEN_SECRET_NAME:?Set GARMIN_TOKEN_SECRET_NAME}"

  if [[ ! -f "$TOKEN_DIR/garmin_tokens.json" ]]; then
    echo "Nothing to persist — $TOKEN_DIR/garmin_tokens.json missing" >&2
    exit 1
  fi

  B64="$(GARMINTOKENS="$TOKEN_DIR" "$0" pack)"
  aws secretsmanager put-secret-value \
    --secret-id "$GARMIN_TOKEN_SECRET_NAME" \
    --secret-string "$B64" \
    --region "$AWS_REGION" \
    --output text >/dev/null
  echo "Persisted rotated tokens to $GARMIN_TOKEN_SECRET_NAME"
}

usage() {
  echo "Usage: $0 pack|restore|persist" >&2
  exit 1
}

case "${1:-}" in
  pack) cmd_pack ;;
  restore) cmd_restore ;;
  persist) cmd_persist ;;
  *) usage ;;
esac
