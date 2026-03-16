#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

LIMIT="${1:-0}"
OUT_FILE="${2:-$SKILL_ROOT/output/x-bookmarks.json}"
STATE_FILE="${3:-$SKILL_ROOT/output/collector-state.json}"
MAX_SCROLL_ROUNDS="${MAX_SCROLL_ROUNDS:-120}"
NO_GROWTH_THRESHOLD="${NO_GROWTH_THRESHOLD:-3}"

if ! [[ "$LIMIT" =~ ^[0-9]+$ ]]; then
  echo "invalid limit: $LIMIT" >&2
  exit 1
fi
if ! [[ "$MAX_SCROLL_ROUNDS" =~ ^[0-9]+$ ]] || [ "$MAX_SCROLL_ROUNDS" -le 0 ]; then
  echo "invalid MAX_SCROLL_ROUNDS: $MAX_SCROLL_ROUNDS" >&2
  exit 1
fi
if ! [[ "$NO_GROWTH_THRESHOLD" =~ ^[0-9]+$ ]] || [ "$NO_GROWTH_THRESHOLD" -le 0 ]; then
  echo "invalid NO_GROWTH_THRESHOLD: $NO_GROWTH_THRESHOLD" >&2
  exit 1
fi

command -v openclaw >/dev/null 2>&1 || { echo "missing dependency: openclaw" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "missing dependency: jq" >&2; exit 1; }

mkdir -p "$(dirname "$OUT_FILE")"
mkdir -p "$(dirname "$STATE_FILE")"
[ -f "$STATE_FILE" ] || printf '{}' > "$STATE_FILE"

BOUNDARY_JSON="$(jq -c '.x.head_links // [] | if type == "array" then . else [] end' "$STATE_FILE" 2>/dev/null || echo '[]')"
if [ "$(echo "$BOUNDARY_JSON" | jq 'length')" -gt 0 ]; then
  MODE="incremental"
  FIRST_RUN=false
else
  MODE="full_scan"
  FIRST_RUN=true
fi

oc_eval() {
  local tid="$1"
  local fn="$2"
  local try out
  for try in 1 2 3; do
    out="$(openclaw browser evaluate --target-id "$tid" --fn "$fn" --json 2>/dev/null || true)"
    if [ -n "$out" ] && echo "$out" | jq -e '.result != null' >/dev/null 2>&1; then
      echo "$out"
      return 0
    fi
    sleep 1
  done
  return 1
}

openclaw browser start --json >/dev/null
OPEN_JSON="$(openclaw browser open https://x.com/i/bookmarks --json)"
TARGET_ID="$(echo "$OPEN_JSON" | jq -r '.targetId')"

openclaw browser wait --target-id "$TARGET_ID" --load domcontentloaded --timeout-ms 45000 --json >/dev/null

EXTRACT_JS="() => {
  const cards = [...document.querySelectorAll('article[data-testid=\"tweet\"]')];
  const items = cards.map((card) => {
    const linkEl = card.querySelector('a[href*=\"/status/\"]');
    const textEl = card.querySelector('[data-testid=\"tweetText\"]');
    const url = linkEl ? new URL(linkEl.getAttribute('href'), location.origin).toString() : null;
    const text = (textEl?.innerText || card.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 400);
    return { url, text };
  }).filter((x) => x.url);
  const pageText = (document.body?.innerText || '').slice(0, 2000);
  const requiresLogin = /log in|sign in|登录/i.test(pageText) && items.length === 0;
  return {
    page_url: location.href,
    title: document.title,
    requires_login: requiresLogin,
    count: items.length,
    items
  };
}"

SCROLL_JS='() => {
  window.scrollBy(0, Math.floor(window.innerHeight * 0.95));
  return true;
}'

ACC_ITEMS='[]'
HEAD_CANDIDATES='[]'
BOUNDARY_HIT=false
NO_GROWTH=0
PREV_COUNT=0
REQUIRES_LOGIN=false
PAGE_URL=""

