'use strict';
// Relative URLs only (served under /manage/). Passwords are fetched with no-store and never cached here.
const el = id => document.getElementById(id);
function cell(tag, value) { const e = document.createElement(tag); e.textContent = value; return e; }
fetch('api/roster/share', {cache: 'no-store'}).then(async r => {
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || ('Request failed (' + r.status + ')'));
  el('url').textContent = data.sign_in_url;
  const table = el('table');
  const head = document.createElement('tr');
  ['#', 'Name', 'Email', 'Password'].forEach(h => head.append(cell('th', h)));
  table.append(head);
  data.items.filter(r => r.in_faig).forEach(r => {
    const tr = document.createElement('tr');
    const pw = cell('td', r.password || '(not stored)');
    pw.className = 'mono';
    tr.append(cell('td', String(r.number)), cell('td', r.display_name || ''), cell('td', r.username), pw);
    table.append(tr);
  });
}).catch(e => { el('error').textContent = e.message; });
