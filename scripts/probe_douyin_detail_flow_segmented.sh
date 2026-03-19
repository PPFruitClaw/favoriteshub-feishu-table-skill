#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$SKILL_ROOT/output/segmented-probe"
SEGMENTS="${1:-6}"
STEPS_PER_SEGMENT="${2:-20}"

mkdir -p "$OUT_DIR"

if ! [[ "$SEGMENTS" =~ ^[0-9]+$ ]] || [ "$SEGMENTS" -le 0 ]; then
  echo "invalid SEGMENTS: $SEGMENTS" >&2
  exit 1
fi
if ! [[ "$STEPS_PER_SEGMENT" =~ ^[0-9]+$ ]] || [ "$STEPS_PER_SEGMENT" -le 0 ]; then
  echo "invalid STEPS_PER_SEGMENT: $STEPS_PER_SEGMENT" >&2
  exit 1
fi

LAST_OUT=""
for ((i=1; i<=SEGMENTS; i++)); do
  OUT_FILE="$OUT_DIR/segment-$(printf '%02d' "$i").json"
  echo "[segment $i/$SEGMENTS] running $STEPS_PER_SEGMENT steps -> $OUT_FILE"
  node "$SCRIPT_DIR/probe_douyin_detail_flow.js" "$OUT_FILE" "$STEPS_PER_SEGMENT"
  LAST_OUT="$OUT_FILE"
  if python3 - "$OUT_FILE" <<'PY'
import json, sys
p=sys.argv[1]
with open(p,'r',encoding='utf-8') as f:
    data=json.load(f)
steps=data.get('steps',[])
stop=False
for s in steps[1:]:
    if s.get('stop_reason'):
        stop=True
        break
print('STOP' if stop else 'CONTINUE')
sys.exit(0 if stop else 1)
PY
  then
    echo "stop condition found in $OUT_FILE"
    break
  fi
  sleep 2
done

echo "last_out=$LAST_OUT"
