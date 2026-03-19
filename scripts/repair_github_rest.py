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

REST = {
    'https://github.com/apachecn/ailearning': {
        '标题': 'AiLearning：数据分析与机器学习实战路线',
        '内容梗概': '这是一个面向数据分析和机器学习学习路径的资料项目，覆盖线性代数、机器学习、PyTorch、NLTK 和 TensorFlow 2 等内容，适合系统入门和实战训练。',
    },
    'https://github.com/apachecn/ntu-hsuantienlin-ml': {
        '标题': '林轩田机器学习课程中文笔记',
        '内容梗概': '这是台湾大学林轩田机器学习课程的中文笔记整理项目，适合做机器学习基础理论复习、课程跟读和知识查阅。',
    },
    'https://github.com/fluencelabs/cli': {
        '标题': 'Fluence CLI：Fluence 网络命令行工具',
        '内容梗概': '这是 Fluence 生态的命令行工具项目，主要用于网络相关操作、开发管理和工作流执行，适合 Fluence 用户和开发者使用。',
    },
    'https://github.com/fluencelabs/nox': {
        '标题': 'Nox：Fluence 的 Rust 实现组件',
        '内容梗概': '这是 Fluence 核心能力的 Rust 实现项目，适合关注 Fluence 基础设施、底层实现和网络组件开发的人。',
    },
    'https://github.com/kk43994/kkclaw': {
        '标题': 'kkclaw：桌面龙虾 AI 助手',
        '内容梗概': '这是一个带桌面宠物形象的 OpenClaw AI 助手项目，结合 Edge TTS 语音和情绪动画表现，适合做桌面陪伴式 AI 助手体验。',
    },
    'https://github.com/taojy123/KeymouseGo': {
        '标题': 'KeymouseGo：鼠标键盘录制与自动化工具',
        '内容梗概': '这是一个类似按键精灵的鼠标键盘录制和自动化操作工具，适合做重复点击、输入模拟和桌面自动化任务。',
    },
    'https://github.com/white0dew/XiaohongshuSkills': {
        '标题': 'XiaohongshuSkills：小红书自动化技能集合',
        '内容梗概': '这是一个面向小红书自动发布、自动评论和自动检索场景的技能项目，支持接入 OpenClaw、Codex、CC 等工作流。',
    },
    'https://github.com/xindoo/agentic-design-patterns': {
        '标题': 'Agent 设计模式中文资料整理',
        '内容梗概': '这是一个围绕 Agent 设计模式整理的中文资料项目，适合系统学习 agentic design patterns、阅读中文版内容并做方法论参考。',
    },
    'https://github.com/2025Emma/vibe-coding-cn': {
        '标题': 'Vibe Coding 中文指南与工作流手册',
        '内容梗概': '这是一个系统化的 Vibe Coding 中文指南仓库，围绕与 AI 结对编程展开，覆盖方法论、提示词、技能库、项目结构、开发流程和工具选型，重点强调先规划、固定上下文、再分步实现。',
    },
    'https://github.com/666ghj/MiroFish': {
        '标题': 'MiroFish：多智能体预测与数字沙盘引擎',
        '内容梗概': '这是一个用多智能体和群体智能做推演预测的项目，能把新闻、政策、金融信号或故事素材转成可交互的数字世界，通过智能体持续演化来生成预测结果，适合做舆情推演、社会预测、金融分析和创意仿真。',
    },
    'https://github.com/blockops1/Qwen35-with-OpenClaw-on-Apple-MLX': {
        '标题': 'Qwen3.5 与 OpenClaw 在 Apple MLX 上的部署方案',
        '内容梗概': '这是一个围绕 Qwen3.5、OpenClaw 和 Apple MLX 组合使用的实践项目，重点是帮助用户在 Apple Silicon 环境里部署和运行本地模型与 OpenClaw 工作流。',
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
        '内容梗概': '这是一个给 OpenClaw 扩展语音表现力和互动风格的技能集合，重点在于让助手更会说、更像人、更有氛围感，适合需要语音输出、角色感和更自然陪伴体验的场景。',
    },
    'https://github.com/Panniantong/Agent-Reach': {
        '标题': 'Agent Reach：给 AI 智能体接入全网内容检索能力',
        '内容梗概': '这是一个给 AI 智能体补上互联网检索和内容读取能力的项目，支持读取和搜索 Twitter、Reddit、YouTube、GitHub、Bilibili 等来源，适合做联网搜索、资料收集和外部知识补充。',
    },
    'https://github.com/ProjectZKM/zkm': {
        '标题': 'zkM：开源零知识虚拟机项目',
        '内容梗概': '这是一个面向零知识证明场景的开源虚拟机项目，目标是提供更通用、稳定且易扩展的 zk 虚拟机能力，适合关注 zk 基础设施、虚拟机设计和证明系统工程实现的人。',
    },
    'https://github.com/QwenLM/Qwen3-TTS': {
        '标题': 'Qwen3-TTS：阿里开源语音合成模型',
        '内容梗概': '这是 Qwen 团队开源的语音合成模型项目，重点能力是生成更自然、更稳定、更有表现力的语音输出，适合做中文语音生成、角色配音和语音交互相关场景。',
    },
    'https://github.com/TianyiDataScience/openclaw-control-center': {
        '标题': 'OpenClaw Control Center：本地可视化控制中心',
        '内容梗概': '这是一个给 OpenClaw 增加可视化控制界面的项目，目标是把原本偏黑盒的运行状态变成可见、可管、可调试的本地控制中心，适合做状态查看、操作管理和运行透明化。',
    },
    'https://github.com/Turbo1123/turbometa-rayban-ai': {
        '标题': 'TurboMeta：中文 Ray-Ban Meta 智能眼镜助手',
        '内容梗概': '这是一个面向 Ray-Ban Meta 智能眼镜场景的中文 AI 助手项目，重点是提供更贴近中文用户使用习惯的语音与交互体验。',
    },
    'https://github.com/VoltAgent/awesome-openclaw-skills': {
        '标题': 'OpenClaw Skills 精选导航',
        '内容梗概': '这是一个按主题整理 OpenClaw 技能的精选导航仓库，重点价值是帮助用户更快找到适合自己的技能分类和实用能力，减少在大量技能里逐个试错的成本。',
    },
    'https://github.com/Wei-Shaw/sub2api': {
        '标题': 'Sub2API：统一接入多家 AI 服务的开源中转平台',
        '内容梗概': '这是一个把 Claude、OpenAI、Gemini、Antigravity 等服务统一接入的开源中转平台，适合做多模型统一管理、订阅复用和成本分摊。',
    },
    'https://github.com/andyhuo520/openclaw-assistant-mvp': {
        '标题': 'OpenClaw Assistant MVP：桌面语音助手原型',
        '内容梗概': '这是一个基于 Electron 的 OpenClaw 桌面语音助手原型项目，结合语音交互和 Live2D 角色表现，适合做桌面陪伴式助手、语音控制和可视化 AI 助手实验。',
    },
    'https://github.com/astonysh/OpenClaw-DeepReeder': {
        '标题': 'OpenClaw-DeepReeder：把网页内容转成长期记忆',
        '内容梗概': '这是一个把网页、X、Reddit、YouTube 等链接内容抓取、清洗并沉淀为 OpenClaw 长期记忆的项目，适合做知识收集、阅读归档和 NotebookLM 输入准备。',
    },
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
    'https://github.com/joeseesun/anything-to-notebooklm': {
        '标题': 'Anything to NotebookLM：多来源内容导入 NotebookLM',
        '内容梗概': '这是一个把网页、微信文章、YouTube、PDF、Markdown 等多种来源内容统一处理后导入 NotebookLM 的项目，适合做资料归档和知识沉淀。',
    },
    'https://github.com/karpathy/autoresearch': {
        '标题': 'autoresearch：自动执行研究任务的 AI Agent 项目',
        '内容梗概': '这是一个让 AI 智能体自动完成研究任务的项目，重点在于把资料搜索、训练和研究流程自动串起来，适合关注自动研究代理和单卡实验的人。',
    },
    'https://github.com/msitarzewski/agency-agents': {
        '标题': 'agency-agents：一套可直接使用的 AI 代理团队',
        '内容梗概': '这是一个把多种 AI 代理角色打包到一起的项目，覆盖前端生成、社区运营等不同任务分工，适合快速搭建可协作的 agent 团队。',
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
    'https://github.com/shareAI-lab/learn-claude-code': {
        '标题': 'learn-claude-code：Claude Code 学习与实践指南',
        '内容梗概': '这是一个围绕 Claude Code 使用方法、实践经验和入门路径整理的学习型项目，适合想系统掌握 Claude Code 工作方式的人。',
    },
    'https://github.com/sickn33/antigravity-awesome-skills': {
        '标题': 'Antigravity Awesome Skills 精选合集',
        '内容梗概': '这是一个收集大量 Agent 技能的精选仓库，重点价值在于集中整理经过验证的实用技能，适合快速查找可直接复用的 agent 能力组件。',
    },
    'https://github.com/tanweai/pua': {
        '标题': 'pua：增强 Codex 与 Claude Code 行动力的技能',
        '内容梗概': '这是一个用于增强 Codex 和 Claude Code 主动性与执行力的技能项目，重点在于让 agent 在复杂任务里表现得更积极、更有推进感。',
    },
    'https://github.com/teng-lin/notebooklm-py': {
        '标题': 'notebooklm-py：NotebookLM 的 Python API 与技能封装',
        '内容梗概': '这是一个为 Google NotebookLM 提供非官方 Python API 和技能封装的项目，适合通过代码方式调用 NotebookLM 的能力，做资料导入、自动化处理和集成开发。',
    },
    'https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools': {
        '标题': '主流 AI 工具系统提示词与模型资料库',
        '内容梗概': '这是一个收集主流 AI 工具系统提示词和模型信息的资料仓库，适合研究不同 AI 工具的行为设计、提示词策略和产品机制。',
    },
    'https://github.com/xindoo/agentic-design-patterns': {
        '标题': 'Agent 设计模式中文资料整理',
        '内容梗概': '这是一个围绕 Agent 设计模式整理的中文资料项目，适合系统学习 agentic design patterns、阅读中文版内容并做方法论参考。',
    },
    'https://github.com/yenchenlin/DeepLearningFlappyBird': {
        '标题': 'DeepLearningFlappyBird：用深度强化学习玩 Flappy Bird',
        '内容梗概': '这是一个用深度强化学习训练智能体玩 Flappy Bird 的经典项目，适合学习 Deep Q-learning 在游戏环境里的基本应用。',
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

    print(json.dumps({'updated': len(updated), 'missing': missing, 'sample': updated[:10]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
