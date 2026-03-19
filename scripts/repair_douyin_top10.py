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
TABLE_ID = 'tblnXdTnE5rTUwb5'

BATCH = {
    'https://www.douyin.com/video/7617037219232918001': {
        '标题': '理想国译丛 M 系列书单盘点',
        '内容梗概': '盘点理想国译丛 M 系列图书，适合关注人文社科阅读和书单推荐的人参考。',
    },
    'https://www.douyin.com/video/7616545853901147392': {
        '标题': '一行指令把任意软件变成原生 AI Agent',
        '内容梗概': '介绍一个港大开源项目，核心能力是用一行指令把普通软件接成原生 AI Agent，方便让更多工具被智能体直接调用。',
    },
    'https://www.douyin.com/video/7613339635393447675': {
        '标题': 'Claude Code 的设计哲学：渐进式披露',
        '内容梗概': '围绕 Claude Code 的设计哲学展开，重点解释“渐进式披露”为什么能让 AI 编程助手在复杂任务里更稳定、更易用。',
    },
    'https://www.douyin.com/video/7615639826234182931': {
        '标题': '港大开源项目：一行指令让软件原生支持 Agent',
        '内容梗概': '介绍一个近期增长很快的港大开源项目，重点在于让任意软件快速获得原生 Agent 能力，降低工具接入智能体工作流的门槛。',
    },
    'https://www.douyin.com/video/7611907968786796490': {
        '标题': '面向闲鱼卖家的自动卖货助手',
        '内容梗概': '介绍一套面向闲鱼卖家的自动化值守系统，能够自动回复、议价并持续跟进客户，适合做电商客服自动化。',
    },
    'https://www.douyin.com/video/7612596965670407462': {
        '标题': '这 50 个 Skills 能显著提升 AI 工作流效率',
        '内容梗概': '分享一批高价值 Skills，核心目的是帮助用户更快搭出高效的 AI 工作流，提升执行力和产出质量。',
    },
    'https://www.douyin.com/video/7612478712906694129': {
        '标题': '解决 OpenClaw 长期记忆的 4 种方法',
        '内容梗概': '总结了优化 OpenClaw 长期记忆的四种方法，重点解决对话中断后信息丢失和 API 成本偏高的问题。',
    },
    'https://www.douyin.com/video/7612237215170694450': {
        '标题': '微软开源可本地运行的小模型',
        '内容梗概': '介绍微软发布的可在本地直接运行的开源小模型，适合关注本地大模型部署和低成本 AI 能力接入的人。',
    },
    'https://www.douyin.com/video/7612313172275498259': {
        '标题': 'OpenClaw 像素办公室可视化项目',
        '内容梗概': '展示一个把 OpenClaw 做成像素办公室风格的可视化项目，通过不同状态切换区域来增强交互感和陪伴感。',
    },
    'https://www.douyin.com/video/7611932915701960569': {
        '标题': 'AI 市场调研效率工具推荐',
        '内容梗概': '分享一个能显著提升市场调研效率的 AI 工具或方法，适合做商业研究、信息搜集和分析工作。',
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
    for link, payload in BATCH.items():
        rid = index.get(link, '')
        if not rid:
            missing.append(link)
            continue
        client.update_record(APP_TOKEN, TABLE_ID, rid, payload)
        updated.append({'link': link, 'record_id': rid, '标题': payload['标题']})

    print(json.dumps({'updated': len(updated), 'missing': missing, 'sample': updated}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
