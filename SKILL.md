---
name: favorites-hub-feishu-table
description: "Use when aggregating favorites/bookmarks/starred items from GitHub, X, Xiaohongshu, Douyin, or ad-hoc links into Feishu Bitable with platform-separated tables and unified fields."
metadata:
  openclaw:
    emoji: "⭐"
    requires:
      bins:
        - openclaw
        - jq
        - gh
---

# FavoritesHub-FeishuTable

将多平台收藏内容聚合到飞书多维表格。  
本技能优先复用现有能力：`github`、`xiaohongshu-skills`、`openclaw browser`、`feishu_bitable_*`。

## 适用范围

- 平台键：`github`、`x`、`xiaohongshu`、`douyin`、`other`
- 子表展示名：`github`、`x`、`小红书`、`抖音`、`other`
- 字段固定为：
  - `标题`
  - `所属平台`
  - `状态`
  - `链接`
  - `内容梗概`
  - `收藏或星标数量`
  - `收录时间`
- 用户未提供某个平台时，跳过该平台，不报错。

## 配置兜底

跨环境按以下优先级取飞书配置（从高到低）：

1. 命令行参数：`--app-id --app-secret --base-url`
2. 环境变量：`FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_BASE_URL`
3. 用户配置文件：
   - 通过 `--config /path/to/favoriteshub.config.json` 指定
   - 或环境变量 `FAVORITESHUB_CONFIG`
   - 或默认查找 `./favoriteshub.config.json`、`~/.openclaw/favoriteshub.config.json`
4. OpenClaw 配置：`channels.feishu.appId/appSecret/domain`

示例配置见：`references/favoriteshub-config.example.json`

## 工作流

### 1) 初始化（一次性）

1. 初始化飞书多维表格（自动）：
   - 运行 `scripts/init_feishu_bitable.py`。
   - 若未提供 `app_token`，脚本会自动创建新多维表格。
   - 自动确保 5 个子表（`github/x/小红书/抖音/other`）和固定字段存在。
   - 自动把主字段重命名为 `标题`，`所属平台/状态` 设为单选。
   - 自动清理默认空白子表（如 `数据表/表格1`）。
   - 默认要求配置真实用户可编辑权限（`--owner-email` / `feishu.owner_email` / `--share-member`）。
   - 分享授权失败默认不中断初始化（可用 `--share-strict` 改为严格失败）。
   - 默认会把文档所有权转移到真实用户（可用 `--skip-owner-transfer` 关闭）。
2. 初始化结果会写入 `output/feishu-target.json`（后续同步复用）。

### 2) 同步（常规执行）

1. 运行采集脚本：
  - `scripts/collect_github_stars.sh`
  - `scripts/collect_x_bookmarks.sh`
  - `scripts/collect_xhs_favorites.sh`
  - `scripts/collect_douyin_favorites_probe.sh`
  - （可选）`scripts/add_other_link_record.sh <url> "<summary>"`
  - `scripts/merge_to_feishu_payload.sh`
  - 采集增量策略：
    - 首次（无 `output/collector-state.json`）：全量扫描当前可滚动收藏列表
    - 后续：命中“上次头部边界链接”即停止，减少重复遍历
    - 可用 `COLLECT_LIMIT` 限制单次最大采集条数（默认 `0` 表示不限制）
2. 读取 `output/feishu-payload.json`。
3. 执行 `scripts/sync_payload_to_feishu.py`，以 `所属平台 + 链接` 作为去重键写入对应子表：
   - 默认 `create-only`：已存在跳过，不重复写入
   - 可切换 `create-or-update`：已存在则更新
   - 不存在：创建新记录
   - 新记录默认 `状态=未学习`（更新记录不覆盖既有状态）
   - `标题` 优先从链接页元数据解析（`og:title` / `twitter:title` / `<title>`），失败自动回退并缓存
   - `内容梗概` 由 OpenClaw 自主读取链接语义并中文概括（不照抄原文，且避免“该仓库/该收藏”开头）
   - 摘要结果自动缓存到 `output/summary-cache.json`，减少重复调用
   - 标题结果自动缓存到 `output/title-cache.json`，减少重复解析
   - `收藏或星标数量` 按整数写入，GitHub/X/小红书/抖音若采集到均会写入

