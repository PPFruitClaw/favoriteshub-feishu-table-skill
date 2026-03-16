#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="$SKILL_ROOT/output"

OUT_FILE="${1:-$OUTPUT_DIR/feishu-payload.json}"
shift || true

command -v jq >/dev/null 2>&1 || { echo "missing dependency: jq" >&2; exit 1; }

if [ "$#" -eq 0 ]; then
  INPUTS=(
    "$OUTPUT_DIR/github-stars.json"
    "$OUTPUT_DIR/x-bookmarks.json"
    "$OUTPUT_DIR/xhs-favorites.json"
    "$OUTPUT_DIR/xhs-favorites-probe.json"
    "$OUTPUT_DIR/douyin-favorites-probe.json"
    "$OUTPUT_DIR/other-links.json"
  )
else
  INPUTS=("$@")
fi

mkdir -p "$(dirname "$OUT_FILE")"

TMP_FILE="$(mktemp)"
printf '[]' > "$TMP_FILE"

for f in "${INPUTS[@]}"; do
  if [ -f "$f" ]; then
    jq -s '.[0] + ((.[1].records // []) | map({
      "所属平台": .platform,
      "链接": .link,
      "内容梗概": (.summary // ""),
      "收藏或星标数量": .favorite_or_star_count,
      "收录时间": .ingested_at
    }))' "$TMP_FILE" "$f" > "${TMP_FILE}.next"
    mv "${TMP_FILE}.next" "$TMP_FILE"
  fi
done

jq 'unique_by((."所属平台" // "") + "|" + (."链接" // "")) | {
  generated_at: (now | todateiso8601),
  total: (length),
  records: (sort_by(."所属平台", ."链接"))
}' "$TMP_FILE" > "$OUT_FILE"

rm -f "$TMP_FILE"
echo "saved: $OUT_FILE"
