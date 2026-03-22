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
- 字段结构以 `references/feishu-schema.md` 为准：
  - 所有子表共享一组基础字段
  - 允许平台扩展字段存在（如 X 的 `作者主页`、GitHub 的 `项目名称`）
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
   - 未显式提供 member_id 时，会按邮箱自动解析并缓存 owner 身份到 `output/owner-identity.json`，后续可无感复用。
2. 初始化结果会写入 `output/feishu-target.json`（后续同步复用）。

### 2) 同步（常规执行）

> 字段定义、平台扩展字段、以及写入映射细节，统一看 `references/feishu-schema.md`。
> 当前 SKILL.md 只保留主流程、验收顺序和高优先级规则，避免主文件越写越胖。

#### 2.1 稳定脚本采集的平台

1. 运行采集脚本：
  - `scripts/collect_github_stars.sh`
  - `scripts/collect_x_bookmarks.sh`
  - `scripts/collect_xhs_favorites.sh`
  - （可选）`scripts/add_other_link_record.sh <url> "<summary>"`
  - `scripts/merge_to_feishu_payload.sh`
  - 采集增量策略：
    - 首次（无 `output/collector-state.json`）：全量扫描当前可滚动收藏列表
    - 后续：命中“上次头部边界链接”即停止，减少重复遍历
    - 可用 `COLLECT_LIMIT` 限制单次最大采集条数（默认 `0` 表示不限制）

#### 2.2 抖音（当前为流程主导，非脚本主导）

> 当前抖音收藏采集的“正式方案”是**流程规则 + 人机协作**，而不是稳定脚本主导。
> `scripts/collect_douyin_favorites_probe.sh`、`scripts/probe_douyin_detail_flow.js` 等仅可视为探针 / 过渡排障工具，
> **不能**把它们当成已经定型的正式采集器。

抖音当前正式主流程：
- 进入 `收藏 -> 视频`
- 点击第一条视频进入详情播放态
- 在详情流中使用 `ArrowDown` 逐条切换
- 每切到一条新内容后，优先读取当前详情右侧收藏按钮的 DOM 状态：`data-e2e="video-player-collect"` 与 `data-e2e-state`
- 默认先按“视频型内容”处理
- 遇到特殊结构时，再分流到“文章/跳转型”
- 一旦收藏按钮不再满足 `data-e2e="video-player-collect"` + `data-e2e-state="video-player-is-collected"`，立即停止

抖音当前强规则：
- **抖音特别规则（强制）**：仅打开 `showTab=collection` 不可靠，必须显式切换到“收藏”tab，再确认内层“视频”tab 已选中；若页面仍停留在“作品”页，则本次采集视为未进入正确状态。
- **抖音新版主流程（强制）**：进入 `收藏 -> 视频` 后，**必须点击第一条视频进入详情播放态**，随后在**视频详情流**里逐条向下切换；**不要再把“收藏列表页直接滚动抓全量”当成主方案**，列表页只负责提供入口首条。
- **抖音详情态验收信号（强制校验）**：进入首条视频后，URL 通常表现为 `user/self?...modal_id=<视频ID>...`；后续是否成功切到下一条，优先看 `modal_id` 是否变化，而不是看 `/video/...` 路径。若没有进入 `modal_id` 详情态，就说明还没进入正确采集链路。
- **抖音收藏态主判据（当前最高优先级）**：详情页右侧收藏按钮应优先通过 DOM 语义字段识别，而不是通过颜色、数字位置或全页文本猜测。当前已确认的收藏按钮标识为 `data-e2e="video-player-collect"`；当前已收藏状态已确认可读为 `data-e2e-state="video-player-is-collected"`。后续流程中，是否仍处于收藏流，应优先以该状态字段为主判据。
- **抖音视频型继续条件（当前默认主路径）**：由于当前真实收藏分布中视频是绝大多数、图文/文章是少数，执行时应默认先按“视频型内容”处理。每次 `ArrowDown` 后，若同时满足 `(1) 主内容变化, (2) modal_id 变化, (3) 页面仍是标准视频详情播放器结构, (4) 当前详情页存在 `data-e2e="video-player-collect"` 且其 `data-e2e-state="video-player-is-collected"``，则可视为“成功切到下一条仍在收藏流内的视频项”，继续执行。
- **抖音内容类型不要误判（强制）**：`AI笔记`、`合集`、`听抖音`、`看相关` 等元素可能出现在正常视频详情页中，它们本身**不能**直接作为“已切到图文/文章”或“已越界推荐流”的依据。判断内容类型时，优先看“中央主区域是否仍是正常可播放视频主体”，而不是只看这些附加标签。
- **抖音文章/跳转型识别（强规则）**：少数收藏内容不是普通视频，而是“文章/跳转型”详情页。其典型信号是：中央主区域出现“当前内容暂时无法播放 / 需要跳转查看完整内容 / 去查看”这类阻断式提示面板，页面重点从“直接播放视频”变成“点击按钮跳转查看完整内容”；与此同时，当前详情页的收藏按钮仍应保持 `data-e2e="video-player-collect"` 且 `data-e2e-state="video-player-is-collected"`。遇到此类内容时，应判定为“仍在收藏流内的文章/跳转型内容”，而**不是**直接判为越界。
- **抖音越界停止条件（当前已验证）**：继续 `ArrowDown` 切到新内容后，若当前详情页的收藏按钮不再满足 `data-e2e="video-player-collect"` + `data-e2e-state="video-player-is-collected"`，则应立即判定“已刷出收藏流，进入普通推荐/普通详情流”，并立刻停止；上一条仍满足收藏态判据的内容，视为真正最后一条收藏内容。注意：`modal_id` 变化只说明“内容切换了”，不能单独证明“还在收藏流内”。
- **抖音三类判定模型（当前推荐）**：
  1. 普通视频型：中央区域是正常视频播放主体，且收藏按钮满足 `data-e2e="video-player-collect"` + `data-e2e-state="video-player-is-collected"` → 继续。
  2. 文章/跳转型：中央区域出现“无法播放 / 去查看 / 跳转查看完整内容”面板，且收藏按钮仍满足 `data-e2e="video-player-collect"` + `data-e2e-state="video-player-is-collected"` → 仍属收藏流，按特殊内容记录。
  3. 非收藏越界型：收藏按钮不再满足 `data-e2e="video-player-collect"` + `data-e2e-state="video-player-is-collected"` → 立即停止。
