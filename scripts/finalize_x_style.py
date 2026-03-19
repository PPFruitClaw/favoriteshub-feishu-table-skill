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
    'https://x.com/AYi_AInotes/status/2028674883346112747': 'OpenClaw 部署完成后，真正要发挥能力，必须先补齐一批基础 Skills，重点涉及技能发现、全网搜索、查询优化，以及安装配置和避坑指南。',
    'https://x.com/AsTonySh/status/2024843352496021943': 'OpenClaw-DeepReeder 能把 X、Reddit、YouTube 和普通网页链接转成可沉淀的内容，再导入 NotebookLM，适合做资料收集、知识沉淀和长期记忆管理。',
    'https://x.com/LawrenceW_Zen/status/2028326213278704012': '这是一篇关于低成本快速跑通 Claude Code 的实战教程，重点是帮助新手用最短路径和最低成本进入 AI Agent 实操。',
    'https://x.com/ResearchWang/status/2027683428154675476': '通过自建 API 矩阵来降低 OpenClaw 的使用成本，重点是减少高额账单并提升多模型调用的灵活性。',
    'https://x.com/ResearchWang/status/2029417736636645823': '分享了一批更进阶的 OpenClaw Skills 和对应教程，重点是帮助已经完成部署的用户把龙虾从陪聊工具真正升级成可执行任务的 AI 管家。',
    'https://x.com/ResearchWang/status/2030151219998793775': 'OpenClaw 的一些关键配置文件和工作机制如果不理解清楚，就算装了很多 Skills，龙虾的执行力和智能程度也提升有限。',
    'https://x.com/ResearchWang/status/2031370561289597343': '借一个热点事件做社会趋势推演，展示如何用 AI 从舆论和事件信号出发去推测某类群体的未来走向。',
    'https://x.com/ResearchWang/status/2032716395709141223': '聚焦 OpenClaw 在多代理协同场景下的实战配置与调优，重点解决随着 Skills、Memory 和知识越来越多后，单 Agent 变卡顿的问题。',
    'https://x.com/lxfater/status/2030848999742398525': '讲如何用 MaxClaw 搭建文章生产流水线，重点解决从部署、配置到接入飞书等通讯工具的完整落地问题。',
    'https://x.com/nopinduoduo/status/2029173276933800183': '分享了一个视频剪辑 Skill，可以根据视频语义自动识别章节并切分段落，适合做长视频整理和内容二次分发。',
    'https://x.com/onenewbite/status/2024819940327379286': 'NotebookLM Skill 能明显增强 OpenClaw 的资料沉淀、知识整合和长期记忆能力，是把龙虾从普通助手提升到知识型助手的关键一环。',
    'https://x.com/oran_ge/status/2020649409521041502': '讨论 AI 时代下互联网产品逻辑的变化，核心观点是传统 SaaS、DAU 和工具平台思路正在失效，Agent 才是新的产品与增长入口。',
    'https://x.com/ring_hyacinth/status/2028021181073527273': '分享了一个像素办公室风格的 OpenClaw 可视化项目，让龙虾根据不同状态切换到不同区域，增强桌面交互感和状态可视化体验。',
    'https://x.com/vista8/status/2029935446810308817': '提醒 OpenClaw 越火的时候越要重视 Skill 体系，不要只盯部署和热度，而要把真正决定能力上限的 Skills 研究透。',
    'https://x.com/xxx111god/status/2033261636195373123': '讨论如何通过 Self-Improving Skills 补上“永续工作”型 Agent 的最后一环，让智能体在任务管理和执行过程中持续优化自身能力。',
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
    for link, summary in REST.items():
        rid = index.get(link, '')
        if not rid:
            continue
        client.update_record(APP_TOKEN, TABLE_ID, rid, {'内容梗概': summary})
        updated.append({'link': link, 'record_id': rid})

    print(json.dumps({'updated': len(updated)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
