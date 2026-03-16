#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

URL="${1:-}"
SUMMARY="${2:-}"
OUT_FILE="${3:-$SKILL_ROOT/output/other-links.json}"
TITLE="${4:-}"

if [ -z "$URL" ]; then
  echo "usage: $0 <url> [summary] [out_file] [title]" >&2
  exit 1
fi

if ! [[ "$URL" =~ ^https?:// ]]; then
  echo "invalid url: $URL" >&2
  exit 1
fi

command -v jq >/dev/null 2>&1 || { echo "missing dependency: jq" >&2; exit 1; }

mkdir -p "$(dirname "$OUT_FILE")"

if [ -z "$SUMMARY" ] && command -v openclaw >/dev/null 2>&1; then
  openclaw browser start --json >/dev/null 2>&1 || true
  OPEN_JSON="$(openclaw browser open "$URL" --json 2>/dev/null || true)"
  TARGET_ID="$(echo "$OPEN_JSON" | jq -r '.targetId // empty')"
  if [ -n "$TARGET_ID" ]; then
    openclaw browser wait --target-id "$TARGET_ID" --load domcontentloaded --timeout-ms 30000 --json >/dev/null 2>&1 || true
    READ_JS="$(cat <<'EOF'
() => {
  const clean = (v) => (v || "").replace(/\s+/g, " ").trim();
  const title = clean(document.title || "");
  const metaDesc = clean(document.querySelector('meta[name="description"]')?.getAttribute("content") || "");
  const p = [...document.querySelectorAll("main p, article p, p")]
    .map((el) => clean(el.innerText || ""))
    .filter((x) => x.length >= 12)
    .slice(0, 3)
    .join(" ");
  const body = clean(document.body?.innerText || "");
  const summary = (metaDesc || p || body).slice(0, 400);
  return { title, summary };
}
EOF
)"
    READ_JSON="$(openclaw browser evaluate --target-id "$TARGET_ID" --fn "$READ_JS" --json 2>/dev/null || true)"
    AUTO_TITLE="$(echo "$READ_JSON" | jq -r '.result.title // ""' 2>/dev/null || true)"
    AUTO_SUMMARY="$(echo "$READ_JSON" | jq -r '.result.summary // ""' 2>/dev/null || true)"
    if [ -z "$TITLE" ] && [ -n "$AUTO_TITLE" ]; then
      TITLE="$AUTO_TITLE"
    fi
    if [ -z "$SUMMARY" ] && [ -n "$AUTO_SUMMARY" ]; then
      SUMMARY="$AUTO_SUMMARY"
    fi
  fi
fi

if [ -z "$TITLE" ]; then
  TITLE="$(echo "$SUMMARY" | sed 's/[[:space:]]\+/ /g' | cut -c1-40)"
fi
if [ -z "$TITLE" ]; then
  TITLE="其他链接收藏"
fi

if [ -f "$OUT_FILE" ]; then
  jq --arg url "$URL" --arg summary "$SUMMARY" --arg title "$TITLE" '
    .source = "other"
    | .generated_at = (now | todateiso8601)
    | .records = (
        (.records // []) + [{
          platform: "other",
          title: $title,
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
  jq -n --arg url "$URL" --arg summary "$SUMMARY" --arg title "$TITLE" '{
    source: "other",
    generated_at: (now | todateiso8601),
    records: [{
      platform: "other",
      title: $title,
      link: $url,
      summary: $summary,
      favorite_or_star_count: null,
      ingested_at: (now | todateiso8601)
    }]
  }' > "$OUT_FILE"
fi

echo "saved: $OUT_FILE"
