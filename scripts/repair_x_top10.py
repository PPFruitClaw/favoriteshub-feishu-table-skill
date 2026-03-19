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

BATCH = {
    'https://x.com/AYi_AInotes/status/2028674883346112747': {
        '标题': 'OpenClaw 新手必装的 4 个核心 Skills',
        '内容梗概': '这条内容在讲 OpenClaw 部署完成后，为什么必须先装一批基础 Skills 才能真正发挥能力，重点覆盖技能发现、全网搜索、查询优化，以及安装配置和避坑指南。',
    },
    'https://x.com/AsTonySh/status/2024843352496021943': {
        '标题': '用 OpenClaw-DeepReeder 把网页内容导入 NotebookLM',
        '内容梗概': '这条内容推荐了 OpenClaw-DeepReeder，重点价值是把 X、Reddit、YouTube 和普通网页链接转成可沉淀的内容，再导入 NotebookLM，适合做资料收集、知识沉淀和长期记忆管理。',
    },
    'https://x.com/LawrenceW_Zen/status/2028326213278704012': {
        '标题': '低成本跑通 Claude Code 的实战教程',
        '内容梗概': '这条内容是一篇关于低成本快速跑通 Claude Code 的实战教程，重点是帮助新手用最短路径和最低成本进入 AI Agent 实操。',
    },
    'https://x.com/onenewbite/status/2024819940327379286': {
        '标题': '为什么 OpenClaw 一定要安装 NotebookLM Skill',
        '内容梗概': '这条内容在讲 NotebookLM Skill 对 OpenClaw 的增强价值，核心意思是让 OpenClaw 拥有更强的资料沉淀、知识整合和长期记忆能力。',
    },
    'https://x.com/ring_hyacinth/status/2028021181073527273': {
        '标题': '像素办公室风格的 OpenClaw 项目开源了',
        '内容梗概': '这条内容分享了一个像素办公室风格的 OpenClaw 可视化项目，重点是让龙虾根据不同状态切换到不同区域，增强桌面交互感和状态可视化体验。',
    },
    'https://x.com/ResearchWang/status/2027683428154675476': {
        '标题': '低成本自建 OpenClaw 私有 API 矩阵',
        '内容梗概': '这条内容在讲如何通过自建 API 矩阵来降低 OpenClaw 的使用成本，重点是减少高额账单并提升多模型调用的灵活性。',
    },
    'https://x.com/ResearchWang/status/2029417736636645823': {
        '标题': '亲测可用的 OpenClaw 高级 Skills 分享',
        '内容梗概': '这条内容分享了一批更进阶的 OpenClaw Skills 和对应教程，重点是帮助已经完成部署的用户把龙虾从陪聊工具真正升级成可执行任务的 AI 管家。',
    },
    'https://x.com/ResearchWang/status/2030151219998793775': {
        '标题': '这些关键文件不懂，OpenClaw 就会又笨又傻',
        '内容梗概': '这条内容在讲 OpenClaw 的一些关键配置文件和工作机制，如果不了解这些文件的作用，就算装了很多 Skills，龙虾的执行力和智能程度也提升有限。',
    },
    'https://x.com/ResearchWang/status/2031370561289597343': {
        '标题': '用 AI 推演当代新青年的社会走向',
        '内容梗概': '这条内容是在借一个热点事件做社会趋势推演，展示如何用 AI 从舆论和事件信号出发去推测某类群体的未来走向。',
    },
    'https://x.com/ResearchWang/status/2032716395709141223': {
        '标题': 'OpenClaw 多代理协同实战教程',
        '内容梗概': '这条内容聚焦 OpenClaw 在多代理协同场景下的实战配置与调优，重点解决随着 Skills、Memory 和知识越来越多后，单 Agent 变卡顿的问题。',
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
