/* AX-NEWS — the reader's space: own sources, display, profile, AI notes.
 * Depends on core.js (window.AX). */
(function () {
  'use strict';
  const { $, $$, esc, icon, api, ago, toast } = AX;
  const KIND = { rss: ['rss', 'Feed'], youtube: ['youtube', 'YouTube'], reddit: ['reddit', 'Reddit'], github: ['github', 'GitHub'], mastodon: ['mastodon', 'Mastodon'], hackernews: ['hackernews', 'Hacker News'] };
  const kindIcon = (k) => { const v = KIND[k] || KIND.rss; return `<span class="kind ${k || 'rss'}" title="${v[1]}">${icon(v[0])}</span>`; };
  const EXAMPLES = [['Hacker News', 'hn'], ['The Verge', 'https://www.theverge.com'], ['r/technology', 'r/technology'], ['Ars Technica', 'https://arstechnica.com'], ['Fireship (YouTube)', 'https://www.youtube.com/@Fireship'], ['uv releases', 'github.com/astral-sh/uv']];
  let topics = [];

  // ── Tabs ───────────────────────────────────────────────────────────────
  function show(tab) {
    $$('[role="tab"]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
    $$('[data-panel]').forEach((p) => p.classList.toggle('hidden', p.dataset.panel !== tab));
    if (tab === 'catalog' && AX.catalogTab) AX.catalogTab();
    if (tab === 'tv' && AX.screensTab) AX.screensTab();
    history.replaceState(null, '', '/account' + (tab === 'sources' ? '' : '#' + tab));
  }
  $('.tabs').addEventListener('click', (e) => { const b = e.target.closest('[data-tab]'); if (b) show(b.dataset.tab); });

  // ── Sources ────────────────────────────────────────────────────────────
  $('[data-examples]').innerHTML = '<span class="muted" style="font-size:13px;align-self:center">Try:</span>' +
    EXAMPLES.map(([l, v]) => `<button class="chip" type="button" data-example="${esc(v)}">${esc(l)}</button>`).join('');
  $('[data-examples]').addEventListener('click', (e) => {
    const b = e.target.closest('[data-example]');
    if (b) { $('#src-input').value = b.dataset.example; $('[data-discover]').requestSubmit(); }
  });

  function categoryOptions(sel) {
    const opts = ['<option value="">My sources</option>'].concat(topics.map((t) => `<option value="${esc(t)}" ${t === sel ? 'selected' : ''}>${esc(AX.topic(t).label)}</option>`));
    return opts.join('');
  }

  $('[data-discover]').addEventListener('submit', async (e) => {
    e.preventDefault();
    const q = e.target.q.value.trim(), btn = e.target.querySelector('button'), err = $('[data-discover-err]'), out = $('[data-found]');
    err.classList.remove('show'); out.innerHTML = '';
    if (!q) return;
    btn.disabled = true; btn.textContent = 'Looking…';
    out.innerHTML = '<div class="skeleton" style="height:96px"></div>';
    try {
      const found = await api('/sources/discover', { method: 'POST', json: { input: q } });
      out.innerHTML = found.map((f, i) => `
        <div class="found-item" data-i="${i}">
          ${kindIcon(f.kind)}
          <div style="min-width:0">
            <div class="t">${esc(f.title)}</div>
            <div class="u">${esc(f.url)}</div>
            ${f.sample && f.sample.length ? `<ul>${f.sample.map((s) => `<li>${esc(s)}</li>`).join('')}</ul>` : ''}
            <div style="display:flex;gap:8px;margin-top:10px;align-items:center;flex-wrap:wrap">
              <select class="select" style="height:34px;width:auto" data-cat>${categoryOptions('')}</select>
              <span class="muted" style="font-size:12.5px">${AX.num(f.count)} recent stories</span>
            </div>
          </div>
          <button class="btn sm ${f.already ? '' : 'primary'}" data-follow="${i}" ${f.already ? 'disabled' : ''}>${f.already ? icon('check', 'sm') + ' Following' : icon('plus', 'sm') + ' Follow'}</button>
        </div>`).join('');
      out._found = found;
    } catch (ex) {
      out.innerHTML = '';
      err.textContent = ex.detail || 'No feed found.'; err.classList.add('show');
    } finally { btn.disabled = false; btn.textContent = 'Find feeds'; }
  });

  $('[data-found]').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-follow]');
    if (!b) return;
    const box = $('[data-found]'), f = box._found[Number(b.dataset.follow)], row = b.closest('.found-item');
    b.disabled = true; b.textContent = 'Adding…';
    try {
      const s = await api('/sources', { method: 'POST', json: { url: f.url, name: f.title, kind: f.kind, category: $('[data-cat]', row).value || null } });
      b.innerHTML = icon('check', 'sm') + ' Following'; b.classList.remove('primary');
      toast(`${s.name}: ${AX.num(s.item_count)} stories added`);
      loadSources();
    } catch (ex) { b.disabled = false; b.innerHTML = icon('plus', 'sm') + ' Follow'; toast(ex.detail || 'Could not add it', true); }
  });

  async function loadSources() {
    const list = $('[data-sources]');
    let rows = [];
    try { rows = await api('/sources'); } catch (e) { list.innerHTML = '<p class="muted">Could not load your sources.</p>'; return; }
    $('[data-src-count]').textContent = rows.length ? `Your sources · ${rows.length}` : 'Your sources';
    if (!rows.length) {
      list.innerHTML = `<div class="empty" style="padding:30px 10px"><div class="art-hero" style="background-image:url(/assets/img/topics/mine.webp)"></div><h2>No source yet</h2><p>Add one on the left: it shows up in <a href="/mine" style="color:var(--accent)">My sources</a> within seconds.</p></div>`;
      return;
    }
    list.innerHTML = rows.map((f) => {
      const status = f.last_error
        ? `<span class="bad" title="${esc(f.last_error)}">${icon('close', 'sm')} ${esc(f.last_error)}</span>`
        : f.last_ok_at ? `<span class="good">${icon('check', 'sm')} checked ${ago(f.last_ok_at)}</span>` : '<span>waiting for its first fetch</span>';
      return `<div class="src-row ${f.active ? '' : 'off'}" data-id="${f.id}">
        ${kindIcon(f.kind)}
        <div style="min-width:0">
          <div class="t"><span>${esc(f.name)}</span></div>
          <div class="s">${status}<span>${AX.num(f.week_count || 0)} this week</span>${f.latest_at ? `<span>latest ${ago(f.latest_at)}</span>` : ''}${f.lang && f.lang !== 'en' ? (f.translatable ? `<span class="tag translated">${esc(f.lang_name)} → English${f.translating ? ` · ${AX.num(f.translating)} in translation` : ''}</span>` : `<span class="bad">${esc(f.lang_name)}: no translation into English yet</span>`) : ''}</div>
          <div class="s"><a href="/mine?feed=${f.id}" style="color:var(--accent)">Read</a><span>${esc(AX.topic(f.category || 'My_Sources').label)}</span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:260px">${esc(f.site_url || f.url)}</span></div>
        </div>
        <div class="ops">
          <label class="switch" title="${f.active ? 'Pause' : 'Resume'}"><input type="checkbox" data-active ${f.active ? 'checked' : ''} aria-label="Active"><i></i></label>
          <button class="btn icon sm ghost" data-refresh title="Fetch now" aria-label="Fetch now">${icon('refresh', 'sm')}</button>
          <button class="btn icon sm ghost" data-rename title="Rename" aria-label="Rename">${icon('settings', 'sm')}</button>
          <button class="btn icon sm ghost danger" data-delete title="Remove" aria-label="Remove">${icon('trash', 'sm')}</button>
        </div>
      </div>`;
    }).join('');
  }
  $('[data-sources]').addEventListener('click', async (e) => {
    const row = e.target.closest('.src-row');
    if (!row) return;
    const id = row.dataset.id, name = $('.t span', row).textContent;
    if (e.target.closest('[data-refresh]')) {
      const b = e.target.closest('[data-refresh]'); b.disabled = true;
      try { const r = await api(`/sources/${id}/refresh`, { method: 'POST' }); toast(r.ok ? `${name}: ${r.new || 0} new` : `${name}: ${r.error}`, !r.ok); }
      catch (ex) { toast(ex.detail || 'Could not refresh', true); }
      loadSources();
    } else if (e.target.closest('[data-rename]')) {
      const n = prompt('Name of this source', name);
      if (n && n.trim() && n !== name) { await api(`/sources/${id}`, { method: 'PATCH', json: { name: n.trim() } }).catch((ex) => toast(ex.detail, true)); loadSources(); }
    } else if (e.target.closest('[data-delete]')) {
      if (!confirm(`Remove “${name}” and every story it brought?`)) return;
      try { await api(`/sources/${id}`, { method: 'DELETE' }); toast('Removed'); } catch (ex) { toast(ex.detail || 'Could not remove', true); }
      loadSources();
    }
  });
  $('[data-sources]').addEventListener('change', async (e) => {
    const cb = e.target.closest('[data-active]');
    if (!cb) return;
    const id = cb.closest('.src-row').dataset.id;
    try { await api(`/sources/${id}`, { method: 'PATCH', json: { active: cb.checked } }); } catch (ex) { toast(ex.detail, true); }
    loadSources();
  });

  $('[data-opml]').addEventListener('change', async (e) => {
    const file = e.target.files[0], msg = $('[data-opml-msg]');
    if (!file) return;
    $('[data-opml-label]').textContent = 'Importing…';
    msg.className = 'alert';
    try {
      const r = await api('/sources/opml', { method: 'POST', json: { opml: await file.text() } });
      msg.textContent = `${r.added} sources added` + (r.failed.length ? ` · ${r.failed.length} could not be read` : '') + '. Their stories arrive within 5 minutes.';
      msg.className = 'alert show ' + (r.failed.length ? 'err' : 'ok');
      loadSources();
    } catch (ex) { msg.textContent = ex.detail || 'Import failed'; msg.className = 'alert show err'; }
    $('[data-opml-label]').textContent = 'Import OPML'; e.target.value = '';
  });

  // ── Display ────────────────────────────────────────────────────────────
  const VIEWS = [['cards', 'grid', 'Cards', 'Pictures and summaries'], ['magazine', 'magazine', 'Magazine', 'A lead story, then the rest'], ['micro', 'micro', 'Micro', 'Short news, one column'], ['list', 'list', 'List', 'Dense headlines by day'], ['mosaic', 'mosaic', 'Mosaic', 'A wall of pictures'], ['timeline', 'timeline', 'Timeline', 'Hour by hour']];
  function renderDisplay() {
    const v = AX.prefs.get('view', 'cards');
    $('[data-opt-view]').innerHTML = VIEWS.map(([k, ic, l, d]) => `<button class="option-card" data-v="${k}" aria-pressed="${k === v}"><span class="pic">${icon(ic, 'lg')}</span><b>${l}</b><small>${d}</small></button>`).join('');
    $$('[data-opt-theme] button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === AX.prefs.get('theme', 'system'))));
    $$('[data-opt-scope] button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === AX.prefs.get('scope', 'public'))));
    const hidden = new Set(AX.prefs.get('hidden_categories', []));
    $('[data-opt-topics]').innerHTML = topics.map((t) => { const m = AX.topic(t); return `<label style="display:flex;gap:10px;align-items:center;font-size:14px"><span class="switch"><input type="checkbox" data-topic-on="${esc(t)}" ${hidden.has(t) ? '' : 'checked'}><i></i></span><span class="thumb" style="width:24px;height:24px;border-radius:7px;background:url(${m.thumb}) 70% 50%/cover"></span>${esc(m.label)}</label>`; }).join('');
  }
  $('[data-opt-view]').addEventListener('click', (e) => { const b = e.target.closest('[data-v]'); if (b) { AX.prefs.set('view', b.dataset.v); renderDisplay(); toast('Layout saved'); } });
  $('[data-opt-theme]').addEventListener('click', (e) => { const b = e.target.closest('[data-v]'); if (b) { AX.prefs.set('theme', b.dataset.v); AX.theme.apply(); renderDisplay(); } });
  $('[data-opt-scope]').addEventListener('click', (e) => { const b = e.target.closest('[data-v]'); if (b) { AX.prefs.set('scope', b.dataset.v); renderDisplay(); toast('Saved'); } });
  $('[data-opt-topics]').addEventListener('change', (e) => {
    const cb = e.target.closest('[data-topic-on]'); if (!cb) return;
    const hidden = new Set(AX.prefs.get('hidden_categories', []));
    if (cb.checked) hidden.delete(cb.dataset.topicOn); else hidden.add(cb.dataset.topicOn);
    AX.prefs.set('hidden_categories', [...hidden]);
  });

  // ── Profile ────────────────────────────────────────────────────────────
  async function loadProfile() {
    try {
      const p = await api('/profile');
      $('[data-username]').value = p.username || ''; $('[data-email]').value = p.email || '—';
      $('[data-kpis]').innerHTML = [[p.articles_read, 'stories read'], [p.feeds_count, 'own sources'], [p.saved_count, 'saved'], [p.knowledge_count, 'AI notes']]
        .map(([n, l]) => `<div class="kpi"><b>${AX.num(n || 0)}</b><span>${l}</span></div>`).join('');
      if (p.knowledge_count) $('[data-notes-tab]').classList.remove('hidden');
    } catch (e) { /* signed out */ }
  }
  $('[data-password]').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target, msg = $('[data-pw-msg]');
    msg.className = 'alert';
    if (f.next.value !== f.confirm.value) { msg.textContent = 'The two new passwords differ.'; msg.className = 'alert show err'; return; }
    try {
      await api('/profile/password', { method: 'POST', json: { current_password: f.current.value, new_password: f.next.value } });
      msg.textContent = 'Password updated.'; msg.className = 'alert show ok'; f.reset();
    } catch (ex) { msg.textContent = ex.detail || 'Could not update it.'; msg.className = 'alert show err'; }
  });

  async function loadNotes() {
    try {
      const notes = await api('/knowledge');
      $('[data-notes]').innerHTML = notes.length ? notes.map((n) => `<div class="src-row" style="grid-template-columns:1fr"><div><div class="t"><span class="tag">${esc(n.domain || '')}</span> ${esc(n.gap_identified || '')}</div><div class="s" style="color:var(--text-2);font-size:14px">${esc(n.gap_resolved || '')}</div><div class="s">${ago(n.created_at)}</div></div></div>`).join('') : '<p class="muted">Nothing yet.</p>';
    } catch (e) { $('[data-notes]').innerHTML = '<p class="muted">Unavailable.</p>'; }
  }

  // ── Start ──────────────────────────────────────────────────────────────
  (async () => {
    const me = await AX.ready;
    if (!me) return;
    $('[data-me-avatar]').innerHTML = AX.avatar(me.username, 'lg');
    try { topics = (await api('/categories')).filter(Boolean); } catch (e) { topics = Object.keys(AX.TOPICS); }
    renderDisplay(); loadSources(); loadProfile(); loadNotes();
    const h = location.hash.slice(1);
    if (['catalog', 'tv', 'display', 'profile', 'notes'].includes(h)) show(h);
  })();
})();
