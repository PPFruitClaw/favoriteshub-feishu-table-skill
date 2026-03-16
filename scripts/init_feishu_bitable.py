#!/usr/bin/env python3
"""Initialize Feishu Bitable structure for FavoritesHub."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from feishu_bitable_api import (
    FeishuBitableClient,
    load_feishu_credentials,
    load_user_config,
    utc_now_iso,
)

TABLES = ["github", "x", "xiaohongshu", "douyin", "other"]

# 1=Text, 2=Number, 5=DateTime, 15=URL
REQUIRED_FIELDS: list[tuple[str, int]] = [
    ("所属平台", 1),
    ("链接", 15),
    ("内容梗概", 1),
    ("收藏或星标数量", 2),
    ("收录时间", 5),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="初始化 FavoritesHub 飞书多维表格结构")
    p.add_argument("--config", default="", help="用户配置文件路径（可选），支持覆盖不同环境")
    p.add_argument("--app-id", default="", help="飞书 app_id（可选，优先级最高）")
    p.add_argument("--app-secret", default="", help="飞书 app_secret（可选，优先级最高）")
    p.add_argument("--base-url", default="", help="飞书 OpenAPI 域名（可选）")
    p.add_argument("--name", default="FavoritesHub-FeishuTable", help="新建多维表格名称（未提供 app_token 时生效）")
    p.add_argument("--app-token", default="", help="已有多维表格 app_token（可选）")
    p.add_argument("--folder-token", default="", help="创建新多维表格时放置目录 token（可选）")
    p.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent.parent / "output" / "feishu-target.json"),
        help="输出目标配置 JSON 路径",
    )
    return p.parse_args()


def ensure_tables(client: FeishuBitableClient, app_token: str) -> dict[str, dict[str, Any]]:
    all_tables = client.list_tables(app_token)
    by_name = {str(t.get("name", "")).strip(): t for t in all_tables if t.get("name")}
    result: dict[str, dict[str, Any]] = {}

    for table_name in TABLES:
        table = by_name.get(table_name)
        if not table:
            table = client.create_table(app_token, table_name)
            # Some API responses return only table metadata without id, re-read table list as fallback.
            if not table.get("table_id"):
                refreshed = client.list_tables(app_token)
                by_name = {str(t.get("name", "")).strip(): t for t in refreshed if t.get("name")}
                table = by_name.get(table_name, table)
        table_id = table.get("table_id")
        if not table_id:
            raise RuntimeError(f"未获取到 table_id: {table_name}")
        result[table_name] = {"table_id": table_id}
    return result


def ensure_fields(client: FeishuBitableClient, app_token: str, table_id: str) -> dict[str, int]:
    fields = client.list_fields(app_token, table_id)
    by_name = {str(f.get("field_name", "")).strip(): f for f in fields if f.get("field_name")}

    for field_name, field_type in REQUIRED_FIELDS:
        if field_name not in by_name:
            created = client.create_field(app_token, table_id, field_name, field_type)
            by_name[field_name] = created

    resolved: dict[str, int] = {}
    for field_name, _ in REQUIRED_FIELDS:
        f = by_name.get(field_name) or {}
        resolved[field_name] = int(f.get("type", 1))
    return resolved


def main() -> None:
    args = parse_args()
    user_cfg = load_user_config(args.config or None)
    feishu_cfg = ((user_cfg.get("feishu") or {}) if isinstance(user_cfg, dict) else {})

    app_id, app_secret, base_url = load_feishu_credentials(
        config=user_cfg,
        override_app_id=args.app_id,
        override_app_secret=args.app_secret,
        override_base_url=args.base_url,
    )
    client = FeishuBitableClient(app_id, app_secret, base_url)

    cfg_app_token = str(feishu_cfg.get("app_token") or feishu_cfg.get("appToken") or "").strip()
    cfg_folder_token = str(feishu_cfg.get("folder_token") or feishu_cfg.get("folderToken") or "").strip()

    app_token_arg = args.app_token.strip()
    folder_token_arg = args.folder_token.strip()
    app_token = app_token_arg or cfg_app_token
    folder_token = folder_token_arg or cfg_folder_token

    if app_token:
        app_meta: dict[str, Any] = {"app_token": app_token}
    else:
        app = client.create_app(args.name, folder_token or None)
        app_token = str(app.get("app_token", "")).strip()
        if not app_token:
            raise RuntimeError("创建多维表格失败：未返回 app_token")
        app_meta = app

    tables = ensure_tables(client, app_token)
    for name, info in tables.items():
        info["fields"] = ensure_fields(client, app_token, info["table_id"])

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_data = {
        "generated_at": utc_now_iso(),
        "app_token": app_token,
        "app_name": app_meta.get("name", args.name),
        "app_url": app_meta.get("url"),
        "tables": tables,
    }
    out_path.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"ok": True, "out": str(out_path), "app_token": app_token, "tables": list(tables.keys())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
