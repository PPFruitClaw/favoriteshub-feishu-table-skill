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
TABLE_ID = 'tblhI0xc1cKdhPRE'

BATCH = {
    'https://github.com/blockops1/Qwen35-with-OpenClaw-on-Apple-MLX': {
        '标题': 'Qwen3.5 与 OpenClaw 在 Apple MLX 上的部署方案',
        '内容梗概': '这是一个围绕 Qwen3.5、OpenClaw 和 Apple MLX 组合使用的实践项目，重点是帮助用户在 Apple Silicon 环境里部署和运行本地模型与 OpenClaw 工作流。',
    },
    'https://github.com/karpathy/autoresearch': {
        '标题': 'autoresearch：自动执行研究任务的 AI Agent 项目',
        '内容梗概': '这是一个让 AI 智能体自动完成研究任务的项目，重点在于把资料搜索、训练和研究流程自动串起来，适合关注自动研究代理和单卡实验的人。',
    },
    'https://github.com/obra/superpowers': {
        '标题': 'Superpowers：面向智能体的软件开发方法与技能框架',
        '内容梗概': '这是一个把技能框架与软件开发方法论结合起来的项目，目标是帮助智能体更稳定地参与软件开发流程，适合做 agent 驱动开发和能力编排。',
    },
    'https://github.com/openclaw/openclaw': {
        '标题': 'OpenClaw：跨平台个人 AI 助手',
        '内容梗概': '这是 OpenClaw 官方主仓库，核心目标是提供一个可在不同系统和平台上运行的个人 AI 助手框架，支持技能扩展、自动化执行、消息接入和多种工具能力。',
    },
    'https://github.com/qeeqbox/social-analyzer': {
        '标题': 'Social Analyzer：跨平台社交账号分析工具',
        '内容梗概': '这是一个支持 API、命令行和 Web 形式的社交账号分析工具，主要用于在大量社交平台上定位、分析和检索目标人物的公开账号信息。',
    },
    'https://github.com/sickn33/antigravity-awesome-skills': {
        '标题': 'Antigravity Awesome Skills 精选合集',
        '内容梗概': '这是一个收集大量 Agent 技能的精选仓库，重点价值在于集中整理经过验证的实用技能，适合快速查找可直接复用的 agent 能力组件。',
    },
    'https://github.com/tanweai/pua': {
        '标题': 'pua：增强 Codex 与 Claude Code 行动力的技能',
        '内容梗概': '这是一个用于增强 Codex 和 Claude Code 主动性与执行力的技能项目，重点在于让 agent 在复杂任务里表现得更积极、更有推进感。',
    },
    'https://github.com/joeseesun/anything-to-notebooklm': {
        '标题': 'Anything to NotebookLM：多来源内容导入 NotebookLM',
        '内容梗概': '这是一个把网页、微信文章、YouTube、PDF、Markdown 等多种来源内容统一处理后导入 NotebookLM 的项目，适合做资料归档和知识沉淀。',
    },
    'https://github.com/Wei-Shaw/sub2api': {
        '标题': 'Sub2API：统一接入多家 AI 服务的开源中转平台',
        '内容梗概': '这是一个把 Claude、OpenAI、Gemini、Antigravity 等服务统一接入的开源中转平台，适合做多模型统一管理、订阅复用和成本分摊。',
    },
    'https://github.com/astonysh/OpenClaw-DeepReeder': {
        '标题': 'OpenClaw-DeepReeder：把网页内容转成长期记忆',
        '内容梗概': '这是一个把网页、X、Reddit、YouTube 等链接内容抓取、清洗并沉淀为 OpenClaw 长期记忆的项目，适合做知识收集、阅读归档和 NotebookLM 输入准备。',
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
