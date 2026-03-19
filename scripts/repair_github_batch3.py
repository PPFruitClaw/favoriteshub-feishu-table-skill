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
    'https://github.com/autoclaw-cc/xiaohongshu-skills': {
        '标题': 'xiaohongshu-skills：面向小红书运营与自动化的技能集合',
        '内容梗概': '这是一个围绕小红书内容运营、发布和自动化处理构建的技能集合，适合把选题、生成、整理和平台操作接入 OpenClaw 工作流。',
    },
    'https://github.com/dreammis/social-auto-upload': {
        '标题': 'social-auto-upload：多平台视频自动分发工具',
        '内容梗概': '这是一个把视频自动上传到抖音、小红书、视频号、TikTok、YouTube 和 Bilibili 等平台的项目，适合做多平台内容分发自动化。',
    },
    'https://github.com/jamiepine/voicebox': {
        '标题': 'Voicebox：开源语音合成与语音生成项目',
        '内容梗概': '这是一个面向语音合成与语音生成场景的开源项目，适合关注可控语音输出、声音生成和语音交互能力的人。',
    },
    'https://github.com/msitarzewski/agency-agents': {
        '标题': 'agency-agents：一套可直接使用的 AI 代理团队',
        '内容梗概': '这是一个把多种 AI 代理角色打包到一起的项目，覆盖前端生成、社区运营等不同任务分工，适合快速搭建可协作的 agent 团队。',
    },
    'https://github.com/shareAI-lab/learn-claude-code': {
        '标题': 'learn-claude-code：Claude Code 学习与实践指南',
        '内容梗概': '这是一个围绕 Claude Code 使用方法、实践经验和入门路径整理的学习型项目，适合想系统掌握 Claude Code 工作方式的人。',
    },
    'https://github.com/teng-lin/notebooklm-py': {
        '标题': 'notebooklm-py：NotebookLM 的 Python API 与技能封装',
        '内容梗概': '这是一个为 Google NotebookLM 提供非官方 Python API 和技能封装的项目，适合通过代码方式调用 NotebookLM 的能力，做资料导入、自动化处理和集成开发。',
    },
    'https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools': {
        '标题': '主流 AI 工具系统提示词与模型资料库',
        '内容梗概': '这是一个收集主流 AI 工具系统提示词和模型信息的资料仓库，适合研究不同 AI 工具的行为设计、提示词策略和产品机制。',
    },
    'https://github.com/yenchenlin/DeepLearningFlappyBird': {
        '标题': 'DeepLearningFlappyBird：用深度强化学习玩 Flappy Bird',
        '内容梗概': '这是一个用深度强化学习训练智能体玩 Flappy Bird 的经典项目，适合学习 Deep Q-learning 在游戏环境里的基本应用。',
    },
    'https://github.com/Turbo1123/turbometa-rayban-ai': {
        '标题': 'TurboMeta：中文 Ray-Ban Meta 智能眼镜助手',
        '内容梗概': '这是一个面向 Ray-Ban Meta 智能眼镜场景的中文 AI 助手项目，重点是提供更贴近中文用户使用习惯的语音与交互体验。',
    },
    'https://github.com/apachecn/ai-roadmap': {
        '标题': 'AI Roadmap：人工智能知识路线图',
        '内容梗概': '这是一个把人工智能相关知识体系整理成路线图和知识树的项目，适合做学习导航、知识梳理和进阶规划。',
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
