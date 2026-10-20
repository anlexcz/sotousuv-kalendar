const REPO = "anlexcz/sotousuv-kalendar";
const WORKFLOW = "calendar-worker.yml";
const SESSION_DAYS = 30;

const json = (data, status = 200, headers = {}) => new Response(JSON.stringify(data, null, 2), {
  status,
  headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers },
});

const html = (body, status = 200) => new Response(body, {
  status,
  headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
});

function getCookie(req, name) {
  const raw = req.headers.get("cookie") || "";
  for (const part of raw.split(";")) {
    const [k, ...rest] = part.trim().split("=");
    if (k === name) return rest.join("=");
  }
  return null;
}

function b64url(bytes) {
  let s = "";
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function hmac(secret, value) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  return b64url(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value)));
}

function safeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function makeSession(env) {
  const exp = Math.floor(Date.now() / 1000) + SESSION_DAYS * 86400;
  const payload = String(exp);
  const sig = await hmac(env.ADMIN_SESSION_SECRET, payload);
  return `${payload}.${sig}`;
}

async function isAuthed(req, env) {
  const token = getCookie(req, "sk_admin");
  if (!token || !env.ADMIN_SESSION_SECRET) return false;
  const [payload, sig] = token.split(".");
  if (!payload || !sig) return false;
  const exp = Number(payload);
  if (!Number.isFinite(exp) || exp < Math.floor(Date.now() / 1000)) return false;
  const expected = await hmac(env.ADMIN_SESSION_SECRET, payload);
  return safeEqual(sig, expected);
}

async function github(env, path, init = {}) {
  if (!env.GITHUB_TOKEN) throw new Error("GITHUB_TOKEN is not configured");
  const response = await fetch(`https://api.github.com/repos/${REPO}${path}`, {
    ...init,
    redirect: "follow",
    headers: {
      "authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "accept": "application/vnd.github+json",
      "x-github-api-version": "2022-11-28",
      "user-agent": "sotousuv-kalendar-admin",
      ...(init.headers || {}),
    },
  });
  if (!response.ok) throw new Error(`GitHub API ${response.status}: ${(await response.text()).slice(0, 500)}`);
  return response;
}

async function eventRows(env) {
  const result = await env.DB.prepare(`
    SELECT e.event_id,e.title,e.categories,e.publish,e.review_state,e.editorial_state,e.event_state,
      (SELECT COUNT(*) FROM terms t WHERE t.event_id=e.event_id AND t.is_active='ANO') AS active_terms,
      COALESCE(
        (SELECT MIN(t.date_from) FROM terms t WHERE t.event_id=e.event_id AND t.is_active='ANO' AND t.date_to >= date('now')),
        (SELECT MAX(t.date_to) FROM terms t WHERE t.event_id=e.event_id AND t.is_active='ANO')
      ) AS next_date,
      COALESCE(
        (SELECT MAX(f.last_seen_at) FROM findings f WHERE f.event_id=e.event_id),
        ea.auto_updated_at,e.updated_at,e.created_at
      ) AS last_checked_at
    FROM events e
    LEFT JOIN event_auto ea ON ea.event_id=e.event_id
    WHERE e.is_active='ANO'
    ORDER BY COALESCE(next_date,'9999-12-31'), e.event_id
  `).all();
  return result.results || [];
}

async function sourceRows(env) {
  const result = await env.DB.prepare(`
    SELECT source_id,label,url,fetch_strategy,parser_key,active,migration_status,
      last_checked_at,last_success_at,next_check_at,last_http_status,consecutive_errors,priority,area
    FROM sources
    WHERE migration_status IN ('MIGRATE','MIGRATE_INACTIVE','FALLBACK_ONLY','ALREADY_PILOT')
    ORDER BY CASE WHEN consecutive_errors>0 THEN 0 ELSE 1 END, COALESCE(last_checked_at,''), label, source_id
  `).all();
  return result.results || [];
}

async function listRuns(env) {
  const response = await github(env, `/actions/workflows/${WORKFLOW}/runs?per_page=30`);
  const data = await response.json();
  return (data.workflow_runs || []).map(r => ({
    id: r.id,
    run_number: r.run_number,
    display_title: r.display_title,
    event: r.event,
    status: r.status,
    conclusion: r.conclusion,
    created_at: r.created_at,
    updated_at: r.updated_at,
    html_url: r.html_url,
  }));
}

