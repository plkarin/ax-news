const API = '/api';
const PAGE_SIZE = 24;

let isLoading = false;
let hasMore = true;
let currentOffset = 0;

let state = {
  category: '', search: '',
  currentArticleId: null, chatBusy: false, view: 'feed',
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
function initTheme() {
  const saved = localStorage.getItem('ax-theme') || 'dark';
  applyTheme(saved);
}
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('ax-theme', theme);
  document.querySelectorAll('.theme-dot').forEach(d =>
    d.classList.toggle('active', d.dataset.theme === theme));
}
document.querySelectorAll('.theme-dot').forEach(d =>
  d.addEventListener('click', () => applyTheme(d.dataset.theme)));

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
  if (res.status===401) { window.location.href='/login.html'; return null; }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────
async function initAuth() {
  const me = await api('/auth/me').catch(()=>null);
  if (!me) { window.location.href='/login.html'; return false; }
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

// ── Tree ──────────────────────────────────────────────────────────
async function buildTree() {
  const data = await api('/categories/tree');
  if (!data) return;
  const tree = document.getElementById('categoryTree');
  const total = data.reduce((s,r)=>s+r.total, 0);

  tree.innerHTML = `
    <div class="tree-root-label">Technology</div>
    <div class="tree-all ${!state.category?'active':''}" data-cat="">
      📰 All Articles <span class="tree-badge">${total}</span>
    </div>`;

  data.forEach(row => {
    const m = TREE_META[row.category] || {label:row.category.replace(/_/g,' '), icon:'📁'};
    const leaf = document.createElement('div');
    leaf.className = 'tree-leaf'+(state.category===row.category?' active':'');
    leaf.dataset.cat = row.category;
    leaf.innerHTML = `${m.icon} ${m.label} <span class="tree-badge">${row.total}</span>`;
    leaf.addEventListener('click', ()=>selectCategory(row.category));
    tree.appendChild(leaf);
  });

  tree.querySelector('[data-cat=""]').addEventListener('click', ()=>selectCategory(''));
}

function selectCategory(cat) {
  state.category = cat;
  document.querySelectorAll('.tree-all,.tree-leaf').forEach(el =>
    el.classList.toggle('active', el.dataset.cat===cat));
  setView('feed');
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
  if (!hasMore && !reset) return;

  if (reset) {
    currentOffset = 0;
    hasMore = true;
    document.getElementById('articleGrid').innerHTML = '';
  }

  isLoading = true;
  const sentinel = document.getElementById('scrollSentinel');
  if (sentinel) sentinel.textContent = 'Loading…';

  const p = new URLSearchParams({ limit: PAGE_SIZE, offset: currentOffset });
  if (state.category) p.set('category', state.category);
  if (state.search) p.set('search', state.search);

  try {
    const articles = await api(`/articles?${p}`);
    if (!articles || articles.length === 0) {
      hasMore = false;
      if (sentinel) sentinel.textContent = currentOffset === 0
        ? 'No articles found.' : '— End of feed —';
      isLoading = false;
      return;
    }
    if (articles.length < PAGE_SIZE) {
      hasMore = false;
      if (sentinel) sentinel.textContent = '— End of feed —';
    } else {
      if (sentinel) sentinel.textContent = '';
    }
    appendArticles(articles);
    currentOffset += articles.length;
  } catch(e) {
    if (sentinel) sentinel.textContent = 'Error loading articles.';
  }
  isLoading = false;
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
    card.addEventListener('click', () => openArticle(a.id));
    grid.appendChild(card);
  });

  lazyFetchImages(articles.filter(a => !a.image_url && a.url));
}

function initInfiniteScroll() {
  const sentinel = document.getElementById('scrollSentinel');
  if (!sentinel) return;
  const observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && hasMore && !isLoading) {
      loadArticles();
    }
  }, { rootMargin: '300px' });
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
      card.addEventListener('click', ()=>openArticle(a.id));
      egrid.appendChild(card);
    });
  } catch(e) {
    panel.innerHTML = `<button class="back-btn" onclick="setView('feed')">← Back</button>
      <div class="empty-state error">Error: ${e.message}</div>`;
  }
}

