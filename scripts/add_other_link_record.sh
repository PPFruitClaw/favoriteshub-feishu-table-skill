#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

URL="${1:-}"
SUMMARY="${2:-}"
OUT_FILE="${3:-$SKILL_ROOT/output/other-links.json}"

if [ -z "$URL" ]; then
  echo "usage: $0 <url> [summary] [out_file]" >&2
  exit 1
fi

if ! [[ "$URL" =~ ^https?:// ]]; then
  echo "invalid url: $URL" >&2
  exit 1
fi

command -v jq >/dev/null 2>&1 || { echo "missing dependency: jq" >&2; exit 1; }

mkdir -p "$(dirname "$OUT_FILE")"

if [ -f "$OUT_FILE" ]; then
  jq --arg url "$URL" --arg summary "$SUMMARY" '
    .source = "other"
    | .generated_at = (now | todateiso8601)
    | .records = (
        (.records // []) + [{
          platform: "other",
          link: $url,
          summary: $summary,
          favorite_or_star_count: null,
          ingested_at: (now | todateiso8601)
        }]
        | unique_by(.link)
        | sort_by(.link)
      )
  ' "$OUT_FILE" > "${OUT_FILE}.tmp"
  mv "${OUT_FILE}.tmp" "$OUT_FILE"
else
  jq -n --arg url "$URL" --arg summary "$SUMMARY" '{
    source: "other",
    generated_at: (now | todateiso8601),
    records: [{
      platform: "other",
      link: $url,
      summary: $summary,
      favorite_or_star_count: null,
      ingested_at: (now | todateiso8601)
    }]
  }' > "$OUT_FILE"
fi

echo "saved: $OUT_FILE"
