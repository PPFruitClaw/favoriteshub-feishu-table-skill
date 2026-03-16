#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

LIMIT="${1:-0}"
OUT_FILE="${2:-$SKILL_ROOT/output/xhs-favorites.json}"
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

BOUNDARY_JSON="$(jq -c '.xiaohongshu.head_links // [] | if type == "array" then . else [] end' "$STATE_FILE" 2>/dev/null || echo '[]')"
if [ "$(echo "$BOUNDARY_JSON" | jq 'length')" -gt 0 ]; then
  MODE="incremental"
  FIRST_RUN=false
else
  MODE="full_scan"
  FIRST_RUN=true
fi

oc_open() {
  local url="$1"
  local try json tid
  for try in 1 2 3; do
    json="$(openclaw browser open "$url" --json 2>/dev/null || true)"
    tid="$(echo "$json" | jq -r '.targetId // empty')"
    if [ -n "$tid" ]; then
      echo "$json"
      return 0
    fi
    sleep 1
  done
  return 1
}

oc_wait() {
  local tid="$1"
  local try
  for try in 1 2 3; do
    if openclaw browser wait --target-id "$tid" --load domcontentloaded --timeout-ms 45000 --json >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

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
OPEN_JSON="$(oc_open 'https://www.xiaohongshu.com/explore')"
TARGET_ID="$(echo "$OPEN_JSON" | jq -r '.targetId')"
oc_wait "$TARGET_ID"

LOGIN_JS='() => {
  const profileHref = document.querySelector(".main-container .user .link-wrapper a.link-wrapper")?.getAttribute("href") || "";
  const pageText = document.body?.innerText || "";
  const loginSignals = [/扫码登录/, /手机号登录/, /验证码登录/, /登录后/];
  const needsLogin = !profileHref || loginSignals.some((r) => r.test(pageText));
  return {
    page_url: location.href,
    title: document.title || "",
    needs_login: needsLogin,
    profile_href: profileHref
  };
}'

LOGIN_JSON="$(oc_eval "$TARGET_ID" "$LOGIN_JS")"

NEEDS_LOGIN="$(echo "$LOGIN_JSON" | jq -r '.result.needs_login')"
PROFILE_HREF="$(echo "$LOGIN_JSON" | jq -r '.result.profile_href // ""')"

if [ "$NEEDS_LOGIN" = "true" ] || [ -z "$PROFILE_HREF" ]; then
  NOW_ISO="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "$LOGIN_JSON" | jq --arg now "$NOW_ISO" --arg mode "$MODE" '{
    source: "xiaohongshu",
    fetched_at: $now,
    mode: $mode,
    page: .result.page_url,
    status: "needs_login",
    message: "please login in current openclaw browser window",
    records: []
  }' > "$OUT_FILE"
  echo "saved: $OUT_FILE"
  exit 0
fi

