#!/usr/bin/env python3
"""Feishu Bitable API helpers for FavoritesHub skill."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class FeishuApiError(RuntimeError):
    """Raised when Feishu OpenAPI returns non-zero code."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_to_ms(value: str | None) -> int:
    if not value:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _normalize_domain(raw: str | None) -> str:
    if not raw:
        return "https://open.feishu.cn"
    val = raw.strip().rstrip("/")
    if not val:
        return "https://open.feishu.cn"
    low = val.lower()
    if low in {"feishu", "cn", "china"}:
        return "https://open.feishu.cn"
    if low in {"lark", "intl", "international"}:
        return "https://open.larksuite.com"
    # Some OpenClaw channel configs use logical labels (e.g. "feishu") instead of hostnames.
    if "." not in val and "://" not in val:
        return "https://open.feishu.cn"
    if val.startswith("http://") or val.startswith("https://"):
        return val
    return f"https://{val}"


def load_user_config(config_path: str | None = None) -> dict[str, Any]:
    """Load optional user config for cross-environment compatibility."""
    candidates: list[Path] = []
    if config_path:
        candidates.append(Path(config_path))
    env_cfg = os.getenv("FAVORITESHUB_CONFIG", "").strip()
    if env_cfg:
        candidates.append(Path(env_cfg))
    candidates.extend(
        [
            Path.cwd() / "favoriteshub.config.json",
            Path.home() / ".openclaw" / "favoriteshub.config.json",
        ]
    )
    for p in candidates:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                continue
    return {}


def _load_openclaw_feishu_config() -> dict[str, Any]:
    config_path = os.getenv("OPENCLAW_CONFIG_PATH", str(Path.home() / ".openclaw" / "openclaw.json"))
    p = Path(config_path)
    if not p.is_file():
        return {}
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return (((cfg.get("channels") or {}).get("feishu")) or {})


def _pick_nonempty(*values: str) -> str:
    for v in values:
        s = (v or "").strip()
        if s:
            return s
    return ""


def _resolve_cfg_value(cfg: dict[str, Any], *keys: str) -> str:
    for k in keys:
        if k in cfg:
            val = _resolve_secret_like(cfg.get(k))
            if val:
                return val
    return ""


def load_feishu_credentials(
    *,
    config: dict[str, Any] | None = None,
    override_app_id: str = "",
    override_app_secret: str = "",
    override_base_url: str = "",
) -> tuple[str, str, str]:
    """Resolve Feishu credentials with fallback priority.

    Priority (high -> low):
    1) explicit overrides (--app-id/--app-secret/--base-url)
    2) environment (FEISHU_APP_ID/FEISHU_APP_SECRET/FEISHU_BASE_URL)
    3) user config file (favoriteshub.config.json / FAVORITESHUB_CONFIG)
    4) OpenClaw config (channels.feishu.*)
    5) defaults (base_url only)
    """
    user_cfg = config or {}
    user_feishu_cfg = ((user_cfg.get("feishu") or {}) if isinstance(user_cfg, dict) else {})
    oc_feishu_cfg = _load_openclaw_feishu_config()

    app_id = _pick_nonempty(
        override_app_id,
        _get_env_or_dotenv("FEISHU_APP_ID"),
        _resolve_cfg_value(user_feishu_cfg, "app_id", "appId"),
        _resolve_cfg_value(oc_feishu_cfg, "appId"),
    )
    app_secret = _pick_nonempty(
        override_app_secret,
        _get_env_or_dotenv("FEISHU_APP_SECRET"),
        _resolve_cfg_value(user_feishu_cfg, "app_secret", "appSecret"),
        _resolve_cfg_value(oc_feishu_cfg, "appSecret"),
    )
    base_url = _pick_nonempty(
        override_base_url,
        os.getenv("FEISHU_BASE_URL", "").strip(),
        _resolve_cfg_value(user_feishu_cfg, "base_url", "baseUrl", "domain"),
        _resolve_cfg_value(oc_feishu_cfg, "domain"),
    )

    if not app_id or not app_secret:
        raise RuntimeError(
            "缺少飞书凭据。可选兜底方式："
            "1) 命令行 --app-id/--app-secret；"
            "2) 环境变量 FEISHU_APP_ID/FEISHU_APP_SECRET；"
            "3) 配置文件 favoriteshub.config.json（或 FAVORITESHUB_CONFIG 指向它）；"
            "4) OpenClaw 配置 channels.feishu.appId/appSecret。"
        )
    return app_id, app_secret, _normalize_domain(base_url)


