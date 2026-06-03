#!/usr/bin/env bash
# Pack ~/.garminconnect for GitHub secret GARMIN_TOKENS_B64 (single line, no spaces).
set -euo pipefail

TOKEN_DIR="${GARMINTOKENS:-$HOME/.garminconnect}"
TOKEN_DIR="$(cd "$(dirname "$TOKEN_DIR")" && pwd)/$(basename "$TOKEN_DIR")"

if [[ ! -d "$TOKEN_DIR" ]] || [[ -z "$(ls -A "$TOKEN_DIR" 2>/dev/null)" ]]; then
  echo "No tokens in $TOKEN_DIR — run: python scripts/mint_token.py" >&2
  exit 1
fi

OUT="$(mktemp -t garmin-tokens.XXXXXX.tar)"
trap 'rm -f "$OUT"' EXIT

tar -cf "$OUT" -C "$TOKEN_DIR" .
B64="$(base64 < "$OUT" | tr -d '\n\r ')"

echo "Paste this entire line into GitHub secret GARMIN_TOKENS_B64:"
echo ""
echo "$B64"
echo ""
echo "Verify decode (should print OK):"
echo "$B64" | tr -d '\n\r ' | base64 -d >/dev/null && echo OK
