#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from feishu_bitable_api import load_feishu_credentials, load_user_config, FeishuBitableClient

APP_TOKEN = 'IQQxb21nMafnbvsCgAdcWHiXnVb'
TABLE_ID = 'tblpZColQ9hewK3C'

REST = {
    'https://x.com/lxfater/status/2030848999742398525': {
        '标题': '手把手教你用 MaxClaw 搭建文章生产流水线',
        '内容梗概': '这条内容在讲如何用 MaxClaw 搭建文章生产流水线，重点解决从部署、配置到接入飞书等通讯工具的完整落地问题。',
    },
    'https://x.com/nopinduoduo/status/2029173276933800183': {
        '标题': '按视频语义自动切分章节的视频剪辑 Skill',
        '内容梗概': '这条内容分享了一个视频剪辑 Skill，可以根据视频语义自动识别章节并切分段落，适合做长视频整理和内容二次分发。',
    },
    'https://x.com/oran_ge/status/2020649409521041502': {
        '标题': '互联网已死，Agent 永生',
        '内容梗概': '这条内容在讨论 AI 时代下互联网产品逻辑的变化，核心观点是传统 SaaS、DAU 和工具平台思路正在失效，Agent 才是新的产品与增长入口。',
    },
    'https://x.com/vista8/status/2029935446810308817': {
        '标题': '龙虾越火，越应该把 Skill 研究透',
        '内容梗概': '这条内容在提醒 OpenClaw 越火的时候越要重视 Skill 体系，核心观点是不要只盯部署和热度，而要把真正决定能力上限的 Skills 研究透。',
    },
    'https://x.com/xxx111god/status/2033261636195373123': {
        '标题': 'Self-Improving Skills：实现“永续” Agent 的最后一环',
        '内容梗概': '这条内容在讨论如何通过 Self-Improving Skills 补上“永续工作”型 Agent 的最后一环，重点是让智能体在任务管理和执行过程中持续优化自身能力。',
    },
}


def normalize_link(v):
    if isinstance(v, dict):
        return (v.get('link') or v.get('text') or '').strip()
    return str(v or '').strip()


def main() -> None:
    cfg = load_user_config(None)
    app_id, app_secret, base_url = load_feishu_credentials(config=cfg)
    client = FeishuBitableClient(app_id, app_secret, base_url)
    items = client.list_records(APP_TOKEN, TABLE_ID)
    index = {}
    for item in items:
        f = item.get('fields') or {}
        index[normalize_link(f.get('链接'))] = str(item.get('record_id') or '')

    updated = []
    missing = []
    for link, payload in REST.items():
        rid = index.get(link, '')
        if not rid:
            missing.append(link)
            continue
        client.update_record(APP_TOKEN, TABLE_ID, rid, payload)
        updated.append({'link': link, 'record_id': rid, '标题': payload['标题']})

    print(json.dumps({'updated': len(updated), 'missing': missing, 'sample': updated}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