def _resolve_secret_like(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        # ${ENV_NAME}
        m = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", text)
        if m:
            return _get_env_or_dotenv(m.group(1))
        # $ENV_NAME
        m2 = re.fullmatch(r"\$([A-Za-z_][A-Za-z0-9_]*)", text)
        if m2:
            return _get_env_or_dotenv(m2.group(1))
        return text
    if isinstance(value, dict):
        source = str(value.get("source", "")).strip().lower()
        if source == "env":
            key = str(value.get("id", "")).strip()
            return _get_env_or_dotenv(key) if key else ""
        # Unknown secret source in standalone scripts: treat as unresolved.
        return ""
    return str(value).strip()


_DOTENV_CACHE: dict[str, str] | None = None


def _load_dotenv_map() -> dict[str, str]:
    global _DOTENV_CACHE
    if _DOTENV_CACHE is not None:
        return _DOTENV_CACHE
    result: dict[str, str] = {}
    candidates = [
        os.getenv("OPENCLAW_ENV_PATH", "").strip(),
        str(Path.home() / ".openclaw" / ".env"),
    ]
    for path in candidates:
        if not path:
            continue
        p = Path(path)
        if not p.is_file():
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                key = k.strip()
                val = v.strip().strip('"').strip("'")
                if key and key not in result:
                    result[key] = val
        except OSError:
            pass
    _DOTENV_CACHE = result
    return result


def _get_env_or_dotenv(key: str) -> str:
    val = os.getenv(key, "").strip()
    if val:
        return val
    return _load_dotenv_map().get(key, "").strip()


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    req_headers = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        req_headers.update(headers)
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url=url, data=body, headers=req_headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {url}: {raw}") from e


class FeishuBitableClient:
    def __init__(self, app_id: str, app_secret: str, base_url: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self._tenant_token: str | None = None

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        base = f"{self.base_url}{path}"
        if not params:
            return base
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        return f"{base}?{query}" if query else base

    def _auth_headers(self) -> dict[str, str]:
        if not self._tenant_token:
            self._tenant_token = self.get_tenant_access_token()
        return {"Authorization": f"Bearer {self._tenant_token}"}

    @staticmethod
    def _ensure_ok(payload: dict[str, Any], api_name: str) -> dict[str, Any]:
        code = payload.get("code")
        if code not in (0, "0", None):
            msg = payload.get("msg") or payload.get("message") or "unknown error"
            raise FeishuApiError(f"{api_name} failed: code={code}, msg={msg}")
        return payload

    def get_tenant_access_token(self) -> str:
        url = self._url("/open-apis/auth/v3/tenant_access_token/internal")
        data = {"app_id": self.app_id, "app_secret": self.app_secret}
        payload = self._ensure_ok(_http_json("POST", url, data=data), "tenant_access_token")
        token = payload.get("tenant_access_token")
        if not token:
            raise FeishuApiError("tenant_access_token missing in response")
        return str(token)

    def create_app(self, name: str, folder_token: str | None = None) -> dict[str, Any]:
        url = self._url("/open-apis/bitable/v1/apps")
        data: dict[str, Any] = {"name": name}
        if folder_token:
            data["folder_token"] = folder_token
        payload = self._ensure_ok(
            _http_json("POST", url, headers=self._auth_headers(), data=data),
            "bitable.app.create",
        )
        return (payload.get("data") or {}).get("app") or {}

    def update_app_name(self, app_token: str, name: str) -> dict[str, Any]:
        """Best-effort rename for bitable app."""
        last_err: Exception | None = None
        for method in ("PUT", "PATCH"):
            try:
                url = self._url(f"/open-apis/bitable/v1/apps/{app_token}")
                payload = self._ensure_ok(
                    _http_json(method, url, headers=self._auth_headers(), data={"name": name}),
                    f"bitable.app.update.{method.lower()}",
                )
                return (payload.get("data") or {}).get("app") or {}
            except Exception as e:  # pragma: no cover
                last_err = e
                continue
        if last_err:
            raise last_err
        raise FeishuApiError("update_app_name failed")

    def list_tables(self, app_token: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            url = self._url(
                f"/open-apis/bitable/v1/apps/{app_token}/tables",
                {"page_size": 100, "page_token": page_token},
            )
            payload = self._ensure_ok(
                _http_json("GET", url, headers=self._auth_headers()),
                "bitable.appTable.list",
            )
            data = payload.get("data") or {}
            items.extend(data.get("items") or [])
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
        return items

    def create_table(self, app_token: str, name: str) -> dict[str, Any]:
        url = self._url(f"/open-apis/bitable/v1/apps/{app_token}/tables")
        payload = self._ensure_ok(
            _http_json("POST", url, headers=self._auth_headers(), data={"table": {"name": name}}),
            "bitable.appTable.create",
        )
        return (payload.get("data") or {}).get("table") or {}

    def update_table_name(self, app_token: str, table_id: str, name: str) -> dict[str, Any]:
        url = self._url(f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}")
        payload = self._ensure_ok(
            _http_json("PUT", url, headers=self._auth_headers(), data={"name": name}),
            "bitable.appTable.update",
        )
        return (payload.get("data") or {}).get("table") or {}

    def delete_table(self, app_token: str, table_id: str) -> None:
        url = self._url(f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}")
        self._ensure_ok(
            _http_json("DELETE", url, headers=self._auth_headers()),
            "bitable.appTable.delete",
        )

    def list_fields(self, app_token: str, table_id: str) -> list[dict[str, Any]]:
        url = self._url(f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields", {"page_size": 500})
        payload = self._ensure_ok(
            _http_json("GET", url, headers=self._auth_headers()),
            "bitable.appTableField.list",
        )
        return (payload.get("data") or {}).get("items") or []

    def create_field(self, app_token: str, table_id: str, field_name: str, field_type: int) -> dict[str, Any]:
        url = self._url(f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields")
        payload = self._ensure_ok(_http_json("POST", url, headers=self._auth_headers(), data={"field_name": field_name, "type": field_type}), "bitable.appTableField.create")
        return (payload.get("data") or {}).get("field") or {}

    def create_field_with_property(
        self,
        app_token: str,
        table_id: str,
        field_name: str,
        field_type: int,
        property_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._url(f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields")
        body: dict[str, Any] = {"field_name": field_name, "type": field_type}
        if property_data:
            body["property"] = property_data
        payload = self._ensure_ok(
            _http_json("POST", url, headers=self._auth_headers(), data=body),
            "bitable.appTableField.create",
        )
        return (payload.get("data") or {}).get("field") or {}

    def update_field(
        self,
        app_token: str,
        table_id: str,
        field_id: str,
        *,
        field_name: str | None = None,
        field_type: int | None = None,
        property_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._url(f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{field_id}")
        body: dict[str, Any] = {}
        if field_name is not None:
            body["field_name"] = field_name
        if field_type is not None:
            body["type"] = field_type
        if property_data is not None:
            body["property"] = property_data
        payload = self._ensure_ok(
            _http_json("PUT", url, headers=self._auth_headers(), data=body),
            "bitable.appTableField.update",
        )
        return (payload.get("data") or {}).get("field") or {}

    def list_records(self, app_token: str, table_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            url = self._url(
                f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                {"page_size": 500, "page_token": page_token, "automatic_fields": "true"},
            )
            payload = self._ensure_ok(
                _http_json("GET", url, headers=self._auth_headers()),
                "bitable.appTableRecord.list",
            )
            data = payload.get("data") or {}
            items.extend(data.get("items") or [])
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
        return items

    def create_record(self, app_token: str, table_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        url = self._url(f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records")
        payload = self._ensure_ok(
            _http_json("POST", url, headers=self._auth_headers(), data={"fields": fields}),
            "bitable.appTableRecord.create",
        )
        return (payload.get("data") or {}).get("record") or {}

    def update_record(self, app_token: str, table_id: str, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        url = self._url(f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}")
        payload = self._ensure_ok(
            _http_json("PUT", url, headers=self._auth_headers(), data={"fields": fields}),
            "bitable.appTableRecord.update",
        )
        return (payload.get("data") or {}).get("record") or {}

    def add_permission_member(
        self,
        token: str,
        *,
        member_id: str,
        member_type: str = "email",
        perm: str = "full_access",
        file_type: str = "bitable",
    ) -> dict[str, Any]:
        """Grant collaborator permission to bitable file.

        Tries drive v1 then v2 for compatibility.
        """
        params = {"type": file_type}
        body = {
            "member_id": member_id,
            "member_type": member_type,
            "perm": perm,
        }
        last_err: Exception | None = None
        for path, api_name in [
            (f"/open-apis/drive/v1/permissions/{token}/members", "drive.permission.member.add.v1"),
            (f"/open-apis/drive/v2/permissions/{token}/members", "drive.permission.member.add.v2"),
        ]:
            try:
                url = self._url(path, params)
                payload = self._ensure_ok(
                    _http_json("POST", url, headers=self._auth_headers(), data=body),
                    api_name,
                )
                return (payload.get("data") or {}).get("member") or {}
            except Exception as e:  # pragma: no cover
                last_err = e
        if last_err:
            raise last_err
        raise FeishuApiError("add_permission_member failed")

    def batch_get_user_ids_by_emails(self, emails: list[str], *, user_id_type: str = "open_id") -> list[dict[str, Any]]:
        """Resolve user IDs from emails via Contact API.

        user_id_type: open_id / user_id / union_id
        """
        normalized = [str(x).strip() for x in emails if str(x).strip()]
        if not normalized:
            return []
        url = self._url(
            "/open-apis/contact/v3/users/batch_get_id",
            {"user_id_type": user_id_type},
        )
        payload = self._ensure_ok(
            _http_json(
                "POST",
                url,
                headers=self._auth_headers(),
                data={"emails": normalized},
            ),
            "contact.user.batch_get_id",
        )
        data = payload.get("data") or {}
        return data.get("user_list") or []

    def resolve_user_id_by_email(self, email: str, *, user_id_type: str = "open_id") -> str:
        e = str(email or "").strip()
        if not e:
            return ""
        items = self.batch_get_user_ids_by_emails([e], user_id_type=user_id_type)
        if not items:
            return ""
        for item in items:
            em = str(item.get("email") or "").strip().lower()
            uid = str(item.get("user_id") or "").strip()
            if em == e.lower() and uid:
                return uid
        uid = str((items[0] or {}).get("user_id") or "").strip()
        return uid

    def transfer_permission_owner(
        self,
        token: str,
        *,
        member_id: str,
        member_type: str = "openid",
        file_type: str = "bitable",
    ) -> dict[str, Any]:
        """Transfer file ownership to target member.

        Feishu/Lark API variants differ across versions, so this method tries
        multiple compatible endpoints/methods and returns first success.
        """
        member_type_normalized = str(member_type or "").strip().lower()
        if member_type_normalized in {"open_id", "openid", "open-id"}:
            member_type_normalized = "openid"
        elif member_type_normalized in {"user_id", "userid", "user-id"}:
            member_type_normalized = "userid"
        elif member_type_normalized in {"union_id", "unionid", "union-id"}:
            member_type_normalized = "unionid"

        body = {
            "type": file_type,
            "token": token,
            "owner": {
                "member_type": member_type_normalized or "openid",
                "member_id": member_id,
            },
            "remove_old_owner": False,
            "cancel_notify": False,
        }
        last_err: Exception | None = None
        # Preferred endpoint in newer docs.
        try:
            url = self._url("/open-apis/drive/permission/member/transfer")
            payload = self._ensure_ok(
                _http_json("POST", url, headers=self._auth_headers(), data=body),
                "drive.permission.member.transfer",
            )
            return payload.get("data") or {}
        except Exception as e:  # pragma: no cover
            last_err = e

        params = {"type": file_type}
        legacy_body = {"member_id": member_id, "member_type": member_type_normalized or "openid"}
        for method in ("POST", "PUT"):
            for path, api_name in [
                (f"/open-apis/drive/v1/permissions/{token}/members/transfer_owner", "drive.permission.member.transfer.v1"),
                (f"/open-apis/drive/v2/permissions/{token}/members/transfer_owner", "drive.permission.member.transfer.v2"),
                (f"/open-apis/drive/v1/permissions/{token}/members/transfer", "drive.permission.member.transfer_alt.v1"),
                (f"/open-apis/drive/v2/permissions/{token}/members/transfer", "drive.permission.member.transfer_alt.v2"),
            ]:
                try:
                    url = self._url(path, params)
                    payload = self._ensure_ok(
                        _http_json(method, url, headers=self._auth_headers(), data=legacy_body),
                        api_name,
                    )
                    return (payload.get("data") or {}).get("member") or {}
                except Exception as e:  # pragma: no cover
                    last_err = e
        if last_err:
            raise last_err
        raise FeishuApiError("transfer_permission_owner failed")
