const API = '/api';
const PAGE_SIZE = 24;

let isLoading = false;
let hasMore = true;
let currentOffset = 0;
let loadRetries = 0;
const MAX_RETRIES = 4;

let state = {
  category: '', search: '',
  view: 'feed',
  isAdmin: false,
};

// ── Sentiment config ──────────────────────────────────────────────
const SENTIMENT = {
  breakthrough:  { label: '🟣 Breakthrough',   cls: 'badge-sentiment-breakthrough'  },
  very_positive: { label: '🟢 Very positive',   cls: 'badge-sentiment-very_positive' },
  positive:      { label: '🟩 Positive',        cls: 'badge-sentiment-positive'      },
  neutral:       { label: '⬜ Neutral',          cls: 'badge-sentiment-neutral'       },
  negative:      { label: '🟧 Negative',        cls: 'badge-sentiment-negative'      },
  very_negative: { label: '🔴 Very negative',   cls: 'badge-sentiment-very_negative' },
};

// Category color palette for placeholders
const CAT_COLORS = {
  'AI':                     {bg:'#1e1b4b', fg:'#818cf8', icon:'🤖'},
  'AI_YouTube':             {bg:'#1e1b4b', fg:'#818cf8', icon:'▶'},
  'Semiconductors':         {bg:'#1c1917', fg:'#a78bfa', icon:'🔬'},
  'Asia_Semiconductors':    {bg:'#1c1917', fg:'#a78bfa', icon:'🏭'},
  'Cybersecurity':          {bg:'#1c0a0a', fg:'#f87171', icon:'🛡'},
  'Cyber_YouTube':          {bg:'#1c0a0a', fg:'#f87171', icon:'▶'},
  'Cloud_Infrastructure':   {bg:'#0c1a2e', fg:'#60a5fa', icon:'☁'},
  'DevOps_SRE':             {bg:'#0f172a', fg:'#38bdf8', icon:'⚙'},
  'Software_Engineering':   {bg:'#0a1628', fg:'#7dd3fc', icon:'💻'},
  'Hardware':               {bg:'#1a1209', fg:'#fbbf24', icon:'🖥'},
  'Robotics_Automation':    {bg:'#0a1a0e', fg:'#4ade80', icon:'🦾'},
  'Quantum_Computing':      {bg:'#1a0a2e', fg:'#c084fc', icon:'⚛'},
  'Biotech_Medtech':        {bg:'#0a1a10', fg:'#34d399', icon:'🧬'},
  'Space_Aerospace':        {bg:'#050a18', fg:'#93c5fd', icon:'🚀'},
  'Energy_GreenTech':       {bg:'#0a1a0a', fg:'#86efac', icon:'🌱'},
  'Telecom_5G':             {bg:'#0a0e1a', fg:'#67e8f9', icon:'📡'},
  'Tech_Market':            {bg:'#1a0e00', fg:'#fcd34d', icon:'📈'},
  'Geopolitics_TechPolicy': {bg:'#1a0a0a', fg:'#fb923c', icon:'🌐'},
  'Research_Papers':        {bg:'#0f1117', fg:'#94a3b8', icon:'📄'},
  'Quant_Finance':          {bg:'#0a1a10', fg:'#6ee7b7', icon:'💹'},
};

function getCatStyle(category) {
  return CAT_COLORS[category] || {bg:'#111827', fg:'#6b7280', icon:'📰'};
}

function buildPlaceholder(category, title) {
  const style = getCatStyle(category);
  return `<div class="card-thumb-placeholder" style="background:${style.bg}">
    <div style="display:flex;flex-direction:column;align-items:center;gap:6px">
      <div style="font-size:2rem">${style.icon}</div>
      <div style="font-size:0.75rem;color:${style.fg};font-weight:700;letter-spacing:1px;
                  text-transform:uppercase;max-width:80%;text-align:center;
                  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">
        ${esc(title||'')}
      </div>
    </div>
  </div>`;
}

const COUNTRY_FLAGS = {
  US:'🇺🇸',CN:'🇨🇳',JP:'🇯🇵',KR:'🇰🇷',TW:'🇹🇼',DE:'🇩🇪',GB:'🇬🇧',FR:'🇫🇷',
  IN:'🇮🇳',SG:'🇸🇬',AU:'🇦🇺',IL:'🇮🇱',NL:'🇳🇱',SE:'🇸🇪',CA:'🇨🇦',BR:'🇧🇷',
  ZA:'🇿🇦',EU:'🇪🇺',GLOBAL:'🌐',
};

