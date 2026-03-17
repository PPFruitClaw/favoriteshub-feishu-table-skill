# FavoritesHub-FeishuTable

## 中文说明

`FavoritesHub-FeishuTable` 是一个 OpenClaw Skill，用于把多个平台的收藏内容聚合到飞书多维表格。

支持平台：
- 抖音（Douyin）
- 小红书（Xiaohongshu）
- X（Twitter）
- GitHub（Stars）
- 其他链接（手动补充）

核心能力：
- 自动初始化飞书多维表（含平台子表与统一字段）
- 按平台采集收藏/星标内容并合并为统一 payload
- 默认增量写入（只新增，避免重复）
- 采集侧支持“首次全量、后续命中边界即停止”
- 支持跨环境配置兜底（CLI 参数 / 环境变量 / 用户配置文件 / OpenClaw 配置）
- `内容梗概` 默认由 OpenClaw 自主读链接并生成中文概括（缓存复用，失败自动兜底）
- 默认要求配置真实飞书用户编辑权限（owner_email/share_members）
- 授权失败默认不中断初始化，失败明细写入 `failed_members`（可用 `--share-strict` 严格模式）
- 默认自动尝试转移文档所有权给真实用户（失败明细写入 `owner_transfer`）
- 支持按邮箱自动解析并缓存 `member_id`（首次后可无感复用）

默认初始化结果：
- 多维表名称：`FavoritesHub-多平台收藏中心`
- 子表：`github`、`x`、`小红书`、`抖音`、`other`

统一字段：
- 标题（主字段，多行文本）
- 所属平台
- 状态（单选：已学习/已过期/未学习/重点收藏，默认未学习）
- 链接
- 内容梗概
- 收藏或星标数量
- 收录时间

数量字段说明：
- `收藏或星标数量` 使用整数写入
- GitHub / X / 小红书 / 抖音若采集到数量均会写入，不再仅限 GitHub
- 标题优先从链接页面解析（`og:title` / `twitter:title` / `title`），失败时自动回退

快速开始：
```bash
# 1) 初始化飞书多维表（首次）
python3 ./scripts/init_feishu_bitable.py --owner-email "you@example.com"

# 2) 采集并合并 payload
./scripts/run_phase2_probes.sh

# 3) 同步到飞书
python3 ./scripts/sync_payload_to_feishu.py
```

可选一键流程：
```bash
./scripts/sync_all_to_feishu.sh
```

注意：
- 本仓库默认不提交 `output/` 运行产物与本地凭据。
- 使用前请按 `references/favoriteshub-config.example.json` 配置飞书凭据。

---

## English

`FavoritesHub-FeishuTable` is an OpenClaw Skill that aggregates favorites/bookmarks/starred items from multiple platforms into Feishu Bitable.

Supported sources:
- Douyin
- Xiaohongshu
- X (Twitter)
- GitHub Stars
- Manual "Other" links

Key capabilities:
- Auto-initialize Feishu Bitable (platform sub-tables + unified schema)
- Collect per-platform favorites/stars and merge into one payload
- Incremental sync by default (`create-only`) to avoid duplicates
- Collector strategy: full scan on first run, boundary-stop on subsequent runs
- Multi-environment config fallback (CLI args / env vars / user config / OpenClaw config)
- `Summary` is generated in Chinese by OpenClaw native reading/summarization by default (with cache + fallback)
- Requires a real Feishu user editor permission by default (owner_email/share_members)
- Ownership transfer to the real user is attempted by default (result in `owner_transfer`)
- Owner member ID can be auto-resolved from email and cached for later no-touch runs

Default first-run shape:
- Bitable name: `FavoritesHub-多平台收藏中心`
- Sub-tables: `github`, `x`, `小红书`, `抖音`, `other`

Unified fields:
- Title (primary)
- Platform
- Status (single select: 未学习/已学习/已过期/重点收藏; default 未学习)
- Link
- Summary
- Favorite/Star Count
- Ingested Time

Count behavior:
- `Favorite/Star Count` is stored as integer
- If available, GitHub/X/Xiaohongshu/Douyin counts are all written (not GitHub-only)
- Title prefers link-page metadata (`og:title` / `twitter:title` / `title`) with automatic fallback

Quick start:
```bash
# 1) Initialize Feishu target (first time)
python3 ./scripts/init_feishu_bitable.py --owner-email "you@example.com"

# 2) Collect and merge payload
./scripts/run_phase2_probes.sh

# 3) Sync to Feishu
python3 ./scripts/sync_payload_to_feishu.py
```

Optional one-command flow:
```bash
./scripts/sync_all_to_feishu.sh
```

Notes:
- Runtime artifacts and local credentials are excluded by default (`output/`, local config).
- Configure Feishu credentials using `references/favoriteshub-config.example.json`.
