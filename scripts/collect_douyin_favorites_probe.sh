#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

LIMIT="${1:-0}"
OUT_FILE="${2:-$SKILL_ROOT/output/douyin-favorites-probe.json}"
STATE_FILE="${3:-$SKILL_ROOT/output/collector-state.json}"
# 兼容旧脚本名，但当前业务方案已不是“列表页滚动抓全量”，而是：
# 收藏 -> 视频 -> 点击首条进入详情流 -> ArrowDown 逐条切换。
# 这里保留旧脚本仅用于过渡排障；后续正式实现应优先按详情流模型重构。
MAX_SCROLL_ROUNDS="${MAX_SCROLL_ROUNDS:-120}"
NO_GROWTH_THRESHOLD="${NO_GROWTH_THRESHOLD:-6}"

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

# 再强调一次：这里的 full_scan / incremental 是“旧 probe 采集脚本自己的术语”，
# 不是抖音当前正式业务方案的权威定义。当前正式方案的主语应当是“详情流中的继续/停止规则”，
# 而不是“列表页是否全量扫描”。

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
sleep 2

# 关键修复：showTab=collection 并不稳定，必须显式点击“收藏”tab，随后再点击内层“视频”tab，确保进入“收藏 -> 视频”总表。
# 但注意：进入这里之后，最新方案要求把“列表页”只当入口，不再把列表页当成主采集面；
# 正式采集应点击第一条进入详情流，在详情流里用 ArrowDown 逐条切换，并以黄色收藏星标是否仍点亮作为越界停止核心信号。
ACTIVATE_COLLECTION_JS="$(cat <<'EOF'
() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const tabs = [...document.querySelectorAll('[role="tab"], [aria-selected], div, span, button')];
  const target = tabs.find(el => clean(el.innerText) === '收藏');
  if (target) {
    target.click();
    return { clicked: true, text: clean(target.innerText) };
  }
  return { clicked: false };
}
EOF
)"
oc_eval "$TARGET_ID" "$ACTIVATE_COLLECTION_JS" >/dev/null || true
sleep 2

ACTIVATE_VIDEO_JS="$(cat <<'EOF'
() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const tabs = [...document.querySelectorAll('[role="tab"], [aria-selected], div, span, button')];
  const target = tabs.find(el => clean(el.innerText) === '视频');
  if (target) {
    target.click();
    return { clicked: true, text: clean(target.innerText) };
  }
  return { clicked: false };
}
EOF
)"
oc_eval "$TARGET_ID" "$ACTIVATE_VIDEO_JS" >/dev/null || true
sleep 2

EXTRACT_JS="$(cat <<'EOF'
() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();

  const parseCompact = (raw) => {
    const text = clean(raw).replace(/,/g, '');
    if (!text) return null;
    const m = text.match(/^([0-9]+(?:\.[0-9]+)?)\s*([kKmMwW万亿wW]?)$/);
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
      ...card.querySelectorAll('[data-e2e*="like"], [data-e2e*="collect"], [class*="like"], [class*="digg"], [class*="collect"], [class*="count"], span')
    ].slice(0, 120);
    for (const node of candidateNodes) {
      const t = clean(node.textContent || '');
      if (!t || t.length > 24) continue;
      const m = t.match(/([0-9]+(?:\.[0-9]+)?\s*[kKmMwW万亿]?)/);
      if (!m) continue;
      const n = parseCompact(m[1]);
      if (n !== null) return n;
    }
    const lines = clean(card.innerText || '').split(' ').filter((x) => x && x.length <= 24);
    for (let i = lines.length - 1; i >= 0; i -= 1) {
      const m = lines[i].match(/^([0-9]+(?:\.[0-9]+)?\s*[kKmMwW万亿]?)$/);
      if (!m) continue;
      const n = parseCompact(m[1]);
      if (n !== null) return n;
    }
    return null;
  };

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

  const tabs = [...document.querySelectorAll('[role="tab"], [aria-selected="true"], div, span, button')];
  const collectionTab = tabs.find((el) => clean(el.innerText) === '收藏');
  const videoTab = tabs.find((el) => clean(el.innerText) === '视频');
  const activeCollection = !!collectionTab && (collectionTab.getAttribute('aria-selected') === 'true' || /active|selected/.test(collectionTab.outerHTML));
  const activeVideo = !!videoTab && (videoTab.getAttribute('aria-selected') === 'true' || /active|selected/.test(videoTab.outerHTML));

  // 过渡说明：这里只是“列表页容器内抓卡片”的旧 probe 思路残留。
  // 它比“全页扫链接”更收敛，但仍不等于当前最新主方案。
  // 最新主方案应在“收藏 -> 视频”里点击首条进入详情流，再用 ArrowDown 逐条切换，
  // 并用“黄色收藏星标是否仍存在且点亮”来判断是否仍在收藏流中。
  // 因此这里产出的 records 只可用于过渡排障，不应再被当作最终稳定采集逻辑。
  const scope = document.querySelector('[data-e2e="user-favorite-list"] [data-e2e="scroll-list"]')
    || document.querySelector('[data-e2e="user-post-list"] [data-e2e="scroll-list"]')
    || document.querySelector('[data-e2e="scroll-list"]');

  const seen = new Set();
  const records = [];
  const anchors = [...(scope ? scope.querySelectorAll('a[href*="/video/"], a[href*="/note/"]') : [])];
  for (const a of anchors) {
    let url = '';
    try {
      const u = new URL(a.getAttribute('href'), location.origin);
      u.search = '';
      url = u.toString();
    } catch (e) {
      url = '';
    }
    if (!url || seen.has(url)) continue;
    const card = a.closest('li, section, article, div') || a.parentElement || a;
    const cardText = clean(card?.innerText || '');
    const rect = card?.getBoundingClientRect ? card.getBoundingClientRect() : {top: 0, bottom: 0};
    // 过滤底部推荐流/热门流：这类内容不是收藏，通常以“热门：抖音精选...”开头，且会在同一块区域挂出多条不同链接
    if (!cardText || /热门：抖音精选/.test(cardText) || /热搜|推荐|抖音精选/.test(cardText.slice(0, 40))) continue;
    seen.add(url);
    const favCount = pickCountFromCard(card || a);
    records.push({
      link: url,
      title: (`抖音内容 ${(url.split('/').pop() || '')}`).trim(),
      summary: cardText.slice(0, 240),
      favorite_or_star_count: favCount,
    });
  }

  return {
    page_url: location.href,
    title: document.title || '',
    needs_login: needsLogin,
    active_collection: activeCollection,
    active_video: activeVideo,
    records: (needsLogin ? [] : records)
  };
}
EOF
)"

