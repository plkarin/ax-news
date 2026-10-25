/* AX-NEWS — administration: dashboard, approvals, accounts. */
(function () {
  'use strict';
  const { $, esc, api, ago, toast } = AX;
  let stats = null;

  async function loadStats() {
    stats = await api('/admin/stats');
    const k = [
      [AX.num(stats.last24h), 'stories in 24 h'], [AX.num(stats.month), 'stories this month'],
      [AX.num(stats.translation_pending), 'waiting for translation'], [AX.num(stats.users), 'accounts'],
      [AX.num(stats.sources), `own sources${stats.sources_failing ? ` · ${stats.sources_failing} failing` : ''}`],
      [stats.last_ingest ? ago(stats.last_ingest) : '—', 'last story in'],
    ];
    $('[data-kpis]').innerHTML = k.map(([n, l]) => `<div class="kpi"><b>${esc(n)}</b><span>${esc(l)}</span></div>`).join('');
  }
  async function loadPending() {
    const rows = await api('/admin/pending-users');
    $('[data-pending-box]').classList.toggle('hidden', !rows.length);
    $('[data-pending]').innerHTML = rows.map((u) => `<tr data-id="${u.id}"><td>${AX.avatar(u.username)} ${esc(u.username)}</td><td>${esc(u.email || '—')}</td><td>${ago(u.created_at)}</td>
      <td style="text-align:right"><button class="btn sm primary" data-approve>Approve</button> <button class="btn sm danger" data-reject>Reject</button></td></tr>`).join('');
  }
  async function loadUsers() {
    const rows = await api('/users');
    $('[data-users]').innerHTML = rows.map((u) => {
      const s = (stats && stats.per_user[u.id]) || { sources: 0, failing: 0 };
      return `<tr data-id="${u.id}" data-name="${esc(u.username)}"><td><span style="display:inline-flex;gap:10px;align-items:center">${AX.avatar(u.username)}<span><b>${esc(u.username)}</b><br><small class="muted">${esc(u.email || '')}</small></span></span></td>
        <td>${u.is_admin ? '<span class="tag topic">Admin</span>' : '<span class="tag">Reader</span>'}</td>
        <td>${AX.num(u.articles_read)}</td><td>${AX.num(s.sources)}${s.failing ? ` <span class="tag" style="color:var(--err)">${s.failing} failing</span>` : ''}</td>
        <td>${u.created_at ? new Date(u.created_at).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' }) : ''}</td>
        <td style="text-align:right">${u.id === AX.me.id ? '' : '<button class="btn sm danger" data-delete>Delete</button>'}</td></tr>`;
    }).join('');
  }
  document.addEventListener('click', async (e) => {
    const tr = e.target.closest('tr[data-id]');
    if (!tr) return;
    const id = tr.dataset.id;
    try {
      if (e.target.closest('[data-approve]')) { await api(`/admin/users/${id}/approve`, { method: 'POST' }); toast('Approved'); }
      else if (e.target.closest('[data-reject]')) { if (!confirm('Reject and delete this request?')) return; await api(`/admin/users/${id}/reject`, { method: 'POST' }); toast('Rejected'); }
      else if (e.target.closest('[data-delete]')) { if (!confirm(`Delete the account “${tr.dataset.name}” and everything it holds (sources, saved stories)?`)) return; await api(`/users/${id}`, { method: 'DELETE' }); toast('Deleted'); }
      else return;
      refresh();
    } catch (ex) { toast(ex.detail || 'Failed', true); }
  });
  $('[data-create]').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target, msg = $('[data-create-msg]');
    try {
      await api('/users', { method: 'POST', json: { username: f.username.value.trim(), email: f.email.value.trim() || null, password: f.password.value } });
      msg.textContent = 'Account created.'; msg.className = 'alert show ok'; f.reset(); refresh();
    } catch (ex) { msg.textContent = ex.detail || 'Could not create it.'; msg.className = 'alert show err'; }
  });
  async function refresh() { await loadStats(); await Promise.all([loadPending(), loadUsers()]); }
  (async () => {
    const me = await AX.ready;
    if (!me || !me.is_admin) { $('[data-denied]').classList.remove('hidden'); return; }
    $('[data-admin]').classList.remove('hidden');
    refresh().catch((e) => toast(e.detail || 'Could not load', true));
  })();
})();
