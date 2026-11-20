'use strict';
// Relative URLs only: the gateway serves this page under /manage/.
const el = id => document.getElementById(id);
function text(tag, value, cls) { const e = document.createElement(tag); e.textContent = value; if (cls) e.className = cls; return e; }

async function api(path, data) {
  const options = data === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Lab-Request': '1'},
    body: JSON.stringify(data)
  };
  const r = await fetch(path, options);
  let value = {};
  try { value = await r.json(); } catch (e) { /* non-JSON error page */ }
  if (!r.ok) throw new Error(value.error || ('Request failed (' + r.status + ')'));
  return value;
}

function price(p) {
  if (!p) return '';
  return 'in ' + p.input + ' / out ' + p.output;
}

function scenarioSection(s, isSelected) {
  const section = document.createElement('section');
  const label = document.createElement('label');
  const input = document.createElement('input');
  input.type = 'checkbox'; input.value = s.id; input.checked = isSelected;
  label.append(input, document.createTextNode(' ' + s.title));
  section.append(label, text('p', s.description));
  section.append(text('p', 'Models: ' + (s.models.map(m => m.public_name + ' (' + price(m.prices) + ')').join(', ') || 'none'), 'muted'));
  section.append(text('p', 'Actions: ' + (s.actions.map(a => a.label).join(', ') || 'none'), 'muted'));
  section.append(text('p', 'Tools: ' + (s.tools.join(', ') || 'none'), 'muted'));
  const details = document.createElement('details');
  details.append(text('summary', 'Prompts and tests'));
  ['clean', 'attack'].forEach(group => {
    (s.prompts[group] || []).forEach(p => details.append(text('p', group + ' · ' + p.id + ': ' + p.text)));
  });
  s.tests.forEach(t => details.append(text('p', 'test ' + t.id + ' · ' + t.action + ' → expect ' + JSON.stringify(t.expect), 'muted')));
  section.append(details);
  return section;
}

// Change 2026-11-20: live auto-approval status (runs in the lab gateway under an instructor's session).
function clock(t) { return t ? new Date(t * 1000).toLocaleTimeString() : '—'; }
function showApproval(a) {
  const box = el('approval');
  let state = a.state || 'unavailable';
  // A running worker that missed two polls plus a margin is shown as stale, not running.
  if (state === 'running' && a.last_run_at && a.now && a.now - a.last_run_at > 2 * (a.interval || 60) + 15) state = 'stale';
  box.className = 'indicator ' + state;
  const last = a.last_result || {};
  box.textContent = 'Auto-approval: ' + state + (state === 'running' || state === 'stale'
    ? ' · until ' + clock(a.ends_at) + ' · last ' + clock(a.last_run_at) + ' · ' + ((a.totals || {}).approved || 0) + ' approved'
    : '');
  const lines = [];
  if (a.owner) lines.push('Started by ' + a.owner + ' at ' + clock(a.started_at) + '.');
  if (a.last_run_at) lines.push('Last run ' + clock(a.last_run_at) + ': ' + (last.approved || 0) + ' approved, ' + (last.failed || 0) + ' failed.');
  (last.errors || []).forEach(e => lines.push(e));
  if (a.stop_reason && state !== 'running') lines.push('Stopped: ' + a.stop_reason + '.');
  box.title = lines.join('\n');
  el('aa-detail').textContent = lines.join(' ');
  const pref = a.preference;
  if (pref && !el('auto-approval').dataset.touched) {
    el('aa-enabled').checked = pref.enabled;
    el('aa-hours').value = pref.hours;
  }
}

// Change 2026-11-20: approval history (newest first, up to 200 rows).
const CHANGE_LABEL = {create: 'add', update: 'change', deletion: 'delete', delete: 'delete'};
async function loadApprovals() {
  const box = el('aa-history');
  const student = el('aa-student').value.trim();
  try {
    const data = await api('api/approvals' + (student ? '?student=' + encodeURIComponent(student) : ''));
    if (!data.items.length) { box.replaceChildren(text('p', 'No approvals recorded yet.', 'muted')); return; }
    const table = document.createElement('table');
    const head = document.createElement('tr');
    ['Time', 'Student', 'Type', 'Object', 'Change', 'Result', 'Approved with'].forEach(h => head.append(text('th', h)));
    table.append(head);
    data.items.forEach(r => {
      const tr = document.createElement('tr');
      tr.append(text('td', new Date(r.at * 1000).toLocaleString()), text('td', r.student), text('td', r.type),
                text('td', r.name), text('td', CHANGE_LABEL[r.change] || r.change),
                text('td', r.outcome + (r.detail ? ' (' + r.detail + ')' : ''), r.outcome === 'approved' ? '' : 'warn'),
                text('td', r.approved_by));
      table.append(tr);
    });
    box.replaceChildren(table);
  } catch (e) { box.replaceChildren(text('p', 'Approval history unavailable: ' + e.message, 'warn')); }
}

// Default-on: when the saved preference is on and nothing is running, start it once per page load
// under this instructor's session (owner decision; no stored credential).
let autoStartTried = false;
async function ensureAutoApproval(a) {
  const pref = a.preference || {};
  if (autoStartTried || !pref.enabled || ['running', 'error', 'unavailable'].includes(a.state)) return;
  autoStartTried = true;
  try { showApproval(await api('api/auto-approve', {enabled: true, hours: pref.hours})); }
  catch (e) { el('aa-detail').textContent = 'Could not start auto-approval: ' + e.message; }
}

