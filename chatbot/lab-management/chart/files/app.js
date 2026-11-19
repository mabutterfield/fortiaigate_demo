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

function showApproval(a) {
  const box = el('approval');
  box.className = 'indicator ' + (a.state || 'unavailable');
  box.textContent = 'Auto-approval: ' + (a.state || 'unavailable');
  box.title = a.detail || '';
}

async function refresh() {
  const state = await api('api/state');
  el('user').textContent = state.user;
  showApproval(state.auto_approval || {});
  const p = state.pricing || {};
  el('pricing').textContent = p.currency ? ('Prices: ' + p.currency + ' ' + (p.unit || '') + '. ' + (p.pricing_note || '')) : '';
  const box = el('scenarios');
  box.replaceChildren();
  if (state.catalog_error) box.append(text('p', state.catalog_error, 'warn'));
  state.catalog.forEach(s => box.append(scenarioSection(s, state.selected.includes(s.id))));
  const list = el('jobs');
  list.replaceChildren();
  if (!state.jobs.length) list.append(text('p', 'No operations recorded.', 'muted'));
  state.jobs.forEach(j => list.append(text('p',
    j.kind + ' · ' + j.status + ' · ' + j.actor + ' · ' + new Date(j.created * 1000).toLocaleString() + ' · ' + j.detail + ' ' + j.request)));
}

async function run(fn) {
  try { el('error').textContent = ''; await fn(); await refresh(); }
  catch (e) { el('error').textContent = e.message; }
}

el('selection').addEventListener('submit', e => {
  e.preventDefault();
  run(() => api('api/selection', {ids: [...el('scenarios').querySelectorAll('input:checked')].map(x => x.value)}));
});
el('models').addEventListener('click', () => run(() => api('api/jobs/models', {})));
el('students').addEventListener('submit', e => {
  e.preventDefault();
  run(() => api('api/jobs/students', {count: Number(el('count').value), start_index: Number(el('start').value), prepopulate: el('prepopulate').checked}));
});
run(async () => {});
setInterval(() => api('api/state').then(s => showApproval(s.auto_approval || {})).catch(() => {}), 15000);
