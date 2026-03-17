#!/usr/bin/env python3
"""Sync FavoritesHub payload into Feishu Bitable tables."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from feishu_bitable_api import (
    FeishuBitableClient,
    load_feishu_credentials,
    load_user_config,
    parse_iso_to_ms,
)


PLATFORM_VALUE_MAP = {
    "github": "github",
    "x": "x",
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "other": "other",
}

SUMMARY_BANNED_PREFIX = re.compile(
    r"^(该仓库|该收藏(?:内容)?|这个收藏(?:内容)?|此收藏(?:内容)?|本收藏(?:内容)?|本仓库)\s*[：:，, ]*"
)


def parse_args() -> argparse.Namespace:
    skill_root = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description="将 feishu-payload.json 同步到飞书多维表格")
    p.add_argument("--config", default="", help="用户配置文件路径（可选），支持覆盖不同环境")
    p.add_argument("--app-id", default="", help="飞书 app_id（可选，优先级最高）")
    p.add_argument("--app-secret", default="", help="飞书 app_secret（可选，优先级最高）")
    p.add_argument("--base-url", default="", help="飞书 OpenAPI 域名（可选）")
    p.add_argument("--payload", default=str(skill_root / "output" / "feishu-payload.json"), help="payload 文件路径")
    p.add_argument("--target", default=str(skill_root / "output" / "feishu-target.json"), help="init 输出目标配置路径")
    p.add_argument(
        "--state",
        default=str(skill_root / "output" / "feishu-sync-state.json"),
        help="本地同步状态缓存（用于增量优化）",
    )
    p.add_argument(
        "--summary-cache",
        default=str(skill_root / "output" / "summary-cache.json"),
        help="内容梗概缓存（减少重复概括）",
    )
    p.add_argument(
        "--summary-mode",
        choices=["openclaw-native"],
        default="openclaw-native",
        help="内容梗概模式（默认使用 OpenClaw 内置能力，不依赖外部 API key）",
    )
    p.add_argument(
        "--write-mode",
        choices=["create-only", "create-or-update"],
        default="create-only",
        help="写入模式：默认仅新增（create-only），可选新增+更新（create-or-update）",
    )
    p.add_argument("--dry-run", action="store_true", help="仅输出将要写入的统计，不实际写入")
    p.add_argument("--strict", action="store_true", help="遇到单条记录失败即退出（默认跳过并继续）")
    return p.parse_args()


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize_platform(raw: str) -> str:
    text = (raw or "").strip().lower()
    mapping = {
        "github": "github",
        "x": "x",
        "xiaohongshu": "xiaohongshu",
        "小红书": "xiaohongshu",
        "douyin": "douyin",
        "抖音": "douyin",
        "other": "other",
        "其他": "other",
    }
    return mapping.get(text, "other")


def platform_select_value(platform_key: str) -> str:
    return PLATFORM_VALUE_MAP.get(platform_key, "other")


def normalize_link(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("link") or value.get("text") or "").strip()
    if isinstance(value, list) and value:
        return normalize_link(value[0])
    return str(value).strip()


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _parse_int_count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 else None
    text = _clean_text(value).replace(",", "")
    if not text:
        return None
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([kKmMwW万亿]?)", text)
    if m:
        base = float(m.group(1))
        unit = m.group(2).lower()
        factor = 1.0
        if unit == "k":
            factor = 1_000.0
        elif unit == "m":
            factor = 1_000_000.0
        elif unit in {"w", "万"}:
            factor = 10_000.0
        elif unit == "亿":
            factor = 100_000_000.0
        val = int(base * factor)
        return val if val >= 0 else None
    try:
        num = int(float(text))
        return num if num >= 0 else None
    except ValueError:
        return None


def _extract_repo_name_from_link(link: str) -> str:
    try:
        p = urlparse(link)
        parts = [x for x in p.path.split("/") if x]
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    except Exception:
        pass
    return ""


def _extract_title(record: dict[str, Any]) -> str:
    title = _clean_text(record.get("标题") or "")
    if title:
        return title[:120]
    platform = normalize_platform(str(record.get("所属平台", "")))
    link = _clean_text(record.get("链接"))
    summary = _clean_text(record.get("内容梗概"))

    if platform == "github":
        repo = _extract_repo_name_from_link(link)
        if repo:
            return repo[:120]
    if summary:
        return summary[:50]
    if link:
        host = urlparse(link).netloc or link
        return f"{platform_select_value(platform)} 收藏 - {host}"[:120]
    return f"{platform_select_value(platform)} 收藏内容"


def _fallback_summary(platform: str, title: str, raw_summary: str, link: str) -> str:
    text = _clean_text(raw_summary)
    if platform == "github":
        repo = _extract_repo_name_from_link(link) or title or "这个项目"
        if text:
            return f"{repo}围绕{text[:72]}展开，包含可直接复用的实现思路与技术要点。"
        return f"{repo}聚焦具体开发问题，建议结合 README 和目录结构快速判断可复用价值。"
    if text:
        return f"内容围绕{text[:78]}展开，适合按主题回看并提炼可执行的方法或观点。"
    if platform == "douyin":
        return "视频主题与观点已入库，可回看原视频和评论区补全上下文信息。"
    if platform == "x":
        return "帖子讨论已入库，可回看线程上下文和引用关系提炼关键结论。"
    if platform == "xiaohongshu":
        return "图文笔记已入库，可回看图片细节和评论反馈提炼实践要点。"
    return "链接内容已入库，建议后续补充核心观点、适用场景和可执行结论。"


def _normalize_summary_output(text: str, *, platform: str, title: str, raw_summary: str, link: str) -> str:
    out = _clean_text(text).strip("“”\"' ")
    out = SUMMARY_BANNED_PREFIX.sub("", out).strip()
    if not out:
        out = _fallback_summary(platform, title, raw_summary, link)
    raw_clean = _clean_text(raw_summary).rstrip("。")
    if raw_clean and out.rstrip("。") == raw_clean:
        out = _fallback_summary(platform, title, raw_summary, link)
    if len(out) > 140:
        out = out[:140].rstrip()
    if out and out[-1] not in "。！？":
        out += "。"
    return out


def _native_summary(platform: str, title: str, raw_summary: str, link: str) -> tuple[str, bool]:
    text = _clean_text(raw_summary)
    if not text:
        return _fallback_summary(platform, title, raw_summary, link), True

    core = text[:90]
    if platform == "github":
        repo = _extract_repo_name_from_link(link) or title or "这个项目"
        return f"{repo}主要覆盖{core[:60]}，适合快速评估技术路线并提炼可复用实现。", False
    if platform == "x":
        return f"这条内容重点讨论{core[:72]}，建议结合上下文线程整理关键观点与结论。", False
    if platform == "douyin":
        return f"这条视频围绕{core[:72]}展开，回看时可重点关注可执行步骤与经验要点。", False
    if platform == "xiaohongshu":
        return f"这篇笔记聚焦{core[:72]}，可结合图文细节提炼适用场景和实践方法。", False
    return f"这条收藏内容围绕{core[:72]}展开，建议按主题沉淀可执行的关键结论。", False


def load_summary_cache(path: str) -> dict[str, str]:
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    result: dict[str, str] = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, str):
            result[k] = v
    return result


def save_summary_cache(path: str, cache: dict[str, str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


class ChineseSummarizer:
    def __init__(self, *, mode: str, cache: dict[str, str]):
        self.mode = mode.strip() or "openclaw-native"
        self.cache = cache
        self.enabled = True
        self.cache_hits = 0
        self.generated = 0
        self.fallback_used = 0
        self.last_error = ""
        self.disabled_reason = ""

    def _cache_key(self, platform: str, title: str, raw_summary: str, link: str) -> str:
        raw = "|".join([platform, _clean_text(title), _clean_text(raw_summary), _clean_text(link)])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def summarize(self, *, platform: str, title: str, raw_summary: str, link: str) -> str:
        key = self._cache_key(platform, title, raw_summary, link)
        cached = self.cache.get(key)
        if isinstance(cached, str) and cached.strip():
            self.cache_hits += 1
            return cached

        output = ""
        used_fallback = False
        try:
            output, used_fallback = _native_summary(platform, title, raw_summary, link)
        except Exception as e:
            self.last_error = str(e)
            self.disabled_reason = "native_summary_failed"
            output = _fallback_summary(platform, title, raw_summary, link)
            used_fallback = True

        self.generated += 1
        if used_fallback:
            self.fallback_used += 1
        final_summary = _normalize_summary_output(
            output,
            platform=platform,
            title=title,
            raw_summary=raw_summary,
            link=link,
        )
        self.cache[key] = final_summary
        return final_summary


def to_fields(
    record: dict[str, Any],
    link_field_type: int,
    *,
    summarizer: ChineseSummarizer,
    default_status: bool,
) -> dict[str, Any]:
    link = str(record.get("链接", "")).strip()
    platform_key = normalize_platform(str(record.get("所属平台", "")))
    title = _extract_title(record)
    summary_zh = summarizer.summarize(
        platform=platform_key,
        title=title,
        raw_summary=str(record.get("内容梗概", "")),
        link=link,
    )
    fields: dict[str, Any] = {
        "标题": title,
        "所属平台": platform_select_value(platform_key),
        "内容梗概": summary_zh,
        "收录时间": parse_iso_to_ms(record.get("收录时间")),
    }
    if link_field_type == 15:
        fields["链接"] = {"text": link, "link": link}
    else:
        fields["链接"] = link
    if default_status:
        status = _clean_text(record.get("状态") or "未学习")
        if status not in {"已学习", "已过期", "未学习"}:
            status = "未学习"
        fields["状态"] = status

    count_val = _parse_int_count(record.get("收藏或星标数量"))
    if count_val is not None:
        fields["收藏或星标数量"] = count_val
    return fields


def build_existing_index(client: FeishuBitableClient, app_token: str, table_id: str) -> dict[str, str]:
    index: dict[str, str] = {}
    for item in client.list_records(app_token, table_id):
        record_id = item.get("record_id")
        fields = item.get("fields") or {}
        link = normalize_link(fields.get("链接"))
        if record_id and link:
            index[link] = str(record_id)
    return index


def load_state(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {"tables": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"tables": {}}
    if not isinstance(data, dict):
        return {"tables": {}}
    if "tables" not in data or not isinstance(data.get("tables"), dict):
        data["tables"] = {}
    return data


def save_state(path: str, state: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    user_cfg = load_user_config(args.config or None)
    payload = load_json(args.payload)
    target = load_json(args.target)

    app_token = str(target.get("app_token", "")).strip()
    if not app_token:
        raise RuntimeError("target 缺少 app_token，请先执行 init_feishu_bitable.py")

    records = payload.get("records") or []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        platform = normalize_platform(str(row.get("所属平台", "")))
        groups[platform].append(row)

    app_id, app_secret, base_url = load_feishu_credentials(
        config=user_cfg,
        override_app_id=args.app_id,
        override_app_secret=args.app_secret,
        override_base_url=args.base_url,
    )
    client = FeishuBitableClient(app_id, app_secret, base_url)

    summary_cache = load_summary_cache(args.summary_cache)
    summarizer = ChineseSummarizer(
        mode=args.summary_mode,
        cache=summary_cache,
    )

    state = load_state(args.state)
    state_tables = state.setdefault("tables", {})

    summary = {
        "total_input": len(records),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "skipped_existing": 0,
        "errors": 0,
        "write_mode": args.write_mode,
        "summary_engine": {
            "name": summarizer.mode,
            "enabled": summarizer.enabled,
            "cache_hits": 0,
            "generated": 0,
            "fallback_used": 0,
            "last_error": "",
            "disabled_reason": "",
        },
        "by_platform": {},
    }

    for platform, rows in groups.items():
        table_info = ((target.get("tables") or {}).get(platform)) or {}
        table_id = str(table_info.get("table_id", "")).strip()
        if not table_id:
            summary["skipped"] += len(rows)
            summary["by_platform"][platform] = {
                "input": len(rows),
                "created": 0,
                "updated": 0,
                "skipped": len(rows),
                "skipped_existing": 0,
            }
            continue

        fields_meta = table_info.get("fields") or {}
        link_field_type = int(fields_meta.get("链接", 15))
        table_state = state_tables.setdefault(table_id, {})
        existing: dict[str, str]
        if isinstance(table_state, dict) and table_state:
            existing = {str(k): str(v) for k, v in table_state.items() if str(k).strip() and str(v).strip()}
        else:
            # 首次无缓存时回读远端，后续优先使用本地状态减少全表遍历
            existing = build_existing_index(client, app_token, table_id)
            state_tables[table_id] = dict(existing)

        p_created = 0
        p_updated = 0
        p_skipped = 0
        p_skipped_existing = 0

        for row in rows:
            link = str(row.get("链接", "")).strip()
            if not link:
                p_skipped += 1
                continue
            if args.dry_run:
                if link not in existing:
                    p_created += 1
                elif args.write_mode == "create-or-update":
                    p_updated += 1
                else:
                    p_skipped_existing += 1
                continue

            try:
                if link in existing and args.write_mode == "create-or-update":
                    fields = to_fields(row, link_field_type, summarizer=summarizer, default_status=False)
                    client.update_record(app_token, table_id, existing[link], fields)
                    p_updated += 1
                elif link not in existing:
                    fields = to_fields(row, link_field_type, summarizer=summarizer, default_status=True)
                    created = client.create_record(app_token, table_id, fields)
                    created_id = created.get("record_id")
                    if created_id:
                        rid = str(created_id)
                        existing[link] = rid
                        if isinstance(state_tables.get(table_id), dict):
                            state_tables[table_id][link] = rid
                    p_created += 1
                else:
                    p_skipped_existing += 1
            except Exception:
                summary["errors"] += 1
                if args.strict:
                    raise

        summary["created"] += p_created
        summary["updated"] += p_updated
        summary["skipped"] += p_skipped
        summary["skipped_existing"] += p_skipped_existing
        summary["by_platform"][platform] = {
            "input": len(rows),
            "created": p_created,
            "updated": p_updated,
            "skipped": p_skipped,
            "skipped_existing": p_skipped_existing,
        }

    summary["summary_engine"]["cache_hits"] = summarizer.cache_hits
    summary["summary_engine"]["generated"] = summarizer.generated
    summary["summary_engine"]["fallback_used"] = summarizer.fallback_used
    summary["summary_engine"]["last_error"] = summarizer.last_error
    summary["summary_engine"]["disabled_reason"] = summarizer.disabled_reason

    if not args.dry_run:
        save_state(args.state, state)
        save_summary_cache(args.summary_cache, summary_cache)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