ROUND=1
while [ "$ROUND" -le "$MAX_SCROLL_ROUNDS" ]; do
  EVAL_JSON="$(oc_eval "$TARGET_ID" "$EXTRACT_JS")"
  PAGE_URL="$(echo "$EVAL_JSON" | jq -r '.result.page_url // ""')"
  REQUIRES_LOGIN="$(echo "$EVAL_JSON" | jq -r '.result.requires_login // false')"
  ROUND_ITEMS="$(echo "$EVAL_JSON" | jq -c '.result.items // []')"

  if [ "$ROUND" -eq 1 ]; then
    HEAD_CANDIDATES="$(echo "$ROUND_ITEMS" | jq -c '
      reduce .[] as $it ({seen: {}, out: []};
        ($it.url // "") as $u
        | if ($u | length) == 0 or .seen[$u] then .
          else .seen[$u] = true | .out += [$u]
          end
      ) | .out[:10]
    ')"
    if [ "$REQUIRES_LOGIN" = "true" ]; then
      break
    fi
  fi

  ACC_ITEMS="$(jq -c -n --argjson acc "$ACC_ITEMS" --argjson cur "$ROUND_ITEMS" '
    ($acc + $cur)
    | reduce .[] as $it ({seen: {}, out: []};
        ($it.url // "") as $u
        | if ($u | length) == 0 or .seen[$u] then .
          else .seen[$u] = true | .out += [$it]
          end
      )
    | .out
  ')"

  if [ "$FIRST_RUN" = false ] && [ "$BOUNDARY_HIT" = false ]; then
    if echo "$ROUND_ITEMS" | jq -e --argjson boundary "$BOUNDARY_JSON" 'any(.[]?; (($boundary | index(.url // "")) != null))' >/dev/null 2>&1; then
      BOUNDARY_HIT=true
    fi
  fi

  CUR_COUNT="$(echo "$ACC_ITEMS" | jq 'length')"
  if [ "$CUR_COUNT" -eq "$PREV_COUNT" ]; then
    NO_GROWTH=$((NO_GROWTH + 1))
  else
    NO_GROWTH=0
  fi
  PREV_COUNT="$CUR_COUNT"

  if [ "$LIMIT" -gt 0 ] && [ "$CUR_COUNT" -ge "$LIMIT" ]; then
    break
  fi
  if [ "$FIRST_RUN" = false ] && [ "$BOUNDARY_HIT" = true ]; then
    break
  fi
  if [ "$NO_GROWTH" -ge "$NO_GROWTH_THRESHOLD" ]; then
    break
  fi

  oc_eval "$TARGET_ID" "$SCROLL_JS" >/dev/null
  sleep 1
  ROUND=$((ROUND + 1))
done

if [ "$REQUIRES_LOGIN" = "true" ]; then
  NOW_ISO="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  jq -n --arg now "$NOW_ISO" --arg page "$PAGE_URL" '{
    source: "x",
    fetched_at: $now,
    page: $page,
    mode: "incremental",
    requires_login: true,
    records: []
  }' > "$OUT_FILE"
  echo "saved: $OUT_FILE"
  exit 0
fi

if [ "$FIRST_RUN" = false ]; then
  FILTERED_ITEMS="$(echo "$ACC_ITEMS" | jq -c --argjson boundary "$BOUNDARY_JSON" '
    reduce .[] as $it (
      {stop: false, out: []};
      if .stop then .
      elif (($boundary | index($it.url // "")) != null) then .stop = true
      else .out += [$it]
      end
    ) | .out
  ')"
else
  FILTERED_ITEMS="$ACC_ITEMS"
fi

if [ "$LIMIT" -gt 0 ]; then
  FILTERED_ITEMS="$(echo "$FILTERED_ITEMS" | jq -c --argjson lim "$LIMIT" '.[0:$lim]')"
fi

NOW_ISO="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

echo "$FILTERED_ITEMS" | jq --arg now "$NOW_ISO" --arg page "$PAGE_URL" --arg mode "$MODE" '{
  source: "x",
  fetched_at: $now,
  page: $page,
  mode: $mode,
  requires_login: false,
  records: [
    .[]? | {
      platform: "x",
      link: .url,
      summary: (.text // ""),
      favorite_or_star_count: null,
      ingested_at: $now
    }
  ]
}' > "$OUT_FILE"

FILTERED_COUNT="$(echo "$FILTERED_ITEMS" | jq 'length')"
if [ "$FIRST_RUN" = true ] || [ "$FILTERED_COUNT" -gt 0 ]; then
  NEW_HEADS="$HEAD_CANDIDATES"
  if [ "$(echo "$NEW_HEADS" | jq 'length')" -eq 0 ]; then
    NEW_HEADS="$(echo "$FILTERED_ITEMS" | jq -c '[.[].url] | map(select(. != null and . != "")) | .[:10]')"
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
  '.x = ((.x // {}) + {
    head_links: $heads,
    updated_at: $now,
    mode: $mode,
    boundary_hit: $boundary_hit
  })' "$STATE_FILE" > "$TMP_STATE"
mv "$TMP_STATE" "$STATE_FILE"

echo "saved: $OUT_FILE"
