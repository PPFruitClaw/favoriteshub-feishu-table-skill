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

TOP10 = {
    'https://github.com/2025Emma/vibe-coding-cn': {
        '标题': 'Vibe Coding 中文指南与工作流手册',
        '内容梗概': '这是一个系统化的 Vibe Coding 中文指南仓库，围绕与 AI 结对编程展开，覆盖方法论、提示词、技能库、项目结构、开发流程和工具选型，重点强调先规划、固定上下文、再分步实现。',
    },
    'https://github.com/CoplayDev/unity-mcp': {
        '标题': 'Unity MCP：连接 Unity 与 AI 助手的桥接工具',
        '内容梗概': '这是一个把 Unity 与 AI 助手连接起来的 MCP 桥接项目，让 Claude、OpenClaw 等助手可以直接理解和操作 Unity 开发环境，适合用于游戏开发自动化与 AI 辅助创作。',
    },
    'https://github.com/D4Vinci/Scrapling': {
        '标题': 'Scrapling：适应复杂网站的网页抓取框架',
        '内容梗概': '这是一个面向复杂网站场景的网页抓取框架，强调从单页请求到大规模爬取的统一处理能力，适合需要兼顾稳定性、扩展性和反爬适应能力的抓取任务。',
    },
    'https://github.com/Gen-Verse/OpenClaw-RL': {
        '标题': 'OpenClaw-RL：用对话方式训练 AI 智能体',
        '内容梗概': '这是一个面向智能体训练的项目，目标是通过更自然的交互方式训练和优化 agent 行为，让开发者能够更低门槛地迭代训练流程和实验强化学习思路。',
    },
    'https://github.com/HKUDS/CLI-Anything': {
        '标题': 'CLI-Anything：让软件天然具备命令行智能体接口',
        '内容梗概': '这是一个让各类软件更容易接入命令行与智能体工作流的项目，重点是把传统软件能力包装成 agent 更容易调用和组合的接口形式，提升自动化与集成效率。',
    },
    'https://github.com/Intent-Lab/VisionClaw': {
        '标题': 'VisionClaw：面向智能眼镜的实时语音视觉助手',
        '内容梗概': '这是一个面向 Meta Ray-Ban 等智能眼镜场景的实时 AI 助手项目，结合语音、视觉和 agent 行动能力，适合做可穿戴设备上的即时感知与交互助手。',
    },
    'https://github.com/JimLiu/baoyu-skills': {
        '标题': 'baoyu-skills：面向内容创作与分发的一组 OpenClaw 技能',
        '内容梗概': '这是一个围绕内容生成、整理、发布和多平台分发构建的技能集合，适合把图文、封面、社交媒体发布等工作流接入 OpenClaw 进行自动化处理。',
    },
    'https://github.com/LeoYeAI/openclaw-master-skills': {
        '标题': 'OpenClaw 高质量技能精选合集',
        '内容梗概': '这是一个聚合 OpenClaw 高质量技能的精选仓库，重点价值在于帮助用户更快发现经过验证的实用技能，减少从海量技能里盲目筛选的成本。',
    },
    'https://github.com/Martian-Engineering/lossless-claw': {
        '标题': 'Lossless Claw：面向 OpenClaw 的无损上下文管理插件',
        '内容梗概': '这是一个专门解决 OpenClaw 上下文管理问题的插件项目，重点是降低上下文丢失和压缩带来的信息损耗，让长流程任务中的记忆衔接更稳定。',
    },
    'https://github.com/NoizAI/skills': {
        '标题': 'NoizAI Skills：增强语音表达与互动体验的技能集合',
        '内容梗概': '这是一个用于增强 OpenClaw 语音表达、互动氛围和人物感的技能集合，适合需要更强“真人感”和更丰富输出风格的场景。',
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
    for link, payload in TOP10.items():
        rid = index.get(link, '')
        if not rid:
            missing.append(link)
            continue
        client.update_record(APP_TOKEN, TABLE_ID, rid, payload)
        updated.append({'link': link, 'record_id': rid, '标题': payload['标题']})

    print(json.dumps({'updated': len(updated), 'missing': missing, 'sample': updated}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
