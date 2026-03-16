#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="$SKILL_ROOT/output"

TARGET_FILE="${1:-$OUTPUT_DIR/feishu-target.json}"
PAYLOAD_FILE="${2:-$OUTPUT_DIR/feishu-payload.json}"
CONFIG_FILE="${3:-${FAVORITESHUB_CONFIG:-}}"
STATE_FILE="${4:-$OUTPUT_DIR/feishu-sync-state.json}"
WRITE_MODE="${WRITE_MODE:-create-only}"

mkdir -p "$OUTPUT_DIR"

chmod +x "$SCRIPT_DIR"/*.sh

if [ ! -f "$TARGET_FILE" ]; then
  echo "target file not found, running init ..."
  if [ -n "$CONFIG_FILE" ]; then
    python3 "$SCRIPT_DIR/init_feishu_bitable.py" --config "$CONFIG_FILE" --out "$TARGET_FILE"
  else
    python3 "$SCRIPT_DIR/init_feishu_bitable.py" --out "$TARGET_FILE"
  fi
fi

echo "collecting payload ..."
"$SCRIPT_DIR/run_phase2_probes.sh"

echo "syncing to feishu ..."
if [ -n "$CONFIG_FILE" ]; then
  python3 "$SCRIPT_DIR/sync_payload_to_feishu.py" --config "$CONFIG_FILE" --target "$TARGET_FILE" --payload "$PAYLOAD_FILE" --state "$STATE_FILE" --write-mode "$WRITE_MODE"
else
  python3 "$SCRIPT_DIR/sync_payload_to_feishu.py" --target "$TARGET_FILE" --payload "$PAYLOAD_FILE" --state "$STATE_FILE" --write-mode "$WRITE_MODE"
fi
