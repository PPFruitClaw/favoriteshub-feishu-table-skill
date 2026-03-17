#!/usr/bin/env python3
"""Initialize Feishu Bitable structure for FavoritesHub."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from feishu_bitable_api import (
    FeishuBitableClient,
    load_feishu_credentials,
    load_user_config,
    utc_now_iso,
)

TABLES = ["github", "x", "xiaohongshu", "douyin", "other"]
TABLE_DISPLAY_NAMES = {
    "github": "github",
    "x": "x",
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "other": "other",
}
TABLE_NAME_ALIASES = {
    "xiaohongshu": ["xiaohongshu", "小红书"],
    "douyin": ["douyin", "抖音"],
    "github": ["github"],
    "x": ["x"],
    "other": ["other", "其他"],
}
PLATFORM_OPTIONS = [{"name": TABLE_DISPLAY_NAMES[k]} for k in TABLES]
STATUS_OPTIONS = [{"name": x} for x in ["已学习", "已过期", "未学习", "重点收藏"]]
DEFAULT_GARBAGE_TABLE_NAMES = {"数据表", "表格", "表格1", "table1", "Table1"}

# 1=Text, 2=Number, 3=SingleSelect, 5=DateTime, 15=URL
REQUIRED_FIELDS: list[tuple[str, int, dict[str, Any] | None]] = [
    ("所属平台", 3, {"options": PLATFORM_OPTIONS}),
    ("状态", 3, {"options": STATUS_OPTIONS}),
    ("链接", 15, None),
    ("内容梗概", 1, None),
    ("收藏或星标数量", 2, None),
    ("收录时间", 5, None),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="初始化 FavoritesHub 飞书多维表格结构")
    p.add_argument("--config", default="", help="用户配置文件路径（可选），支持覆盖不同环境")
    p.add_argument("--app-id", default="", help="飞书 app_id（可选，优先级最高）")
    p.add_argument("--app-secret", default="", help="飞书 app_secret（可选，优先级最高）")
    p.add_argument("--base-url", default="", help="飞书 OpenAPI 域名（可选）")
    p.add_argument("--name", default="FavoritesHub-多平台收藏中心", help="新建多维表格名称（未提供 app_token 时生效）")
    p.add_argument("--app-token", default="", help="已有多维表格 app_token（可选）")
    p.add_argument("--folder-token", default="", help="创建新多维表格时放置目录 token（可选）")
    p.add_argument("--owner-email", default="", help="真实飞书用户邮箱（默认授予 full_access）")
    p.add_argument(
        "--transfer-owner-email",
        default="",
        help="转移所有权目标邮箱（默认复用 owner_email）",
    )
    p.add_argument(
        "--transfer-owner-member-id",
        default="",
        help="转移所有权目标 member_id（优先级高于邮箱）",
    )
    p.add_argument(
        "--transfer-owner-member-type",
        default="openid",
        choices=["openid", "userid", "unionid", "email"],
        help="转移所有权目标 member_id 的类型（默认 openid）",
    )
    p.add_argument(
        "--transfer-owner-id-type",
        default="open_id",
        choices=["open_id", "user_id", "union_id"],
        help="按邮箱解析 member_id 时返回的 ID 类型（默认 open_id）",
    )
    p.add_argument(
        "--share-member",
        action="append",
        default=[],
        help="共享成员，格式 type:id[:perm]，例如 email:alice@example.com:full_access",
    )
    p.add_argument(
        "--cleanup-force",
        action="store_true",
        help="强制清理默认垃圾表（即使含历史记录）",
    )
    p.add_argument(
        "--allow-bot-only",
        action="store_true",
        help="允许仅机器人可编辑（默认关闭，建议保留真实用户编辑权限）",
    )
    p.add_argument(
        "--share-strict",
        action="store_true",
        help="分享成员授权失败时立即报错退出（默认失败不阻塞初始化）",
    )
    p.add_argument(
        "--skip-owner-transfer",
        action="store_true",
        help="跳过所有权转移（默认有真实用户邮箱时会自动尝试转移）",
    )
    p.add_argument(
        "--transfer-owner-strict",
        action="store_true",
        help="所有权转移失败时立即报错退出（默认失败不中断初始化）",
    )
    p.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent.parent / "output" / "feishu-target.json"),
        help="输出目标配置 JSON 路径",
    )
    p.add_argument(
        "--owner-identity-cache",
        default=str(Path(__file__).resolve().parent.parent / "output" / "owner-identity.json"),
        help="owner 身份缓存文件（用于无感复用 member_id）",
    )
    return p.parse_args()


def ensure_tables(client: FeishuBitableClient, app_token: str) -> dict[str, dict[str, Any]]:
    all_tables = client.list_tables(app_token)
    by_name = {str(t.get("name", "")).strip(): t for t in all_tables if t.get("name")}
    result: dict[str, dict[str, Any]] = {}

    for table_key in TABLES:
        desired_name = TABLE_DISPLAY_NAMES.get(table_key, table_key)
        table = by_name.get(desired_name)
        if not table:
            for alias in TABLE_NAME_ALIASES.get(table_key, []):
                if alias in by_name:
                    table = by_name[alias]
                    break
        if not table:
            table = client.create_table(app_token, desired_name)
            # Some API responses return only table metadata without id, re-read table list as fallback.
            if not table.get("table_id"):
                refreshed = client.list_tables(app_token)
                by_name = {str(t.get("name", "")).strip(): t for t in refreshed if t.get("name")}
                table = by_name.get(desired_name, table)
        else:
            current_name = str(table.get("name", "")).strip()
            table_id = str(table.get("table_id", "")).strip()
            if table_id and current_name != desired_name:
                try:
                    table = client.update_table_name(app_token, table_id, desired_name) or table
                except Exception:
                    pass
        table_id = table.get("table_id")
        if not table_id:
            raise RuntimeError(f"未获取到 table_id: {table_key}")
        result[table_key] = {"table_id": table_id}
    return result


def _find_primary_field(fields: list[dict[str, Any]]) -> dict[str, Any] | None:
    for f in fields:
        if bool(f.get("is_primary")):
            return f
        prop = f.get("property") or {}
        if isinstance(prop, dict) and bool(prop.get("is_primary")):
            return f
    return fields[0] if fields else None


def ensure_primary_title_field(client: FeishuBitableClient, app_token: str, table_id: str) -> None:
    fields = client.list_fields(app_token, table_id)
    primary = _find_primary_field(fields)
    if not primary:
        return
    field_id = str(primary.get("field_id") or "")
    field_name = str(primary.get("field_name") or "").strip()
    field_type = int(primary.get("type", 1))
    if not field_id:
        return
    if field_name != "标题":
        client.update_field(app_token, table_id, field_id, field_name="标题", field_type=field_type)


def ensure_fields(client: FeishuBitableClient, app_token: str, table_id: str) -> dict[str, int]:
    ensure_primary_title_field(client, app_token, table_id)
    fields = client.list_fields(app_token, table_id)
    by_name = {str(f.get("field_name", "")).strip(): f for f in fields if f.get("field_name")}

    for field_name, field_type, property_data in REQUIRED_FIELDS:
        if field_name not in by_name:
            created = client.create_field_with_property(app_token, table_id, field_name, field_type, property_data)
            by_name[field_name] = created
        else:
            existing = by_name[field_name]
            existing_type = int(existing.get("type", 1))
            field_id = str(existing.get("field_id") or "")
            needs_update = (existing_type != field_type) or (field_name in {"所属平台", "状态"})
            if needs_update and field_id:
                client.update_field(
                    app_token,
                    table_id,
                    field_id,
                    field_name=field_name,
                    field_type=field_type,
                    property_data=property_data,
                )
    # Re-read to get latest types after updates.
    fields = client.list_fields(app_token, table_id)
    by_name = {str(f.get("field_name", "")).strip(): f for f in fields if f.get("field_name")}

    resolved: dict[str, int] = {}
    for field_name, _, _ in REQUIRED_FIELDS:
        f = by_name.get(field_name) or {}
        resolved[field_name] = int(f.get("type", 1))
    return resolved


def cleanup_default_empty_tables(client: FeishuBitableClient, app_token: str, *, force: bool = False) -> list[str]:
    removed: list[str] = []
    all_tables = client.list_tables(app_token)
    keep = set(TABLE_DISPLAY_NAMES.values())
    for aliases in TABLE_NAME_ALIASES.values():
        keep.update(aliases)
    for t in all_tables:
        name = str(t.get("name", "")).strip()
        table_id = str(t.get("table_id", "")).strip()
        if not name or not table_id:
            continue
        if name in keep:
            continue
        if name not in DEFAULT_GARBAGE_TABLE_NAMES:
            continue
        records = client.list_records(app_token, table_id)
        if records and not force:
            continue
        client.delete_table(app_token, table_id)
        removed.append(name)
    return removed


def _parse_share_member_text(text: str) -> dict[str, str] | None:
    raw = text.strip()
    if not raw:
        return None
    parts = raw.split(":")
    if len(parts) < 2:
        return None
    member_type = parts[0].strip().lower()
    member_id = parts[1].strip()
    perm = (parts[2].strip().lower() if len(parts) >= 3 else "full_access")
    if not member_type or not member_id:
        return None
    return {"member_type": member_type, "member_id": member_id, "perm": perm}


def _is_placeholder_email(email: str) -> bool:
    e = email.strip().lower()
    if not e:
        return False
    return e in {"you@example.com", "example@example.com"} or e.endswith("@example.com")


def _is_valid_email(email: str) -> bool:
    e = email.strip()
    if not e:
        return False
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e) is not None


def _resolve_owner_email(args: argparse.Namespace, feishu_cfg: dict[str, Any]) -> str:
    owner_email = str(
        args.owner_email
        or feishu_cfg.get("owner_email")
        or feishu_cfg.get("user_email")
        or feishu_cfg.get("editor_email")
        or ""
    ).strip()
    if not owner_email:
        owner_email = str(os.getenv("FAVORITESHUB_OWNER_EMAIL", "")).strip()
    if not owner_email:
        owner_email = str(os.getenv("FEISHU_USER_EMAIL", "")).strip()
    return owner_email


def _resolve_transfer_owner_email(args: argparse.Namespace, feishu_cfg: dict[str, Any]) -> str:
    transfer_email = str(
        args.transfer_owner_email
        or feishu_cfg.get("transfer_owner_email")
        or feishu_cfg.get("transferOwnerEmail")
        or ""
    ).strip()
    if transfer_email:
        return transfer_email
    return _resolve_owner_email(args, feishu_cfg)


def _truthy(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _normalize_member_type(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"open_id", "openid", "open-id"}:
        return "openid"
    if text in {"user_id", "userid", "user-id"}:
        return "userid"
    if text in {"union_id", "unionid", "union-id"}:
        return "unionid"
    if text == "email":
        return "email"
    return "openid"


def load_owner_identity_cache(path: str) -> dict[str, str]:
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "member_id": str(data.get("member_id") or "").strip(),
        "member_type": _normalize_member_type(str(data.get("member_type") or "openid")),
        "email": str(data.get("email") or "").strip(),
    }


def save_owner_identity_cache(path: str, identity: dict[str, str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "member_id": str(identity.get("member_id") or "").strip(),
        "member_type": _normalize_member_type(str(identity.get("member_type") or "openid")),
        "email": str(identity.get("email") or "").strip(),
        "updated_at": utc_now_iso(),
    }
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_share_members(args: argparse.Namespace, feishu_cfg: dict[str, Any]) -> list[dict[str, str]]:
    members: list[dict[str, str]] = []

    for x in args.share_member:
        item = _parse_share_member_text(x)
        if item:
            members.append(item)

    cfg_list = feishu_cfg.get("share_members")
    if isinstance(cfg_list, list):
        for item in cfg_list:
            if isinstance(item, str):
                parsed = _parse_share_member_text(item)
                if parsed:
                    members.append(parsed)
            elif isinstance(item, dict):
                member_type = str(item.get("member_type") or item.get("type") or "").strip().lower()
                member_id = str(item.get("member_id") or item.get("id") or "").strip()
                perm = str(item.get("perm") or "full_access").strip().lower()
                if member_type and member_id:
                    members.append({"member_type": member_type, "member_id": member_id, "perm": perm})

    owner_email = _resolve_owner_email(args, feishu_cfg)
    if owner_email and not _is_placeholder_email(owner_email):
        members.append({"member_type": "email", "member_id": owner_email, "perm": "full_access"})

    # de-dup
    uniq: dict[str, dict[str, str]] = {}
    for m in members:
        key = f"{m['member_type']}::{m['member_id']}"
        uniq[key] = m
    return list(uniq.values())


def ensure_share_members(
    client: FeishuBitableClient,
    app_token: str,
    members: list[dict[str, str]],
    *,
    strict: bool = False,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    granted: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    for m in members:
        member_type = str(m.get("member_type") or "").strip().lower()
        member_id = str(m.get("member_id") or "").strip()
        perm = str(m.get("perm") or "full_access").strip().lower()

        if member_type == "email" and (_is_placeholder_email(member_id) or not _is_valid_email(member_id)):
            err = {
                "member_type": member_type,
                "member_id": member_id,
                "perm": perm,
                "error": "invalid_or_placeholder_email",
            }
            failed.append(err)
            if strict:
                raise RuntimeError(f"无效邮箱：{member_id}")
            continue

        try:
            client.add_permission_member(
                app_token,
                member_id=member_id,
                member_type=member_type,
                perm=perm,
                file_type="bitable",
            )
            granted.append({"member_type": member_type, "member_id": member_id, "perm": perm})
        except Exception as e:
            err = {
                "member_type": member_type,
                "member_id": member_id,
                "perm": perm,
                "error": str(e),
            }
            failed.append(err)
            if strict:
                raise
    return granted, failed


def try_transfer_owner(
    client: FeishuBitableClient,
    app_token: str,
    *,
    member_id: str,
    member_type: str,
    email: str = "",
    strict: bool = False,
) -> dict[str, Any]:
    mid = str(member_id or "").strip()
    mtype = _normalize_member_type(member_type)
    if not mid:
        return {"attempted": False, "ok": False, "member_id": "", "member_type": mtype, "error": "missing_member_id"}
    if mtype == "email" and (_is_placeholder_email(mid) or not _is_valid_email(mid)):
        return {"attempted": False, "ok": False, "member_id": mid, "member_type": mtype, "error": "invalid_email"}
    try:
        result = client.transfer_permission_owner(
            app_token,
            member_id=mid,
            member_type=mtype,
            file_type="bitable",
        )
        return {
            "attempted": True,
            "ok": True,
            "member_id": mid,
            "member_type": mtype,
            "email": str(email or "").strip(),
            "result": result,
        }
    except Exception as e:
        if strict:
            raise
        return {
            "attempted": True,
            "ok": False,
            "member_id": mid,
            "member_type": mtype,
            "email": str(email or "").strip(),
            "error": str(e),
        }


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
        try:
            updated = client.update_app_name(app_token, args.name)
            if isinstance(updated, dict) and updated:
                app_meta.update(updated)
        except Exception:
            pass
    else:
        app = client.create_app(args.name, folder_token or None)
        app_token = str(app.get("app_token", "")).strip()
        if not app_token:
            raise RuntimeError("创建多维表格失败：未返回 app_token")
        app_meta = app

    removed_tables = cleanup_default_empty_tables(client, app_token, force=args.cleanup_force)
    tables = ensure_tables(client, app_token)
    for name, info in tables.items():
        info["fields"] = ensure_fields(client, app_token, info["table_id"])
    share_members = resolve_share_members(args, feishu_cfg)
    granted_members: list[dict[str, str]] = []
    failed_members: list[dict[str, str]] = []
    if share_members:
        granted_members, failed_members = ensure_share_members(
            client,
            app_token,
            share_members,
            strict=args.share_strict,
        )
    cfg_transfer_owner = feishu_cfg.get("transfer_owner")
    transfer_owner = (not args.skip_owner_transfer) and _truthy(cfg_transfer_owner, default=True)
    transfer_owner_email = _resolve_transfer_owner_email(args, feishu_cfg)
    cached_owner_identity = load_owner_identity_cache(args.owner_identity_cache)
    cfg_member_id = str(
        feishu_cfg.get("transfer_owner_member_id")
        or feishu_cfg.get("transferOwnerMemberId")
        or ""
    ).strip()
    cfg_member_type = _normalize_member_type(
        str(
            feishu_cfg.get("transfer_owner_member_type")
            or feishu_cfg.get("transferOwnerMemberType")
            or "openid"
        )
    )

    owner_member_id = ""
    owner_member_type = "openid"
    owner_identity_source = ""

    if args.transfer_owner_member_id.strip():
        owner_member_id = args.transfer_owner_member_id.strip()
        owner_member_type = _normalize_member_type(args.transfer_owner_member_type)
        owner_identity_source = "cli_member_id"
    elif cfg_member_id:
        owner_member_id = cfg_member_id
        owner_member_type = cfg_member_type
        owner_identity_source = "config_member_id"
    elif cached_owner_identity.get("member_id"):
        owner_member_id = str(cached_owner_identity.get("member_id") or "").strip()
        owner_member_type = _normalize_member_type(cached_owner_identity.get("member_type") or "openid")
        owner_identity_source = "cache_member_id"

    if not owner_member_id and transfer_owner_email and _is_valid_email(transfer_owner_email):
        try:
            resolved_id = client.resolve_user_id_by_email(
                transfer_owner_email,
                user_id_type=args.transfer_owner_id_type,
            )
        except Exception:
            resolved_id = ""
        if resolved_id:
            owner_member_id = resolved_id
            owner_member_type = _normalize_member_type(args.transfer_owner_id_type)
            owner_identity_source = "email_resolved"

    if not share_members and not args.allow_bot_only and not (transfer_owner and owner_member_id):
        raise RuntimeError(
            "缺少真实用户编辑权限配置。请至少提供一种："
            "--owner-email / --share-member / feishu.owner_email / FAVORITESHUB_OWNER_EMAIL；"
            "或提供可用于所有权转移的 member_id / 可解析邮箱。"
            "如确需仅机器人可编辑，请显式添加 --allow-bot-only。"
        )

    owner_transfer = {"attempted": False, "ok": False, "member_id": "", "member_type": "", "error": ""}
    if transfer_owner and owner_member_id:
        owner_transfer = try_transfer_owner(
            client,
            app_token,
            member_id=owner_member_id,
            member_type=owner_member_type,
            email=transfer_owner_email,
            strict=args.transfer_owner_strict,
        )
        owner_transfer["source"] = owner_identity_source
        if owner_transfer.get("ok"):
            save_owner_identity_cache(
                args.owner_identity_cache,
                {
                    "member_id": owner_member_id,
                    "member_type": owner_member_type,
                    "email": transfer_owner_email,
                },
            )
    elif transfer_owner and not owner_member_id:
        owner_transfer = {
            "attempted": False,
            "ok": False,
            "member_id": "",
            "member_type": "",
            "error": "missing_transfer_owner_identity",
            "source": owner_identity_source or "none",
        }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_data = {
        "generated_at": utc_now_iso(),
        "app_token": app_token,
        "app_name": app_meta.get("name", args.name),
        "app_url": app_meta.get("url"),
        "tables": tables,
        "removed_tables": removed_tables,
        "granted_members": granted_members,
        "failed_members": failed_members,
        "owner_transfer": owner_transfer,
        "owner_identity_cache": args.owner_identity_cache,
    }
    out_path.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "out": str(out_path),
                "app_token": app_token,
                "tables": list(tables.keys()),
                "removed_tables": removed_tables,
                "granted_members": granted_members,
                "failed_members": failed_members,
                "owner_transfer": owner_transfer,
                "owner_identity_cache": args.owner_identity_cache,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
