# 平台能力现状与缺口

## 已可直接采集

- `GitHub`：使用 `gh api graphql` 获取 starred repositories，含 `stargazerCount`。
- `X`：使用 `openclaw browser` 访问书签页并抽取 `status` 链接、正文摘要与互动计数（可解析时）。

## 当前为流程主导 / 半自动稳定

- `Douyin`：当前已验证的稳定部分是**流程**，不是脚本。
  - 正式主流程：`收藏 -> 视频 -> 点击首条进入详情流 -> ArrowDown 逐条切换`
  - 默认大多数内容按“普通视频型”处理，少数会出现“文章/跳转型”
  - 当前最可靠的收藏态主判据：详情右侧收藏按钮的 `data-e2e="video-player-collect"` 与 `data-e2e-state="video-player-is-collected"`
  - 当前最可靠的越界停止信号：收藏按钮不再满足 `data-e2e="video-player-collect"` + `data-e2e-state="video-player-is-collected"`
  - `modal_id` 变化只能证明内容切换，不能单独证明仍在收藏流中
  - 现有 `probe` / `favorites_probe` 脚本更适合用于探测、排障、复盘，不应视为正式稳定采集器

## 当前受限

- `Xiaohongshu`：已通过 `openclaw browser` 实现收藏页抓取（`collect_xhs_favorites.sh`），不再启动独立浏览器。
  - 依赖用户在当前 `openclaw browser` 会话中保持登录态。
  - 收藏页计数通过页面文本与选择器启发式提取，页面结构变化时可能失效。
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
