/* AX-NEWS — TV screens in the account page: make a screen, choose its
 * topics, layout and theme, open it on a TV. Depends on core.js. */
(function () {
  'use strict';
  const { $, $$, esc, icon, api, ago, toast } = AX;
  const LAYOUTS = {
    spotlight: ['Spotlight', 'One story, full screen, and what comes next'],
    newsroom: ['Newsroom', 'A main story beside the live list'],
    wall: ['Wall', 'Five tiles, one turning at a time'],
    columns: ['Columns', 'A column per topic, scrolling'],
    headlines: ['Headlines', 'Big words only, readable from afar'],
    magazine: ['Magazine', 'An editorial cover'],
  };
  const THEMES = {
    aurora: ['Aurora', '#050a16', '#5aa8ff', '#a78bfa'],
    broadcast: ['Broadcast', '#07080b', '#ff2d3d', '#ffb800'],
    paper: ['Paper', '#f4efe6', '#b4321f', '#1c1a17'],
    terminal: ['Terminal', '#030806', '#3dff8f', '#ffc53d'],
    clinic: ['Clinic', '#f3f8fa', '#0a9396', '#0d2a33'],
    nebula: ['Nebula', '#0a0614', '#f472b6', '#818cf8'],
  };
  let screens = [], defaults = {}, editing = null, me = null, used = [];

  // A drawing of the layout in the theme's colours.
  function mini(cfg) {
    const t = THEMES[cfg.theme] || THEMES.aurora;
    return `<div class="tv-mini l-${esc(cfg.layout)}" style="--m-bg:${t[1]};--m-a:${t[2]};--m-b:${t[3]}">${'<i></i>'.repeat(6)}</div>`;
  }

  async function load() {
    try {
      const r = await api('/tv/screens');
      screens = r.screens; defaults = r.defaults;
    } catch (e) { $('[data-tv-list]').innerHTML = '<p class="muted">Screens are unavailable.</p>'; return; }
    render();
  }

  function render() {
    const box = $('[data-tv-list]');
    if (!screens.length) {
      box.innerHTML = `<div class="panel empty" style="grid-column:1/-1;padding:34px 10px"><h2>No screen yet</h2><p>Make one for each TV: the lobby, the break room, the lab. Each has its own address, topics and look.</p><button class="btn primary" data-tv-new>New screen</button></div>`;
      return;
    }
    box.innerHTML = screens.map((s) => {
      const c = s.config;
      const topics = c.topics.length ? c.topics.slice(0, 4).map((k) => AX.topic(k).label).join(', ') + (c.topics.length > 4 ? ` +${c.topics.length - 4}` : '') : 'Every topic';
      return `<article class="panel tv-card" data-id="${s.id}">
        ${mini(c)}
        <div class="tv-card-body">
          <div class="t">${esc(s.name)}</div>
          <div class="s">${esc(LAYOUTS[c.layout][0])} · ${esc(THEMES[c.theme][0])} · ${esc(topics)}</div>
          <div class="s">${c.scope === 'public' ? 'Shared feeds' : c.scope === 'mine' ? 'Your sources only' : 'Shared feeds and your sources'} · ${s.last_seen_at ? `on air ${ago(s.last_seen_at)}` : 'not opened yet'}</div>
          <div class="tv-url"><code>${esc(s.url)}</code><button class="btn icon sm ghost" data-copy title="Copy the address" aria-label="Copy the address">${icon('copy', 'sm')}</button></div>
        </div>
        <div class="tv-card-ops">
          <a class="btn sm primary" href="${esc(s.url)}" target="_blank" rel="noopener">Open</a>
          <button class="btn sm" data-edit>Settings</button>
          <button class="btn sm ghost" data-rotate title="A new address: the old one stops working">New address</button>
          <button class="btn icon sm ghost danger" data-del title="Delete" aria-label="Delete">${icon('trash', 'sm')}</button>
        </div>
      </article>`;
    }).join('');
  }

  function form(s) {
    const c = s ? s.config : { ...defaults, title: 'Tech Intelligence' };
    const name = s ? s.name : '';
    const doms = AX.DOMAINS.map((d) => {
      const cats = Object.keys(AX.TOPICS).filter((k) => AX.DOMAIN_OF[k] === d.key);
      if (!cats.length) return '';
      return `<fieldset class="tv-topics-dom"><legend>${esc(d.label)}</legend>${cats.map((k) => `
        <label class="tv-topic${used.includes(k) ? ' has' : ''}"><input type="checkbox" name="topic" value="${esc(k)}" ${c.topics.includes(k) ? 'checked' : ''}><span style="--topic:${esc(AX.topic(k).color)}">${esc(AX.topic(k).label)}</span></label>`).join('')}</fieldset>`;
    }).join('');
    const mine = AX.TOPICS.My_Sources ? `<label class="tv-topic"><input type="checkbox" name="topic" value="My_Sources" ${c.topics.includes('My_Sources') ? 'checked' : ''}><span>My sources (uncategorised)</span></label>` : '';
    return `
      <div class="tv-editor-head"><h3>${s ? 'Screen settings' : 'New screen'}</h3><button class="btn icon sm ghost" type="button" data-close aria-label="Close">${icon('close', 'sm')}</button></div>
      <div class="grid-2">
        <div>
          <div class="field"><label for="tv-name">Name (for you)</label><input class="input" id="tv-name" name="name" maxlength="80" placeholder="Lobby, break room…" value="${esc(name)}"></div>
          <div class="field"><label for="tv-title">Title on screen</label><input class="input" id="tv-title" name="title" maxlength="60" value="${esc(c.title)}"><span class="hint">Under the AX·NEWS name: “Tech Intelligence”, “Oncology Watch”…</span></div>
        </div>
        <div>
          <div class="field"><label>What it shows</label>
            <div class="segmented" data-seg="scope">${[['public', 'Shared feeds'], ['all', 'Shared + mine'], ['mine', 'Only mine']].map(([v, l]) => `<button type="button" data-v="${v}" aria-pressed="${c.scope === v}">${l}</button>`).join('')}</div>
            <span class="hint">“Mine” puts your own sources on the screen: anyone who has its address sees their headlines.</span></div>
          <div class="field"><label>Alerts band</label>
            <div class="segmented" data-seg="alerts">${[['cve', 'Security (CVE)'], ['keywords', 'My words'], ['none', 'None']].map(([v, l]) => `<button type="button" data-v="${v}" aria-pressed="${c.alerts === v}">${l}</button>`).join('')}</div>
            <input class="input${c.alerts === 'keywords' ? '' : ' hidden'}" style="margin-top:8px" name="alert_words" placeholder="FDA approval, phase 3, breakthrough" value="${esc((c.alert_words || []).join(', '))}"></div>
        </div>
      </div>
      <div class="field"><label>Layout</label><div class="option-cards tv-layouts">${Object.entries(LAYOUTS).map(([k, [l, d]]) => `
        <button type="button" class="option-card" data-layout="${k}" aria-pressed="${c.layout === k}">${mini({ layout: k, theme: c.theme })}<b>${l}</b><small>${d}</small></button>`).join('')}</div></div>
      <div class="field"><label>Theme</label><div class="tv-themes">${Object.entries(THEMES).map(([k, [l, bg, a, b]]) => `
        <button type="button" class="tv-swatch" data-theme="${k}" aria-pressed="${c.theme === k}" style="--s-bg:${bg};--s-a:${a};--s-b:${b}"><i></i><span>${l}</span></button>`).join('')}</div></div>
      <div class="field"><label>Topics <span class="muted" style="font-weight:500">— none ticked: every topic of what it shows. Bold: topics with stories now.</span></label><div class="tv-topics">${doms}${mine}</div></div>
      <div class="grid-2">
        <div class="field"><label for="tv-dwell">Seconds per story: <b data-dwell-v>${c.dwell}</b></label><input id="tv-dwell" type="range" name="dwell" min="6" max="60" step="1" value="${c.dwell}"></div>
        <div class="field"><label for="tv-hours">Stories from the last</label><select class="select" id="tv-hours" name="hours">${[[12, '12 hours'], [24, '24 hours'], [48, '2 days'], [72, '3 days'], [168, 'week']].map(([v, l]) => `<option value="${v}" ${c.hours === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
      </div>
      <div class="tv-switches">${[['show_qr', 'QR code to read on a phone'], ['show_ticker', 'Headline ticker'], ['show_clock', 'Clock'], ['rotate_layouts', 'A different layout every hour'], ['night_dim', 'Dim from 20:00 to 07:00']].map(([k, l]) => `
        <label><span class="switch"><input type="checkbox" name="${k}" ${c[k] ? 'checked' : ''}><i></i></span>${l}</label>`).join('')}</div>
      <div style="display:flex;gap:10px;margin-top:18px"><button class="btn primary" type="submit">${s ? 'Save' : 'Create the screen'}</button><button class="btn" type="button" data-close>Cancel</button></div>`;
  }

  function open(s) {
    editing = s;
    const f = $('[data-tv-form]');
    f.innerHTML = form(s);
    f.classList.remove('hidden');
    f.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  function read(f) {
    const pressed = (sel) => { const b = $(`${sel} [aria-pressed="true"]`, f); return b ? b.dataset.v || b.dataset.layout || b.dataset.theme : undefined; };
    const el = f.elements;
    return {
      name: el.namedItem('name').value.trim(),
      config: {
        title: el.namedItem('title').value.trim(), scope: pressed('[data-seg="scope"]'), alerts: pressed('[data-seg="alerts"]'),
        alert_words: el.namedItem('alert_words').value.split(',').map((w) => w.trim()).filter(Boolean),
        layout: pressed('.tv-layouts'), theme: pressed('.tv-themes'),
        topics: $$('input[name="topic"]:checked', f).map((i) => i.value),
        dwell: Number(el.namedItem('dwell').value), hours: Number(el.namedItem('hours').value),
        ...Object.fromEntries(['show_qr', 'show_ticker', 'show_clock', 'rotate_layouts', 'night_dim'].map((k) => [k, el.namedItem(k).checked])),
      },
    };
  }

  const f = $('[data-tv-form]');
  f.addEventListener('click', (e) => {
    const b = e.target.closest('button[type="button"]');
    if (!b) return;
    if (b.matches('[data-close]')) { f.classList.add('hidden'); return; }
    const group = b.parentElement;
    if (b.matches('[data-v],[data-layout],[data-theme]')) {
      group.querySelectorAll('[aria-pressed]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      if (group.matches('[data-seg="alerts"]')) f.elements.namedItem('alert_words').classList.toggle('hidden', b.dataset.v !== 'keywords');
      if (b.dataset.theme) $$('.tv-layouts .tv-mini', f).forEach((m) => { const t = THEMES[b.dataset.theme]; m.style.cssText = `--m-bg:${t[1]};--m-a:${t[2]};--m-b:${t[3]}`; });
    }
  });
  f.addEventListener('input', (e) => { if (e.target.name === 'dwell') $('[data-dwell-v]', f).textContent = e.target.value; });
  f.addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = read(f), btn = f.querySelector('[type="submit"]');
    btn.disabled = true;
    try {
      if (editing) await api(`/tv/screens/${editing.id}`, { method: 'PATCH', json: body });
      else { const s = await api('/tv/screens', { method: 'POST', json: body }); toast('Screen created — open it on the TV'); window.open(s.url, '_blank', 'noopener'); }
      f.classList.add('hidden');
      await load();
    } catch (ex) { toast(ex.detail || 'Could not save', true); }
    btn.disabled = false;
  });

  document.addEventListener('click', async (e) => {
    if (e.target.closest('[data-tv-new]')) { open(null); return; }
    const card = e.target.closest('.tv-card');
    if (!card) return;
    const s = screens.find((x) => String(x.id) === card.dataset.id);
    if (e.target.closest('[data-edit]')) open(s);
    else if (e.target.closest('[data-copy]')) {
      try { await navigator.clipboard.writeText(s.url); toast('Address copied'); } catch (ex) { prompt('The screen’s address', s.url); }
    } else if (e.target.closest('[data-rotate]')) {
      if (!confirm(`Give “${s.name}” a new address? The TV showing the old one will stop until you open the new one.`)) return;
      try { await api(`/tv/screens/${s.id}/token`, { method: 'POST' }); toast('New address ready'); load(); } catch (ex) { toast(ex.detail || 'Failed', true); }
    } else if (e.target.closest('[data-del]')) {
      if (!confirm(`Delete “${s.name}”? The TV showing it will stop.`)) return;
      try { await api(`/tv/screens/${s.id}`, { method: 'DELETE' }); toast('Deleted'); load(); } catch (ex) { toast(ex.detail || 'Failed', true); }
    }
  });

  let started = false;
  AX.screensTab = async () => {
    if (started) return;
    started = true;
    me = await AX.ready;
    try { used = (await api('/categories')).filter(Boolean); } catch (e) { used = []; }
    load();
  };
})();