// ── Modal ─────────────────────────────────────────────────────────
async function openArticle(articleId) {
  api(`/articles/${articleId}/read`, { method: 'POST' }).catch(() => {});
  const card = document.querySelector(`[data-article-id="${articleId}"]`);
  if (card) card.classList.add('read');

  const article = await api(`/articles/${articleId}`);
  if (!article) return;

  function formatContent(raw) {
    if (!raw) return '';
    const tmp = document.createElement('div');
    tmp.innerHTML = raw;
    const text = (tmp.textContent || '').replace(/\s+/g, ' ').trim();
    if (!text || text.length < 30) return '';
    const sentences = text.match(/[^.!?]+[.!?]+/g) || [text];
    const paragraphs = [];
    let current = '';
    for (const s of sentences) {
      current += s + ' ';
      if (current.length > 280) {
        paragraphs.push(current.trim());
        current = '';
      }
    }
    if (current.trim()) paragraphs.push(current.trim());
    return paragraphs.map(p => `<p>${esc(p)}</p>`).join('');
  }

  const contentHtml = formatContent(article.content_raw);
  const entities = typeof article.entities === 'string'
    ? JSON.parse(article.entities || '[]') : (article.entities || []);
  const flag = article.country_code
    ? `${flagImg(article.country_code, 16)} ${esc(article.country_code !== 'GLOBAL' ? article.country_code : '')}` : '';

  document.getElementById('articleModal')?.remove();

  const modal = document.createElement('div');
  modal.id = 'articleModal';
  modal.className = 'modal-overlay';
  modal.innerHTML = `
    <div class="modal-container">
      <div class="modal-header">
        <button class="modal-close" onclick="document.getElementById('articleModal').remove()">
          ✕ Close
        </button>
        <div class="modal-meta">
          <span class="modal-source">${esc(article.feed_source || '')}</span>
          ${article.category ? `<span class="modal-cat">${esc(article.category.replace(/_/g,' '))}</span>` : ''}
          <span class="modal-time">${article.published_at ? timeAgo(article.published_at) : ''}</span>
          ${flag ? `<span class="badge badge-country">${flag}</span>` : ''}
        </div>
        <div class="modal-title">${esc(article.title)}</div>
        <div class="modal-badges">
          ${entities.slice(0,5).map(e => `<span class="badge badge-entity">${esc(e)}</span>`).join('')}
          ${article.sentiment && article.sentiment !== 'neutral' && SENTIMENT[article.sentiment]
            ? `<span class="badge ${SENTIMENT[article.sentiment].cls}">${SENTIMENT[article.sentiment].label}</span>`
            : ''}
        </div>
      </div>
      ${article.image_url
        ? `<img class="modal-hero" src="${esc(article.image_url)}" alt="" onerror="this.style.display='none'">`
        : ''}
      <div class="modal-body">
        ${contentHtml
          ? `<div class="modal-content-block">${contentHtml}</div>`
          : `<div class="modal-content-block" style="font-style:italic;color:rgba(232,244,255,.4)">
               No preview available for this article.
             </div>`}
        ${article.url
          ? `<a href="${esc(article.url)}" target="_blank" rel="noopener" class="modal-read-more">
               Read full article ↗
             </a>`
          : ''}
        ${state.isAdmin ? `
        <div class="modal-ai-section">
          <div class="modal-ai-title">🤖 AI Analysis</div>
          <div class="modal-ai-messages" id="aiMessages"></div>
          <div class="modal-ai-input">
            <input type="text" id="aiInput" placeholder="Ask about this article..."
              onkeydown="if(event.key==='Enter') sendAiMsg(${articleId})">
            <button onclick="sendAiMsg(${articleId})">Ask</button>
          </div>
        </div>
        ` : ''}
      </div>
    </div>`;

  modal.addEventListener('click', e => {
    if (e.target === modal) modal.remove();
  });

  document.body.appendChild(modal);

  setTimeout(() => buildTree(), 500);
}

function closeModal() {
  document.getElementById('articleModal')?.remove();
  document.getElementById('modal') && (document.getElementById('modal').style.display='none');
  state.currentArticleId=null;
}

