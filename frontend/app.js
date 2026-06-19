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

// ── Badges ────────────────────────────────────────────────────────
function buildBadges(article) {
  const parts = [];

  if (article.country_code) {
    const flag = COUNTRY_FLAGS[article.country_code] || '🌐';
    parts.push(`<span class="badge badge-country">${flag} ${esc(article.country_code)}</span>`);
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
  const flag = article.country_code && article.country_code !== 'GLOBAL'
    ? (COUNTRY_FLAGS[article.country_code] || '🌐') + ' ' + article.country_code : '';

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

// ── View switching ────────────────────────────────────────────────
function setView(view) {
  state.view=view;
  document.getElementById('feedView').style.display = view==='feed'?'':'none';
  document.getElementById('entityView').style.display = view==='entity'?'':'none';
  document.getElementById('knowledgeView').style.display = view==='knowledge'?'':'none';
  document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  if (view==='knowledge') loadKnowledge();
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