if [[ "$PROFILE_HREF" =~ ^https?:// ]]; then
  PROFILE_URL="$PROFILE_HREF"
else
  PROFILE_URL="https://www.xiaohongshu.com${PROFILE_HREF}"
fi

PROFILE_OPEN="$(oc_open "$PROFILE_URL")"
PROFILE_ID="$(echo "$PROFILE_OPEN" | jq -r '.targetId')"
oc_wait "$PROFILE_ID"

CLICK_TAB_JS='() => {
  const nodes = [...document.querySelectorAll("button,span,a,div")];
  const collectTab = nodes.find((el) => (el.textContent || "").trim() === "收藏");
  if (collectTab) {
    collectTab.click();
    return { clicked: true, message: "collect tab clicked" };
  }
  return { clicked: false, message: "collect tab not found, fallback to current list" };
}'

TAB_JSON="$(oc_eval "$PROFILE_ID" "$CLICK_TAB_JS")"

EXTRACT_JS="$(cat <<'EOF'
() => {
  const parseCompact = (raw) => {
    const text = (raw || '').replace(/,/g, '').trim();
    if (!text) return null;
    const m = text.match(/^([0-9]+(?:\.[0-9]+)?)\s*([kKmMwW万亿]?)$/);
    if (!m) return null;
    const base = Number(m[1]);
    if (!Number.isFinite(base)) return null;
    const unit = (m[2] || '').toLowerCase();
    let factor = 1;
    if (unit === 'k') factor = 1000;
    else if (unit === 'm') factor = 1000000;
    else if (unit === 'w' || unit === '万') factor = 10000;
    else if (unit === '亿') factor = 100000000;
    const out = Math.round(base * factor);
    if (!Number.isFinite(out) || out < 0 || out > 1000000000) return null;
    return out;
  };

  const pickCountFromCard = (card) => {
    const candidateNodes = [
      ...card.querySelectorAll('[class*="like"], [class*="collect"], [class*="count"], [data-count], span')
    ].slice(0, 120);
    for (const node of candidateNodes) {
      const t = (node.textContent || '').replace(/\s+/g, ' ').trim();
      if (!t || t.length > 20) continue;
      const m = t.match(/([0-9]+(?:\.[0-9]+)?\s*[kKmMwW万亿]?)/);
      if (!m) continue;
      const n = parseCompact(m[1]);
      if (n !== null) return n;
    }

    const lines = (card.innerText || '')
      .split('\n')
      .map((x) => x.trim())
      .filter((x) => x && x.length <= 20);
    for (let i = lines.length - 1; i >= 0; i -= 1) {
      const m = lines[i].match(/^([0-9]+(?:\.[0-9]+)?\s*[kKmMwW万亿]?)$/);
      if (!m) continue;
      const n = parseCompact(m[1]);
      if (n !== null) return n;
    }
    return null;
  };

  const normalize = (href) => {
    if (!href) return '';
    try {
      const u = new URL(href, location.origin);
      u.searchParams.delete('xsec_token');
      u.searchParams.delete('xsec_source');
      return u.toString();
    } catch (e) {
      return '';
    }
  };

  const seen = new Set();
  const records = [];
  const anchors = [...document.querySelectorAll('a[href*=\"/explore/\"]')];
  for (const a of anchors) {
    const link = normalize(a.getAttribute('href'));
    if (!link || seen.has(link)) continue;
    seen.add(link);
    const card = a.closest('section,article,div') || a.parentElement || a;
    const summary = (card?.innerText || a.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 300);
    const favoriteOrStarCount = pickCountFromCard(card);
    records.push({ link, summary, favorite_or_star_count: favoriteOrStarCount });
  }

  const pageText = (document.body?.innerText || '').slice(0, 2000);
  return {
    page_url: location.href,
    title: document.title || '',
    requires_login: location.href.includes('/website-login/') || /扫码登录|手机号登录|验证码登录|请先登录|登录后/.test(pageText),
    empty_hint: /暂无收藏|还没有收藏|仅自己可见/.test(pageText),
    count: records.length,
    records
  };
}
EOF
)"

SCROLL_JS='() => {
  window.scrollBy(0, Math.floor(window.innerHeight * 0.9));
  return true;
}'

ACC_ITEMS='[]'
HEAD_CANDIDATES='[]'
BOUNDARY_HIT=false
NO_GROWTH=0
PREV_COUNT=0
LAST_EXTRACT='{}'
CAPTCHA_LOGIN=false

