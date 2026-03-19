#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="$SKILL_ROOT/output"
COLLECT_LIMIT="${COLLECT_LIMIT:-0}"
COLLECT_STATE_FILE="${COLLECT_STATE_FILE:-$OUTPUT_DIR/collector-state.json}"

chmod +x "$SCRIPT_DIR"/*.sh

run_step() {
  local name="$1"
  shift
  echo "==> $name"
  if "$@"; then
    echo "[OK] $name"
  else
    echo "[WARN] $name failed (continue)"
  fi
}

run_step "collect_github_stars" "$SCRIPT_DIR/collect_github_stars.sh" "$COLLECT_LIMIT" "$OUTPUT_DIR/github-stars.json" "$COLLECT_STATE_FILE"
run_step "collect_x_bookmarks" "$SCRIPT_DIR/collect_x_bookmarks.sh" "$COLLECT_LIMIT" "$OUTPUT_DIR/x-bookmarks.json" "$COLLECT_STATE_FILE"
run_step "collect_xhs_favorites" "$SCRIPT_DIR/collect_xhs_favorites.sh" "$COLLECT_LIMIT" "$OUTPUT_DIR/xhs-favorites.json" "$COLLECT_STATE_FILE"
# 注意：抖音当前仍保留旧的 probe 脚本入口名，但业务规则已经切换到“收藏 -> 视频 -> 点击首条进入详情流 -> ArrowDown 逐条切换”的新版主流程。
# 若后续重构脚本，优先保留新流程含义，不要再退回“列表页滚动抓全量”的旧实现。
run_step "collect_douyin_favorites_probe" "$SCRIPT_DIR/collect_douyin_favorites_probe.sh" "$COLLECT_LIMIT" "$OUTPUT_DIR/douyin-favorites-probe.json" "$COLLECT_STATE_FILE"
run_step "merge_to_feishu_payload" "$SCRIPT_DIR/merge_to_feishu_payload.sh"

echo
echo "phase2 probes done."
echo "payload: $OUTPUT_DIR/feishu-payload.json"
echo "note: Douyin remains flow-first; current Douyin probe scripts are for probing/debugging, not the final official collector."
