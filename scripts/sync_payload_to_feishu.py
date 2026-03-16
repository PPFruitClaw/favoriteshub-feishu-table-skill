#!/usr/bin/env python3
"""Sync FavoritesHub payload into Feishu Bitable tables."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from feishu_bitable_api import (
    FeishuBitableClient,
    load_feishu_credentials,
    load_user_config,
    parse_iso_to_ms,
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
    if text in {"github", "x", "xiaohongshu", "douyin", "other"}:
        return text
    return "other"


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


def to_fields(record: dict[str, Any], link_field_type: int) -> dict[str, Any]:
    link = str(record.get("链接", "")).strip()
    fields: dict[str, Any] = {
        "所属平台": record.get("所属平台", ""),
        "内容梗概": record.get("内容梗概", ""),
        "收录时间": parse_iso_to_ms(record.get("收录时间")),
    }
    if link_field_type == 15:
        fields["链接"] = {"text": link, "link": link}
    else:
        fields["链接"] = link

    count_val = record.get("收藏或星标数量")
    if count_val is not None and str(count_val).strip() != "":
        try:
            fields["收藏或星标数量"] = float(count_val)
        except ValueError:
            pass
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
            fields = to_fields(row, link_field_type)
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
                    client.update_record(app_token, table_id, existing[link], fields)
                    p_updated += 1
                elif link not in existing:
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

    if not args.dry_run:
        save_state(args.state, state)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
