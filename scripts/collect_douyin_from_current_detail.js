#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const OUT = process.argv[2] || path.join(ROOT, 'output', 'douyin-favorites-probe.json');
const TARGET_ID = process.argv[3];
const MAX_STEPS = Number(process.argv[4] || 20);

if (!TARGET_ID) {
  console.error('usage: node collect_douyin_from_current_detail.js <out> <targetId> [maxSteps]');
  process.exit(1);
}

function oc(args) {
  const out = execFileSync('openclaw', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  return JSON.parse(out);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

const inspect = `() => {
  const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const href = location.href;
  let modalId = null;
  try { modalId = new URL(location.href).searchParams.get('modal_id') || null; } catch (e) {}
  const collectEl = document.querySelector('[data-e2e="video-player-collect"]');
  const collectState = collectEl?.getAttribute('data-e2e-state') || null;
  const collectText = clean(collectEl?.textContent || '') || null;
  const texts = [...document.querySelectorAll('div,span,h1,h2,h3,a[href*="/user/"],button')].map(el => clean(el.textContent || '')).filter(Boolean);
  let author = null;
  for (const t of texts) { if (t.length <= 60 && t.startsWith('@')) { author = t; break; } }
  const joined = texts.join(' | ');
  const articleJump = /当前内容暂时无法播放|需要跳转查看完整内容|去查看/.test(joined);
  const noteLike = /图文|AI笔记/.test(joined) || /图文/.test(author || '');
  return {
    href,
    modal_id: modalId,
    author,
    article_jump: articleJump,
    note_like: noteLike,
    collect: {
      found: Boolean(collectEl),
      state: collectState,
      is_collected: collectState === 'video-player-is-collected',
      text: collectText
    }
  };
}`;

const arrowDown = `() => {
  const active = document.activeElement || document.body;
  const ev1 = new KeyboardEvent('keydown', { key: 'ArrowDown', code: 'ArrowDown', keyCode: 40, which: 40, bubbles: true });
  const ev2 = new KeyboardEvent('keyup', { key: 'ArrowDown', code: 'ArrowDown', keyCode: 40, which: 40, bubbles: true });
  active.dispatchEvent(ev1); document.dispatchEvent(ev1); window.dispatchEvent(ev1);
  active.dispatchEvent(ev2); document.dispatchEvent(ev2); window.dispatchEvent(ev2);
  return { ok: true };
}`;

(async () => {
  const records = [];
  const seen = new Set();
  let state = oc(['browser', 'evaluate', '--target-id', TARGET_ID, '--fn', inspect, '--json']).result;
  for (let i = 0; i <= MAX_STEPS; i += 1) {
    if (state?.modal_id && state?.collect?.is_collected) {
      const kind = state.article_jump ? 'article' : (state.note_like ? 'note' : 'video');
      const link = kind === 'article'
        ? `https://www.douyin.com/article/${state.modal_id}`
        : kind === 'note'
          ? `https://www.douyin.com/note/${state.modal_id}`
          : `https://www.douyin.com/video/${state.modal_id}`;
      if (!seen.has(link)) {
        seen.add(link);
        records.push({
          platform: 'douyin',
          title: `抖音收藏内容 ${state.modal_id}`,
          link,
          summary: state.author || '',
          favorite_or_star_count: (() => {
            const t = state.collect.text || '';
            if (/^[0-9]+(?:\.[0-9]+)?万$/.test(t)) return Math.round(parseFloat(t) * 10000);
            if (/^[0-9]+(?:\.[0-9]+)?$/.test(t)) return Number(t);
            return null;
          })(),
          ingested_at: new Date().toISOString()
        });
      }
    } else {
      break;
    }
    oc(['browser', 'evaluate', '--target-id', TARGET_ID, '--fn', arrowDown, '--json']);
    await sleep(2200);
    state = oc(['browser', 'evaluate', '--target-id', TARGET_ID, '--fn', inspect, '--json']).result;
  }
  const out = {
    source: 'douyin',
    fetched_at: new Date().toISOString(),
    mode: 'detail_flow_current_target',
    status: records.length ? 'ok' : 'no_records',
    records
  };
  fs.writeFileSync(OUT, JSON.stringify(out, null, 2));
  process.stdout.write(JSON.stringify({ ok: true, total: records.length, out: OUT }, null, 2) + '\n');
})().catch(err => {
  console.error(err.stack || err.message || String(err));
  process.exit(1);
});
