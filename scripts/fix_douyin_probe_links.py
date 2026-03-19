#!/usr/bin/env python3
import json
from pathlib import Path

p = Path('output/douyin-favorites-probe.json')
obj = json.loads(p.read_text(encoding='utf-8'))
changed = 0
for r in obj.get('records', []):
    s = str(r.get('summary', ''))
    link = str(r.get('link', ''))
    if ('图文' in s or 'AI笔记' in s) and '/video/' in link:
        r['link'] = link.replace('/video/', '/note/')
        changed += 1
p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'ok': True, 'changed': changed, 'path': str(p)}, ensure_ascii=False))
