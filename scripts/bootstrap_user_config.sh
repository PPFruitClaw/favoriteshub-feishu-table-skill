#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXAMPLE_FILE="$SKILL_ROOT/references/favoriteshub-config.example.json"

OUT_FILE="${1:-$PWD/favoriteshub.config.json}"
FORCE="${2:-}"

if [ ! -f "$EXAMPLE_FILE" ]; then
  echo "example config not found: $EXAMPLE_FILE" >&2
  exit 1
fi

if [ -f "$OUT_FILE" ] && [ "$FORCE" != "--force" ]; then
  echo "config already exists: $OUT_FILE"
  echo "use '--force' to overwrite"
  exit 0
fi

cp "$EXAMPLE_FILE" "$OUT_FILE"

echo "created: $OUT_FILE"
echo "next:"
echo "1) fill feishu.app_id / feishu.app_secret"
echo "2) run:"
echo "   python3 \"$SCRIPT_DIR/init_feishu_bitable.py\" --config \"$OUT_FILE\""
echo "   python3 \"$SCRIPT_DIR/sync_payload_to_feishu.py\" --config \"$OUT_FILE\""