- **抖音过时方案（明确废弃）**：不要再把“收藏列表页持续滚动到底并直接抓 `/video/` / `/note/` 链接”当成当前主方案；这条旧路容易混入 footer / SEO / 推荐流，也会把“还能继续刷”误判成“还有收藏”。

2. 读取 `output/feishu-payload.json`。
3. 执行 `scripts/sync_payload_to_feishu.py`，以 `所属平台 + 链接` 作为去重键写入对应子表：
   - 默认 `create-only`：已存在跳过，不重复写入
   - 可切换 `create-or-update`：已存在则更新
   - 不存在：创建新记录
   - 新记录默认 `状态=未学习`（更新记录不覆盖既有状态）
   - **脚本主要负责结构化搬运，不负责最终内容质量拍板**：采集、去重、链接、平台、数量、时间这些交给脚本
   - **`标题` 与 `内容梗概` 的最终质量由 OpenClaw 主代理负责**：主代理应读取链接真实内容后，生成简洁、直接、中文、可读的标题与梗概
   - **新增记录的收尾流程（强制）**：凡是本轮新写入 Feishu Bitable 的记录，主代理都必须在入表后立即逐条复核该批新增记录，并亲自重写 `标题` 与 `内容梗概`；脚本生成的标题/摘要只能视为临时占位草稿，**不能**直接作为最终版交付，也**不能**在未人工回写前把任务视为完成。
  - **结构字段补齐也属于收尾的一部分（新增强规则）**：若本轮涉及平台扩展字段（如 X 的 `作者主页`、GitHub 的 `项目名称`），则必须在“标题/梗概润色”之外，额外检查这类结构字段是否已全量补齐。只补一批样本、不做全表缺口检查，不算完成。
  - **完成判定（强制）**：只有当以下条件同时满足时，才能向用户汇报本轮已完成：
    1. 新增记录已入表
    2. 该批新增记录的 `标题` 与 `内容梗概` 已由主代理人工复写完成
    3. 若本轮涉及平台扩展字段，则对应字段缺口已检查为 `0`
  - **推荐分工（已验证）**：
     - 脚本：负责拉取 GitHub stars / X 书签 / 小红书收藏、合并 payload、去重、写入基础结构字段
     - 抖音：当前以正式流程规则 + 主代理/人工协作为主，probe 脚本只负责探测、排障、辅助验证，不应假定为稳定主采集器
     - OpenClaw 主代理：负责读取真实页面内容、亲自提炼中文标题、亲自提炼中文梗概、决定最终文案是否入表；这一步不能外包给脚本自动生成。
   - **标题风格规则**：直接说内容，不要 `GitHub - ...`、`@用户名 · 日期`、链接碎片、导航噪音；能概括主题时，不要只写“xxx 项目”
   - **内容梗概风格规则**：直接进入内容本身，不要用“这条内容… / 这篇内容… / 这条帖子… / 这个项目…”作为固定开头；避免“重点讨论… / 内容围绕… / 建议结合上下文…”这类模板句
   - GitHub 梗概优先写：项目用途、解决的问题、适用场景
   - X 梗概优先写：帖子在讲什么、分享了什么方法/教程/观点/项目
   - 小红书梗概优先写：笔记分享了什么经验、攻略、做法或避坑信息
   - 平台扩展字段（如 GitHub 的 `项目名称`、X 的 `作者主页`）的填写规则与验收要求，统一看 `references/feishu-schema.md` + 下文“验收与回报规则”
   - 抖音梗概优先写：视频讲了什么主题、方法、教程或观点；若原始摘要仍是热门噪音或拼接流，先不要直接入表，应先清洗
   - **统一批处理规则（全平台适用）**：标题和梗概阶段默认按 **20 条一批** 执行：先读取这一批真实链接内容，再由主代理人工撰写并回写，确认风格与质量稳定后再继续下一批。
   - **抖音采集优先级规则**：先保证“链接列表准确”，再做标题/梗概；如果链接集合还不可信（数量对不上、夹带推荐流、重复或误抓），禁止继续批量写文案。
   - **抖音当前推荐执行方式**：优先遵循正式流程（收藏 -> 视频 -> 首条 -> 详情流 ArrowDown -> 读取 `data-e2e="video-player-collect"` 与 `data-e2e-state` 判断是否仍为 `video-player-is-collected`），再由主代理读取当前已渲染内容并抽取链接集合；不要再把“脚本必须完全替代流程本身”当成当前目标。
   - 不要把 `GitHub - ...`、`@用户名 · 日期`、链接碎片、`Skip to content`、`Contribute to development...` 这类页面噪音直接写进最终表格
   - 若批量生成人工文案质量不稳定，优先保持 **20 条一批 + 主代理验收 + 再继续下一批** 的节奏，而不是盲目全量刷新
   - 使用浏览器读取页面内容时，必须遵守：**一次只开 1 个页面，等待加载，再读取，随后立即关闭**；禁止批量同时打开大量页面，避免浏览器内存膨胀
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

