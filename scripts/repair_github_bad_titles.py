#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from feishu_bitable_api import load_feishu_credentials, load_user_config, FeishuBitableClient
import sync_payload_to_feishu as sync

APP_TOKEN = 'IQQxb21nMafnbvsCgAdcWHiXnVb'
TABLE_ID = 'tblhI0xc1cKdhPRE'


def normalize_link(v):
    if isinstance(v, dict):
        return (v.get('link') or v.get('text') or '').strip()
    return str(v or '').strip()


def looks_bad(title: str, summary: str) -> bool:
    return (
        title.startswith('GitHub - ') or
        'Skip to content' in title or
        'Contribute to development' in title or
        'Skip to content' in summary or
        'Contribute to development' in summary or
        summary.startswith('Contribute to development') or
        summary.startswith('Skip to content') or
        title.endswith('...')
    )


def make_better(link: str, raw_title: str, raw_summary: str) -> tuple[str, str]:
    owner, name = sync._extract_repo_slug_parts(link)
    title, summary = sync._github_browser_title_and_summary(link, raw_title, raw_summary)

    bad_text = lambda s: (not s) or ('Contribute to development' in s) or ('Skip to content' in s)

    # 二次兜底：避免把 GitHub 未登录/导航文案写回去
    if bad_text(title):
        if name:
            title = f'{name} 项目'
        else:
            title = sync._make_chinese_title('github', raw_title, raw_summary, link)

    if bad_text(summary):
        cleaned = sync._trim_sentence(raw_summary, 120)
        if cleaned and not bad_text(cleaned):
            summary = cleaned
        else:
            repo_name = name or sync._extract_repo_name_from_link(link) or '这个项目'
            summary = f'{repo_name} 的项目说明、核心能力和适用场景。'

    # 进一步压制半截英文标题，统一成简洁中文项目名
    if title and (title.endswith('simply') or title.endswith('framework') or len(title) < 6):
        if name:
            title = f'{name} 项目'

    if title and title[-1] in '。；;，,':
        title = title[:-1]
    if summary and summary[-1] not in '。！？':
        summary += '。'
    return title[:60], summary[:140]


def main() -> None:
    cfg = load_user_config(None)
    app_id, app_secret, base_url = load_feishu_credentials(config=cfg)
    client = FeishuBitableClient(app_id, app_secret, base_url)

    items = client.list_records(APP_TOKEN, TABLE_ID)
    updated = []
    skipped = []
    for item in items:
        fields = item.get('fields') or {}
        title = str(fields.get('标题') or '')
        summary = str(fields.get('内容梗概') or '')
        link = normalize_link(fields.get('链接'))
        if not looks_bad(title, summary):
            continue
        record_id = str(item.get('record_id') or '')
        if not record_id or not link:
            skipped.append({'link': link, 'reason': 'missing_record_or_link'})
            continue
        new_title, new_summary = make_better(link, title, summary)
        client.update_record(APP_TOKEN, TABLE_ID, record_id, {'标题': new_title, '内容梗概': new_summary})
        updated.append({'record_id': record_id, 'link': link, 'title': new_title, 'summary': new_summary})

    print(json.dumps({'updated': len(updated), 'skipped': len(skipped), 'sample': updated[:10]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