async function refresh() {
  const state = await api('api/state');
  el('user').textContent = state.user;
  el('gui-only').hidden = !state.gui_only;
  showApproval(state.auto_approval || {});
  ensureAutoApproval(state.auto_approval || {});
  const p = state.pricing || {};
  el('pricing').textContent = p.currency ? ('Prices: ' + p.currency + ' ' + (p.unit || '') + '. ' + (p.pricing_note || '')) : '';
  const box = el('scenarios');
  box.replaceChildren();
  if (state.catalog_error) box.append(text('p', state.catalog_error, 'warn'));
  state.catalog.forEach(s => box.append(scenarioSection(s, state.selected.includes(s.id))));
  el('actions').textContent = state.faig_actions ? '' : 'FAIG actions are not configured yet: deploy the gateway, then redeploy lab management.';
  el('models').disabled = !state.faig_actions;
  const list = el('jobs');
  list.replaceChildren();
  if (!state.jobs.length) list.append(text('p', 'No operations recorded.', 'muted'));
  state.jobs.forEach(j => {
    const section = document.createElement('section');
    section.append(text('p', j.kind + ' · ' + new Date(j.created * 1000).toLocaleString() + ' · ' + j.actor + ' · ', 'muted'));
    section.firstChild.append(text('span', j.status, 'status ' + j.status));
    section.append(text('pre', j.detail));
    list.append(section);
  });
  return state;
}

let polling = null;
function pollWhileRunning(state) {
  const busy = state && state.jobs.some(j => j.status === 'queued' || j.status === 'running');
  if (busy && !polling) polling = setInterval(() => refresh().then(s => { if (!s.jobs.some(j => j.status === 'queued' || j.status === 'running')) { clearInterval(polling); polling = null; loadRoster(); } }).catch(() => {}), 2000);
}

async function run(fn) {
  try { el('error').textContent = ''; await fn(); pollWhileRunning(await refresh()); }
  catch (e) { el('error').textContent = e.message; }
}

el('selection').addEventListener('submit', e => {
  e.preventDefault();
  run(() => api('api/selection', {ids: [...el('scenarios').querySelectorAll('input:checked')].map(x => x.value)}));
});
el('models').addEventListener('click', () => run(() => api('api/jobs/models', {})));
function pwMode() { return document.querySelector('input[name=pwmode]:checked').value; }
document.querySelectorAll('input[name=pwmode]').forEach(r => r.addEventListener('change', () => { el('pwlabel').hidden = pwMode() === 'generated'; }));
el('students').addEventListener('submit', e => {
  e.preventDefault();
  const body = {count: Number(el('count').value), start_index: Number(el('start').value), prepopulate: el('prepopulate').checked, password_mode: pwMode()};
  if (pwMode() !== 'generated') body.password = el('password').value;
  run(async () => { await api('api/jobs/students', body); el('password').value = ''; });
});

// Change 2026-11-20: password reset (moved here from the chatbot Admin tab).
function rMode() { return document.querySelector('input[name=rmode]:checked').value; }
document.querySelectorAll('input[name=rmode]').forEach(r => r.addEventListener('change', () => { el('rlabel').hidden = rMode() === 'generated'; }));
el('reset').addEventListener('submit', e => {
  e.preventDefault();
  const body = {number: Number(el('rnumber').value), password_mode: rMode()};
  if (rMode() !== 'generated') body.password = el('rpassword').value;
  run(async () => { await api('api/jobs/password', body); el('rpassword').value = ''; });
});

el('prepop').addEventListener('submit', e => {
  e.preventDefault();
  run(() => api('api/jobs/prepopulate', {count: Number(el('pcount').value), start_index: Number(el('pstart').value),
                                        restore: el('prestore').checked}));
});

async function loadRoster() {
  const box = el('roster');
  try {
    const data = await api('api/roster');
    box.replaceChildren();
    if (!data.items.length) { box.append(text('p', 'No students yet.', 'muted')); return; }
    const table = document.createElement('table');
    const head = document.createElement('tr');
    ['#', 'Name', 'Account', 'Workspace', 'In FAIG', 'Keys', 'Password stored', ''].forEach(h => head.append(text('th', h)));
    table.append(head);
    data.items.forEach(r => {
      const tr = document.createElement('tr');
      const name = document.createElement('input');
      name.value = r.display_name; name.maxLength = 80; name.placeholder = 'optional';
      const save = document.createElement('button'); save.type = 'button'; save.textContent = 'Save name';
      save.addEventListener('click', () => run(async () => { await api('api/roster/name', {student: r.student, display_name: name.value}); await loadRoster(); }));
      const nameCell = document.createElement('td'); nameCell.append(name);
      tr.append(text('td', String(r.number)), nameCell, text('td', r.username), text('td', r.workspace),
                text('td', r.in_faig ? 'yes' : 'no'), text('td', String(r.keys)), text('td', r.password_stored ? 'yes' : 'no'));
      const actions = document.createElement('td'); actions.append(save); tr.append(actions);
      table.append(tr);
    });
    box.append(table);
  } catch (e) { box.replaceChildren(text('p', 'Student list unavailable: ' + e.message, 'warn')); }
}

el('aa-history-box').addEventListener('toggle', () => { if (el('aa-history-box').open) loadApprovals(); });
el('aa-history-form').addEventListener('submit', e => { e.preventDefault(); loadApprovals(); });
el('auto-approval').addEventListener('input', () => { el('auto-approval').dataset.touched = '1'; });
el('auto-approval').addEventListener('submit', e => {
  e.preventDefault();
  run(async () => {
    showApproval(await api('api/auto-approve', {enabled: el('aa-enabled').checked, hours: Number(el('aa-hours').value)}));
    delete el('auto-approval').dataset.touched;
  });
});

run(async () => {});
loadRoster();
setInterval(() => api('api/state').then(s => {
  showApproval(s.auto_approval || {});
  if ((s.auto_approval || {}).history_added && el('aa-history-box').open) loadApprovals();
}).catch(() => {}), 15000);
