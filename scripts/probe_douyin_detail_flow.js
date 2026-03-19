#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const OUT = process.argv[2] || path.join(ROOT, 'output', 'douyin-detail-flow-probe.json');
const MAX_STEPS = Number(process.argv[3] || process.env.MAX_STEPS || 12);

// 说明：这是“详情流链路探针”，不是正式采集器。
// 它的用途是帮助验证：是否成功进入详情流、ArrowDown 是否可切下一条、
// 以及当前详情页的收藏按钮是否仍满足
// data-e2e="video-player-collect" + data-e2e-state="video-player-is-collected"。
// 后续若业务规则继续演化，应优先更新 SKILL.md 中的正式流程描述，
// 不要把这个 probe 脚本误当成最终权威实现。

function oc(args, { json = true, quiet = false } = {}) {
  try {
    const out = execFileSync('openclaw', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
    return json ? JSON.parse(out) : out;
  } catch (err) {
    if (!quiet) {
      const stderr = err.stderr?.toString?.() || err.message;
      throw new Error(`openclaw ${args.join(' ')} failed: ${stderr}`);
    }
    return null;
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function main() {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });

  oc(['browser', 'start', '--json'], { quiet: true });
  const opened = oc(['browser', 'open', 'https://www.douyin.com/user/self?showTab=collection', '--json']);
  const targetId = opened.targetId;
  oc(['browser', 'wait', '--target-id', targetId, '--load', 'domcontentloaded', '--timeout-ms', '45000', '--json']);
  await sleep(2500);

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

  oc(['browser', 'evaluate', '--target-id', targetId, '--fn', clickCollection, '--json']);
  await sleep(1500);
  oc(['browser', 'evaluate', '--target-id', targetId, '--fn', clickVideo, '--json']);
  await sleep(2500);

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
    if (!first) return { ok: false, reason: 'no-first-video-anchor' };
    const href = first.href || first.getAttribute('href') || '';
    first.click();
    return { ok: true, href };
  }`;

  const entered = oc(['browser', 'evaluate', '--target-id', targetId, '--fn', enterFirstVideo, '--json']);
  await sleep(3500);

  const inspect = `() => {
    const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();
    const href = location.href;
    let modalId = null;
    try {
      modalId = new URL(location.href).searchParams.get('modal_id') || null;
    } catch (e) {}

    const texts = [...document.querySelectorAll('div,span,h1,h2,h3,a[href*="/user/"],button')]
      .map(el => clean(el.textContent || ''))
      .filter(Boolean);

    let author = null;
    for (const t of texts) {
      if (t.length <= 32 && t.startsWith('@')) {
        author = t;
        break;
      }
    }

    let title = null;
    for (const t of texts) {
      if (t.length < 2 || t.length > 160) continue;
      if (t.startsWith('@')) continue;
      if (/^[0-9]{2}:[0-9]{2}\\s*\\/\\s*[0-9]{2}:[0-9]{2}$/.test(t)) continue;
      if (/章节要点|发送|倍速|智能|清屏|连播|听抖音|客户端|搜索|精选推荐|读屏标签|当前内容暂时无法播放|需要跳转查看完整内容|去查看/.test(t)) continue;
      title = t;
      break;
    }

    const joined = texts.join(' | ');
    const articleJump = /当前内容暂时无法播放|需要跳转查看完整内容|去查看/.test(joined);

    const collectEl = document.querySelector('[data-e2e="video-player-collect"]');
    const collectState = collectEl?.getAttribute('data-e2e-state') || null;
    const collectText = clean(collectEl?.textContent || '') || null;
    const collect = {
      found: Boolean(collectEl),
      state: collectState,
      is_collected: collectState === 'video-player-is-collected',
      text: collectText,
      hint: collectEl ? 'data-e2e=video-player-collect' : 'collect-element-not-found'
    };

    const textHead = [author, title, collectState, collectText].filter(Boolean).join(' | ');

    return {
      href,
      modal_id: modalId,
      author,
      title,
      article_jump: articleJump,
      collect,
      text_head: textHead.slice(0, 400)
    };
  }`;

  const arrowDown = `() => {
    const active = document.activeElement || document.body;
    const ev1 = new KeyboardEvent('keydown', { key: 'ArrowDown', code: 'ArrowDown', keyCode: 40, which: 40, bubbles: true });
    const ev2 = new KeyboardEvent('keyup', { key: 'ArrowDown', code: 'ArrowDown', keyCode: 40, which: 40, bubbles: true });
    active.dispatchEvent(ev1);
    document.dispatchEvent(ev1);
    window.dispatchEvent(ev1);
    active.dispatchEvent(ev2);
    document.dispatchEvent(ev2);
    window.dispatchEvent(ev2);
    return { ok: true };
  }`;

  const steps = [];
  let prev = oc(['browser', 'evaluate', '--target-id', targetId, '--fn', inspect, '--json']).result;
  steps.push({ index: 0, action: 'enter_first_video', entered: entered.result || null, state: prev });

  for (let i = 1; i <= MAX_STEPS; i += 1) {
    oc(['browser', 'evaluate', '--target-id', targetId, '--fn', arrowDown, '--json']);
    await sleep(2200);
    const cur = oc(['browser', 'evaluate', '--target-id', targetId, '--fn', inspect, '--json']).result;
    const changed = {
      href_changed: cur.href !== prev.href,
      modal_changed: cur.modal_id !== prev.modal_id,
      author_changed: cur.author !== prev.author,
      title_changed: cur.title !== prev.title,
      collect_state_changed: (cur.collect?.state || null) !== (prev.collect?.state || null),
    };
    const stillCollected = cur.collect?.is_collected === true;
    steps.push({
      index: i,
      action: 'ArrowDown',
      state: cur,
      changed,
      accepted_as_next_favorite: Boolean((changed.modal_changed || changed.title_changed || changed.author_changed) && stillCollected),
      stop_reason: stillCollected ? null : 'collect_state_not_is_collected'
    });
    prev = cur;
    if (!stillCollected) break;
  }

  const result = {
    source: 'douyin-detail-flow-probe',
    fetched_at: new Date().toISOString(),
    target_id: targetId,
    max_steps: MAX_STEPS,
    steps,
  };

  fs.writeFileSync(OUT, JSON.stringify(result, null, 2));
  process.stdout.write(JSON.stringify({ ok: true, out: OUT, steps: steps.length }, null, 2) + '\n');
}

main().catch(err => {
  process.stderr.write(String(err.stack || err.message || err) + '\n');
  process.exit(1);
});