SCROLL_JS='() => {
  const list = document.querySelector("[data-e2e=\"user-favorite-list\"] [data-e2e=\"scroll-list\"]")
    || document.querySelector("[data-e2e=\"user-post-list\"] [data-e2e=\"scroll-list\"]")
    || document.querySelector("[data-e2e=\"scroll-list\"]");
  const delta = Math.max(260, Math.floor(window.innerHeight * 0.55));
  if (list) {
    const before = list.scrollTop;
    list.scrollTop = list.scrollTop + delta;
    return {ok: true, mode: 'list', before, top: list.scrollTop, delta};
  }
  const before = window.scrollY;
  window.scrollBy(0, delta);
  return {ok: true, mode: 'window', before, top: window.scrollY, delta};
}'

ACC_ITEMS='[]'
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
  ROUND_ITEMS="$(echo "$EVAL_JSON" | jq -c '.result.records // []')"

  if [ "$ROUND" -eq 1 ]; then
    HEAD_CANDIDATES="$(echo "$ROUND_ITEMS" | jq -c '
      reduce .[] as $it ({seen: {}, out: []};
        ($it.link // "") as $u
        | if ($u | length) == 0 or .seen[$u] then .
          else .seen[$u] = true | .out += [$u]
        end
      ) | .out[:10]
    ')"
    if [ "$NEEDS_LOGIN" = "true" ]; then
      break
    fi
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

  oc_eval "$TARGET_ID" "$SCROLL_JS" >/dev/null
  sleep 3
  ROUND=$((ROUND + 1))
done

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

NOW_ISO="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "$LAST_EVAL" | jq --arg now "$NOW_ISO" --arg mode "$MODE" --argjson items "$FILTERED_ITEMS" '{
  source: "douyin",
  fetched_at: $now,
  mode: $mode,
  note: "probe_only_not_official_flow",
  page: .result.page_url,
  status: (if .result.needs_login then "needs_login" elif (($items | length) > 0) then "ok" else "no_records" end),
  records: [
    $items[]? | {
      platform: "douyin",
      title: (.title // ("抖音视频 " + (((.link // "") | split("/") | last) // ""))),
      link: (.link // ""),
      summary: (.summary // ""),
      favorite_or_star_count: (.favorite_or_star_count // null),
      ingested_at: $now
    }
  ]
}' > "$OUT_FILE"

if [ "$NEEDS_LOGIN" = "false" ]; then
  FILTERED_COUNT="$(echo "$FILTERED_ITEMS" | jq 'length')"
  if [ "$FIRST_RUN" = true ] || [ "$FILTERED_COUNT" -gt 0 ]; then
    NEW_HEADS="$HEAD_CANDIDATES"
    if [ "$(echo "$NEW_HEADS" | jq 'length')" -eq 0 ]; then
      NEW_HEADS="$(echo "$FILTERED_ITEMS" | jq -c 'map(.link // "") | map(select(. != "")) | .[:10]')"
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