### 3) 临时链接入库（other）

1. 接收用户给出的任意链接（非四大平台）。
2. 由 OpenClaw 自动读取链接内容并生成初始摘要（可选手工覆盖）。
3. 调用 `scripts/add_other_link_record.sh <url> \"<summary>\"` 生成/更新 `output/other-links.json`（`<summary>` 可省略）。
4. 写入 `other` 子表：
   - `所属平台=other`
   - `链接=<url>`
   - `内容梗概=<summary>`
   - `收藏或星标数量` 可空
   - `收录时间=<当前时间>`

## 执行命令

```bash
# 一键只读采集 + 合并 payload
./scripts/run_phase2_probes.sh

# 初始化飞书目标（首次）
python3 ./scripts/init_feishu_bitable.py --owner-email "you@example.com"

# 初始化（显式指定配置文件）
python3 ./scripts/init_feishu_bitable.py --config ./favoriteshub.config.json

# 初始化（显式传入凭据）
python3 ./scripts/init_feishu_bitable.py --app-id "cli_xxx" --app-secret "sec_xxx"

# 初始化并自动授权协作者（示例）
python3 ./scripts/init_feishu_bitable.py --share-member "email:you@example.com:full_access"

# 初始化并绑定真实用户编辑权限（推荐）
python3 ./scripts/init_feishu_bitable.py --owner-email "you@example.com"

# 初始化并在所有权转移失败时立即退出（可选）
python3 ./scripts/init_feishu_bitable.py --owner-email "you@example.com" --transfer-owner-strict

# 同步 payload 到飞书
python3 ./scripts/sync_payload_to_feishu.py

# 同步（显式指定配置文件）
python3 ./scripts/sync_payload_to_feishu.py --config ./favoriteshub.config.json

# 同步（可选显式指定摘要模式，默认即 openclaw-native）
python3 ./scripts/sync_payload_to_feishu.py --summary-mode openclaw-native

# 一键全流程（无 target 时会自动初始化）
./scripts/sync_all_to_feishu.sh

# 一键全流程（带配置文件）
./scripts/sync_all_to_feishu.sh output/feishu-target.json output/feishu-payload.json ./favoriteshub.config.json

# 单独运行（示例）
./scripts/collect_github_stars.sh 0
./scripts/collect_x_bookmarks.sh 0
./scripts/collect_xhs_favorites.sh 0
./scripts/collect_douyin_favorites_probe.sh 0
./scripts/add_other_link_record.sh "https://example.com/post/1" "示例梗概"
./scripts/merge_to_feishu_payload.sh
python3 ./scripts/sync_payload_to_feishu.py --dry-run

# 限制本次最多采集 100 条（可选）
COLLECT_LIMIT=100 ./scripts/run_phase2_probes.sh
```

## 失败处理

- `x` 未登录：`collect_x_bookmarks.sh` 会输出 `requires_login=true`，跳过写入该平台。
- `xiaohongshu` 未登录：`collect_xhs_favorites.sh` 输出 `status=needs_login`，在当前 `openclaw browser` 窗口登录后重试。
- `douyin` 未登录：输出 `status=needs_login`，等待用户登录后重试。
- 无需外部 API key：默认使用 OpenClaw 内置摘要流程，不阻塞写入。
- 未配置真实用户权限：`init_feishu_bitable.py` 默认会报错并提示补齐 `owner_email/share_members`（可用 `--allow-bot-only` 强制跳过）。
- 分享授权失败：默认记录到 `failed_members` 但不中断；可用 `--share-strict` 强制报错退出。
- 所有权转移失败：默认记录到 `owner_transfer` 但不中断；可用 `--transfer-owner-strict` 强制报错退出。
- 飞书写入失败：保留 payload 与 target 配置，不丢弃采集结果，允许重放写入。

## 约束

- 不在脚本中写死用户路径，统一使用相对路径和环境变量。
- 不记录敏感凭据到文件。
- 合并阶段去重，避免重复入库。

## 参考

- 字段与类型：`references/feishu-schema.md`
- 目标配置格式：`references/feishu-target-format.md`
- 配置文件示例：`references/favoriteshub-config.example.json`
- 当前能力与缺口：`references/platform-gaps.md`