async function runLog(env, runId) {
  const jobsResponse = await github(env, `/actions/runs/${runId}/jobs?per_page=100`);
  const jobsData = await jobsResponse.json();
  const parts = [];
  for (const job of jobsData.jobs || []) {
    parts.push(`===== ${job.name} · ${job.conclusion || job.status} =====\n`);
    try {
      const logResponse = await github(env, `/actions/jobs/${job.id}/logs`, { headers: { accept: "text/plain" } });
      const text = await logResponse.text();
      parts.push(text.slice(0, 700000));
    } catch (e) {
      parts.push(`[Log unavailable: ${e.message}]\n`);
    }
  }
  return parts.join("\n").slice(0, 1000000);
}

async function dispatch(env, inputs) {
  const response = await github(env, `/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ref: "main", inputs }),
  });
  return response.status === 204;
}

const baseCss = `
:root{font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;color:#17202a;background:#f5f7fa}*{box-sizing:border-box}
body{margin:0}header{background:#17202a;color:white;padding:18px 24px}header h1{margin:0;font-size:22px}.wrap{max-width:1400px;margin:0 auto;padding:22px}
.card{background:white;border:1px solid #dfe5eb;border-radius:12px;padding:16px;margin-bottom:16px;box-shadow:0 1px 3px #0000000d}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:10px;border-bottom:1px solid #edf0f3;vertical-align:top}th{font-size:12px;text-transform:uppercase;color:#67717d}
.badge{display:inline-block;padding:3px 7px;border-radius:999px;background:#edf2f7;font-size:12px;margin:1px}.ok{background:#e7f7ed;color:#176b36}.warn{background:#fff3d6;color:#805b00}.bad{background:#fde8e8;color:#9b1c1c}
button{border:0;border-radius:8px;padding:8px 11px;background:#17202a;color:white;cursor:pointer}button.secondary{background:#e9eef3;color:#17202a}button:disabled{opacity:.5;cursor:wait}
input{padding:10px 12px;border:1px solid #cfd7df;border-radius:8px;width:100%}.row{display:flex;gap:10px;align-items:center}.row>*{min-width:0}.muted{color:#6b7480;font-size:13px}
.tabs{display:flex;gap:8px;margin-bottom:16px}.tabs button.active{background:#2563eb}.hidden{display:none!important}pre{white-space:pre-wrap;background:#0d1117;color:#d6deeb;padding:14px;border-radius:10px;max-height:70vh;overflow:auto;font-size:12px}
.modal{position:fixed;inset:0;background:#0008;display:flex;align-items:center;justify-content:center;padding:20px}.modalBox{background:white;width:min(1200px,96vw);max-height:90vh;border-radius:12px;padding:18px;overflow:auto}
@media(max-width:800px){.wrap{padding:12px}.tableWrap{overflow:auto}table{min-width:900px}.row{flex-direction:column;align-items:stretch}}
`;

function publicPage() {
  return `<!doctype html><html lang="cs"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Šotoušův kalendář</title><style>${baseCss}</style></head><body>
<header><h1>Šotoušův kalendář</h1></header><main class="wrap"><div class="card"><div class="row"><input id="q" placeholder="Hledat akci…"><span class="muted">Prototyp</span></div></div><div class="card tableWrap"><table><thead><tr><th>ID</th><th>Akce</th><th>Termín</th><th>Kategorie</th><th>Termíny</th><th>Poslední kontrola</th><th>Stav</th></tr></thead><tbody id="body"></tbody></table></div></main>
<script>
let events=[];const fmt=v=>v?new Date(v.length===10?v+'T00:00:00':v).toLocaleString('cs-CZ',{dateStyle:'medium',timeStyle:v.length===10?undefined:'short'}):'—';
function draw(){const q=document.querySelector('#q').value.toLowerCase();document.querySelector('#body').innerHTML=events.filter(e=>(e.title||'').toLowerCase().includes(q)).map(e=>'<tr><td>'+e.event_id+'</td><td><b>'+esc(e.title)+'</b></td><td>'+fmt(e.next_date)+'</td><td>'+esc(e.categories||'—')+'</td><td>'+e.active_terms+'</td><td>'+fmt(e.last_checked_at)+'</td><td><span class="badge '+(e.publish==='ANO'?'ok':'warn')+'">'+(e.publish==='ANO'?'publikováno':'draft')+'</span></td></tr>').join('')}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
fetch('/api/events').then(r=>r.json()).then(d=>{events=d.events||[];draw()});document.querySelector('#q').addEventListener('input',draw);
</script></body></html>`;
}

function adminPage() {
  return `<!doctype html><html lang="cs"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Šotoušův kalendář · Admin</title><style>${baseCss}</style></head><body>
<header><div class="row" style="justify-content:space-between"><h1>Šotoušův kalendář · Admin</h1><button id="logout" class="secondary">Odhlásit</button></div></header>
<main class="wrap"><div id="login" class="card" style="max-width:420px;margin:60px auto"><h2>Přihlášení</h2><input id="password" type="password" placeholder="Heslo"><div style="height:10px"></div><button id="loginBtn">Přihlásit</button><p id="loginErr" class="muted"></p></div>
<div id="app" class="hidden"><div class="tabs"><button data-tab="events" class="active">Události</button><button data-tab="sources">Zdroje</button><button data-tab="runs">Runy</button><button id="batch" class="secondary">Spustit collect-batch</button><button id="refresh" class="secondary">Obnovit</button></div>
<section id="events" class="card tableWrap"></section><section id="sources" class="card tableWrap hidden"></section><section id="runs" class="card tableWrap hidden"></section></div></main>
<div id="modal" class="modal hidden"><div class="modalBox"><div class="row" style="justify-content:space-between"><h3 id="modalTitle">Log</h3><button id="close" class="secondary">Zavřít</button></div><pre id="log"></pre></div></div>
<script>
const fmt=v=>v?new Date(v.length===10?v+'T00:00:00':v).toLocaleString('cs-CZ',{dateStyle:'medium',timeStyle:v.length===10?undefined:'short'}):'—';const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url,opt={}){const r=await fetch(url,{...opt,headers:{'content-type':'application/json',...(opt.headers||{})}});if(r.status===401){showLogin();throw new Error('Nepřihlášeno')}if(!r.ok)throw new Error((await r.text()).slice(0,500));return r.headers.get('content-type')?.includes('json')?r.json():r.text()}
function showLogin(){document.querySelector('#login').classList.remove('hidden');document.querySelector('#app').classList.add('hidden');document.querySelector('#logout').classList.add('hidden')}function showApp(){document.querySelector('#login').classList.add('hidden');document.querySelector('#app').classList.remove('hidden');document.querySelector('#logout').classList.remove('hidden')}
async function loadEvents(){const d=await api('/api/admin/events');document.querySelector('#events').innerHTML='<table><thead><tr><th>ID</th><th>Akce</th><th>Termín</th><th>Kategorie</th><th>Termíny</th><th>Poslední kontrola</th><th>Stav</th></tr></thead><tbody>'+d.events.map(e=>'<tr><td>'+e.event_id+'</td><td><b>'+esc(e.title)+'</b></td><td>'+fmt(e.next_date)+'</td><td>'+esc(e.categories||'—')+'</td><td>'+e.active_terms+'</td><td>'+fmt(e.last_checked_at)+'</td><td>'+esc(e.review_state)+' / '+esc(e.editorial_state)+' / '+esc(e.publish)+'</td></tr>').join('')+'</tbody></table>'}
async function loadSources(){const d=await api('/api/admin/sources');document.querySelector('#sources').innerHTML='<table><thead><tr><th>Zdroj</th><th>Strategie</th><th>Poslední kontrola</th><th>Poslední úspěch</th><th>Další</th><th>HTTP</th><th>Chyby</th><th></th></tr></thead><tbody>'+d.sources.map(s=>'<tr><td><b>'+esc(s.label||s.source_id)+'</b><div class="muted">'+esc(s.source_id)+'</div></td><td>'+esc(s.fetch_strategy||s.parser_key||'—')+'</td><td>'+fmt(s.last_checked_at)+'</td><td>'+fmt(s.last_success_at)+'</td><td>'+fmt(s.next_check_at)+'</td><td>'+esc(s.last_http_status??'—')+'</td><td><span class="badge '+((s.consecutive_errors||0)>0?'bad':'ok')+'">'+(s.consecutive_errors||0)+'</span></td><td><button onclick="checkSource(\''+esc(s.source_id)+'\',this)">Zkontrolovat</button></td></tr>').join('')+'</tbody></table>'}
async function loadRuns(){const d=await api('/api/admin/runs');document.querySelector('#runs').innerHTML='<table><thead><tr><th>#</th><th>Run</th><th>Spuštění</th><th>Stav</th><th>Čas</th><th></th></tr></thead><tbody>'+d.runs.map(r=>'<tr><td>'+r.run_number+'</td><td>'+esc(r.display_title||'Calendar worker')+'</td><td>'+esc(r.event)+'</td><td><span class="badge '+(r.conclusion==='success'?'ok':r.conclusion?'bad':'warn')+'">'+esc(r.conclusion||r.status)+'</span></td><td>'+fmt(r.created_at)+'</td><td><button onclick="showLog('+r.id+')">Log</button> <a target="_blank" href="'+esc(r.html_url)+'">GitHub</a></td></tr>').join('')+'</tbody></table>'}
async function loadAll(){await Promise.all([loadEvents(),loadSources(),loadRuns()])}window.checkSource=async(id,b)=>{b.disabled=true;try{await api('/api/admin/sources/'+encodeURIComponent(id)+'/check',{method:'POST',body:'{}'});b.textContent='Spuštěno'}catch(e){alert(e.message)}finally{setTimeout(()=>b.disabled=false,1500)}};window.showLog=async(id)=>{document.querySelector('#modal').classList.remove('hidden');document.querySelector('#modalTitle').textContent='Run '+id;document.querySelector('#log').textContent='Načítám…';try{document.querySelector('#log').textContent=await api('/api/admin/runs/'+id+'/log')}catch(e){document.querySelector('#log').textContent=e.message}};
document.querySelector('#loginBtn').onclick=async()=>{try{await api('/api/admin/login',{method:'POST',body:JSON.stringify({password:document.querySelector('#password').value})});showApp();await loadAll()}catch(e){document.querySelector('#loginErr').textContent='Chybné heslo nebo chyba přihlášení.'}};document.querySelector('#logout').onclick=async()=>{await fetch('/api/admin/logout',{method:'POST'});showLogin()};document.querySelector('#batch').onclick=async e=>{e.target.disabled=true;try{await api('/api/admin/collect-batch',{method:'POST',body:'{}'});alert('collect-batch byl spuštěn')}finally{e.target.disabled=false}};document.querySelector('#refresh').onclick=loadAll;document.querySelector('#close').onclick=()=>document.querySelector('#modal').classList.add('hidden');document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.remove('active'));b.classList.add('active');['events','sources','runs'].forEach(id=>document.querySelector('#'+id).classList.toggle('hidden',id!==b.dataset.tab))});
api('/api/admin/me').then(()=>{showApp();loadAll()}).catch(()=>showLogin());
</script></body></html>`;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    try {
      if (url.pathname === "/" && req.method === "GET") return html(publicPage());
      if ((url.pathname === "/admin" || url.pathname === "/admin/") && req.method === "GET") return html(adminPage());
      if (url.pathname === "/api/events" && req.method === "GET") return json({ events: await eventRows(env) });

      if (url.pathname === "/api/admin/login" && req.method === "POST") {
        if (!env.ADMIN_PASSWORD || !env.ADMIN_SESSION_SECRET) return json({ error: "Admin secrets are not configured" }, 503);
        const body = await req.json().catch(() => ({}));
        if (!safeEqual(String(body.password || ""), String(env.ADMIN_PASSWORD))) return json({ error: "Invalid password" }, 401);
        const token = await makeSession(env);
        return json({ ok: true }, 200, {
          "set-cookie": `sk_admin=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${SESSION_DAYS * 86400}`,
        });
      }
      if (url.pathname === "/api/admin/logout" && req.method === "POST") {
        return json({ ok: true }, 200, { "set-cookie": "sk_admin=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0" });
      }

      if (url.pathname.startsWith("/api/admin/")) {
        if (!(await isAuthed(req, env))) return json({ error: "Unauthorized" }, 401);
        if (url.pathname === "/api/admin/me" && req.method === "GET") return json({ ok: true });
        if (url.pathname === "/api/admin/events" && req.method === "GET") return json({ events: await eventRows(env) });
        if (url.pathname === "/api/admin/sources" && req.method === "GET") return json({ sources: await sourceRows(env) });
        if (url.pathname === "/api/admin/runs" && req.method === "GET") return json({ runs: await listRuns(env) });
        if (url.pathname === "/api/admin/collect-batch" && req.method === "POST") {
          await dispatch(env, { command: "collect-batch", source_id: "" });
          return json({ ok: true, dispatched: "collect-batch" });
        }
        const sourceMatch = url.pathname.match(/^\/api\/admin\/sources\/([^/]+)\/check$/);
        if (sourceMatch && req.method === "POST") {
          const sourceId = decodeURIComponent(sourceMatch[1]);
          await dispatch(env, { command: "collect-source", source_id: sourceId });
          return json({ ok: true, source_id: sourceId });
        }
        const logMatch = url.pathname.match(/^\/api\/admin\/runs\/(\d+)\/log$/);
        if (logMatch && req.method === "GET") {
          return new Response(await runLog(env, logMatch[1]), { headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" } });
        }
      }
      return json({ error: "Not found" }, 404);
    } catch (e) {
      return json({ error: e?.message || String(e) }, 500);
    }
  },
};
