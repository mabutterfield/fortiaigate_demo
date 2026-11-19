'use strict';
const el = id => document.getElementById(id);
function text(tag, value) { const e = document.createElement(tag); e.textContent = value; return e; }
async function api(path, data) { const r = await fetch(path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Instructor-Request':'1'}, body:JSON.stringify(data)}); const value = await r.json(); if (!r.ok) throw new Error(value.error || 'Request failed'); return value; }
async function refresh() {
  const state = await api('/api/state'); const box = el('scenarios'); box.replaceChildren();
  state.catalog.forEach(s => { const section = document.createElement('section'); const label = document.createElement('label'); const input = document.createElement('input'); input.type='checkbox'; input.value=s.id; input.checked=state.selected.includes(s.id); label.append(input, document.createTextNode(' '+s.title+' ('+s.alias+')')); section.append(label, text('p',s.description), text('p','Tools: '+(s.tools.join(', ') || 'none')), text('p','Actions: '+s.actions.map(a=>a.action).join(', '))); const details=document.createElement('details'); details.append(text('summary','Sample prompts and tests'), text('pre',JSON.stringify({prompts:s.sample_prompts,tests:s.tests},null,2))); section.append(details); box.append(section); });
  const jobs=el('jobs'); jobs.replaceChildren(); if (!state.jobs.length) jobs.append(text('p','No operations recorded.')); state.jobs.forEach(j=>jobs.append(text('p',`${j.kind} · ${j.status} · ${j.actor} · ${new Date(j.created*1000).toLocaleString()} · ${j.detail} ${j.request}`)));
}
async function run(fn) { try { el('error').textContent=''; await fn(); await refresh(); } catch(e) { el('error').textContent=e.message; } }
el('selection').addEventListener('submit', e=>{e.preventDefault(); run(()=>api('/api/selection',{ids:[...el('scenarios').querySelectorAll('input:checked')].map(x=>x.value)}));});
el('deploy').addEventListener('click',()=>run(()=>api('/api/jobs/deploy',{})));
el('students').addEventListener('submit',e=>{e.preventDefault(); run(()=>api('/api/jobs/students',{count:Number(el('count').value),start_index:Number(el('start').value),prepopulate:el('prepopulate').checked}));});
run(async()=>{});
