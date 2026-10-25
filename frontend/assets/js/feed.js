/* AX-NEWS — the feed: six layouts, the reader, topics, trending, saving.
 * Depends on core.js (window.AX). */
(function () {
  'use strict';
  const { $, $$, esc, icon, topic, api, ago, toast } = AX;
  const PAGE = 24;
  const VIEWS = [
    ['cards', 'grid', 'Cards'], ['magazine', 'magazine', 'Magazine'], ['micro', 'micro', 'Micro'],
    ['list', 'list', 'List'], ['mosaic', 'mosaic', 'Mosaic'], ['timeline', 'timeline', 'Timeline'],
  ];
  const SENT = {
    breakthrough: 'Breakthrough', very_positive: 'Very positive', positive: 'Positive',
    negative: 'Negative', very_negative: 'Very negative',
  };
  const page = document.body.dataset.feed || 'feed';
  const params = new URLSearchParams(location.search);
  const S = {
    scope: page === 'mine' ? 'mine' : (params.get('scope') || 'public'),
    saved: page === 'saved',
    category: params.get('topic') || '',
    search: params.get('q') || '',
    source: params.get('source') || '',
    feed: params.get('feed') || '',
    entity: params.get('entity') || '',
    view: params.get('view') || '',
    items: [], offset: 0, more: true, loading: false, newest: null, cursor: -1, open: null,
    topics: [], mine: [],
  };
  const feedEl = $('#feed'), itemsEl = $('[data-items]'), sentinel = $('[data-sentinel]');

  // ── Layout switcher ───────────────────────────────────────────────────
  function renderViews() {
    $('[data-views]').innerHTML = VIEWS.map(([v, ic, label]) =>
      `<button data-view="${v}" aria-pressed="${S.view === v}" title="${label} (v)">${icon(ic, 'sm')}<span>${label}</span></button>`).join('');
  }
  function setView(v, save = true) {
    if (!VIEWS.some((x) => x[0] === v)) v = 'cards';
    S.view = v;
    feedEl.className = 'view-' + v;
    $$('[data-view]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.view === v)));
    if (save) AX.prefs.set(page === 'mine' ? 'view_mine' : 'view', v);
    renderItems();
  }
  $('[data-views]').addEventListener('click', (e) => { const b = e.target.closest('[data-view]'); if (b) setView(b.dataset.view); });

  // ── Scope tabs (everyone / everything / mine) ─────────────────────────
  function renderScope() {
    const tabs = $('[data-scope-tabs]');
    if (page !== 'feed') { tabs.classList.add('hidden'); return; }
    $$('[data-scope]', tabs).forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.scope === S.scope)));
  }
  $('[data-scope-tabs]').addEventListener('click', (e) => {
    const b = e.target.closest('[data-scope]');
    if (!b) return;
    S.scope = b.dataset.scope;
    AX.prefs.set('scope', S.scope);
    renderScope(); reload();
  });

  // ── Header ─────────────────────────────────────────────────────────────
  function renderHead(total) {
    let title = 'Top stories', sub = '';
    if (S.saved) { title = 'Saved for later'; sub = 'Stories you kept, newest first.'; }
    else if (S.entity) { title = S.entity; sub = 'Every story that mentions it, from the shared feeds.'; }
    else if (S.feed) { const f = S.mine.find((x) => String(x.id) === String(S.feed)); title = f ? f.name : 'Source'; sub = f ? (f.site_url || f.url) : ''; }
    else if (S.source) { title = S.source; sub = 'One publisher, newest first.'; }
    else if (S.category) { const t = topic(S.category); title = t.label; const n = S.topics.find((x) => x.category === S.category); sub = n ? `${AX.num(n.total)} stories this month · ${AX.num(n.today)} today` : ''; }
    else if (S.scope === 'mine' || page === 'mine') { title = 'My sources'; sub = S.mine.length ? `${S.mine.length} sources you follow, privately.` : 'Follow any site, channel or feed — only you see them.'; }
    else if (S.scope === 'all') { title = 'Everything'; sub = 'The shared feeds and your own sources together.'; }
    else { const n = S.topics.reduce((s, x) => s + (x.today || 0), 0); sub = n ? `${AX.num(n)} stories in the last 24 hours, from 200+ sources` : 'From 200+ sources worldwide'; }
    if (S.search) { title = `“${S.search}”`; sub = 'Search in titles and sources'; }
    $('[data-feed-title]').textContent = title;
    $('[data-feed-sub]').textContent = sub || ' ';
    document.title = `${title} — AX-NEWS`;
  }

  // ── Loading ────────────────────────────────────────────────────────────
  function query() {
    const p = new URLSearchParams({ limit: PAGE, offset: S.offset });
    if (S.saved) p.set('saved', 'true');
    else if (S.feed) p.set('feed', S.feed);
    else p.set('scope', page === 'mine' ? 'mine' : S.scope);
    if (S.category) p.set('category', S.category);
    if (S.search) p.set('search', S.search);
    if (S.source) p.set('source', S.source);
    return p;
  }
  async function load() {
    if (S.loading || !S.more) return;
    S.loading = true;
    sentinel.textContent = S.items.length ? 'Loading…' : '';
    if (!S.items.length) itemsEl.innerHTML = skeletons();
    try {
      let batch;
      if (S.entity) {
        const d = await api(`/entities/${encodeURIComponent(S.entity)}?limit=60`);
        batch = d.articles || [];
        S.more = false;
      } else {
        batch = await api('/articles?' + query());
        S.more = batch.length === PAGE;
      }
      if (!S.items.length) itemsEl.innerHTML = '';
      S.items.push(...batch);
      S.offset += batch.length;
      if (!S.newest && S.items.length) S.newest = S.items[0].published_at;
      renderItems();
      sentinel.textContent = S.more ? '' : (S.items.length ? 'You are all caught up.' : '');
    } catch (e) {
      if (!S.items.length) itemsEl.innerHTML = '';
      if (e.status === 401) { emptyState('Sign in first', 'Your own sources and saved stories are tied to your account.', true); S.more = false; }
      else { sentinel.innerHTML = `Could not load the stories. <button class="btn sm" data-retry>Retry</button>`; }
    } finally {
      S.loading = false;
      feedEl.setAttribute('aria-busy', 'false');
    }
  }
  function reload() {
    S.items = []; S.offset = 0; S.more = true; S.newest = null; S.cursor = -1;
    feedEl.setAttribute('aria-busy', 'true');
    renderHead(); syncUrl(); markTopics();
    $('[data-new-pill]').classList.remove('show');
    load();
  }
  sentinel.addEventListener('click', (e) => { if (e.target.closest('[data-retry]')) { sentinel.textContent = ''; load(); } });
  new IntersectionObserver((en) => { if (en[0].isIntersecting) load(); }, { rootMargin: '900px 0px' }).observe(sentinel);

  function skeletons() {
    const n = S.view === 'list' || S.view === 'timeline' ? 8 : 6;
    const h = { cards: 330, magazine: 300, micro: 150, list: 44, mosaic: 280, timeline: 76 }[S.view] || 300;
    return Array.from({ length: n }, () => `<div class="skeleton" style="height:${h}px;border-radius:18px;margin-bottom:${S.view === 'list' ? 2 : 0}px"></div>`).join('');
  }
  function emptyState(title, text, signIn) {
    const art = topic(S.category || (page === 'mine' ? 'My_Sources' : '')).art;
    itemsEl.innerHTML = `<div class="empty" style="grid-column:1/-1;column-span:all">
      <div class="art-hero" style="background-image:url(${art})"></div>
      <h2>${esc(title)}</h2><p>${esc(text)}</p>
      ${signIn ? '<a class="btn primary" href="/login.html">Sign in</a>' : page === 'mine' || S.scope === 'mine' ? '<a class="btn primary" href="/account">Add a source</a>' : ''}
    </div>`;
  }

  // ── Rendering ──────────────────────────────────────────────────────────
  function media(a, i, cls = '') {
    const t = topic(a.category);
    const ar = S.view === 'mosaic' ? ` style="--ar:${['4/5', '1/1', '3/4', '4/3', '4/5', '2/3'][i % 6]}"` : '';
    if (AX.safeUrl(a.image_url)) {
      return `<div class="media ${cls}"${ar}><img src="${esc(AX.safeUrl(a.image_url))}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" data-fallback="${esc(t.art)}"></div>`;
    }
    return `<div class="media art-fallback ${cls}"${ar} data-og="${esc(AX.safeUrl(a.url))}" data-id="${a.id}"><img src="${S.view === 'micro' || S.view === 'timeline' ? t.thumb : t.art}" alt="" loading="lazy" decoding="async"><span class="label">${esc(t.label)}</span></div>`;
  }
  function src(a) {
    return `<div class="src">${AX.avatar(a.feed_source)}<b>${esc(a.feed_source || 'Unknown')}</b><span class="sep">·</span><time datetime="${esc(a.published_at)}">${ago(a.published_at)}</time></div>`;
  }
  function sentiment(a) {
    if (!a.sentiment || !SENT[a.sentiment]) return '';
    return `<span class="sentiment s-${a.sentiment}"><span class="dot"></span>${SENT[a.sentiment]}</span>`;
  }
  function tags(a, n = 2) {
    const out = [];
    if (a.personal) out.push(`<span class="tag mine">${icon('radar', 'sm')}Mine</span>`);
    if (a.original_lang && a.original_lang !== 'en') out.push(`<span class="tag translated" title="Translated from ${esc(a.original_lang)}">${icon('globe', 'sm')}${esc(a.original_lang.toUpperCase())}</span>`);
    (a.entities || []).slice(0, n).forEach((e) => out.push(`<button class="tag link" data-entity="${esc(e)}">${esc(e)}</button>`));
    return out.length ? `<div class="tags">${out.join('')}</div>` : '';
  }
  function saveBtn(a) {
    return `<button class="save-btn" data-save="${a.id}" aria-pressed="${!!a.is_saved}" title="Save (s)" aria-label="Save">${icon('bookmark', 'sm')}</button>`;
  }
  function titleLink(a, cls = 'title') {
    return `<h2 class="${cls}"><a href="/?a=${a.id}" data-open="${a.id}">${esc(a.title)}</a></h2>`;
  }
  function art(a, i, extra = '') {
    const t = topic(a.category);
    return `<article class="art${a.is_read ? ' read' : ''}${extra}" data-id="${a.id}" data-i="${i}" style="--topic:${t.color}">`;
  }
  const R = {
    cards: (a, i) => `${art(a, i)}${media(a, i)}<div class="body">${src(a)}${titleLink(a, 'title clamp-3')}
        ${a.excerpt ? `<p class="excerpt clamp-2">${esc(a.excerpt)}</p>` : ''}
        <div class="meta"><span>${sentiment(a) || (a.reading_minutes > 1 ? `<span class="muted">${a.reading_minutes} min read</span>` : `<span class="tag topic">${esc(topic(a.category).label)}</span>`)}</span>${saveBtn(a)}</div></div></article>`,
    magazine: (a, i) => {
      const t = topic(a.category), kind = i === 0 ? ' lead' : i < 3 ? ' second' : '';
      return `${art(a, i, kind)}${media(a, i)}<div class="body"><div class="kicker">${esc(t.label)}</div>${titleLink(a, 'title')}
        ${a.excerpt ? `<p class="excerpt clamp-3">${esc(a.excerpt)}</p>` : ''}${src(a)}
        <div class="meta">${sentiment(a)}${tags(a, 2)}</div></div></article>`;
    },
    micro: (a, i) => `${art(a, i)}<div class="body">${src(a)}${titleLink(a, 'title')}
        ${a.excerpt ? `<p class="excerpt clamp-3">${esc(a.excerpt)}</p>` : ''}
        <div class="meta"><div class="tags">${sentiment(a)}${tags(a, 3).replace('<div class="tags">', '').replace(/<\/div>$/, '')}</div>${saveBtn(a)}</div></div>${media(a, i)}</article>`,
    list: (a, i) => `${art(a, i)}<span class="time">${AX.hhmm(a.published_at)}</span>${titleLink(a, 'title')}${src(a).replace(/<span class="sep">.*?<\/time>/, '')}${saveBtn(a)}</article>`,
    mosaic: (a, i) => `${art(a, i)}${media(a, i)}<div class="shade"></div><div class="body">${src(a)}${titleLink(a, 'title clamp-3')}</div>${saveBtn(a)}</article>`,
    timeline: (a, i) => `${art(a, i)}${media(a, i)}<div class="body">${titleLink(a, 'title clamp-2')}${src(a)}</div></article>`,
  };
  function renderItems() {
    if (!S.items.length) {
      if (!S.loading && !S.more) {
        if (S.saved) emptyState('Nothing saved yet', 'Press the bookmark on any story to keep it here.');
        else if (S.search) emptyState('No story matches', 'Try fewer words, or another topic.');
        else if (page === 'mine' || S.scope === 'mine') emptyState(S.mine.length ? 'No story yet' : 'Make it yours', S.mine.length ? 'Your sources have nothing in the last 30 days.' : 'Add a site, a YouTube channel, a subreddit or any RSS feed. Only you will see it.');
        else emptyState('No story', 'Nothing here in the last 30 days.');
      }
      return;
    }
    let html = '', lastDay = '', lastHour = '';
    S.items.forEach((a, i) => {
      if (S.view === 'list') {
        const d = AX.day(a.published_at);
        if (d !== lastDay) { html += `<div class="day">${esc(d)}</div>`; lastDay = d; }
      }
      if (S.view === 'timeline') {
        const d = new Date(a.published_at), key = d.toDateString() + d.getHours(), day = AX.day(a.published_at);
        if (key !== lastHour) {
          const h = String(d.getHours()).padStart(2, '0');
          html += `<div class="hour"><span>${h}:00</span>${day !== lastDay ? esc(day) + ' · ' : ''}${h}:00 – ${String((d.getHours() + 1) % 24).padStart(2, '0')}:00</div>`;
          lastHour = key; lastDay = day;
        }
      }
      html += R[S.view](a, i);
    });
    itemsEl.innerHTML = html;
    observeOg();
    if (S.cursor >= 0) highlight(S.cursor, false);
  }

  // Pictures: a broken one falls back to its topic's illustration; a card
  // without one asks for the page's og:image when it comes into view.
  document.addEventListener('error', (e) => {
    const img = e.target;
    if (img.tagName === 'IMG' && img.dataset.fallback && img.src !== location.origin + img.dataset.fallback) {
      img.src = img.dataset.fallback; img.closest('.media')?.classList.add('art-fallback');
    }
  }, true);
  const ogQueue = [], ogSeen = new Set();
  let ogBusy = 0;
  const ogObs = 'IntersectionObserver' in window ? new IntersectionObserver((en) => {
    en.forEach((x) => { if (x.isIntersecting) { ogObs.unobserve(x.target); ogQueue.push(x.target); } });
    pumpOg();
  }, { rootMargin: '200px' }) : null;
  function observeOg() { if (ogObs) $$('.media[data-og]', itemsEl).forEach((m) => { if (m.dataset.og && !ogSeen.has(m.dataset.id)) ogObs.observe(m); }); }
  async function pumpOg() {
    while (ogBusy < 3 && ogQueue.length && ogSeen.size < 48) {
      const m = ogQueue.shift(), id = m.dataset.id;
      if (ogSeen.has(id)) continue;
      ogSeen.add(id); ogBusy++;
      api('/proxy/ogimage?url=' + encodeURIComponent(m.dataset.og)).then((r) => {
        if (!r || !r.image_url) return;
        const it = S.items.find((x) => String(x.id) === id);
        if (!AX.safeUrl(r.image_url)) return;
        if (it) it.image_url = r.image_url;
        $$(`.media[data-id="${CSS.escape(id)}"]`).forEach((el) => {
          const img = new Image();
          img.onload = () => { el.classList.remove('art-fallback'); el.querySelector('.label')?.remove(); el.querySelector('img').replaceWith(img); };
          img.alt = ''; img.referrerPolicy = 'no-referrer'; img.src = r.image_url;
        });
      }).catch(() => {}).finally(() => { ogBusy--; pumpOg(); });
    }
  }

  // ── Clicks in the feed ─────────────────────────────────────────────────
  itemsEl.addEventListener('click', (e) => {
    const ent = e.target.closest('[data-entity]');
    if (ent) { e.preventDefault(); e.stopPropagation(); openEntity(ent.dataset.entity); return; }
    const sv = e.target.closest('[data-save]');
    if (sv) { e.preventDefault(); e.stopPropagation(); toggleSave(Number(sv.dataset.save)); return; }
    const a = e.target.closest('.art');
    if (!a) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
    e.preventDefault();
    openReader(Number(a.dataset.id));
  });

  async function toggleSave(id) {
    if (!AX.me) { toast('Sign in to save stories.'); return; }
    const a = S.items.find((x) => x.id === id) || (S.open && S.open.id === id ? S.open : null);
    const on = !(a && a.is_saved);
    try {
      await api(`/articles/${id}/save`, { method: on ? 'POST' : 'DELETE' });
      S.items.filter((x) => x.id === id).forEach((x) => { x.is_saved = on; });
      if (S.open && S.open.id === id) S.open.is_saved = on;
      $$(`[data-save="${id}"]`).forEach((b) => b.setAttribute('aria-pressed', String(on)));
      const rb = $('[data-reader-save]'); if (S.open && S.open.id === id) rb.setAttribute('aria-pressed', String(on));
      toast(on ? 'Saved for later' : 'Removed from saved');
      if (S.saved && !on) { S.items = S.items.filter((x) => x.id !== id); renderItems(); }
    } catch (err) { toast('Could not save: ' + (err.detail || 'error'), true); }
  }

  // ── Reader ─────────────────────────────────────────────────────────────
  const reader = $('[data-reader]'), scrim = $('[data-scrim]'), body = $('[data-reader-body]');
  $('[data-reader-prev]').innerHTML = icon('left'); $('[data-reader-next]').innerHTML = icon('right');
  $('[data-reader-save]').innerHTML = icon('bookmark'); $('[data-reader-share]').innerHTML = icon('share');
  $('[data-reader-close]').innerHTML = icon('close');
  let lastFocus = null;
  async function openReader(id, push = true) {
    lastFocus = document.activeElement;
    const idx = S.items.findIndex((x) => x.id === id);
    if (idx >= 0) S.cursor = idx;
    const base = S.items[idx] || { id };
    reader.hidden = false;
    requestAnimationFrame(() => { reader.classList.add('open'); scrim.classList.add('open'); });
    document.body.style.overflow = 'hidden';
    body.innerHTML = readerHTML(base, true);
    if (push) history.pushState({ a: id }, '', withParam('a', id));
    $('[data-reader-close]').focus();
    try {
      const full = await api('/articles/' + id);
      if (!full.image_url && base.image_url) full.image_url = base.image_url;
      S.open = full;
      body.innerHTML = readerHTML(full, false);
      $('[data-reader-save]').setAttribute('aria-pressed', String(!!full.is_saved));
      document.title = `${full.title} — AX-NEWS`;
      api(`/articles/${id}/view`, { method: 'POST' }).catch(() => {});
      if (AX.me) api(`/articles/${id}/read`, { method: 'POST' }).then(() => {
        const it = S.items.find((x) => x.id === id); if (it) it.is_read = true;
        $$(`.art[data-id="${id}"]`).forEach((el) => el.classList.add('read'));
      }).catch(() => {});
    } catch (e) {
      body.innerHTML = `<div class="empty"><h2>This story is no longer here</h2><p>It may be older than 30 days.</p></div>`;
    }
  }
  function readerHTML(a, loading) {
    const t = topic(a.category);
    const img = AX.safeUrl(a.image_url) ? `<img src="${esc(AX.safeUrl(a.image_url))}" alt="" referrerpolicy="no-referrer" data-fallback="${esc(t.art)}">` : `<img src="${esc(t.art)}" alt="">`;
    const foreign = a.original_lang && a.original_lang !== 'en' && /[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/.test((a.paragraphs || []).join(' '));
    const paras = foreign ? [] : (a.paragraphs || []).filter((p) => p.length > 40 || (a.paragraphs || []).length < 4);
    const lede = paras.length ? paras[0] : (a.excerpt || '');
    const rest = paras.slice(1, 10);
    const host = (() => { try { return new URL(a.url).hostname.replace(/^www\./, ''); } catch (e) { return a.feed_source || 'the source'; } })();
    return `<div class="hero">${img}</div>
      <div class="content">
        <div class="tags"><span class="tag topic" style="--topic:${t.color}">${esc(t.label)}</span>${a.personal ? `<span class="tag mine">${icon('radar', 'sm')}My source</span>` : ''}${a.original_lang && a.original_lang !== 'en' ? `<span class="tag translated">${icon('globe', 'sm')}Translated from ${esc(a.original_lang.toUpperCase())}</span>` : ''}</div>
        <h1>${esc(a.title || '')}</h1>
        <div class="byline">${AX.avatar(a.feed_source)}<b>${esc(a.feed_source || '')}</b><span>${a.published_at ? new Date(a.published_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : ''}</span>
          ${a.reading_minutes ? `<span>${icon('clock', 'sm')} ${a.reading_minutes} min</span>` : ''}${a.view_count ? `<span>${icon('eye', 'sm')} ${AX.num(a.view_count)}</span>` : ''}${sentiment(a)}</div>
        ${loading ? '<div class="skeleton" style="height:120px"></div>' : foreign ? `<p class="muted">The full text is in its original language (${esc(a.original_lang.toUpperCase())}); only the headline is translated.</p>` : `<p class="lede">${esc(lede)}</p><div class="text">${rest.map((p) => `<p>${esc(p)}</p>`).join('')}</div>`}
        <div class="cta">
          ${AX.safeUrl(a.url) ? `<a class="btn primary" href="${esc(AX.safeUrl(a.url))}" target="_blank" rel="noopener noreferrer">${icon('external', 'sm')} Read on ${esc(host)}</a>` : ''}
          <button class="btn" data-copy>${icon('copy', 'sm')} Copy link</button>
        </div>
        ${(a.entities || []).length ? `<div class="tags">${(a.entities || []).map((e) => `<button class="tag link" data-entity="${esc(e)}">${esc(e)}</button>`).join('')}</div>` : ''}
        ${AX.me && AX.me.is_admin && !loading ? `<div class="ai"><h3>${icon('sparkle', 'sm')} Ask the analyst</h3><div data-ai-log></div>
          <form class="add-row" data-ai-form><input class="input" name="q" placeholder="What does this change? Who is affected?" autocomplete="off"><button class="btn primary">Ask</button></form></div>` : ''}
      </div>`;
  }
  function closeReader(pop = false) {
    if (reader.hidden) return;
    reader.classList.remove('open'); scrim.classList.remove('open');
    document.body.style.overflow = '';
    setTimeout(() => { reader.hidden = true; }, 320);
    S.open = null;
    renderHead();
    if (!pop) history.pushState({}, '', withParam('a', null));
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  function step(d) {
    if (!S.items.length) return;
    const i = Math.max(0, Math.min(S.items.length - 1, (S.cursor < 0 ? 0 : S.cursor + d)));
    S.cursor = i;
    openReader(S.items[i].id);
    if (i > S.items.length - 4) load();
  }
  $('[data-reader-close]').addEventListener('click', () => closeReader());
  scrim.addEventListener('click', () => closeReader());
  $('[data-reader-prev]').addEventListener('click', () => step(-1));
  $('[data-reader-next]').addEventListener('click', () => step(1));
  $('[data-reader-save]').addEventListener('click', () => S.open && toggleSave(S.open.id));
  $('[data-reader-share]').addEventListener('click', () => share());
  body.addEventListener('click', (e) => {
    const ent = e.target.closest('[data-entity]');
    if (ent) { closeReader(); openEntity(ent.dataset.entity); }
    if (e.target.closest('[data-copy]')) share(true);
  });
  body.addEventListener('submit', async (e) => {
    const f = e.target.closest('[data-ai-form]');
    if (!f || !S.open) return;
    e.preventDefault();
    const q = f.q.value.trim(); if (!q) return;
    const log = $('[data-ai-log]', body);
    log.insertAdjacentHTML('beforeend', `<div class="msg me">${esc(q)}</div><div class="msg bot" data-pending>Thinking…</div>`);
    f.q.value = '';
    try {
      const r = await api(`/articles/${S.open.id}/chat`, { method: 'POST', json: { message: q } });
      $('[data-pending]', log).outerHTML = `<div class="msg bot">${esc(r.response)}</div>`;
    } catch (err) { $('[data-pending]', log).outerHTML = `<div class="msg bot">${esc(err.detail || 'The analyst is not available.')}</div>`; }
  });
  async function share(copyOnly) {
    if (!S.open) return;
    const url = location.origin + '/?a=' + S.open.id;
    if (!copyOnly && navigator.share) { try { await navigator.share({ title: S.open.title, url }); return; } catch (e) { /* cancelled */ } }
    try { await navigator.clipboard.writeText(url); toast('Link copied'); } catch (e) { toast(url); }
  }

  // ── Entities ───────────────────────────────────────────────────────────
  function openEntity(name) { S.entity = name; S.category = ''; S.source = ''; S.feed = ''; S.search = ''; $('[data-search]').value = ''; reload(); scrollTo({ top: 0, behavior: 'smooth' }); }

  // ── Topics (left rail, phone strip) ────────────────────────────────────
  async function loadTopics() {
    try { S.topics = (await api('/categories/tree')).sort((a, b) => b.total - a.total); } catch (e) { S.topics = []; }
    const hidden = new Set(AX.prefs.get('hidden_categories', []));
    const list = S.topics.filter((t) => !hidden.has(t.category));
    const all = `<button class="topic-link" data-topic=""><span class="thumb" style="background-image:url(/assets/img/topics/default-sm.webp)"></span><span class="name">All topics</span><span class="count">${AX.num(S.topics.reduce((s, x) => s + x.total, 0))}</span></button>`;
    $('[data-topics]').innerHTML = all + list.map((t) => {
      const m = topic(t.category);
      return `<button class="topic-link" data-topic="${esc(t.category)}" style="--topic:${m.color}"><span class="thumb" style="background-image:url(${m.thumb})"></span><span class="name">${esc(m.label)}</span><span class="count">${t.today ? `<b>+${AX.num(t.today)}</b> ` : ''}</span></button>`;
    }).join('');
    $('[data-topics-strip]').innerHTML = `<button class="chip" data-topic="">All</button>` + list.map((t) => `<button class="chip" data-topic="${esc(t.category)}">${esc(topic(t.category).label)} <span class="count">${AX.num(t.today || t.total)}</span></button>`).join('');
    markTopics(); renderHead();
  }
  function markTopics() {
    $$('[data-topic]').forEach((b) => b.classList.toggle('active', !S.entity && !S.source && !S.feed && b.dataset.topic === S.category && !S.saved));
    $$('[data-my-feed]').forEach((b) => b.classList.toggle('active', b.dataset.myFeed === String(S.feed)));
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-topic]');
    if (!b) return;
    if (S.saved || page === 'mine') { location.href = '/?topic=' + encodeURIComponent(b.dataset.topic); return; }
    S.category = b.dataset.topic; S.entity = ''; S.source = ''; S.feed = '';
    reload(); scrollTo({ top: 0, behavior: 'smooth' });
  });

  // Personal sources in the rail
  async function loadMine() {
    if (!AX.me) return;
    try { S.mine = await api('/sources'); } catch (e) { S.mine = []; }
    const n = S.mine.reduce((s, f) => s + (f.week_count || 0), 0);
    $('[data-mine-count]').textContent = n ? '+' + AX.num(n) : '';
    $('[data-my-sources]').innerHTML = S.mine.slice(0, 12).map((f) =>
      `<a class="topic-link" href="/mine?feed=${f.id}" data-my-feed="${f.id}">${AX.avatar(f.name)}<span class="name">${esc(f.name)}</span>
        <span class="count">${f.last_error ? `<span class="err" title="${esc(f.last_error)}">!</span>` : f.week_count ? AX.num(f.week_count) : ''}</span></a>`).join('')
      + `<a class="topic-link" href="/account">${icon('plus', 'sm')}<span class="name">Add a source</span></a>`;
    markTopics(); renderHead();
  }

  // ── Trending (right rail) ──────────────────────────────────────────────
  async function loadTrending() {
    try {
      const d = await api('/trending');
      $('[data-last24]').textContent = AX.num(d.last24h);
      const max = Math.max(1, ...d.entities.map((x) => x.n));
      $('[data-trending]').innerHTML = d.entities.slice(0, 10).map((x, i) =>
        `<button class="trend" data-entity-rail="${esc(x.entity)}"><span class="rank">${i + 1}</span><span class="name">${esc(x.entity)}</span><span class="n">${AX.num(x.n)}</span><span class="bar"><i style="width:${Math.round(100 * x.n / max)}%"></i></span></button>`).join('') || '<p class="muted">Quiet day.</p>';
      $('[data-sources-top]').innerHTML = d.sources.slice(0, 6).map((x) =>
        `<button class="trend" data-source-rail="${esc(x.feed_source)}">${AX.avatar(x.feed_source)}<span class="name">${esc(x.feed_source)}</span><span class="n">${AX.num(x.n)}</span></button>`).join('');
    } catch (e) { $('[data-trending]').innerHTML = '<p class="muted">Unavailable.</p>'; }
  }
  document.addEventListener('click', (e) => {
    const en = e.target.closest('[data-entity-rail]');
    if (en) { if (page !== 'feed') { location.href = '/?entity=' + encodeURIComponent(en.dataset.entityRail); return; } openEntity(en.dataset.entityRail); }
    const so = e.target.closest('[data-source-rail]');
    if (so) { if (page !== 'feed') { location.href = '/?source=' + encodeURIComponent(so.dataset.sourceRail); return; } S.source = so.dataset.sourceRail; S.category = ''; S.entity = ''; reload(); scrollTo({ top: 0, behavior: 'smooth' }); }
  });

  // ── Search ─────────────────────────────────────────────────────────────
  const search = $('[data-search]');
  search.value = S.search;
  search.addEventListener('input', AX.debounce(() => {
    S.search = search.value.trim(); S.entity = '';
    if (S.saved || page === 'mine') { if (S.search.length > 1) location.href = '/?q=' + encodeURIComponent(S.search); return; }
    reload();
  }, 350));

  // ── New stories ────────────────────────────────────────────────────────
  const pill = $('[data-new-pill]');
  async function pollNew() {
    if (document.hidden || !S.newest || S.saved || S.search || S.entity || S.feed || S.source) return;
    try {
      const p = new URLSearchParams({ since: S.newest, scope: page === 'mine' ? 'mine' : S.scope });
      if (S.category) p.set('category', S.category);
      const { count } = await api('/articles/count?' + p);
      if (count > 0) { pill.innerHTML = `${icon('flame', 'sm')} ${count} new ${count === 1 ? 'story' : 'stories'}`; pill.classList.add('show'); }
    } catch (e) { /* offline */ }
  }
  pill.addEventListener('click', () => { pill.classList.remove('show'); reload(); scrollTo({ top: 0, behavior: 'smooth' }); });
  setInterval(pollNew, 90000);

  // ── Keyboard ───────────────────────────────────────────────────────────
  function highlight(i, scroll = true) {
    $$('.art.kb', itemsEl).forEach((x) => x.classList.remove('kb'));
    const el = $(`.art[data-i="${i}"]`, itemsEl);
    if (!el) return;
    el.classList.add('kb');
    if (scroll) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
  document.addEventListener('keydown', (e) => {
    if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) || e.metaKey || e.ctrlKey || e.altKey) return;
    const open = !reader.hidden;
    if (e.key === 'Escape' && open) { closeReader(); return; }
    if (open && (e.key === 'ArrowRight' || e.key === 'j')) { step(1); return; }
    if (open && (e.key === 'ArrowLeft' || e.key === 'k')) { step(-1); return; }
    if (e.key === 's') { const it = open ? S.open : S.items[S.cursor]; if (it) toggleSave(it.id); return; }
    if (open) return;
    if (e.key === 'j' || e.key === 'k') {
      S.cursor = Math.max(0, Math.min(S.items.length - 1, S.cursor + (e.key === 'j' ? 1 : -1)));
      highlight(S.cursor);
      if (S.cursor > S.items.length - 4) load();
    } else if ((e.key === 'o' || e.key === 'Enter') && S.cursor >= 0 && S.items[S.cursor]) {
      openReader(S.items[S.cursor].id);
    } else if (e.key === 'v') {
      const i = VIEWS.findIndex((x) => x[0] === S.view);
      setView(VIEWS[(i + 1) % VIEWS.length][0]);
    }
  });

  // ── URL ────────────────────────────────────────────────────────────────
  function withParam(k, v) {
    const u = new URL(location.href);
    if (v === null || v === '' || v === undefined) u.searchParams.delete(k); else u.searchParams.set(k, v);
    return u.pathname + (u.searchParams.toString() ? '?' + u.searchParams : '');
  }
  function syncUrl() {
    const u = new URL(location.href);
    const set = (k, v) => { if (v) u.searchParams.set(k, v); else u.searchParams.delete(k); };
    set('topic', S.category); set('q', S.search); set('entity', S.entity); set('source', S.source); set('feed', S.feed);
    set('scope', page === 'feed' && S.scope !== 'public' ? S.scope : '');
    history.replaceState(history.state, '', u.pathname + (u.searchParams.toString() ? '?' + u.searchParams : ''));
  }
  window.addEventListener('popstate', () => {
    const a = new URLSearchParams(location.search).get('a');
    if (a) openReader(Number(a), false); else closeReader(true);
  });

  // ── Start ──────────────────────────────────────────────────────────────
  (async () => {
    await AX.ready;
    if (page === 'feed' && !params.get('scope') && AX.me) S.scope = AX.prefs.get('scope', 'public');
    if (!AX.me && S.scope !== 'public') S.scope = 'public';
    S.view = S.view || AX.prefs.get(page === 'mine' ? 'view_mine' : 'view', page === 'mine' ? 'micro' : 'cards');
    renderViews(); renderScope();
    feedEl.className = 'view-' + S.view;
    renderHead();
    loadTopics(); loadTrending(); loadMine();
    load();
    const a = params.get('a');
    if (a) openReader(Number(a), false);
  })();
})();
