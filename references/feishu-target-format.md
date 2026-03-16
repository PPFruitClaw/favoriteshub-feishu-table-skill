# feishu-target.json 格式

`init_feishu_bitable.py` 会输出目标配置文件，供后续同步复用：

```json
{
  "generated_at": "2026-03-17T00:00:00Z",
  "app_token": "bascnxxxx",
  "app_name": "FavoritesHub-FeishuTable",
  "app_url": "https://xxx.feishu.cn/base/xxxx",
  "tables": {
    "github": {
      "table_id": "tblxxxx",
      "fields": {
        "所属平台": 1,
        "链接": 15,
        "内容梗概": 1,
        "收藏或星标数量": 2,
        "收录时间": 5
      }
    }
  }
}
```

字段类型说明：
- `1` 文本
- `2` 数字
- `5` 日期时间
- `15` URL

补充：
- 凭据建议放在用户配置文件中，通过 `--config` 或 `FAVORITESHUB_CONFIG` 指定。
- 示例见 `references/favoriteshub-config.example.json`。