const TREE_META = {
  'AI':                     {label:'Artificial Intelligence', icon:'🤖'},
  'AI_YouTube':             {label:'AI — YouTube',           icon:'▶'},
  'Semiconductors':         {label:'Semiconductors',         icon:'🔬'},
  'Asia_Semiconductors':    {label:'Asia Semiconductors',    icon:'🏭'},
  'Cybersecurity':          {label:'Cybersecurity',          icon:'🛡'},
  'Cyber_YouTube':          {label:'Cyber — YouTube',        icon:'▶'},
  'Cloud_Infrastructure':   {label:'Cloud & Infrastructure', icon:'☁'},
  'DevOps_SRE':             {label:'DevOps & SRE',           icon:'⚙'},
  'Software_Engineering':   {label:'Software Engineering',   icon:'💻'},
  'Hardware':               {label:'Hardware',               icon:'🖥'},
  'Robotics_Automation':    {label:'Robotics & Automation',  icon:'🦾'},
  'Quantum_Computing':      {label:'Quantum Computing',      icon:'⚛'},
  'Biotech_Medtech':        {label:'Biotech & Medtech',      icon:'🧬'},
  'Space_Aerospace':        {label:'Space & Aerospace',      icon:'🚀'},
  'Energy_GreenTech':       {label:'Energy & Green Tech',    icon:'🌱'},
  'Telecom_5G':             {label:'Telecom & 5G',           icon:'📡'},
  'Tech_Market':            {label:'Tech Market & VC',       icon:'📈'},
  'Geopolitics_TechPolicy': {label:'Geopolitics & Policy',   icon:'🌐'},
  'Research_Papers':        {label:'Research Papers',        icon:'📄'},
  'Quant_Finance':          {label:'Quant Finance',          icon:'💹'},
};

// ── Theme ─────────────────────────────────────────────────────────
let currentTheme = 'dark';

function initTheme() {
  const prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;
  applyTheme(prefersLight ? 'light' : 'dark');
}
function applyTheme(theme) {
  currentTheme = theme;
  document.documentElement.setAttribute('data-theme', theme);
  const btn = document.getElementById('themeToggle');
  if (btn) btn.textContent = theme === 'dark' ? '☀' : '🌙';
}
document.getElementById('themeToggle')?.addEventListener('click', () => {
  applyTheme(currentTheme === 'dark' ? 'light' : 'dark');
});

// ── Utils ─────────────────────────────────────────────────────────
function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function timeAgo(s) {
  const d = Math.floor((Date.now()-new Date(s))/1000);
  if (d<60) return 'just now';
  if (d<3600) return `${Math.floor(d/60)}m ago`;
  if (d<86400) return `${Math.floor(d/3600)}h ago`;
  return new Date(s).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});
}
function toast(msg, isError=false) {
  const t = document.createElement('div');
  t.className = 'toast'+(isError?' error':'');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(()=>t.remove(), 3000);
}
async function api(path, opts={}) {
  const res = await fetch(API+path, {credentials:'same-origin',...opts});
  if (res.status===401) { return null; }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function apiWithRetry(path, attempts = 3) {
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetch(`/api${path}`, { credentials: 'include' });
      if (res.status === 429) {
        const ra = parseInt(res.headers.get('retry-after') || '2', 10);
        await sleep(Math.min(ra, 5) * 1000);
        continue;
      }
      if (res.status >= 500) {
        await sleep(400 * Math.pow(2, i));
        continue;
      }
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      await sleep(400 * Math.pow(2, i));
    }
  }
  return null;
}

// ── Auth ──────────────────────────────────────────────────────────
async function initAuth() {
  const me = await api('/auth/me').catch(()=>null);
  if (!me) {
    // Anonymous visitor — full read access
    state.isAdmin = false;
    const hu = document.getElementById('headerUser'); if (hu) hu.textContent = '';
    const lb = document.getElementById('logoutBtn'); if (lb) lb.style.display = 'none';
    const ll = document.getElementById('loginLink'); if (ll) ll.style.display = '';
    return true;
  }
  document.getElementById('headerUser').textContent = me.username;
  state.isAdmin = me.is_admin || false;
  if (me.is_admin) document.getElementById('adminLink').style.display='';
  if (me.is_admin) document.getElementById('syncBtn').style.display='';
  return true;
}
document.getElementById('logoutBtn').addEventListener('click', async () => {
  await fetch(API+'/auth/logout', {method:'POST',credentials:'same-origin'});
  window.location.href='/login.html';
});

