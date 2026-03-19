#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const OUT = process.argv[2] || path.join(ROOT, 'output', 'douyin-favorites-probe.json');
const MAX_STEPS = Number(process.argv[3] || 120);

function oc(args) {
  const out = execFileSync('openclaw', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  return JSON.parse(out);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

const clickCollection = `() => {
  const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const nodes = [...document.querySelectorAll('[role="tab"],button,div,span')];
  const el = nodes.find(n => clean(n.innerText) === '收藏');
  if (!el) return { ok: false };
  el.click();
  return { ok: true };
}`;

const clickVideo = `() => {
  const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const nodes = [...document.querySelectorAll('[role="tab"],button,div,span')];
  const el = nodes.find(n => clean(n.innerText) === '视频');
  if (!el) return { ok: false };
  el.click();
  return { ok: true };
}`;

const enterFirstVideo = `() => {
  const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const list = document.querySelector('[data-e2e="user-favorite-list"] [data-e2e="scroll-list"]')
    || document.querySelector('[data-e2e="user-post-list"] [data-e2e="scroll-list"]')
    || document.querySelector('[data-e2e="scroll-list"]');
  const links = [...(list ? list.querySelectorAll('a[href*="/video/"], a[href*="/note/"]') : [])];
  const first = links.find(a => {
    const txt = clean((a.closest('li,section,article,div') || a).innerText || '');
    return txt && !/热门：抖音精选|推荐|热搜/.test(txt.slice(0, 50));
  });
  if (!first) return { ok: false, count: links.length };
  const href = first.href || first.getAttribute('href') || '';
  first.click();
  return { ok: true, href, count: links.length };
}`;

const waitDetail = `() => new Promise(resolve => {
  const check = () => {
    let modalId = null;
    try { modalId = new URL(location.href).searchParams.get('modal_id') || null; } catch (e) {}
    if (modalId) { resolve({ ok: true, href: location.href, modalId }); return; }
    setTimeout(check, 500);
  };
  check();
})`;

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
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  oc(['browser', 'start', '--json']);
  const opened = oc(['browser', 'open', 'https://www.douyin.com/user/self?showTab=collection', '--json']);
  const targetId = opened.targetId;
  oc(['browser', 'wait', '--target-id', targetId, '--load', 'domcontentloaded', '--timeout-ms', '45000', '--json']);
  await sleep(2500);
  oc(['browser', 'evaluate', '--target-id', targetId, '--fn', clickCollection, '--json']);
  await sleep(1500);
  oc(['browser', 'evaluate', '--target-id', targetId, '--fn', clickVideo, '--json']);
  await sleep(2500);
  oc(['browser', 'evaluate', '--target-id', targetId, '--fn', enterFirstVideo, '--json']);
  await sleep(1500);
  oc(['browser', 'evaluate', '--target-id', targetId, '--fn', waitDetail, '--json']);
  
  const records = [];
  const seen = new Set();
  let lastCollectedState = null;
  let stopReason = null;
  let steps = 0;
  while (steps <= MAX_STEPS) {
    const state = oc(['browser', 'evaluate', '--target-id', targetId, '--fn', inspect, '--json']).result;
    if (!(state?.modal_id && state?.collect?.is_collected)) {
      stopReason = state?.collect?.state || 'not_collected_or_missing_modal';
      break;
    }
    const kind = state.article_jump ? 'article' : (state.note_like ? 'note' : 'video');
    const link = kind === 'article'
      ? `https://www.douyin.com/article/${state.modal_id}`
      : kind === 'note'
        ? `https://www.douyin.com/note/${state.modal_id}`
        : `https://www.douyin.com/video/${state.modal_id}`;
    if (!seen.has(link)) {
      seen.add(link);
      const t = state.collect.text || '';
      let count = null;
      if (/^[0-9]+(?:\.[0-9]+)?万$/.test(t)) count = Math.round(parseFloat(t) * 10000);
      else if (/^[0-9]+(?:\.[0-9]+)?$/.test(t)) count = Number(t);
      records.push({
        platform: 'douyin',
        title: `抖音收藏内容 ${state.modal_id}`,
        link,
        summary: state.author || '',
        favorite_or_star_count: count,
        ingested_at: new Date().toISOString()
      });
    }
    lastCollectedState = state;
    oc(['browser', 'evaluate', '--target-id', targetId, '--fn', arrowDown, '--json']);
    await sleep(2200);
    steps += 1;
  }

  const out = {
    source: 'douyin',
    fetched_at: new Date().toISOString(),
    mode: 'detail_flow_until_end',
    status: records.length ? 'ok' : 'no_records',
    stop_reason: stopReason,
    last_collected_modal_id: lastCollectedState?.modal_id || null,
    total_records: records.length,
    records
  };
  fs.writeFileSync(OUT, JSON.stringify(out, null, 2));
  process.stdout.write(JSON.stringify({ ok: true, total: records.length, stop_reason: stopReason, out: OUT }, null, 2) + '\n');
})().catch(err => {
  console.error(err.stack || err.message || String(err));
  process.exit(1);
});
