#!/usr/bin/env python3
"""Sync FavoritesHub payload into Feishu Bitable tables."""

from __future__ import annotations

import argparse
import hashlib
import html
import ipaddress
import json
import re
import subprocess
import urllib.request
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
TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
OG_TITLE_RE = re.compile(
    r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"'](.*?)[\"'][^>]*>",
    re.IGNORECASE | re.DOTALL,
)
TW_TITLE_RE = re.compile(
    r"<meta[^>]+name=[\"']twitter:title[\"'][^>]+content=[\"'](.*?)[\"'][^>]*>",
    re.IGNORECASE | re.DOTALL,
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
        "--title-cache",
        default=str(skill_root / "output" / "title-cache.json"),
        help="标题缓存（减少重复链接解析）",
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
    p.add_argument("--platforms", default="", help="仅处理指定平台，逗号分隔，如 github,x")
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
        num = int(round(float(text)))
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


def _extract_repo_slug_parts(link: str) -> tuple[str, str]:
    repo = _extract_repo_name_from_link(link)
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return owner.strip(), name.strip()
    return "", repo.strip()


def _strip_noise(text: str) -> str:
    out = _clean_text(text)
    out = re.sub(r"^GitHub\s*[-:|]\s*", "", out, flags=re.IGNORECASE)
    out = re.sub(r"^X\s*[:：-]\s*", "", out, flags=re.IGNORECASE)
    out = re.sub(r"^Twitter\s*[:：-]\s*", "", out, flags=re.IGNORECASE)
    out = re.sub(r"^[#【\[]?\s*(仓库|项目|帖子|推文|笔记|视频|链接)\s*[】\]]?\s*[:：-]\s*", "", out)
    out = re.sub(r"@[A-Za-z0-9_]+", "", out)
    out = re.sub(r"\b[A-Z][a-z]{2}\s+\d{1,2}\b", "", out)
    out = re.sub(r"\bArticle\b", "", out, flags=re.IGNORECASE)
    out = re.sub(r"https?://\S+", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\b[\w.-]+/[\w.-]+\b", "", out)
    out = re.sub(r"\s+", " ", out).strip(" -_|·:：，,。")
    return out


def _trim_sentence(text: str, limit: int) -> str:
    out = _strip_noise(text)
    if len(out) <= limit:
        return out
    shortened = out[:limit]
    for sep in ["。", "！", "？", ";", "；", ",", "，", " "]:
        idx = shortened.rfind(sep)
        if idx >= max(12, limit // 2):
            shortened = shortened[:idx]
            break
    return shortened.strip(" -_|·:：，,。")


def _make_chinese_title(platform: str, raw_title: str, raw_summary: str, link: str) -> str:
    title = _trim_sentence(raw_title, 34)
    summary = _trim_sentence(raw_summary, 50)
    if platform == "github":
        owner, name = _extract_repo_slug_parts(link)
        if title and len(title) >= 6 and title.lower() not in {name.lower(), f"{owner}/{name}".lower()}:
            return title[:40]
        if summary and len(summary) >= 6:
            return summary[:40]
        if name:
            return f"{name} 项目"[:40]
        repo = _extract_repo_name_from_link(link)
        if repo:
            return repo[:40]
    if platform == "x":
        if title and len(title) >= 10:
            return title[:40]
        if summary and len(summary) >= 10:
            return summary[:40]
        return "X 内容摘录"
    if platform == "xiaohongshu":
        if title and len(title) >= 6:
            return title[:40]
        if summary and len(summary) >= 6:
            return summary[:40]
        return "小红书笔记"
    if platform == "douyin":
        if title and len(title) >= 6:
            return title[:40]
        if summary and len(summary) >= 6:
            return summary[:40]
        return "抖音视频"
    if title:
        return title[:40]
    if summary:
        return summary[:40]
    host = urlparse(link).netloc or "链接"
    return f"{host} 内容"


def _extract_title_fallback(record: dict[str, Any]) -> str:
    platform = normalize_platform(str(record.get("所属平台", "")))
    link = _clean_text(record.get("链接"))
    title = _clean_text(record.get("标题") or "")
    summary = _clean_text(record.get("内容梗概") or "")
    return _make_chinese_title(platform, title, summary, link)[:120]


def _looks_generic_title(title: str) -> bool:
    t = _clean_text(title).strip().lower()
    if not t or len(t) <= 2:
        return True
    generic_exact = {
        "x",
        "github",
        "douyin",
        "xiaohongshu",
        "登录",
        "log in",
        "just a moment...",
    }
    if t in generic_exact:
        return True
    generic_contains = ["登录", "sign in", "log in", "安全验证", "just a moment", "访问受限"]
    return any(x in t for x in generic_contains)


def _normalize_page_title(raw: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = _clean_text(text).strip("-_|· ")
    for sep in [" - ", " | ", " · ", " — ", "_"]:
        if sep in text:
            left, right = text.rsplit(sep, 1)
            right_l = right.strip().lower()
            if right_l in {"github", "x", "twitter", "小红书", "抖音", "douyin"}:
                text = left.strip()
                break
    if len(text) > 120:
        text = text[:120].rstrip()
    return text


def _fetch_title_from_link(link: str, *, timeout: int = 10) -> str:
    if not link or not re.match(r"^https?://", link, flags=re.IGNORECASE):
        return ""
    parsed = urlparse(link)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return ""
    if host == "localhost":
        return ""
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return ""
    except ValueError:
        pass
    req = urllib.request.Request(
        link,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(220_000).decode("utf-8", errors="ignore")
    except Exception:
        return ""

    for pattern in (OG_TITLE_RE, TW_TITLE_RE, TITLE_TAG_RE):
        m = pattern.search(raw)
        if not m:
            continue
        candidate = _normalize_page_title(m.group(1))
        if candidate and not _looks_generic_title(candidate):
            return candidate
    return ""


# 标题/梗概生成已改为由主代理直接负责，不再由此脚本自动读页面并产出最终文案。
# 本脚本保留为结构化同步器：负责把 payload 里的结果可靠写入飞书表。


class LinkTitleResolver:
    def __init__(self, *, cache: dict[str, str]):
        self.cache = cache
        self.cache_hits = 0
        self.fetch_attempts = 0
        self.fetch_success = 0
        self.fetch_failures = 0

    def resolve(self, record: dict[str, Any]) -> str:
        link = _clean_text(record.get("链接"))
        raw_title = _clean_text(record.get("标题") or "")
        if raw_title:
            if link:
                self.cache[link] = raw_title
            return raw_title[:120]
        fallback = _extract_title_fallback(record)
        if link and fallback:
            self.cache[link] = fallback
        return fallback


def _fallback_summary(platform: str, title: str, raw_summary: str, link: str) -> str:
    text = _trim_sentence(raw_summary, 110)
    if text:
        return text
    if platform == "github":
        owner, name = _extract_repo_slug_parts(link)
        repo_name = name or _extract_repo_name_from_link(link) or _strip_noise(title) or "这个项目"
        return f"{repo_name} 的项目说明、能力边界和使用场景。"
    if platform == "x":
        return "帖子里的核心观点、方法或结论。"
    if platform == "xiaohongshu":
        return "笔记里的经验、做法和适用场景。"
    if platform == "douyin":
        return "视频里的主要观点、步骤或经验。"
    return "链接里的主要内容和关键信息。"


def _normalize_summary_output(text: str, *, platform: str, title: str, raw_summary: str, link: str) -> str:
    out = _clean_text(text).strip("“”\"' ")
    out = SUMMARY_BANNED_PREFIX.sub("", out).strip()
    out = _strip_noise(out)
    if not out:
        out = _fallback_summary(platform, title, raw_summary, link)
    if len(out) > 140:
        out = _trim_sentence(out, 140)
    if out and out[-1] not in "。！？":
        out += "。"
    return out


def _native_summary(platform: str, title: str, raw_summary: str, link: str) -> tuple[str, bool]:
    text = _trim_sentence(raw_summary, 110)
    if text:
        return text, False
    return _fallback_summary(platform, title, raw_summary, link), True


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

        output = _clean_text(raw_summary)
        if not output:
            output = _fallback_summary(platform, title, raw_summary, link)
            self.fallback_used += 1

        self.generated += 1
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
    title_resolver: LinkTitleResolver,
    default_status: bool,
) -> dict[str, Any]:
    link = str(record.get("链接", "")).strip()
    platform_key = normalize_platform(str(record.get("所属平台", "")))
    title = title_resolver.resolve(record)
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
        if status not in {"已学习", "已过期", "未学习", "重点收藏"}:
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
    platform_filter = {
        normalize_platform(x)
        for x in [s.strip() for s in str(args.platforms or '').split(',') if s.strip()]
    }
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        platform = normalize_platform(str(row.get("所属平台", "")))
        if platform_filter and platform not in platform_filter:
            continue
        groups[platform].append(row)

    app_id, app_secret, base_url = load_feishu_credentials(
        config=user_cfg,
        override_app_id=args.app_id,
        override_app_secret=args.app_secret,
        override_base_url=args.base_url,
    )
    client = FeishuBitableClient(app_id, app_secret, base_url)

    summary_cache = load_summary_cache(args.summary_cache)
    title_cache = load_summary_cache(args.title_cache)
    summarizer = ChineseSummarizer(
        mode=args.summary_mode,
        cache=summary_cache,
    )
    title_resolver = LinkTitleResolver(cache=title_cache)

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
        "title_engine": {
            "cache_hits": 0,
            "fetch_attempts": 0,
            "fetch_success": 0,
            "fetch_failures": 0,
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
                    fields = to_fields(
                        row,
                        link_field_type,
                        summarizer=summarizer,
                        title_resolver=title_resolver,
                        default_status=False,
                    )
                    client.update_record(app_token, table_id, existing[link], fields)
                    p_updated += 1
                elif link not in existing:
                    fields = to_fields(
                        row,
                        link_field_type,
                        summarizer=summarizer,
                        title_resolver=title_resolver,
                        default_status=True,
                    )
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
    summary["title_engine"]["cache_hits"] = title_resolver.cache_hits
    summary["title_engine"]["fetch_attempts"] = title_resolver.fetch_attempts
    summary["title_engine"]["fetch_success"] = title_resolver.fetch_success
    summary["title_engine"]["fetch_failures"] = title_resolver.fetch_failures

    if not args.dry_run:
        save_state(args.state, state)
        save_summary_cache(args.summary_cache, summary_cache)
        save_summary_cache(args.title_cache, title_cache)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
