# 平台能力现状与缺口

## 已可直接采集

- `GitHub`：使用 `gh api graphql` 获取 starred repositories，含 `stargazerCount`。
- `X`：使用 `openclaw browser` 访问书签页并抽取 `status` 链接与正文摘要。
- `Douyin`：可通过浏览器探测收藏页；未登录时返回 `needs_login`，已登录可抽取视频链接。

## 当前受限

- `Xiaohongshu`：已通过 `openclaw browser` 实现收藏页抓取（`collect_xhs_favorites.sh`），不再启动独立浏览器。
  - 依赖用户在当前 `openclaw browser` 会话中保持登录态。
  - 页面结构变化时可能需要调整选择器。

## 飞书写入能力

- 现已补充脚本化 OpenAPI 写入链路：
  - `init_feishu_bitable.py`：自动建 app（可选）+ 自动建子表 + 自动补字段
  - `sync_payload_to_feishu.py`：按 `所属平台 + 链接` 做 upsert
- 仍可继续复用 `feishu_bitable_*` 工具进行人工排障或手动干预。

## 设计原则

- 优先复用现有 skill 和工具，避免重复造轮子。
- 平台不可用时不阻断全流程，按平台降级并继续写入可用数据。
- 用户未提供某平台账号时，直接跳过该平台。