ROUND=1
while [ "$ROUND" -le "$MAX_SCROLL_ROUNDS" ]; do
  EXTRACT_JSON="$(oc_eval "$PROFILE_ID" "$EXTRACT_JS")"
  LAST_EXTRACT="$EXTRACT_JSON"
  ROUND_ITEMS="$(echo "$EXTRACT_JSON" | jq -c '.result.records // []')"
  ROUND_NEEDS_LOGIN="$(echo "$EXTRACT_JSON" | jq -r '.result.requires_login // false')"

  if [ "$ROUND" -eq 1 ]; then
    HEAD_CANDIDATES="$(echo "$ROUND_ITEMS" | jq -c '
      reduce .[] as $it ({seen: {}, out: []};
        ($it.link // "") as $u
        | if ($u | length) == 0 or .seen[$u] then .
          else .seen[$u] = true | .out += [$u]
          end
      ) | .out[:10]
    ')"
  fi

  if [ "$ROUND_NEEDS_LOGIN" = "true" ]; then
    CAPTCHA_LOGIN=true
    break
  fi

  ACC_ITEMS="$(jq -c -n --argjson acc "$ACC_ITEMS" --argjson cur "$ROUND_ITEMS" '
    ($acc + $cur)
    | reduce .[] as $it ({seen: {}, out: []};
        ($it.link // "") as $u
        | if ($u | length) == 0 or .seen[$u] then .
          else .seen[$u] = true | .out += [$it]
          end
      )
    | .out
  ')"

  if [ "$FIRST_RUN" = false ] && [ "$BOUNDARY_HIT" = false ]; then
    if echo "$ROUND_ITEMS" | jq -e --argjson boundary "$BOUNDARY_JSON" 'any(.[]?; (($boundary | index(.link // "")) != null))' >/dev/null 2>&1; then
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

  oc_eval "$PROFILE_ID" "$SCROLL_JS" >/dev/null
  sleep 1
  ROUND=$((ROUND + 1))
done

NOW_ISO="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
if [ "$CAPTCHA_LOGIN" = "true" ]; then
  echo "$LAST_EXTRACT" | jq --arg now "$NOW_ISO" --arg mode "$MODE" --arg tabmsg "$(echo "$TAB_JSON" | jq -r '.result.message // ""')" '{
    source: "xiaohongshu",
    fetched_at: $now,
    mode: $mode,
    page: .result.page_url,
    status: "needs_login",
    message: "login required or captcha verification needed in current openclaw browser window",
    tab_message: $tabmsg,
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
      elif (($boundary | index($it.link // "")) != null) then .stop = true
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

echo "$LAST_EXTRACT" | jq \
  --arg now "$NOW_ISO" \
  --arg mode "$MODE" \
  --argjson records "$FILTERED_ITEMS" \
  --arg tabmsg "$(echo "$TAB_JSON" | jq -r '.result.message // ""')" '{
  source: "xiaohongshu",
  fetched_at: $now,
  mode: $mode,
  page: .result.page_url,
  status: (
    if .result.requires_login then "needs_login"
    elif (($records | length) > 0) then "ok"
    elif .result.empty_hint then "empty"
    else "no_records"
    end
  ),
  message: (
    if .result.requires_login then "login required or captcha verification needed in current openclaw browser window"
    else $tabmsg
    end
  ),
  records: [
    $records[]? | {
      platform: "xiaohongshu",
      title: ((.summary // "") | gsub("\\s+"; " ") | .[0:40]),
      link: .link,
      summary: (.summary // ""),
      favorite_or_star_count: (.favorite_or_star_count // null),
      ingested_at: $now
    }
  ]
}' > "$OUT_FILE"

FILTERED_COUNT="$(echo "$FILTERED_ITEMS" | jq 'length')"
if [ "$FIRST_RUN" = true ] || [ "$FILTERED_COUNT" -gt 0 ]; then
  NEW_HEADS="$HEAD_CANDIDATES"
  if [ "$(echo "$NEW_HEADS" | jq 'length')" -eq 0 ]; then
    NEW_HEADS="$(echo "$FILTERED_ITEMS" | jq -c '[.[].link] | map(select(. != null and . != "")) | .[:10]')"
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
  '.xiaohongshu = ((.xiaohongshu // {}) + {
    head_links: $heads,
    updated_at: $now,
    mode: $mode,
    boundary_hit: $boundary_hit
  })' "$STATE_FILE" > "$TMP_STATE"
mv "$TMP_STATE" "$STATE_FILE"

echo "saved: $OUT_FILE"
