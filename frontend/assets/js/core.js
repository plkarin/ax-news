/* AX-NEWS — shared by every page on base.html: icons, topics, API, the
 * signed-in reader, preferences, theme and the top bar.
 * No framework, no build step: one global, AX. */
(function () {
  'use strict';
  const AX = (window.AX = window.AX || {});

  // ── Icons (24×24 strokes) ──────────────────────────────────────────────
  const P = {
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/>',
    grid: '<rect x="3" y="3" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="2"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2"/>',
    magazine: '<rect x="3" y="3" width="18" height="9" rx="2"/><path d="M3 16h8M3 20h8M14 16h7M14 20h7"/>',
    micro: '<rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/>',
    mosaic: '<rect x="3" y="3" width="8" height="11" rx="2"/><rect x="13" y="3" width="8" height="6" rx="2"/><rect x="3" y="16" width="8" height="5" rx="2"/><rect x="13" y="11" width="8" height="10" rx="2"/>',
    timeline: '<path d="M6 3v18"/><circle cx="6" cy="7" r="2"/><circle cx="6" cy="17" r="2"/><path d="M11 7h10M11 17h10"/>',
    bookmark: '<path d="M6 3h12v18l-6-4-6 4z"/>',
    external: '<path d="M14 4h6v6M20 4l-9 9M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
    share: '<circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="m8.2 10.9 7.6-4.4M8.2 13.1l7.6 4.4"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    left: '<path d="m15 18-6-6 6-6"/>', right: '<path d="m9 6 6 6-6 6"/>',
    home: '<path d="M3 11 12 4l9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    radar: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12 18 6"/><circle cx="12" cy="12" r="1.2"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    shield: '<path d="M12 3 4 6v6c0 5 3.4 8.2 8 9 4.6-.8 8-4 8-9V6z"/>',
    logout: '<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l5-5-5-5M15 12H3"/>',
    plus: '<path d="M12 5v14M5 12h14"/>', check: '<path d="m5 12 5 5L20 7"/>',
    refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6"/>', trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    rss: '<path d="M5 11a8 8 0 0 1 8 8M5 5a14 14 0 0 1 14 14"/><circle cx="6" cy="18" r="1.5"/>',
    youtube: '<rect x="2.5" y="5.5" width="19" height="13" rx="4"/><path d="m10 9.5 5 2.5-5 2.5z"/>',
    reddit: '<circle cx="12" cy="14" r="7"/><circle cx="9.3" cy="13.5" r="1"/><circle cx="14.7" cy="13.5" r="1"/><path d="M9.5 17c1.5 1 3.5 1 5 0M12 7l1.2-4 4 1"/><circle cx="18.5" cy="4.5" r="1.5"/>',
    github: '<path d="M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12.3 12.3 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21"/>',
    mastodon: '<path d="M20.5 8.5c0-4-2.6-5.2-2.6-5.2-2.6-1.2-9.2-1.2-11.8 0 0 0-2.6 1.2-2.6 5.2 0 4.7-.3 10.5 4.3 11.7 1.7.4 3.1.5 4.3.4 2.1-.1 3.3-.8 3.3-.8l-.1-1.6s-1.5.5-3.2.4c-1.7-.1-3.4-.2-3.7-2.2v-.6s1.7.4 3.8.5c1.3.1 2.5-.1 3.7-.2 2.4-.3 4.4-1.7 4.6-3 .4-2 .3-4.6.3-4.6zM16.9 13.6h-2.2V8.3c0-1.1-.5-1.7-1.4-1.7-1 0-1.5.7-1.5 1.9v2.9H9.6V8.5c0-1.2-.5-1.9-1.5-1.9-.9 0-1.4.6-1.4 1.7v5.3H4.5"/>',
    hackernews: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="m8 7 4 6 4-6M12 13v4"/>',
    upload: '<path d="M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
    download: '<path d="M12 4v12M7 11l5 5 5-5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
    sparkle: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>', chat: '<path d="M21 12a8 8 0 0 1-11.9 7L3 21l2-5.6A8 8 0 1 1 21 12z"/>',
    flame: '<path d="M12 3s5 4.5 5 9.5A5 5 0 0 1 7 12.5C7 10 9 8.5 9 8.5s.5 2.5 2.5 3C11 8 12 3 12 3z"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a1 1 0 0 1 1-1h10"/>',
  };
  AX.icon = (name, cls = '') => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${P[name] || ''}</svg>`;

  // ── Topics: label, accent, illustration (made in Canva) ────────────────
  const T = {
    AI: ['Artificial Intelligence', '#7c8cff', 'ai'],
    AI_YouTube: ['AI — Video', '#e879f9', 'video'],
    Semiconductors: ['Semiconductors', '#a78bfa', 'semiconductors'],
    Asia_Semiconductors: ['Asia Semiconductors', '#a78bfa', 'semiconductors'],
    Cybersecurity: ['Cybersecurity', '#fb7185', 'cybersecurity'],
    Cyber_YouTube: ['Cyber — Video', '#e879f9', 'video'],
    Cloud_Infrastructure: ['Cloud & Infrastructure', '#60a5fa', 'cloud'],
    DevOps_SRE: ['DevOps & SRE', '#22d3ee', 'devops'],
    Software_Engineering: ['Software Engineering', '#38bdf8', 'software'],
    Hardware: ['Hardware', '#fbbf24', 'hardware'],
    Robotics_Automation: ['Robotics & Automation', '#4ade80', 'robotics'],
    Quantum_Computing: ['Quantum Computing', '#c084fc', 'quantum'],
    Biotech_Medtech: ['Biotech & Medtech', '#2dd4bf', 'biotech'],
    Space_Aerospace: ['Space & Aerospace', '#93c5fd', 'space'],
    Energy_GreenTech: ['Energy & Green Tech', '#86efac', 'energy'],
    Telecom_5G: ['Telecom & 5G', '#67e8f9', 'telecom'],
    Tech_Market: ['Tech Market & VC', '#facc15', 'market'],
    Geopolitics_TechPolicy: ['Geopolitics & Policy', '#fb923c', 'geopolitics'],
    Research_Papers: ['Research Papers', '#cbd5e1', 'research'],
    Quant_Finance: ['Quant Finance', '#34d399', 'quant-finance'],
    My_Sources: ['My sources', '#f472b6', 'mine'],
  };
  // Every other topic comes from catalog/taxonomy.json, embedded in the page.
  try {
    const tax = JSON.parse(document.getElementById('ax-taxonomy').textContent);
    for (const [k, v] of Object.entries(tax.categories || {})) if (!T[k]) T[k] = v.slice(0, 3);
    AX.DOMAINS = tax.domains || [];
    AX.DOMAIN_OF = Object.fromEntries(Object.entries(tax.categories || {}).map(([k, v]) => [k, v[3]]));
  } catch (e) { AX.DOMAINS = []; AX.DOMAIN_OF = {}; }
  AX.topic = (key) => {
    const t = T[key];
    if (t) return { key, label: t[0], color: t[1], art: `/assets/img/topics/${t[2]}.webp`, thumb: `/assets/img/topics/${t[2]}-sm.webp` };
    const label = String(key || 'News').replace(/_/g, ' ');
    return { key, label, color: '#7c8cff', art: '/assets/img/topics/default.webp', thumb: '/assets/img/topics/default-sm.webp' };
  };
  AX.TOPICS = T;

  // ── Small helpers ──────────────────────────────────────────────────────
  AX.esc = (s) => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  AX.hue = (s) => { let h = 0; for (const c of String(s || '')) h = (h * 31 + c.charCodeAt(0)) % 360; return h; };
  AX.initials = (s) => { const w = String(s || '?').replace(/[^\p{L}\p{N} ]/gu, ' ').trim().split(/\s+/); return ((w[0] || '?')[0] + (w[1] ? w[1][0] : '')).toUpperCase(); };
  AX.avatar = (name, cls = '') => `<span class="avatar ${cls}" style="--h:${AX.hue(name)}" aria-hidden="true">${AX.esc(AX.initials(name))}</span>`;
  const RTF = typeof Intl !== 'undefined' && Intl.RelativeTimeFormat ? new Intl.RelativeTimeFormat('en', { numeric: 'auto', style: 'short' }) : null;
  AX.ago = (iso) => {
    if (!iso) return '';
    const s = Math.round((Date.now() - new Date(iso)) / 1000);
    if (s < 45) return 'just now';
    const steps = [[60, 'second'], [3600, 'minute', 60], [86400, 'hour', 3600], [604800, 'day', 86400]];
    for (let i = 1; i < steps.length; i++) if (s < steps[i][0]) return RTF ? RTF.format(-Math.round(s / steps[i][2]), steps[i][1]) : '';
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  };
  AX.hhmm = (iso) => iso ? new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '';
  AX.day = (iso) => {
    const d = new Date(iso), t = new Date();
    const y = new Date(); y.setDate(t.getDate() - 1);
    if (d.toDateString() === t.toDateString()) return 'Today';
    if (d.toDateString() === y.toDateString()) return 'Yesterday';
    return d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' });
  };
  // Only http(s) addresses ever reach an href or a src: a feed can carry
  // javascript: links.
  AX.safeUrl = (u) => (/^https?:\/\//i.test(String(u || '')) ? String(u) : '');
  AX.num = (n) => Number(n || 0).toLocaleString('en-US');
  AX.debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  AX.$ = (sel, root = document) => root.querySelector(sel);
  AX.$$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  AX.toast = (msg, isError = false) => {
    let box = AX.$('.toasts');
    if (!box) { box = document.createElement('div'); box.className = 'toasts'; box.setAttribute('role', 'status'); document.body.appendChild(box); }
    const t = document.createElement('div');
    t.className = 'toast' + (isError ? ' error' : '');
    t.textContent = msg;
    box.appendChild(t);
    setTimeout(() => t.remove(), 3200);
  };

  // ── API ────────────────────────────────────────────────────────────────
  // Resolves to the JSON body; throws {status, detail} on an error status.
  AX.api = async (path, opts = {}) => {
    const o = { credentials: 'same-origin', ...opts, headers: { ...(opts.headers || {}) } };
    if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers['Content-Type'] = 'application/json'; delete o.json; }
    let res;
    for (let attempt = 0; attempt < 3; attempt++) {
      res = await fetch('/api' + path, o);
      if (res.status !== 429 && res.status < 500) break;
      if (o.method && o.method !== 'GET') break;
      await new Promise((r) => setTimeout(r, 500 * 2 ** attempt));
    }
    const ct = res.headers.get('content-type') || '';
    const body = ct.includes('json') ? await res.json().catch(() => null) : await res.text();
    if (!res.ok) {
      const detail = body && body.detail ? (typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)) : res.statusText;
      throw { status: res.status, detail };
    }
    return body;
  };

  // ── The reader (signed in or not) ──────────────────────────────────────
  AX.me = null;
  AX.ready = (async () => {
    try { AX.me = await AX.api('/auth/me'); } catch (e) { AX.me = null; }
    renderAccount();
    document.documentElement.classList.toggle('signed-in', !!AX.me);
    AX.$$('[data-auth="in"]').forEach((el) => el.classList.toggle('hidden', !AX.me));
    AX.$$('[data-auth="out"]').forEach((el) => el.classList.toggle('hidden', !!AX.me));
    AX.$$('[data-auth="admin"]').forEach((el) => el.classList.toggle('hidden', !(AX.me && AX.me.is_admin)));
    if (AX.me) await AX.prefs.load();
    return AX.me;
  })();

  // ── Preferences: in the browser, and in the account when signed in ─────
  const LS = 'ax-prefs';
  AX.prefs = {
    data: (() => { try { return JSON.parse(localStorage.getItem(LS) || '{}'); } catch (e) { return {}; } })(),
    get(k, d) { return this.data[k] !== undefined ? this.data[k] : d; },
    set(k, v) {
      this.data[k] = v;
      try { localStorage.setItem(LS, JSON.stringify(this.data)); } catch (e) { /* private mode */ }
      if (AX.me) this._push();
    },
    _push: AX.debounce(() => { AX.api('/prefs', { method: 'PUT', json: AX.prefs.data }).catch(() => {}); }, 600),
    async load() {
      try {
        const server = await AX.api('/prefs');
        this.data = { ...this.data, ...server };
        try { localStorage.setItem(LS, JSON.stringify(this.data)); } catch (e) { /* ignore */ }
      } catch (e) { /* keep local */ }
      AX.theme.apply();
    },
  };

  // ── Theme: system, dark or light ───────────────────────────────────────
  AX.theme = {
    current() {
      const p = AX.prefs.get('theme', 'system');
      if (p !== 'system') return p;
      return window.matchMedia && matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    },
    apply() {
      const t = this.current();
      document.documentElement.dataset.theme = t;
      AX.$$('[data-theme-toggle]').forEach((b) => { b.innerHTML = AX.icon(t === 'dark' ? 'sun' : 'moon'); b.title = t === 'dark' ? 'Light theme' : 'Dark theme'; });
    },
    toggle() { AX.prefs.set('theme', this.current() === 'dark' ? 'light' : 'dark'); this.apply(); },
  };
  AX.theme.apply();

  // ── Top bar ────────────────────────────────────────────────────────────
  function renderAccount() {
    const slot = AX.$('[data-account]');
    if (!slot) return;
    if (!AX.me) {
      slot.innerHTML = `<a class="btn sm primary" href="/login.html">Sign in</a>`;
      return;
    }
    const u = AX.me;
    slot.innerHTML = `
      <div class="menu" data-menu>
        <button class="btn icon" aria-haspopup="true" aria-expanded="false" title="${AX.esc(u.username)}">${AX.avatar(u.username)}</button>
        <div class="menu-pop" role="menu">
          <div class="who">${AX.avatar(u.username, 'lg')}<div><b>${AX.esc(u.username)}</b><small>${u.is_admin ? 'Administrator' : 'Reader'}</small></div></div>
          <hr>
          <a href="/mine" role="menuitem">${AX.icon('radar')} My sources</a>
          <a href="/saved" role="menuitem">${AX.icon('bookmark')} Saved</a>
          <a href="/account" role="menuitem">${AX.icon('settings')} Account & display</a>
          ${u.is_admin ? `<a href="/admin.html" role="menuitem">${AX.icon('shield')} Administration</a>` : ''}
          <hr>
          <button data-logout role="menuitem">${AX.icon('logout')} Sign out</button>
        </div>
      </div>`;
    AX.$('[data-logout]', slot).addEventListener('click', async () => {
      await AX.api('/auth/logout', { method: 'POST' }).catch(() => {});
      location.href = '/';
    });
  }
  document.addEventListener('click', (e) => {
    const m = e.target.closest('[data-menu]');
    AX.$$('[data-menu].open').forEach((x) => { if (x !== m) { x.classList.remove('open'); x.firstElementChild.setAttribute('aria-expanded', 'false'); } });
    if (m && e.target.closest('[data-menu] > button')) {
      const open = m.classList.toggle('open');
      m.firstElementChild.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    if (e.target.closest('[data-theme-toggle]')) AX.theme.toggle();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') AX.$$('[data-menu].open').forEach((x) => x.classList.remove('open'));
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
    if (!typing && (e.key === '/' || (e.key === 'k' && (e.metaKey || e.ctrlKey)))) {
      const s = AX.$('[data-search]');
      if (s) { e.preventDefault(); s.focus(); s.select(); }
    }
  });
  // On pages other than the feed, the search goes to the feed.
  const s = AX.$('[data-search]');
  if (s && !document.body.dataset.feed) {
    s.addEventListener('keydown', (e) => { if (e.key === 'Enter' && s.value.trim()) location.href = '/?q=' + encodeURIComponent(s.value.trim()); });
  }
})();