// ── Category pills (unified, all screen sizes) ────────────────────
async function buildCatPills() {
  const wrap = document.getElementById('catPills');
  if (!wrap) return;
  let cats = [];
  try {
    cats = await api('/categories/tree').catch(()=>api('/categories')) || [];
  } catch(e) { cats = []; }
  const norm = cats.map(c => ({
    name: c.category || c.name,
    count: c.count || c.total || c.article_count || 0
  })).filter(c => c.name);

  const allActive = !state.category ? 'active' : '';
  let html = `<button class="cat-pill ${allActive}" data-cat="">All`;
  const total = norm.reduce((s,c)=>s+(c.count||0),0);
  html += total ? ` <span class="cat-pill-count">${total.toLocaleString()}</span>` : '';
  html += `</button>`;

  html += norm.map(c => {
    const active = state.category === c.name ? 'active' : '';
    const label = c.name.replace(/_/g,' ');
    return `<button class="cat-pill ${active}" data-cat="${esc(c.name)}">${esc(label)}${c.count?` <span class="cat-pill-count">${c.count.toLocaleString()}</span>`:''}</button>`;
  }).join('');

  wrap.innerHTML = html;
  wrap.querySelectorAll('.cat-pill').forEach(p => {
    p.addEventListener('click', () => {
      state.category = p.dataset.cat || null;
      wrap.querySelectorAll('.cat-pill').forEach(x=>x.classList.remove('active'));
      p.classList.add('active');
      hasMore = true;
      loadArticles(true);
      p.scrollIntoView({behavior:'smooth', inline:'center', block:'nearest'});
    });
  });
}

function selectCategory(cat) {
  state.category = cat || null;
  const wrap = document.getElementById('catPills');
  if (wrap) wrap.querySelectorAll('.cat-pill').forEach(x =>
    x.classList.toggle('active', (x.dataset.cat||'') === (cat||'')));
  hasMore = true;
  loadArticles(true);
}

// ── Flag images ───────────────────────────────────────────────────
function flagImg(countryCode, size = 20) {
  if (!countryCode || countryCode === 'GLOBAL') {
    return `<span class="flag-global" title="Global">🌐</span>`;
  }
  const code = countryCode.toLowerCase();
  return `<img src="https://flagcdn.com/${size}x${Math.round(size*0.75)}/${code}.png"
               srcset="https://flagcdn.com/${size*2}x${Math.round(size*1.5)}/${code}.png 2x"
               alt="${esc(countryCode)}" title="${esc(countryCode)}"
               class="flag-icon" loading="lazy"
               onerror="this.style.display='none'">`;
}

// ── Badges ────────────────────────────────────────────────────────
function buildBadges(article) {
  const parts = [];

  if (article.country_code) {
    const code = article.country_code;
    parts.push(`<span class="badge badge-country">${flagImg(code, 16)} ${esc(code !== 'GLOBAL' ? code : '')}</span>`);
  }

  if (article.entities && article.entities.length) {
    const ents = typeof article.entities==='string'
      ? JSON.parse(article.entities) : article.entities;
    ents.slice(0,3).forEach(e => {
      parts.push(`<span class="badge badge-entity" onclick="event.stopPropagation();showEntity('${esc(e)}')">${esc(e)}</span>`);
    });
  }

  if (article.sentiment && article.sentiment!=='neutral') {
    const s = SENTIMENT[article.sentiment] || SENTIMENT.neutral;
    parts.push(`<span class="badge ${s.cls}">${s.label}</span>`);
  }

  return parts.length ? `<div class="card-badges">${parts.join('')}</div>` : '';
}

// ── Articles ──────────────────────────────────────────────────────
async function loadArticles(reset = false) {
  if (isLoading) return;
  if (reset) {
    currentOffset = 0;
    hasMore = true;
    loadRetries = 0;
    const grid = document.getElementById('articleGrid');
    if (grid) grid.innerHTML = '';
  }
  if (!hasMore) return;

  isLoading = true;
  const sentinel = document.getElementById('scrollSentinel');
  if (sentinel) sentinel.textContent = 'Loading…';

  const p = new URLSearchParams({ limit: PAGE_SIZE, offset: currentOffset });
  if (state.category) p.set('category', state.category);
  if (state.search) p.set('search', state.search);

  try {
    const articles = await apiWithRetry(`/articles?${p.toString()}`, 3);

    if (!articles) {
      loadRetries++;
      if (sentinel) sentinel.textContent = '';
      isLoading = false;
      setTimeout(() => { if (!isLoading && hasMore) maybeAutoLoad(); }, 1200 * Math.min(loadRetries, 4));
      return;
    }

    loadRetries = 0;

    if (articles.length === 0) {
      hasMore = false;
      if (sentinel) sentinel.textContent = currentOffset === 0
        ? 'No articles found.' : '— End of feed —';
      isLoading = false;
      return;
    }

    appendArticles(articles);
    currentOffset += articles.length;

    if (articles.length < PAGE_SIZE) {
      hasMore = false;
      if (sentinel) sentinel.textContent = '— End of feed —';
    } else if (sentinel) {
      sentinel.textContent = '';
    }
  } catch (e) {
    loadRetries++;
    if (sentinel) sentinel.textContent = '';
    isLoading = false;
    setTimeout(() => { if (!isLoading && hasMore) maybeAutoLoad(); }, 1200 * Math.min(loadRetries, 4));
    return;
  }
  isLoading = false;
}