function appendMsg(role, content) {
  const msgs = document.getElementById('chatMsgs');
  const div = document.createElement('div');
  div.className=`msg ${role}`; div.textContent=content;
  msgs.appendChild(div); msgs.scrollTop=msgs.scrollHeight;
}

async function sendChat() {
  if (!state.currentArticleId||state.chatBusy) return;
  const input = document.getElementById('chatInput');
  const msg = input.value.trim(); if (!msg) return;
  input.value=''; state.chatBusy=true;
  document.getElementById('chatSend').disabled=true;
  appendMsg('user',msg);
  const thinking = document.createElement('div');
  thinking.className='msg system'; thinking.textContent='⟳ Analysing…';
  document.getElementById('chatMsgs').appendChild(thinking);
  try {
    const res = await api('/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({article_id:state.currentArticleId, message:msg})});
    thinking.remove();
    if (res) { appendMsg('assistant',res.response);
      if (res.knowledge_updated) toast(`Knowledge updated: ${res.knowledge_updated.domain}`); }
  } catch(e) { thinking.remove(); appendMsg('system','Error communicating with AI assistant.'); }
  state.chatBusy=false; document.getElementById('chatSend').disabled=false;
}

async function sendAiMsg(articleId, autoMsg) {
  const input = document.getElementById('aiInput');
  const messages = document.getElementById('aiMessages');
  if (!input || !messages) return;

  const text = autoMsg || input.value.trim();
  if (!text) return;
  if (!autoMsg) input.value = '';

  const userMsg = document.createElement('div');
  userMsg.className = 'ai-msg user';
  userMsg.textContent = text;
  messages.appendChild(userMsg);

  const loadMsg = document.createElement('div');
  loadMsg.className = 'ai-msg assistant ai-response';
  loadMsg.textContent = 'Analysing...';
  messages.appendChild(loadMsg);
  messages.scrollTop = messages.scrollHeight;

  try {
    const res = await fetch(API + `/articles/${articleId}/chat`, {
      credentials: 'same-origin',
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    });
    if (!res.ok) {
      let detail = '';
      try { const j = await res.json(); detail = j.detail || ''; } catch(_) {}
      throw new Error(detail || `${res.status} ${res.statusText}`);
    }
    const data = await res.json();
    let md = data?.response || 'No response.';
    md = md
      .replace(/(#{1,3}\s*)(Key Points)/gi,   '$1🔑 Key Points')
      .replace(/(#{1,3}\s*)(Bottom Line)/gi,  '$1💡 Bottom Line')
      .replace(/(#{1,3}\s*)Why(\s*[:\n])/gi,  '$1❓ Why$2')
      .replace(/(#{1,3}\s*)(Context)/gi,       '$1📌 Context')
      .replace(/(#{1,3}\s*)(Trade-off)/gi,     '$1⚖️ Trade-off');
    loadMsg.innerHTML = typeof marked !== 'undefined' ? marked.parse(md) : md.replace(/\n/g, '<br>');
  } catch(e) {
    loadMsg.textContent = 'Error: ' + (e.message || 'Could not reach AI service.');
  }
  messages.scrollTop = messages.scrollHeight;
}

// ── Knowledge ─────────────────────────────────────────────────────
async function loadKnowledge() {
  const list = document.getElementById('knowledgeList');
  list.innerHTML='<div class="empty-state">Loading…</div>';
  try {
    const data = await api('/knowledge/full');
    if (!data) return;
    const domains = Object.keys(data);
    document.getElementById('knowledgeCount').textContent=`${domains.length} domains`;
    if (!domains.length) {
      list.innerHTML='<div class="empty-state">No knowledge entries yet.<br>Chat with the AI assistant on articles to build your knowledge base.</div>'; return;
    }
    list.innerHTML='';
    domains.forEach(domain=>{
      const sec=document.createElement('div'); sec.className='knowledge-section';
      sec.innerHTML=`<div class="knowledge-domain-label">${esc(domain)}</div>`;
      data[domain].forEach(entry=>{
        const item=document.createElement('div'); item.className='knowledge-item';
        const gapId = esc(entry.gap_identified||'');
        const gapRes = esc(entry.gap_resolved||'');
        const artTitle = entry.article_title ? `<span>${esc(entry.article_title)}</span>` : '';
        const artTime = entry.created_at ? `<span>${timeAgo(entry.created_at)}</span>` : '';
        item.innerHTML=`
          <div class="knowledge-gap-lbl">Gap identified</div>
          <div class="knowledge-gap">${gapId}</div>
          ${gapRes ? `<div class="knowledge-gap-lbl knowledge-resolved-lbl">Gap resolved</div>
          <div class="knowledge-resolved">${gapRes}</div>` : ''}
          <div class="knowledge-meta">${artTitle}${artTime}
            <button class="delete-btn" data-id="${entry.id}" onclick="deleteKnowledge(${entry.id},this)">Delete</button>
          </div>`;
        sec.appendChild(item);
      });
      list.appendChild(sec);
    });
  } catch(e) { list.innerHTML=`<div class="empty-state error">${e.message}</div>`; }
}

async function deleteKnowledge(id, btn) {
  if (!confirm('Delete this knowledge entry?')) return;
  try { await api(`/knowledge/${id}`,{method:'DELETE'}); btn.closest('.knowledge-item').remove(); toast('Entry deleted'); }
  catch(e) { toast('Failed to delete',true); }
}

// ── Architecture ──────────────────────────────────────────────────
async function loadArchitecture() {
  const content = document.getElementById('architectureContent');
  const statsLine = document.getElementById('archStatsLine');
  if (!content) return;
  content.innerHTML = '<div class="muted" style="padding:20px">Loading...</div>';
  try {
    const data = await api('/architecture');
    const { docs, sources, stats, tech_stack } = data;

    if (statsLine) {
      statsLine.textContent = `📊 ${stats.total_articles.toLocaleString()} articles · 🌐 ${stats.total_sources} sources · ✅ ${stats.translated.toLocaleString()} translated`;
    }

    // Section icons
    const sectionIcons = {
      overview: '🏗️', network: '🌐', haproxy: '🔒',
      ratelimit: '🚦', translation: '🌍', security: '🛡️'
    };

    const docsHtml = docs.map(d => `
      <div class="arch-card">
        <div class="arch-card-label">${sectionIcons[d.section] || '📄'} ${esc(d.section)}</div>
        <div class="arch-card-title">${esc(d.title)}</div>
        <div class="arch-card-body">${esc(d.content)}</div>
      </div>
    `).join('');

    // Tech stack badges (GitHub shields.io style, rendered locally)
    const stackByCategory = {};
    (tech_stack || []).forEach(t => {
      if (!stackByCategory[t.category]) stackByCategory[t.category] = [];
      stackByCategory[t.category].push(t);
    });
    const badgesHtml = Object.entries(stackByCategory).map(([cat, items]) => `
      <div style="margin-bottom:14px">
        <div class="arch-badge-cat">${esc(cat)}</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px">
          ${items.map(t => `
            <img src="https://img.shields.io/badge/${encodeURIComponent(t.name)}-${t.badge_color}?style=for-the-badge${t.badge_logo ? '&logo='+t.badge_logo+'&logoColor=white' : ''}"
                 alt="${esc(t.name)}" style="height:24px;border-radius:4px">
          `).join('')}
        </div>
      </div>
    `).join('');

    // Source stats table
    const sourcesRows = sources.map(s => {
      const pct = s.article_count > 0 ? Math.round((s.translated_count / s.article_count) * 100) : 0;
      const statusIcon = pct === 100 ? '✅' : pct >= 50 ? '🟡' : '🔴';
      return `
        <tr>
          <td style="padding:8px 12px;font-size:.82rem">${esc(s.feed_source)}</td>
          <td style="padding:8px 12px;font-size:.82rem;text-align:right">${s.article_count.toLocaleString()}</td>
          <td style="padding:8px 12px;font-size:.82rem;text-align:right">${statusIcon} ${pct}%</td>
          <td style="padding:8px 12px;font-size:.78rem;color:var(--muted)">${s.last_ingested ? timeAgo(s.last_ingested) : '—'}</td>
        </tr>`;
    }).join('');

    content.innerHTML = `
      <div class="arch-vibe-banner">
        🤖 <strong>Built entirely with Claude Code</strong> — running directly on ax-lab05, this entire site (backend, frontend, infra config, and every bug fix) was built through conversational "vibe coding". No manual code was hand-typed.
      </div>

      <div class="arch-grid">${docsHtml}</div>

      <div class="arch-section-title">📐 Infrastructure Diagram</div>
      <div class="arch-diagram-wrap">${buildArchDiagram()}</div>

      <div class="arch-section-title">🧰 Tech Stack</div>
      <div class="arch-card" style="padding:20px 24px">${badgesHtml}</div>

      <div class="arch-section-title">📡 Live Source Statistics</div>
      <div class="arch-card" style="padding:20px 24px">
        <table style="width:100%;border-collapse:collapse">
          <thead>
            <tr style="font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--border)">
              <th style="padding:8px 12px;text-align:left">Source</th>
              <th style="padding:8px 12px;text-align:right">Articles</th>
              <th style="padding:8px 12px;text-align:right">Translated</th>
              <th style="padding:8px 12px;text-align:left">Last Update</th>
            </tr>
          </thead>
          <tbody>${sourcesRows}</tbody>
        </table>
      </div>
    `;
  } catch(e) {
    content.innerHTML = '<div class="muted" style="padding:20px;color:var(--error,#ff4d6d)">⚠️ Failed to load architecture data.</div>';
  }
}

function buildArchDiagram() {
  return `
<svg viewBox="0 0 1000 480" style="width:100%;height:auto;max-width:1000px" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="#4d9fff"/>
    </marker>
  </defs>
  <style>
    .node-box { fill:#111118; stroke:#1e1e2e; stroke-width:1.5; rx:10; }
    .node-label { fill:#e8f4ff; font-family:system-ui,sans-serif; font-size:13px; font-weight:700; text-anchor:middle; }
    .node-sub { fill:#4a7aa8; font-family:system-ui,sans-serif; font-size:10px; text-anchor:middle; }
    .flow-line { stroke:#4d9fff; stroke-width:2; fill:none; marker-end:url(#arrow); }
    .zone-label { fill:#4a7aa8; font-family:system-ui,sans-serif; font-size:10px; font-weight:700; letter-spacing:1px; text-transform:uppercase; }
  </style>

  <!-- Internet -->
  <rect x="40" y="30" width="140" height="60" class="node-box"/>
  <text x="110" y="55" class="node-label">🌐 Internet</text>
  <text x="110" y="72" class="node-sub">Users worldwide</text>

  <!-- Cloudflare -->
  <rect x="240" y="30" width="160" height="60" class="node-box" stroke="#f38020"/>
  <text x="320" y="55" class="node-label">☁️ Cloudflare</text>
  <text x="320" y="72" class="node-sub">DNS + Proxy (orange)</text>

  <!-- HAProxy -->
  <rect x="460" y="30" width="180" height="70" class="node-box" stroke="#106DA9"/>
  <text x="550" y="52" class="node-label">🔒 HAProxy</text>
  <text x="550" y="68" class="node-sub">TLS A+ · 88.190.8.43</text>
  <text x="550" y="82" class="node-sub">Rate limit 500r/10s</text>

  <!-- Nginx -->
  <rect x="700" y="30" width="160" height="70" class="node-box" stroke="#009639"/>
  <text x="780" y="52" class="node-label">🔁 Nginx</text>
  <text x="780" y="68" class="node-sub">ax-lab05:80</text>
  <text x="780" y="82" class="node-sub">CSP · Rate limit</text>

  <!-- FastAPI -->
  <rect x="700" y="160" width="160" height="70" class="node-box" stroke="#009688"/>
  <text x="780" y="182" class="node-label">⚡ FastAPI</text>
  <text x="780" y="198" class="node-sub">uvicorn :8000</text>
  <text x="780" y="212" class="node-sub">2 workers</text>

  <!-- PostgreSQL -->
  <rect x="700" y="290" width="160" height="60" class="node-box" stroke="#4169E1"/>
  <text x="780" y="315" class="node-label">🗄️ PostgreSQL</text>
  <text x="780" y="332" class="node-sub">61K+ articles</text>

  <!-- Argos worker -->
  <rect x="460" y="290" width="180" height="70" class="node-box" stroke="#00897B"/>
  <text x="550" y="312" class="node-label">🌍 Argos Translate</text>
  <text x="550" y="328" class="node-sub">Standalone process</text>
  <text x="550" y="342" class="node-sub">MemoryMax=1G</text>

  <!-- FreshRSS -->
  <rect x="240" y="290" width="160" height="70" class="node-box" stroke="#ff9800"/>
  <text x="320" y="312" class="node-label">📰 FreshRSS</text>
  <text x="320" y="328" class="node-sub">ax-lab04</text>
  <text x="320" y="342" class="node-sub">200+ RSS sources</text>

  <!-- Claude Code -->
  <rect x="40" y="290" width="160" height="70" class="node-box" stroke="#D97757"/>
  <text x="120" y="312" class="node-label">🤖 Claude Code</text>
  <text x="120" y="328" class="node-sub">cbrain subprocess</text>
  <text x="120" y="342" class="node-sub">Admin chat + vibe coding</text>

  <!-- Flow lines -->
  <path d="M180,60 L240,60" class="flow-line"/>
  <path d="M400,60 L460,60" class="flow-line"/>
  <path d="M640,65 L700,65" class="flow-line"/>
  <path d="M780,100 L780,160" class="flow-line"/>
  <path d="M780,230 L780,290" class="flow-line"/>
  <path d="M700,195 L640,310" class="flow-line"/>
  <path d="M460,325 L400,325" class="flow-line"/>
  <path d="M240,325 L200,325" class="flow-line"/>
  <path d="M780,260 Q900,260 900,195 Q900,160 860,180" class="flow-line" stroke-dasharray="4,3"/>

  <text x="500" y="410" class="zone-label">🏠 Homelab — ax-lab04 / ax-lab05 / ax-haproxy (192.168.1.0/24)</text>
  <rect x="40" y="270" width="820" height="100" fill="none" stroke="#1e1e2e" stroke-width="1" stroke-dasharray="6,4" rx="8"/>
</svg>`;
}

// ── Sync ──────────────────────────────────────────────────────────
async function syncFeed() {
  const btn=document.getElementById('syncBtn');
  btn.disabled=true; btn.textContent='⟳ Syncing…';
  try {
    const res=await fetch(API+'/sync',{method:'POST',credentials:'same-origin'});
    const data=await res.json();
    toast(`${data.synced} synced, ${data.enriched||0} enriched`);
    await buildTree(); await loadArticles(true);
  } catch(e) { toast('Sync failed',true); }
  btn.disabled=false; btn.textContent='⟳ Sync';
}

// ── Metrics ───────────────────────────────────────────────────────
let metricsPollTimer = null;

function startMetricsPolling() {
  stopMetricsPolling();
  metricsPollTimer = setInterval(loadMetrics, 45000);
}
function stopMetricsPolling() {
  if (metricsPollTimer) { clearInterval(metricsPollTimer); metricsPollTimer = null; }
}

function fmtBytes(gb) {
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(gb*1024).toFixed(0)} MB`;
}
function fmtUptime(hours) {
  if (hours < 24) return `${hours.toFixed(1)}h`;
  const days = Math.floor(hours / 24);
  return `${days}d ${(hours % 24).toFixed(0)}h`;
}
function gaugeColor(pct) {
  if (pct < 50) return '#00e676';
  if (pct < 80) return '#ffb800';
  return '#ff4d6d';
}

function buildGauge(label, pct, sublabel) {
  const color = gaugeColor(pct);
  const circumference = 2 * Math.PI * 42;
  const offset = circumference - (pct / 100) * circumference;
  return `
    <div class="metric-gauge">
      <svg viewBox="0 0 100 100" width="110" height="110">
        <circle cx="50" cy="50" r="42" fill="none" stroke="#1e1e2e" stroke-width="8"/>
        <circle cx="50" cy="50" r="42" fill="none" stroke="${color}" stroke-width="8"
          stroke-linecap="round" stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"
          transform="rotate(-90 50 50)" style="transition:stroke-dashoffset .5s ease"/>
        <text x="50" y="48" text-anchor="middle" font-size="20" font-weight="800" fill="#e8f4ff">${pct.toFixed(0)}%</text>
        <text x="50" y="64" text-anchor="middle" font-size="8" fill="#4a7aa8">${esc(sublabel||'')}</text>
      </svg>
      <div class="metric-gauge-label">${esc(label)}</div>
    </div>`;
}

function buildSparkline(data, color) {
  if (!data || data.length < 2) return '<div class="muted" style="font-size:.75rem">Collecting data...</div>';
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  const w = 280, h = 50;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return `
    <svg viewBox="0 0 ${w} ${h}" width="100%" height="50" preserveAspectRatio="none">
      <polyline points="${points}" fill="none" stroke="${color}" stroke-width="2"/>
    </svg>`;
}

async function loadMetrics() {
  const content = document.getElementById('metricsContent');
  const refreshLine = document.getElementById('metricsRefreshLine');
  if (!content) return;
  try {
    const m = await api('/metrics');

    if (refreshLine) refreshLine.textContent = `🔄 Updated ${new Date().toLocaleTimeString()} · auto-refresh 45s`;

    content.innerHTML = `
      <div class="metrics-gauges">
        ${buildGauge('CPU', m.cpu.percent, `${m.cpu.count} cores`)}
        ${buildGauge('Memory', m.memory.percent, fmtBytes(m.memory.used_gb))}
        ${buildGauge('Disk', m.disk.percent, fmtBytes(m.disk.used_gb))}
      </div>

      <div class="metrics-grid">
        <div class="arch-card">
          <div class="arch-card-label">🖥️ CPU</div>
          <div class="metric-row"><span>Current</span><strong>${m.cpu.percent.toFixed(1)}%</strong></div>
          <div class="metric-row"><span>Min / Max (history)</span><strong>${m.cpu.min_history}% / ${m.cpu.max_history}%</strong></div>
          <div class="metric-row"><span>Load avg (1/5/15min)</span><strong>${m.cpu.load_avg_1} / ${m.cpu.load_avg_5} / ${m.cpu.load_avg_15}</strong></div>
          <div class="metric-row"><span>Cores</span><strong>${m.cpu.count}</strong></div>
          ${buildSparkline(m.history.cpu, '#4d9fff')}
        </div>

        <div class="arch-card">
          <div class="arch-card-label">🧠 Memory</div>
          <div class="metric-row"><span>Used / Total</span><strong>${fmtBytes(m.memory.used_gb)} / ${fmtBytes(m.memory.total_gb)}</strong></div>
          <div class="metric-row"><span>Available</span><strong>${fmtBytes(m.memory.available_gb)}</strong></div>
          <div class="metric-row"><span>Min / Max (history)</span><strong>${m.memory.min_history}% / ${m.memory.max_history}%</strong></div>
          <div class="metric-row"><span>Swap used</span><strong>${fmtBytes(m.memory.swap_used_gb)} / ${fmtBytes(m.memory.swap_total_gb)}</strong></div>
          ${buildSparkline(m.history.mem, '#a855f7')}
        </div>

        <div class="arch-card">
          <div class="arch-card-label">💾 Disk</div>
          <div class="metric-row"><span>Used / Total</span><strong>${fmtBytes(m.disk.used_gb)} / ${fmtBytes(m.disk.total_gb)}</strong></div>
          <div class="metric-row"><span>Free</span><strong>${fmtBytes(m.disk.free_gb)}</strong></div>
          <div class="metric-row"><span>Read / Write (cumulative)</span><strong>${m.disk.read_mb.toFixed(0)} MB / ${m.disk.write_mb.toFixed(0)} MB</strong></div>
        </div>

        <div class="arch-card">
          <div class="arch-card-label">📡 Network</div>
          <div class="metric-row"><span>Send rate</span><strong>${m.network.sent_rate_kb.toFixed(1)} KB/s</strong></div>
          <div class="metric-row"><span>Receive rate</span><strong>${m.network.recv_rate_kb.toFixed(1)} KB/s</strong></div>
          <div class="metric-row"><span>Total sent</span><strong>${m.network.total_sent_gb.toFixed(2)} GB</strong></div>
          <div class="metric-row"><span>Total received</span><strong>${m.network.total_recv_gb.toFixed(2)} GB</strong></div>
        </div>

        <div class="arch-card">
          <div class="arch-card-label">⚙️ FastAPI Process</div>
          <div class="metric-row"><span>RSS Memory</span><strong>${m.process.rss_mb.toFixed(0)} MB</strong></div>
          <div class="metric-row"><span>Virtual Memory</span><strong>${m.process.vms_mb.toFixed(0)} MB</strong></div>
          <div class="metric-row"><span>App uptime</span><strong>${fmtUptime(m.process.uptime_seconds/3600)}</strong></div>
          <div class="metric-row"><span>DB pool (used/free)</span><strong>${m.db.pool_size - m.db.pool_free}/${m.db.pool_size}</strong></div>
        </div>

        <div class="arch-card">
          <div class="arch-card-label">🐧 System</div>
          <div class="metric-row"><span>Hostname</span><strong>${esc(m.system.hostname)}</strong></div>
          <div class="metric-row"><span>System uptime</span><strong>${fmtUptime(m.system.uptime_hours)}</strong></div>
        </div>

        <div class="arch-card" style="grid-column:1/-1">
          <div class="arch-card-label">📰 Application Stats (live from DB)</div>
          <div class="metrics-grid" style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-top:8px">
            <div class="metric-stat"><div class="metric-stat-n">${m.db.total_articles.toLocaleString()}</div><div class="metric-stat-l">Total articles</div></div>
            <div class="metric-stat"><div class="metric-stat-n">${m.db.last_hour}</div><div class="metric-stat-l">Last hour</div></div>
            <div class="metric-stat"><div class="metric-stat-n">${m.db.last_24h.toLocaleString()}</div><div class="metric-stat-l">Last 24h</div></div>
            <div class="metric-stat"><div class="metric-stat-n">${m.db.pending_translation}</div><div class="metric-stat-l">Pending translation</div></div>
            <div class="metric-stat"><div class="metric-stat-n">${m.db.total_users}</div><div class="metric-stat-l">Total users</div></div>
            <div class="metric-stat"><div class="metric-stat-n">${m.db.pending_approvals}</div><div class="metric-stat-l">Pending approvals</div></div>
            <div class="metric-stat"><div class="metric-stat-n">${m.db.active_sessions}</div><div class="metric-stat-l">Active sessions</div></div>
          </div>
        </div>
      </div>
    `;
  } catch(e) {
    content.innerHTML = '<div class="muted" style="padding:20px;color:var(--error,#ff4d6d)">⚠️ Failed to load metrics.</div>';
  }
}

// ── View switching ────────────────────────────────────────────────
function setView(view) {
  state.view=view;
  document.getElementById('feedView').style.display = view==='feed'?'':'none';
  document.getElementById('entityView').style.display = view==='entity'?'':'none';
  document.getElementById('knowledgeView').style.display = view==='knowledge'?'':'none';
  document.getElementById('architectureView').style.display = view==='architecture'?'':'none';
  document.getElementById('metricsView').style.display = view==='metrics'?'':'none';
  document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  if (view==='knowledge') loadKnowledge();
  if (view==='architecture') loadArchitecture();
  if (view==='metrics') { loadMetrics(); startMetricsPolling(); } else { stopMetricsPolling(); }
}

// ── Init ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async ()=>{
  initTheme();
  const authed = await initAuth(); if (!authed) return;
  document.querySelectorAll('.nav-btn').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
  document.getElementById('syncBtn').addEventListener('click',syncFeed);
  document.getElementById('modalClose').addEventListener('click',closeModal);
  document.getElementById('modalBackdrop').addEventListener('click',closeModal);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();});
  document.getElementById('chatSend').addEventListener('click',sendChat);
  document.getElementById('chatInput').addEventListener('keydown',e=>{
    if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendChat();}
  });
  let searchTimer;
  document.getElementById('searchInput').addEventListener('input',e=>{
    clearTimeout(searchTimer);
    searchTimer=setTimeout(()=>{state.search=e.target.value;hasMore=true;loadArticles(true);},350);
  });
  await buildTree();
  await loadArticles(true);
  initInfiniteScroll();
});
