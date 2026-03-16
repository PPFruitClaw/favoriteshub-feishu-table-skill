#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

LIMIT="${1:-0}"
OUT_FILE="${2:-$SKILL_ROOT/output/github-stars.json}"
STATE_FILE="${3:-$SKILL_ROOT/output/collector-state.json}"
PAGE_SIZE="${PAGE_SIZE:-100}"
MAX_PAGES="${MAX_PAGES:-200}"

if ! [[ "$LIMIT" =~ ^[0-9]+$ ]]; then
  echo "invalid limit: $LIMIT" >&2
  exit 1
fi
if ! [[ "$PAGE_SIZE" =~ ^[0-9]+$ ]] || [ "$PAGE_SIZE" -le 0 ]; then
  echo "invalid PAGE_SIZE: $PAGE_SIZE" >&2
  exit 1
fi
if ! [[ "$MAX_PAGES" =~ ^[0-9]+$ ]] || [ "$MAX_PAGES" -le 0 ]; then
  echo "invalid MAX_PAGES: $MAX_PAGES" >&2
  exit 1
fi

command -v gh >/dev/null 2>&1 || { echo "missing dependency: gh" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "missing dependency: jq" >&2; exit 1; }

mkdir -p "$(dirname "$OUT_FILE")"
mkdir -p "$(dirname "$STATE_FILE")"
[ -f "$STATE_FILE" ] || printf '{}' > "$STATE_FILE"

BOUNDARY_JSON="$(jq -c '.github.head_links // [] | if type == "array" then . else [] end' "$STATE_FILE" 2>/dev/null || echo '[]')"
if [ "$(echo "$BOUNDARY_JSON" | jq 'length')" -gt 0 ]; then
  MODE="incremental"
  FIRST_RUN=false
else
  MODE="full_scan"
  FIRST_RUN=true
fi

QUERY=$(cat <<'EOF'
query($limit: Int!, $after: String) {
  viewer {
    login
    starredRepositories(first: $limit, after: $after, orderBy: {field: STARRED_AT, direction: DESC}) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        nameWithOwner
        url
        stargazerCount
        description
      }
    }
  }
}
EOF
)

RESULT_NODES='[]'
HEAD_CANDIDATES='[]'
BOUNDARY_HIT=false
CURSOR=""
PAGE=0

while true; do
  PAGE=$((PAGE + 1))
  if [ -n "$CURSOR" ]; then
    RAW_JSON="$(gh api graphql -f query="$QUERY" -F limit="$PAGE_SIZE" -F after="$CURSOR")"
  else
    RAW_JSON="$(gh api graphql -f query="$QUERY" -F limit="$PAGE_SIZE")"
  fi

  PAGE_NODES="$(echo "$RAW_JSON" | jq -c '.data.viewer.starredRepositories.nodes // []')"
  if [ "$PAGE" -eq 1 ]; then
    HEAD_CANDIDATES="$(echo "$PAGE_NODES" | jq -c '[.[].url] | map(select(. != null and . != "")) | .[:10]')"
  fi

  if [ "$FIRST_RUN" = false ]; then
    PAGE_RESULT="$(echo "$PAGE_NODES" | jq -c --argjson boundary "$BOUNDARY_JSON" '
      reduce .[] as $n (
        {items: [], hit: false};
        if .hit then .
        elif (($boundary | index($n.url)) != null) then .hit = true
        else .items += [$n]
        end
      )
    ')"
    PAGE_ITEMS="$(echo "$PAGE_RESULT" | jq -c '.items')"
    if [ "$(echo "$PAGE_RESULT" | jq -r '.hit')" = "true" ]; then
      BOUNDARY_HIT=true
    fi
  else
    PAGE_ITEMS="$PAGE_NODES"
  fi

  RESULT_NODES="$(jq -c -n --argjson a "$RESULT_NODES" --argjson b "$PAGE_ITEMS" '$a + $b')"

  if [ "$LIMIT" -gt 0 ] && [ "$(echo "$RESULT_NODES" | jq 'length')" -ge "$LIMIT" ]; then
    RESULT_NODES="$(echo "$RESULT_NODES" | jq -c --argjson lim "$LIMIT" '.[0:$lim]')"
    break
  fi

  if [ "$BOUNDARY_HIT" = true ]; then
    break
  fi

  HAS_NEXT="$(echo "$RAW_JSON" | jq -r '.data.viewer.starredRepositories.pageInfo.hasNextPage // false')"
  CURSOR="$(echo "$RAW_JSON" | jq -r '.data.viewer.starredRepositories.pageInfo.endCursor // empty')"
  if [ "$HAS_NEXT" != "true" ] || [ -z "$CURSOR" ] || [ "$PAGE" -ge "$MAX_PAGES" ]; then
    break
  fi
done

NOW_ISO="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

echo "$RESULT_NODES" | jq --arg now "$NOW_ISO" --arg mode "$MODE" '{
  source: "github",
  fetched_at: $now,
  mode: $mode,
  records: [
    .[]? | {
      platform: "github",
      link: .url,
      summary: ((.nameWithOwner // "") + " " + (.description // "")) | gsub("\\s+"; " ") | .[0:300],
      favorite_or_star_count: (.stargazerCount // null),
      ingested_at: $now
    }
  ]
}' > "$OUT_FILE"

RESULT_COUNT="$(echo "$RESULT_NODES" | jq 'length')"
if [ "$FIRST_RUN" = true ] || [ "$RESULT_COUNT" -gt 0 ]; then
  NEW_HEADS="$HEAD_CANDIDATES"
  if [ "$(echo "$NEW_HEADS" | jq 'length')" -eq 0 ]; then
    NEW_HEADS="$(echo "$RESULT_NODES" | jq -c '[.[].url] | map(select(. != null and . != "")) | .[:10]')"
  fi
  if [ "$(echo "$NEW_HEADS" | jq 'length')" -eq 0 ]; then
    NEW_HEADS="$BOUNDARY_JSON"
  fi
else
  NEW_HEADS="$BOUNDARY_JSON"
fi

TMP_STATE="$(mktemp)"
jq \
  --argjson heads "$NEW_HEADS" \
  --arg now "$NOW_ISO" \
  --arg mode "$MODE" \
  --argjson boundary_hit "$BOUNDARY_HIT" \
  '.github = ((.github // {}) + {
    head_links: $heads,
    updated_at: $now,
    mode: $mode,
    boundary_hit: $boundary_hit
  })' "$STATE_FILE" > "$TMP_STATE"
mv "$TMP_STATE" "$STATE_FILE"

echo "saved: $OUT_FILE"