function maybeAutoLoad() {
  const sentinel = document.getElementById('scrollSentinel');
  if (!sentinel || isLoading || !hasMore) return;
  const rect = sentinel.getBoundingClientRect();
  if (rect.top < window.innerHeight + 400) loadArticles();
}

function appendArticles(articles) {
  const grid = document.getElementById('articleGrid');
  articles.forEach(a => {
    const card = document.createElement('div');
    card.className = 'card' + (a.is_read ? ' read' : '');
    card.dataset.articleId = a.id;
    card.dataset.url = a.url || '';

    const thumb = a.image_url
      ? `<img class="card-thumb" src="${esc(a.image_url)}" alt="" loading="lazy"
           onerror="this.outerHTML=buildPlaceholder('${esc(a.category||'')}','${esc((a.title||'').replace(/'/g,'').replace(/\\/g,''))}')">`
      : buildPlaceholder(a.category, a.title);

    const translatedBadge = (a.original_lang && a.original_lang !== 'en')
      ? `<span class="badge badge-translated" title="Translated from ${a.original_lang}">🌐 ${a.original_lang.toUpperCase()}</span>`
      : '';

    card.innerHTML = `
      ${thumb}
      <div class="card-body">
        <div class="card-meta">
          <span class="card-source">${esc(a.feed_source||'')}</span>
          ${a.category ? `<span class="card-cat">${esc(a.category.replace(/_/g,' '))}</span>` : ''}
          ${translatedBadge}
        </div>
        <div class="card-title">${esc(a.title)}</div>
        <div class="card-date">${a.published_at ? timeAgo(a.published_at) : ''}</div>
        ${buildBadges(a)}
      </div>`;
    card.addEventListener('click', () => {
      api(`/articles/${a.id}/view`, { method: 'POST' })
        .then(r => {
          const el = card.querySelector('.card-views');
          if (el && r && typeof r.views === 'number') el.textContent = `👁 ${r.views}`;
        }).catch(()=>{});
      const url = a.url || card.dataset.url || '';
      if (url) window.open(url, '_blank', 'noopener');
    });
    grid.appendChild(card);
  });

  lazyFetchImages(articles.filter(a => !a.image_url && a.url));
}

function initInfiniteScroll() {
  const sentinel = document.getElementById('scrollSentinel');
  if (!sentinel) return;
  let scheduled = false;
  const observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && hasMore && !isLoading && !scheduled) {
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        loadArticles();
      });
    }
  }, { rootMargin: '600px 0px' });
  observer.observe(sentinel);
}

async function lazyFetchImages(articles) {
  for (const a of articles.slice(0, 12)) {
    try {
      const res = await api(`/proxy/ogimage?url=${encodeURIComponent(a.url)}`);
      if (res && res.image_url) {
        const card = document.querySelector(`[data-article-id="${a.id}"]`);
        if (card) {
          const placeholder = card.querySelector('.card-thumb-placeholder');
          if (placeholder) {
            const img = document.createElement('img');
            img.className = 'card-thumb';
            img.src = res.image_url;
            img.alt = '';
            img.loading = 'lazy';
            img.onerror = function() {
              this.outerHTML = buildPlaceholder(a.category, a.title);
            };
            placeholder.replaceWith(img);
          }
        }
      }
    } catch(e) { /* silent fail */ }
  }
}

