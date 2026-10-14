'use strict';
let csrf='';
const el=id=>document.getElementById(id);
async function api(path,body){
 const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});
 const d=await r.json().catch(()=>({error:'Request failed (HTTP '+r.status+').'}));if(!r.ok)throw new Error(d.error||'Request failed');return d;
}
async function refresh(){try{
 const d=await api('/api/admin/paytm-test');el('status').textContent=d.active?(d.matching?'Demo matching active — TEST alerts enabled':'Capture active — no live verification'):'Capture stopped';
 el('results').textContent=d.captures.map(r=>`${new Date(r.captured_at*1000).toLocaleString()} | ${r.amount_paise===null?'Amount not recognized':'₹'+(r.amount_paise/100).toFixed(2)} | ${r.outcome} | repeats: ${r.repeats}`).join('\n')||'No notifications captured yet.';
 }catch(e){el('status').textContent=e.message;}}
el('start').onclick=async()=>{try{const d=await api('/api/admin/paytm-test/start',{matching:el('matching').checked});el('token').value=d.token;el('credentials').hidden=false;await refresh();}catch(e){el('status').textContent=e.message;}};
el('stop').onclick=async()=>{try{await api('/api/admin/paytm-test/stop',{});el('token').value='';el('credentials').hidden=true;await refresh();}catch(e){el('status').textContent=e.message;}};
el('reveal').onclick=()=>{el('token').type=el('token').type==='password'?'text':'password';};
(async()=>{try{csrf=(await api('/api/admin/state')).csrf;await refresh();setInterval(refresh,3000);}catch(e){el('status').textContent='Sign in at /admin first. '+e.message;}})();
