#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_DIR="$(cd "$SKILL_ROOT/../.." && pwd)"

XHS_DIR_DEFAULT="$WORKSPACE_DIR/skills/xiaohongshu-skills"
XHS_DIR="${XHS_DIR:-$XHS_DIR_DEFAULT}"
OUT_FILE="${1:-$SKILL_ROOT/output/xhs-favorites-probe.json}"

mkdir -p "$(dirname "$OUT_FILE")"

if ! command -v jq >/dev/null 2>&1; then
  echo "missing dependency: jq" >&2
  exit 1
fi

if ! command -v bash >/dev/null 2>&1 || ! command -v uv >/dev/null 2>&1; then
  jq -n '{
    source: "xiaohongshu",
    fetched_at: (now | todateiso8601),
    status: "blocked_missing_dependency",
    message: "missing bash or uv dependency"
  }' > "$OUT_FILE"
  echo "saved: $OUT_FILE"
  exit 0
fi

if [ ! -d "$XHS_DIR" ]; then
  jq -n --arg dir "$XHS_DIR" '{
    source: "xiaohongshu",
    fetched_at: (now | todateiso8601),
    status: "blocked_missing_dependency",
    message: ("xiaohongshu-skills not found: " + $dir)
  }' > "$OUT_FILE"
  echo "saved: $OUT_FILE"
  exit 0
fi

set +e
LOGIN_JSON="$(cd "$XHS_DIR" && uv run python scripts/cli.py check-login 2>/dev/null)"
RC=$?
set -e

if [ -z "$LOGIN_JSON" ]; then
  jq -n '{
    source: "xiaohongshu",
    fetched_at: (now | todateiso8601),
    status: "error",
    message: "check-login did not return JSON"
  }' > "$OUT_FILE"
  echo "saved: $OUT_FILE"
  exit 0
fi

if [ "$RC" -ne 0 ]; then
  # 未登录场景下 xhs-cli 会返回非 0，这里只做探测不视为失败
  :
fi

LOGGED_IN="$(echo "$LOGIN_JSON" | jq -r '.logged_in // false')"

if [ "$LOGGED_IN" != "true" ]; then
  echo "$LOGIN_JSON" | jq '{
    source: "xiaohongshu",
    fetched_at: (now | todateiso8601),
    status: "needs_login",
    message: "xiaohongshu session not logged in",
    login: .
  }' > "$OUT_FILE"
  echo "saved: $OUT_FILE"
  exit 0
fi

echo "$LOGIN_JSON" | jq '{
  source: "xiaohongshu",
  fetched_at: (now | todateiso8601),
  status: "blocked_missing_collector",
  message: "logged in, but favorites list collector is not implemented yet",
  login: .
}' > "$OUT_FILE"

echo "saved: $OUT_FILE"
