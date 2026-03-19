() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const clickTab = (label) => {
    const tabs = [...document.querySelectorAll('[role="tab"], div, span, button')];
    const target = tabs.find(el => clean(el.innerText) === label);
    if (target) {
      target.click();
      return true;
    }
    return false;
  };

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  const listLinks = () => {
    const links = [...document.querySelectorAll('a[href*="/video/"], a[href*="/note/"]')]
      .map(a => {
        try {
          const u = new URL(a.getAttribute('href'), location.origin);
          u.search = '';
          return u.toString();
        } catch {
          return '';
        }
      })
      .filter(Boolean);
    return [...new Set(links)];
  };

  return (async () => {
    clickTab('收藏');
    await sleep(1500);
    clickTab('视频');
    await sleep(2000);

    const centerX = Math.floor(window.innerWidth * 0.5);
    const centerY = Math.floor(window.innerHeight * 0.72);

    const counts = [];
    let prevCount = 0;
    let stableRounds = 0;
    for (let i = 0; i < 35; i += 1) {
      const el = document.elementFromPoint(centerX, centerY) || document.body;
      el.dispatchEvent(new WheelEvent('wheel', {deltaY: 1400, bubbles: true, cancelable: true}));
      await sleep(1800);
      const links = listLinks();
      const count = links.length;
      counts.push({i: i + 1, count, last10: links.slice(-10)});
      if (count === prevCount) stableRounds += 1;
      else stableRounds = 0;
      prevCount = count;
      if (stableRounds >= 6) break;
    }
    const finalLinks = listLinks();
    return {
      finalCount: finalLinks.length,
      first10: finalLinks.slice(0, 10),
      last20: finalLinks.slice(-20),
      rounds: counts,
      currentUrl: location.href,
    };
  })();
}
