#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

LIMIT="${1:-0}"
OUT_FILE="${2:-$SKILL_ROOT/output/douyin-favorites-probe.json}"
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

mkdir -p "$(dirname "$OUT_FILE")"
mkdir -p "$(dirname "$STATE_FILE")"
[ -f "$STATE_FILE" ] || printf '{}' > "$STATE_FILE"

command -v openclaw >/dev/null 2>&1 || { echo "missing dependency: openclaw" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "missing dependency: jq" >&2; exit 1; }

BOUNDARY_JSON="$(jq -c '.douyin.head_links // [] | if type == "array" then . else [] end' "$STATE_FILE" 2>/dev/null || echo '[]')"
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
OPEN_JSON="$(openclaw browser open 'https://www.douyin.com/user/self?showTab=collection' --json)"
TARGET_ID="$(echo "$OPEN_JSON" | jq -r '.targetId')"

openclaw browser wait --target-id "$TARGET_ID" --load domcontentloaded --timeout-ms 45000 --json >/dev/null

EXTRACT_JS="$(cat <<'EOF'
() => {
  const text = document.body?.innerText || '';
  const loginSignals = [
    /登录后即可观看喜欢、收藏的视频/,
    /未登录/,
    /扫码登录/,
    /验证码登录/,
    /密码登录/,
    /获取验证码/
  ];
  const needsLogin = loginSignals.some((r) => r.test(text));

  const links = [...document.querySelectorAll('a[href*=\"/video/\"]')]
    .map((a) => {
      const u = new URL(a.getAttribute('href'), location.origin);
      u.search = '';
      return u.toString();
    })
    .filter((v, i, arr) => v && arr.indexOf(v) === i);

  return {
    page_url: location.href,
    title: document.title || '',
    needs_login: needsLogin,
    links: (needsLogin ? [] : links)
  };
}
EOF
)"

SCROLL_JS='() => {
  window.scrollBy(0, Math.floor(window.innerHeight * 0.95));
  return true;
}'

ACC_LINKS='[]'
HEAD_CANDIDATES='[]'
BOUNDARY_HIT=false
NO_GROWTH=0
PREV_COUNT=0
LAST_EVAL='{}'
NEEDS_LOGIN=false

ROUND=1
while [ "$ROUND" -le "$MAX_SCROLL_ROUNDS" ]; do
  EVAL_JSON="$(oc_eval "$TARGET_ID" "$EXTRACT_JS")"
  LAST_EVAL="$EVAL_JSON"
  NEEDS_LOGIN="$(echo "$EVAL_JSON" | jq -r '.result.needs_login // false')"
  ROUND_LINKS="$(echo "$EVAL_JSON" | jq -c '.result.links // []')"

  if [ "$ROUND" -eq 1 ]; then
    HEAD_CANDIDATES="$(echo "$ROUND_LINKS" | jq -c '
      reduce .[] as $u ({seen: {}, out: []};
        if ($u | length) == 0 or .seen[$u] then .
        else .seen[$u] = true | .out += [$u]
        end
      ) | .out[:10]
    ')"
    if [ "$NEEDS_LOGIN" = "true" ]; then
      break
    fi
  fi

  ACC_LINKS="$(jq -c -n --argjson acc "$ACC_LINKS" --argjson cur "$ROUND_LINKS" '
    ($acc + $cur)
    | reduce .[] as $u ({seen: {}, out: []};
        if ($u | length) == 0 or .seen[$u] then .
        else .seen[$u] = true | .out += [$u]
        end
      )
    | .out
  ')"

  if [ "$FIRST_RUN" = false ] && [ "$BOUNDARY_HIT" = false ]; then
    if echo "$ROUND_LINKS" | jq -e --argjson boundary "$BOUNDARY_JSON" 'any(.[]?; (($boundary | index(.)) != null))' >/dev/null 2>&1; then
      BOUNDARY_HIT=true
    fi
  fi

  CUR_COUNT="$(echo "$ACC_LINKS" | jq 'length')"
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

if [ "$FIRST_RUN" = false ]; then
  FILTERED_LINKS="$(echo "$ACC_LINKS" | jq -c --argjson boundary "$BOUNDARY_JSON" '
    reduce .[] as $u (
      {stop: false, out: []};
      if .stop then .
      elif (($boundary | index($u)) != null) then .stop = true
      else .out += [$u]
      end
    ) | .out
  ')"
else
  FILTERED_LINKS="$ACC_LINKS"
fi

if [ "$LIMIT" -gt 0 ]; then
  FILTERED_LINKS="$(echo "$FILTERED_LINKS" | jq -c --argjson lim "$LIMIT" '.[0:$lim]')"
fi

NOW_ISO="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "$LAST_EVAL" | jq --arg now "$NOW_ISO" --arg mode "$MODE" --argjson links "$FILTERED_LINKS" '{
  source: "douyin",
  fetched_at: $now,
  mode: $mode,
  page: .result.page_url,
  status: (if .result.needs_login then "needs_login" elif (($links | length) > 0) then "ok" else "no_records" end),
  records: [
    $links[]? | {
      platform: "douyin",
      link: .,
      summary: "",
      favorite_or_star_count: null,
      ingested_at: $now
    }
  ]
}' > "$OUT_FILE"

if [ "$NEEDS_LOGIN" = "false" ]; then
  FILTERED_COUNT="$(echo "$FILTERED_LINKS" | jq 'length')"
  if [ "$FIRST_RUN" = true ] || [ "$FILTERED_COUNT" -gt 0 ]; then
    NEW_HEADS="$HEAD_CANDIDATES"
    if [ "$(echo "$NEW_HEADS" | jq 'length')" -eq 0 ]; then
      NEW_HEADS="$(echo "$FILTERED_LINKS" | jq -c 'map(select(. != null and . != "")) | .[:10]')"
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
    '.douyin = ((.douyin // {}) + {
      head_links: $heads,
      updated_at: $now,
      mode: $mode,
      boundary_hit: $boundary_hit
    })' "$STATE_FILE" > "$TMP_STATE"
  mv "$TMP_STATE" "$STATE_FILE"
fi

echo "saved: $OUT_FILE"
