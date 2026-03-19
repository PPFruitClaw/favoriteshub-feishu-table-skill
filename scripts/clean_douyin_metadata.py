#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IN_FILE = ROOT / 'output' / 'douyin-favorites-probe.json'
OUT_FILE = ROOT / 'output' / 'douyin-favorites-cleaned.json'

NOISE_PATTERNS = [
    r'展开$',
    r'##ai',
    r'#\S+',
    r'\s+',
]

AUTHOR_PREFIX_RE = re.compile(r'^@+')
AUTHOR_DATE_RE = re.compile(r'^@[^·]+·\s*[^\s]+')
ID_TITLE_RE = re.compile(r'^抖音收藏内容\s+\d+$')


def clean_text(text: str) -> str:
    s = (text or '').strip()
    s = AUTHOR_PREFIX_RE.sub('@', s)
    for pat in NOISE_PATTERNS:
        s = re.sub(pat, ' ' if pat == r'\s+' else '', s)
    s = re.sub(r'\s+', ' ', s).strip(' -_|·，,。')
    return s


def make_title(summary: str, link: str, old_title: str) -> str:
    if old_title and not ID_TITLE_RE.match(old_title):
        t = clean_text(old_title)
        if t:
            return t[:40]
    s = summary or ''
    s = re.sub(r'^@[^·]+·\s*[^\s]+', '', s).strip()
    s = clean_text(s)
    if s:
        return s[:40]
    if '/article/' in link:
        return '抖音文章内容'
    if '/note/' in link:
        return '抖音图文内容'
    return '抖音视频内容'


def make_summary(summary: str, title: str) -> str:
    s = clean_text(summary)
    s = re.sub(r'^@[^·]+·\s*[^\s]+', '', s).strip()
    s = clean_text(s)
    if s:
        return s[:120]
    return title


def main() -> None:
    obj = json.loads(IN_FILE.read_text(encoding='utf-8'))
    out_records = []
    for r in obj.get('records', []):
        link = r.get('link', '')
        old_title = r.get('title', '')
        raw_summary = r.get('summary', '')
        title = make_title(raw_summary, link, old_title)
        summary = make_summary(raw_summary, title)
        out = dict(r)
        out['title'] = title
        out['summary'] = summary
        out_records.append(out)
    out = dict(obj)
    out['records'] = out_records
    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'ok': True, 'total': len(out_records), 'out': str(OUT_FILE)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
