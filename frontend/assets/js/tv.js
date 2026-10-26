/*
 * AX-NEWS TV: the news of a screen's topics, around the clock.
 *
 * /tv.html shows the shared feeds (?layout=…&theme=…&topics=AI,Cybersecurity);
 * /tv/<token> shows an account's screen, set up in its account panel.
 *
 * Made to run for months untouched: the feed is asked for every two minutes
 * (less often while the network is down, the last news staying on screen and
 * in localStorage for the next start); the page reloads itself when the site
 * changes and once a night; it keeps the screen awake, hides the cursor and
 * moves its fixed parts a few pixels now and then.
 */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const boot = JSON.parse($('#tv-boot').textContent);
  const TAX = JSON.parse($('#ax-taxonomy').textContent);
  const LAYOUTS = ['spotlight', 'newsroom', 'wall', 'columns', 'headlines', 'magazine'];
  const THEMES = ['aurora', 'broadcast', 'paper', 'terminal', 'clinic', 'nebula'];
  const REFRESH_MS = 120000;
  const CACHE_KEY = 'ax-tv:' + (boot.token || 'public');
  const LANG = { fr: 'French', de: 'German', es: 'Spanish', it: 'Italian', pt: 'Portuguese', nl: 'Dutch', pl: 'Polish', sv: 'Swedish', da: 'Danish', nb: 'Norwegian', fi: 'Finnish', cs: 'Czech', el: 'Greek', ro: 'Romanian', hu: 'Hungarian', uk: 'Ukrainian', ru: 'Russian', tr: 'Turkish', ar: 'Arabic', fa: 'Persian', he: 'Hebrew', hi: 'Hindi', id: 'Indonesian', th: 'Thai', vi: 'Vietnamese', zh: 'Chinese', ja: 'Japanese', ko: 'Korean' };

  const tvEl = $('#tv'), stage = $('#stage');
  const state = {
    config: null, stories: [], alerts: [], counts: {}, idx: 0, paused: false,
    timer: null, tick: 0, failures: 0, lastOk: 0, known: new Set(), reload: false,
    layout: null, alertIdx: 0,
  };

  // ── Small helpers ────────────────────────────────────────────────────────
  const esc = (s) => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  const safeUrl = (u) => (/^https?:\/\//i.test(String(u || '')) ? String(u) : '');
  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* full or blocked */ } },
  };
  function topic(key) {
    const t = TAX.categories[key];
    if (t) return { label: t[0], color: t[1], art: `/assets/img/topics/${t[2]}.webp` };
    return { label: String(key || 'News').replace(/_/g, ' '), color: '#5aa8ff', art: '/assets/img/topics/default.webp' };
  }
  function ago(iso) {
    if (!iso) return '';
    const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
    if (m < 1) return 'just now';
    if (m < 60) return `${m} min ago`;
    const h = Math.round(m / 60);
    if (h < 24) return `${h} h ago`;
    return `${Math.round(h / 24)} d ago`;
  }
  const hhmm = (iso) => (iso ? new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '');
  async function getJSON(url) {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 20000);
    try {
      const r = await fetch(url, { credentials: 'omit', cache: 'no-store', signal: ctl.signal });
      if (!r.ok) { const e = new Error('HTTP ' + r.status); e.status = r.status; throw e; }
      return await r.json();
    } finally { clearTimeout(t); }
  }

  // ── Configuration ────────────────────────────────────────────────────────
  const params = new URLSearchParams(location.search);
  function publicConfig() {
    const pick = (k, list, d) => (list.includes(params.get(k)) ? params.get(k) : d);
    const flag = (k, d) => (params.get(k) === '0' ? false : params.get(k) === '1' ? true : d);
    return {
      layout: pick('layout', LAYOUTS, 'spotlight'), theme: pick('theme', THEMES, 'aurora'),
      title: 'Tech Intelligence', dwell: Math.min(60, Math.max(6, parseInt(params.get('dwell'), 10) || 12)),
      show_qr: flag('show_qr', true), show_ticker: flag('show_ticker', true), show_clock: flag('show_clock', true),
      rotate_layouts: flag('rotate_layouts', false), night_dim: flag('night_dim', false),
      topics: (params.get('topics') || '').split(',').filter(Boolean),
    };
  }
  function feedUrl() {
    if (boot.token) return `/api/tv/s/${encodeURIComponent(boot.token)}/feed`;
    const q = new URLSearchParams();
    for (const k of ['topics', 'alerts', 'dwell']) if (params.get(k)) q.set(k, params.get(k));
    return '/api/tv/public/feed' + (q.toString() ? '?' + q : '');
  }
  function currentLayout() {
    const c = state.config;
    if (c.rotate_layouts && !state.manualLayout) return LAYOUTS[new Date().getHours() % LAYOUTS.length];
    return c.layout;
  }
  function applyChrome() {
    const c = state.config;
    document.documentElement.dataset.tvTheme = c.theme;
    document.documentElement.dataset.layout = currentLayout();
    tvEl.dataset.showQr = c.show_qr ? 'on' : 'off';
    tvEl.dataset.showTicker = c.show_ticker ? 'on' : 'off';
    tvEl.dataset.showClock = c.show_clock ? 'on' : 'off';
    document.documentElement.style.setProperty('--dwell', c.dwell + 's');
    $('[data-title]').textContent = c.title || 'Tech Intelligence';
    document.title = (c.title || 'AX-NEWS') + ' — AX-NEWS TV';
  }

  // ── Pictures: the story's own, or its topic's illustration ───────────────
  function pic(s, cls = '') {
    const t = topic(s.category);
    const img = safeUrl(s.image_url);
    return `<div class="pic ${cls}${img ? '' : ' art'}" data-src="${esc(img)}" data-art="${esc(t.art)}"><img class="front" alt="" src="${esc(img || t.art)}"></div>`;
  }
  // After a render: a picture that does not load becomes the illustration; a
  // small one is shown whole over a blurred copy instead of being stretched.
  function hydrate(root) {
    root.querySelectorAll('.pic').forEach((box) => {
      const img = box.querySelector('img.front');
      if (!img) return;
      const art = box.dataset.art;
      const check = () => {
        if (!box.dataset.src) return;
        const w = box.clientWidth * (window.devicePixelRatio || 1);
        if (img.naturalWidth && img.naturalWidth < w * 0.62) {
          box.classList.add('small');
          if (!box.querySelector('img.back')) {
            const back = document.createElement('img');
            back.className = 'back'; back.alt = ''; back.src = img.src;
            box.insertBefore(back, img);
          }
        }
      };
      img.addEventListener('error', () => {
        if (img.src.indexOf(art) === -1) { img.src = art; box.classList.add('art'); box.dataset.src = ''; }
        else if (img.src.indexOf('default.webp') === -1) img.src = '/assets/img/topics/default.webp';
      }, { once: false });
      if (img.complete && img.naturalWidth) check(); else img.addEventListener('load', check, { once: true });
    });
  }
  function preload(s) {
    if (s && safeUrl(s.image_url)) { const i = new Image(); i.src = s.image_url; }
  }

  // ── Story pieces ─────────────────────────────────────────────────────────
  function kicker(s) {
    const t = topic(s.category);
    return `<div class="kicker" style="--topic:${esc(t.color)}">${esc(t.label)}</div>`;
  }
  function meta(s) {
    const tr = s.lang ? `<span class="tr">Translated from ${esc(LANG[s.lang] || s.lang)}</span>` : '';
    return `<div class="meta"><span class="src">${esc(s.source)}</span><span class="dot"></span><span>${esc(ago(s.published_at))}</span>${tr}</div>`;
  }
  function qr(s) {
    if (!state.config.show_qr) return '';
    const q = boot.token && s.personal ? `?s=${encodeURIComponent(boot.token)}` : '';
    return `<div class="qr"><img alt="" src="/api/tv/qr/${s.id}${q}" width="120" height="120"><span>Scan to read on your phone</span></div>`;
  }
  const long = (s) => (s.title || '').length > 95 ? ' long' : '';
  const at = (i) => state.stories[((i % state.stories.length) + state.stories.length) % state.stories.length];

  // ── Layouts ──────────────────────────────────────────────────────────────
  const render = {
    spotlight(i) {
      const s = at(i);
      const next = [1, 2, 3, 4].map((k) => at(i + k));
      stage.innerHTML = `
        <article class="spot fade-in">
          ${pic(s, 'kb')}<div class="shade"></div>
          <div class="body">${kicker(s)}<h1 class="headline${long(s)}">${esc(s.title)}</h1>
            ${s.excerpt ? `<p class="excerpt">${esc(s.excerpt)}</p>` : ''}${meta(s)}</div>
          ${qr(s)}<div class="progress"><i></i></div>
        </article>
        <aside class="queue"><h3>Up next</h3>${next.map((n) => `
          <div class="q fade-in">${pic(n)}<div><div class="t">${esc(n.title)}</div><div class="m">${esc(n.source)} · ${esc(ago(n.published_at))}</div></div></div>`).join('')}
        </aside>`;
      return s;
    },
    newsroom(i) {
      const s = at(i);
      const n = Math.min(state.stories.length, 9);
      const start = Math.floor((i % state.stories.length) / n) * n;
      const list = Array.from({ length: n }, (_, k) => [start + k, at(start + k)]);
      stage.innerHTML = `
        <article class="nr-main fade-in">${pic(s, 'kb')}
          <div class="lower"><div class="progress"><i></i></div>${kicker(s)}<h1 class="headline">${esc(s.title)}</h1>
            ${s.excerpt ? `<p class="excerpt">${esc(s.excerpt)}</p>` : ''}${meta(s)}${qr(s)}</div>
        </article>
        <aside class="nr-list"><h3><span>Latest</span><span>${esc(state.counts.day || '')} today</span></h3>
          ${list.map(([k, x]) => `<div class="nr-item${k % state.stories.length === i % state.stories.length ? ' now' : ''}"><div class="time">${esc(hhmm(x.published_at))}</div>
            <div><div class="t">${esc(x.title)}</div><div class="m">${esc(x.source)} · ${esc(topic(x.category).label)}</div></div></div>`).join('')}
        </aside>`;
      return s;
    },
    wall(i, step) {
      // Five tiles: one big, four small. The first call fills them; then one
      // tile turns at each step.
      const tiles = stage.querySelectorAll('.tile');
      const tile = (s, big) => `${pic(s, big ? 'kb' : '')}<div class="shade"></div><div class="body">${kicker(s)}
        <h2 class="headline">${esc(s.title)}</h2>${big && s.excerpt ? `<p class="excerpt">${esc(s.excerpt)}</p>` : ''}
        <div class="meta"><span class="src">${esc(s.source)}</span><span class="dot"></span><span>${esc(ago(s.published_at))}</span></div></div>${big ? qr(s) : ''}`;
      if (!step || tiles.length !== 5) {
        stage.innerHTML = [0, 1, 2, 3, 4].map((k) => `<article class="tile${k === 0 ? ' big' : ''} flip" data-k="${k}">${tile(at(i + k), k === 0)}</article>`).join('');
        state.wallNext = i + 5;
        return at(i);
      }
      const k = step % 5 === 0 ? 0 : 1 + ((step - 1) % 4);
      const el = stage.querySelector(`.tile[data-k="${k}"]`);
      const s = at(state.wallNext++);
      el.classList.remove('flip'); void el.offsetWidth; el.classList.add('flip');
      el.innerHTML = tile(s, k === 0);
      hydrate(el);
      return s;
    },
    columns(i, step) {
      if (step && stage.querySelector('.col')) return at(i);   // scrolls by itself
      const c = state.config;
      const counts = {};
      state.stories.forEach((s) => { counts[s.category] = (counts[s.category] || 0) + 1; });
      let keys = (c.topics || []).filter((k) => counts[k]);
      if (keys.length < 2) keys = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
      keys = keys.slice(0, portrait() ? 3 : 4);
      stage.innerHTML = keys.map((k) => {
        const t = topic(k);
        const items = state.stories.filter((s) => s.category === k).slice(0, 16);
        const html = items.map((s) => `<div class="ci"><div class="t">${esc(s.title)}</div><div class="m"><b>${esc(hhmm(s.published_at))}</b> · ${esc(s.source)}</div></div>`).join('');
        return `<section class="col fade-in" style="--topic:${esc(t.color)}">
          <div class="col-head">${pic({ category: k, image_url: '' })}<div class="shade"></div><h2>${esc(t.label)}<small>${items.length} stories</small></h2></div>
          <div class="col-list"><div class="col-scroll">${html}${html}</div></div></section>`;
      }).join('');
      // Scroll only a column taller than its box, at a reading pace.
      requestAnimationFrame(() => stage.querySelectorAll('.col-scroll').forEach((el) => {
        const half = el.scrollHeight / 2, box = el.parentElement.clientHeight;
        if (half > box) { el.classList.add('run'); el.style.setProperty('--scroll', Math.round(half / (box / 14)) + 's'); }
        else el.innerHTML = el.innerHTML.slice(0, el.innerHTML.length / 2);
      }));
      return at(i);
    },
    headlines(i) {
      const n = portrait() ? 8 : 5;
      const len = state.stories.length;
      const start = Math.floor((i % len) / n) * n;
      const s = at(i);
      stage.innerHTML = `
        <div class="hl-list">${Array.from({ length: Math.min(n, len) }, (_, k) => at(start + k)).map((x) => `
          <div class="hl${x === s ? ' now' : ''}"><div class="time">${esc(hhmm(x.published_at))}</div>
            <div><div class="t">${esc(x.title)}</div>${x.excerpt ? `<p class="excerpt">${esc(x.excerpt)}</p>` : ''}
            <div class="m">${esc(x.source)} · ${esc(topic(x.category).label)}</div></div></div>`).join('')}
        </div>
        <aside class="hl-side">${pic(s, 'kb')}${qr(s)}<div class="progress"><i></i></div></aside>`;
      return s;
    },
    magazine(i) {
      const s = at(i);
      const d = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
      stage.innerHTML = `
        ${pic(s, 'mag-pic kb')}
        <article class="mag-body fade-in">
          <div class="mag-mast"><span>AX·NEWS — ${esc(state.config.title || '')}</span><span>${esc(d)}</span></div>
          ${kicker(s)}<h1 class="headline${long(s)}">${esc(s.title)}</h1>
          ${s.excerpt ? `<p class="excerpt">${esc(s.excerpt)}</p>` : ''}
          <div class="mag-foot">${meta(s)}${qr(s)}</div><div class="progress"><i></i></div>
        </article>`;
      return s;
    },
  };
  const portrait = () => matchMedia('(orientation: portrait)').matches;

  // ── Rotation ─────────────────────────────────────────────────────────────
  function show(i, step = 0) {
    clearTimeout(state.timer);
    if (state.reload) { location.reload(); return; }
    const layout = currentLayout();
    if (layout !== state.layout) { state.layout = layout; document.documentElement.dataset.layout = layout; step = 0; }
    if (!state.stories.length) {
      stage.innerHTML = `<div class="tv-empty"><h2>No news yet</h2><p>This screen's topics have no story in the last ${esc(state.config.hours || 48)} hours. It will fill as soon as one arrives.</p></div>`;
      state.timer = setTimeout(() => show(0), 30000);
      return;
    }
    const s = render[layout](i, step);
    hydrate(stage);
    const bg = $('.tv-bg-story');
    if (s && safeUrl(s.image_url)) { bg.style.backgroundImage = `url("${s.image_url.replace(/"/g, '%22')}")`; bg.classList.add('on'); }
    else bg.classList.remove('on');
    preload(at(i + 1));
    state.idx = i;
    const wait = (layout === 'wall' ? state.config.dwell / 2 : layout === 'columns' ? state.config.dwell * 3 : state.config.dwell) * 1000;
    if (!state.paused) state.timer = setTimeout(() => show(layout === 'wall' || layout === 'columns' ? i : i + 1, step + 1), wait);
  }

  // ── Feed ─────────────────────────────────────────────────────────────────
  function ingest(data, fromCache) {
    const fresh = (data.stories || []).filter((s) => s && s.id && s.title);
    if (!fromCache && state.known.size) {
      const added = fresh.filter((s) => !state.known.has(s.id));
      if (added.length) justIn(added[0]);
    }
    fresh.forEach((s) => state.known.add(s.id));
    if (state.known.size > 5000) state.known = new Set(fresh.map((s) => s.id));
    const current = state.stories.length ? at(state.idx) : null;
    state.stories = fresh;
    state.alerts = data.alerts || [];
    state.counts = data.counts || {};
    // Keep the story on screen where it is in the new list.
    if (current) { const k = fresh.findIndex((s) => s.id === current.id); state.idx = k >= 0 ? k : 0; }
    renderCounts(); renderTicker(); renderAlert();
    // The columns are drawn once per list: redraw them with the new one.
    if (!fromCache && state.layout === 'columns' && stage.firstElementChild) show(state.idx);
    if (!fromCache && data.version && boot.version && data.version !== boot.version) {
      const last = store.get('ax-tv:reloaded') || 0;
      if (Date.now() - last > 10 * 60000) { store.set('ax-tv:reloaded', Date.now()); state.reload = true; }
    }
  }
  async function refresh() {
    try {
      const data = await getJSON(feedUrl());
      ingest(data, false);
      store.set(CACHE_KEY, { at: Date.now(), data });
      state.failures = 0; state.lastOk = Date.now();
      status('');
      if (!stage.firstElementChild) show(0);
      loaded();
      schedule(REFRESH_MS + Math.random() * 20000);
    } catch (e) {
      state.failures++;
      if (e.status === 404 && boot.token) {
        status('This screen was removed or its address changed. Ask its owner for the new one.', true);
        schedule(10 * 60000);
        loaded();
        return;
      }
      const since = state.lastOk ? new Date(state.lastOk) : null;
      if (state.failures >= 2) status(since ? `Offline — news from ${hhmm(since.toISOString())}` : 'Offline — retrying…', true);
      schedule(Math.min(5 * 60000, 15000 * Math.pow(2, state.failures - 1)));
    }
  }
  function schedule(ms) { clearTimeout(state.refreshTimer); state.refreshTimer = setTimeout(refresh, ms); }
  function loaded() { $('[data-loading]').classList.add('done'); }

  // ── Top, ticker, alert band, notices ─────────────────────────────────────
  function renderCounts() {
    const c = state.counts || {};
    $('[data-counts]').innerHTML = c.day ? `
      <div class="tv-count"><b>${esc(c.hour)}</b><span>Last hour</span></div>
      <div class="tv-count"><b>${esc(c.day)}</b><span>Last 24 h</span></div>
      <div class="tv-count"><b>${esc(c.sources)}</b><span>Sources</span></div>` : '';
  }
  function renderTicker() {
    const inner = $('[data-ticker-inner]');
    const items = state.stories.slice(0, 40);
    inner.innerHTML = items.map((s) => `<span>${esc(s.title)}<em>${esc(s.source)}</em></span>`).join('');
    requestAnimationFrame(() => {
      const px = inner.scrollWidth + inner.parentElement.clientWidth;
      const speed = parseFloat(getComputedStyle(document.documentElement).fontSize) * 6; // 6 rem a second
      inner.style.setProperty('--ticker', Math.max(30, Math.round(px / speed)) + 's');
    });
  }
  function renderAlert() {
    const band = $('[data-alert]');
    if (!state.alerts.length) { band.classList.add('hidden'); return; }
    band.classList.remove('hidden');
    const a = state.alerts[state.alertIdx++ % state.alerts.length];
    const cve = state.config.alerts === 'cve' || (!boot.token && !params.get('alerts'));
    $('[data-alert-label]').textContent = cve ? 'SECURITY' : 'ALERT';
    $('[data-alert-text]').innerHTML = `${a.label ? `<b>${esc(a.label)}</b>` : ''}${esc(a.title)}`;
  }
  let justInTimer;
  function justIn(s) {
    const el = $('[data-justin]');
    $('[data-justin-text]').textContent = s.title;
    el.classList.add('show');
    clearTimeout(justInTimer);
    justInTimer = setTimeout(() => el.classList.remove('show'), 9000);
  }
  function status(msg, bad) {
    const el = $('[data-status]');
    el.textContent = msg; el.classList.toggle('show', !!msg); el.classList.toggle('bad', !!bad);
  }
  function clock() {
    const d = new Date();
    const t = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    const el = $('[data-clock]');
    if (el.textContent !== t) {
      el.textContent = t;
      $('[data-date]').textContent = d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' });
      night();
      if (state.config && state.config.rotate_layouts && d.getMinutes() === 0 && currentLayout() !== state.layout) show(state.idx);
    }
  }
  function night() {
    const h = new Date().getHours();
    tvEl.classList.toggle('night', !!(state.config && state.config.night_dim && (h >= 20 || h < 7)));
  }

  // ── Around the clock ─────────────────────────────────────────────────────
  let lock = null;
  async function wake() {
    try { if ('wakeLock' in navigator && document.visibilityState === 'visible') lock = await navigator.wakeLock.request('screen'); } catch (e) { lock = null; }
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') { wake(); refresh(); }
  });
  function drift() {
    const r = () => (Math.round(Math.random() * 8) - 4) + 'px';
    document.documentElement.style.setProperty('--dx', r());
    document.documentElement.style.setProperty('--dy', r());
  }
  setInterval(drift, 4 * 60000);
  setInterval(() => { if (state.alerts.length > 1) renderAlert(); }, 10000);
  // A fresh page once a night, between 4 and 5 o'clock, if the site answers.
  (function nightly() {
    const now = new Date(), at = new Date(now);
    at.setHours(4, Math.floor(Math.random() * 59), 0, 0);
    if (at <= now) at.setDate(at.getDate() + 1);
    setTimeout(async () => {
      try { await getJSON('/api/tv/version'); location.reload(); } catch (e) { nightly(); }
    }, at - now);
  })();
  let idleTimer;
  function awake() {
    document.body.classList.remove('idle');
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => document.body.classList.add('idle'), 3000);
  }
  document.addEventListener('mousemove', awake, { passive: true });
  awake();
  window.addEventListener('online', refresh);
  window.addEventListener('resize', () => { if (state.stories.length) show(state.idx); });

  // ── Keys (a keyboard or a remote) ────────────────────────────────────────
  function cycle(key, list) {
    const c = state.config;
    c[key] = list[(list.indexOf(key === 'layout' ? currentLayout() : c[key]) + 1) % list.length];
    if (key === 'layout') state.manualLayout = true;
    applyChrome();
    if (!boot.token) { params.set(key, c[key]); history.replaceState(null, '', '?' + params); }
    hint(`${key === 'layout' ? 'Layout' : 'Theme'}: ${c[key]}`);
    show(state.idx);
  }
  function hint(text) {
    const el = $('[data-hint]');
    if (text) el.textContent = text;
    el.classList.add('show');
    clearTimeout(hint.t);
    hint.t = setTimeout(() => el.classList.remove('show'), 4000);
  }
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === 'f') { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen().catch(() => {}); }
    else if (k === 'l') cycle('layout', LAYOUTS);
    else if (k === 't') cycle('theme', THEMES);
    else if (k === ' ' || k === 'k') { state.paused = !state.paused; tvEl.classList.toggle('paused', state.paused); hint(state.paused ? 'Paused' : 'Playing'); if (!state.paused) show(state.idx); else clearTimeout(state.timer); e.preventDefault(); }
    else if (k === 'arrowright') show(state.idx + 1);
    else if (k === 'arrowleft') show(state.idx - 1);
    else if (k === 'q') { state.config.show_qr = !state.config.show_qr; applyChrome(); show(state.idx); }
    else return;
    wake();
  });
  // Full screen and the wake lock need a first touch on some browsers.
  document.addEventListener('click', () => { wake(); if (!document.fullscreenElement && document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {}); }, { once: true });

  // ── Start ────────────────────────────────────────────────────────────────
  async function start() {
    if (boot.token) {
      try {
        const s = await getJSON(`/api/tv/s/${encodeURIComponent(boot.token)}`);
        state.config = s.config;
        store.set(CACHE_KEY + ':config', s.config);
      } catch (e) {
        state.config = store.get(CACHE_KEY + ':config');
        if (!state.config) {
          $('[data-loading-text]').textContent = e.status === 404 ? 'This screen does not exist any more.' : 'Waiting for the network…';
          setTimeout(start, 30000);
          return;
        }
      }
    } else {
      state.config = publicConfig();
    }
    applyChrome();
    clock(); setInterval(clock, 1000);
    const cached = store.get(CACHE_KEY);
    if (cached && cached.data && Date.now() - cached.at < 7 * 86400000) {
      ingest(cached.data, true);
      state.lastOk = cached.at;
      show(0); loaded();
    }
    wake(); drift();
    hint();
    refresh();
  }
  start();
})();
