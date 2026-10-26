/* AX-NEWS — the world feed catalog in the account page: browse by field,
 * search, follow a feed as one of your sources (translated into English).
 * An administrator may also share a feed with everyone. Depends on core.js. */
(function () {
  'use strict';
  const { $, esc, icon, api, ago, toast } = AX;
  let all = [], domain = 'health', q = '', lang = '', taxonomy = null, me = null;

  async function load() {
    try { taxonomy = await api('/catalog/taxonomy'); } catch (e) { return; }
    const byDomain = {};
    taxonomy.counts.forEach((c) => { byDomain[c.domain] = (byDomain[c.domain] || 0) + c.feeds; });
    $('[data-cat-domains]').innerHTML = taxonomy.domains.map((d) =>
      `<button class="chip${d.key === domain ? ' active' : ''}" data-domain="${esc(d.key)}">${esc(d.label)} <span class="count">${AX.num(byDomain[d.key] || 0)}</span></button>`).join('');
    $('[data-cat-lang]').innerHTML = '<option value="">Every language</option>' + taxonomy.languages.map((l) =>
      `<option value="${esc(l.code)}">${esc(l.name)} · ${l.feeds}${l.translatable ? '' : ' (no translation yet)'}</option>`).join('');
    const total = taxonomy.counts.reduce((n, c) => n + c.feeds, 0), active = taxonomy.counts.reduce((n, c) => n + c.active, 0);
    $('[data-cat-intro]').textContent = `${AX.num(total)} feeds in ${taxonomy.languages.length} languages, each checked and answering today. ${AX.num(active)} already make the shared feed; follow any other and its stories join your own sources — in English, whatever language it is written in.`;
    await list();
  }

  async function list() {
    const box = $('[data-cat-list]');
    box.innerHTML = '<div class="skeleton" style="height:240px"></div>';
    const p = new URLSearchParams({ limit: '1000' });
    if (q) p.set('q', q); else p.set('domain', domain);
    if (lang) p.set('lang', lang);
    try { all = await api('/catalog?' + p); } catch (e) { box.innerHTML = '<p class="muted">The catalog is unavailable.</p>'; return; }
    if (!all.length) { box.innerHTML = '<div class="panel"><p class="muted" style="margin:0">No feed matches.</p></div>'; return; }
    const groups = {};
    all.forEach((f) => (groups[f.category] = groups[f.category] || []).push(f));
    box.innerHTML = Object.entries(groups).map(([cat, feeds]) => {
      const t = AX.topic(cat);
      return `<section class="panel cat-group" style="--topic:${esc(t.color)}">
        <div class="cat-group-head"><span class="thumb" style="background-image:url(${esc(t.thumb)})"></span><h3>${esc(t.label)}</h3><span class="muted">${feeds.length} feed${feeds.length > 1 ? 's' : ''}</span></div>
        <div class="cat-rows">${feeds.map(row).join('')}</div></section>`;
    }).join('');
  }

  function row(f) {
    let action;
    if (f.active) action = `<span class="tag" title="Everyone gets it in the shared feed">${icon('check', 'sm')} In the shared feed</span>`;
    else if (!f.translatable) action = `<span class="tag" title="No translation model for this language is installed yet">No ${esc(f.lang_name)} translation yet</span>`;
    else if (f.followed) action = `<button class="btn sm" data-unfollow="${f.id}">${icon('check', 'sm')} Following</button>`;
    else action = `<button class="btn sm primary" data-follow="${f.id}">${icon('plus', 'sm')} Follow</button>`;
    const share = me && me.is_admin && f.provider !== 'freshrss' && f.translatable
      ? `<button class="btn sm ghost" data-share="${f.id}" data-on="${f.active ? '0' : '1'}" title="${f.active ? 'Stop sharing it' : 'Add it to everyone’s shared feed'}">${f.active ? 'Unshare' : 'Share with everyone'}</button>` : '';
    const host = (f.site_url || f.url).replace(/^https?:\/\/(www\.)?/, '').replace(/\/.*$/, '');
    return `<div class="cat-row">
      <div style="min-width:0">
        <div class="t">${esc(f.title)}${f.lang !== 'en' ? ` <span class="tag translated" title="Written in ${esc(f.lang_name)}, shown in English">${esc(f.lang.toUpperCase())} → EN</span>` : ''}</div>
        <div class="s"><span>${esc(host)}</span>${f.region && f.region !== 'global' ? `<span>${esc(f.region)}</span>` : ''}<span>${AX.num(f.items)} recent</span>${f.newest ? `<span>latest ${ago(f.newest)}</span>` : ''}</div>
      </div>
      <div class="ops">${share}${action}</div>
    </div>`;
  }

  $('[data-cat-domains]').addEventListener('click', (e) => {
    const b = e.target.closest('[data-domain]');
    if (!b) return;
    domain = b.dataset.domain; q = ''; $('[data-cat-q]').value = '';
    $('[data-cat-domains]').querySelectorAll('.chip').forEach((c) => c.classList.toggle('active', c === b));
    list();
  });
  $('[data-cat-q]').addEventListener('input', AX.debounce((e) => {
    q = e.target.value.trim();
    $('[data-cat-domains]').querySelectorAll('.chip').forEach((c) => c.classList.toggle('active', !q && c.dataset.domain === domain));
    list();
  }, 300));
  $('[data-cat-lang]').addEventListener('change', (e) => { lang = e.target.value; list(); });
  $('[data-cat-list]').addEventListener('click', async (e) => {
    const f = e.target.closest('[data-follow]'), u = e.target.closest('[data-unfollow]'), s = e.target.closest('[data-share]');
    const b = f || u || s;
    if (!b) return;
    b.disabled = true;
    const feed = all.find((x) => String(x.id) === (b.dataset.follow || b.dataset.unfollow || b.dataset.share));
    try {
      if (f) { b.textContent = 'Adding…'; await api(`/catalog/${feed.id}/follow`, { method: 'POST' }); feed.followed = true; toast(`${feed.title}: following${feed.lang !== 'en' ? ' — its stories appear once translated' : ''}`); }
      else if (u) { if (!confirm(`Stop following “${feed.title}” and remove its stories?`)) { b.disabled = false; return; } await api(`/catalog/${feed.id}/follow`, { method: 'DELETE' }); feed.followed = false; toast('Removed'); }
      else { const on = b.dataset.on === '1'; await api(`/admin/catalog/${feed.id}/share`, { method: 'POST', json: { active: on } }); feed.active = on; toast(on ? `${feed.title} is now in everyone’s feed` : 'No longer shared'); }
    } catch (ex) { toast(ex.detail || 'That did not work', true); }
    b.closest('.cat-row').outerHTML = row(feed);
  });

  let started = false;
  AX.catalogTab = async () => {
    if (started) return;
    started = true;
    me = await AX.ready;
    load();
  };
})();