// ── Entity Detail ─────────────────────────────────────────────────
async function showEntity(entityName) {
  setView('entity');
  const panel = document.getElementById('entityView');
  panel.innerHTML = `<button class="back-btn" onclick="setView('feed')">← Back to feed</button>
    <div class="empty-state">Loading ${esc(entityName)} news…</div>`;

  try {
    const data = await api(`/entities/${encodeURIComponent(entityName)}`);
    if (!data) return;
    const s = data.stats;
    const pct = s.sentiment_score_pct;
    const sentiment_labels = Object.entries(s.sentiment_counts||{})
      .map(([k,v])=>`<span class="badge ${(SENTIMENT[k]||SENTIMENT.neutral).cls}">${v}×${(SENTIMENT[k]||SENTIMENT.neutral).label}</span>`)
      .join(' ');

    panel.innerHTML = `
      <button class="back-btn" onclick="setView('feed');loadArticles()">← Back to feed</button>
      <div class="entity-panel">
        <div class="entity-name">${esc(entityName)}</div>
        <div class="entity-stats">
          <div class="stat-chip"><div class="stat-val">${s.total_articles}</div><div class="stat-lbl">Articles</div></div>
          <div class="stat-chip"><div class="stat-val">${s.last10_positive}</div><div class="stat-lbl">Positive (last 10)</div></div>
          <div class="stat-chip"><div class="stat-val">${s.last10_negative}</div><div class="stat-lbl">Negative (last 10)</div></div>
          <div class="stat-chip"><div class="stat-val">${pct}%</div><div class="stat-lbl">Sentiment score</div></div>
        </div>
        <div style="margin-bottom:6px;font-size:.78rem;color:var(--muted)">Sentiment distribution (last 10)</div>
        <div class="sentiment-bar"><div class="sentiment-fill" style="width:${pct}%"></div></div>
        <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">${sentiment_labels}</div>
      </div>
      <div class="article-grid" id="entityGrid"></div>`;

    const egrid = document.getElementById('entityGrid');
    if (!data.articles.length) {
      egrid.innerHTML='<div class="empty-state">No articles found.</div>'; return;
    }
    data.articles.forEach(a => {
      const card = document.createElement('div');
      card.className = 'card'+(a.is_read?' read':'');
      const thumb = a.image_url
        ? `<img class="card-thumb" src="${esc(a.image_url)}" alt="" loading="lazy"
               onerror="this.outerHTML='<div class=card-thumb-placeholder>📰</div>'">`
        : `<div class="card-thumb-placeholder">📰</div>`;
      card.dataset.url = a.url || '';
      card.innerHTML = `
        ${thumb}
        <div class="card-body">
          <div class="card-meta">
            <span class="card-source">${esc(a.feed_source||'')}</span>
            ${a.category?`<span class="card-cat">${esc(a.category.replace(/_/g,' '))}</span>`:''}
          </div>
          <div class="card-title">${esc(a.title)}</div>
          <div class="card-date">${a.published_at?timeAgo(a.published_at):''}</div>
          ${buildBadges(a)}
        </div>`;
      card.addEventListener('click', () => {
        api(`/articles/${a.id}/view`, { method: 'POST' }).catch(()=>{});
        const url = a.url || card.dataset.url || '';
        if (url) window.open(url, '_blank', 'noopener');
      });
      egrid.appendChild(card);
    });
  } catch(e) {
    panel.innerHTML = `<button class="back-btn" onclick="setView('feed')">← Back</button>
      <div class="empty-state error">Error: ${e.message}</div>`;
  }
}

// ── Sync ──────────────────────────────────────────────────────────
async function syncFeed() {
  const btn=document.getElementById('syncBtn');
  btn.disabled=true; btn.textContent='⟳ Syncing…';
  try {
    const res=await fetch(API+'/sync',{method:'POST',credentials:'same-origin'});
    const data=await res.json();
    toast(`${data.synced} synced, ${data.enriched||0} enriched`);
    await buildCatPills(); await loadArticles(true);
  } catch(e) { toast('Sync failed',true); }
  btn.disabled=false; btn.textContent='⟳ Sync';
}



// ── View switching ────────────────────────────────────────────────
function setView(view) {
  state.view = view;
  document.getElementById('feedView').style.display = view === 'feed' ? '' : 'none';
  document.getElementById('entityView').style.display = view === 'entity' ? '' : 'none';
}

// ── Init ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async ()=>{
  initTheme();
  const authed = await initAuth(); if (!authed) return;
  document.getElementById('syncBtn').addEventListener('click',syncFeed);
  let searchTimer;
  document.getElementById('searchInput').addEventListener('input',e=>{
    clearTimeout(searchTimer);
    searchTimer=setTimeout(()=>{state.search=e.target.value;hasMore=true;loadArticles(true);},350);
  });
  await buildCatPills();
  await loadArticles(true);
  initInfiniteScroll();
});