# 初始化并显式指定 member_id（可选，优先级最高）
python3 ./scripts/init_feishu_bitable.py --transfer-owner-member-id "ou_xxx" --transfer-owner-member-type openid

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
# 注意：抖音这个 probe 脚本仅用于探测/排障，不代表正式主流程
./scripts/collect_douyin_favorites_probe.sh 0
./scripts/add_other_link_record.sh "https://example.com/post/1" "示例梗概"
./scripts/merge_to_feishu_payload.sh
python3 ./scripts/sync_payload_to_feishu.py --dry-run

# 限制本次最多采集 100 条（可选）
COLLECT_LIMIT=100 ./scripts/run_phase2_probes.sh
```

## 验收与回报规则

- **先查缺口，再宣称完成**：凡是“补字段 / 改字段 / 删旧列”类任务，必须先在线读取真实表结构与记录，确认缺口数量；不要根据脚本覆盖范围、局部样本、或“看起来差不多”来宣称完成。
- **先补齐，再删旧字段**：像 X 表这种从 `作者` 迁移到 `作者主页` 的场景，必须遵守顺序：
  1. 批量补新字段
  2. 复查缺口是否为 `0`
  3. 抽样确认展示/点击正常
  4. 最后再删除旧字段
- **GitHub 项目名称验收方式**：不能只看最近新增那一批，必须做全表缺口检查，确认 `项目名称` 为空的记录数为 `0`。
- **X 作者主页验收方式**：不能只抽样看几个 `@handle`，必须做全表缺口检查，确认 `作者主页` 为空的记录数为 `0`；若还要删旧列，再额外确认列删除后的字段结构正确。
- **默认不要把一次性修复脚本写进长期主流程**：像 `repair_*`、`fix_*` 这类脚本更适合作为临时收尾工具，不应让主流程默认依赖它们来判断“系统已经稳定”。长期 skill 应记录规则、验收口径与正式入口，而不是把一次性补丁误写成标准流程。

## 失败处理

- `x` 未登录：`collect_x_bookmarks.sh` 会输出 `requires_login=true`，跳过写入该平台。
- `x` 新版页面结构 / 慢加载导致脚本可能拿到空列表：优先使用 `browser` 的 `profile="user"` 连接真实 Chrome，在用户完成 attach 确认后，以当前可见 bookmarks 页面做辅助验证；不要把 attach 等待误判为 browser/gateway 故障。
- `xiaohongshu` 未登录：`collect_xhs_favorites.sh` 输出 `status=needs_login`，在当前 `openclaw browser` 窗口登录后重试。
- `douyin` 未登录：输出 `status=needs_login`，等待用户登录后重试。
- 无需外部 API key：默认使用 OpenClaw 内置摘要流程，不阻塞写入。
- 未配置真实用户权限：`init_feishu_bitable.py` 默认会报错并提示补齐 `owner_email/share_members`（可用 `--allow-bot-only` 强制跳过）。
- 分享授权失败：默认记录到 `failed_members` 但不中断；可用 `--share-strict` 强制报错退出。
- 所有权转移失败：默认记录到 `owner_transfer` 但不中断；可用 `--transfer-owner-strict` 强制报错退出。
- 若未提供 member_id 且邮箱无法解析：`owner_transfer.error=missing_transfer_owner_identity`，可手动提供 `--transfer-owner-member-id`。
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
，允许重放写入。
