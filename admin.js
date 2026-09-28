const $=s=>document.querySelector(s),esc=SK.escapeHtml;
let adminView="all",events=[];

async function api(url,options={}){
 const r=await fetch(url,{credentials:"same-origin",headers:{"Content-Type":"application/json",...(options.headers||{})},...options});
 const data=await r.json().catch(()=>({}));
 if(!r.ok)throw Object.assign(new Error(data.error||"api_error"),{status:r.status,data});
 return data;
}

function firstDate(e){return (e.dates&&e.dates[0])||{} }
function displayDate(e){const d=firstDate(e);return d.starts_on||"Bez data"}
function displayPlace(e){return [e.city,e.place].filter(Boolean).join(" · ")||e.region||"—"}

async function loadSession(){
 try{const {user}=await api("api/auth.php");renderSession(user)}catch{renderSession(null)}
}

function renderSession(user){
 $("#adminLogin").hidden=!!user;$("#adminApp").hidden=!user;
 if(user){$("#adminUser").textContent=user.display_name||user.email;loadEvents()}
}

$("#adminLoginForm").onsubmit=async e=>{
 e.preventDefault();$("#adminLoginError").hidden=true;
 const f=e.currentTarget;
 try{const {user}=await api("api/auth.php",{method:"POST",body:JSON.stringify({email:f.email.value.trim(),password:f.password.value})});f.reset();renderSession(user)}
 catch{$("#adminLoginError").hidden=false}
};

$("#adminLogout").onclick=async()=>{await api("api/auth.php",{method:"DELETE"});events=[];renderSession(null)};

async function loadEvents(){
 const {events:list}=await api("api/admin/events.php");events=list;renderList();
}

function renderList(){
 const q=$("#adminSearch").value.trim().toLowerCase();
 const filtered=events.filter(e=>{
  const hay=[e.title,e.city,e.place,e.region].join(" ").toLowerCase();
  const viewOk=adminView==="all"||(adminView==="review"&&e.review_status==="automatic")||(adminView==="cancelled"&&e.status==="cancelled")||(adminView==="hidden"&&e.status==="hidden");
  return (!q||hay.includes(q))&&viewOk;
 });
 $("#adminCount").textContent="("+events.length+")";
 const reviewCount=events.filter(e=>e.review_status==="automatic").length;$("#reviewCount").textContent=reviewCount?"("+reviewCount+")":"";
 $("#adminList").innerHTML=filtered.length?filtered.map(e=>{
  const cats=(e.categories||[]).map(id=>(SK.CATEGORY_BY_ID[id]||SK.CATEGORY_BY_ID.other).label).join(", ");
  return '<button class="admin-row" data-id="'+esc(e.id)+'"><div class="admin-row-main"><small>'+esc(displayDate(e))+'</small><strong>'+esc(SK.stripEmoji(e.title))+'</strong><span class="admin-row-mobilemeta">'+esc(displayPlace(e))+' · '+esc(cats)+'</span></div><span class="admin-cell admin-place">'+esc(displayPlace(e))+'</span><span class="admin-cell admin-cats">'+esc(cats)+'</span><span class="admin-cell"><span class="admin-status '+esc(e.status)+'">'+({active:"Aktivní",cancelled:"Zrušená",hidden:"Skrytá"}[e.status]||e.status)+'</span></span><span class="admin-cell"><span class="admin-review '+esc(e.review_status)+'"><i class="fas '+(e.review_status==="human_reviewed"?"fa-user-check":"fa-robot")+'"></i>'+(e.review_status==="human_reviewed"?"Zkontrolovaná":"Robot")+'</span></span></button>'
 }).join(""):'<div class="admin-empty">Žádné akce.</div>';
 document.querySelectorAll(".admin-row").forEach(b=>b.onclick=()=>openEditor(b.dataset.id));
}

$("#adminSearch").addEventListener("input",renderList);
document.querySelectorAll("#adminTabs button").forEach(b=>b.onclick=()=>{adminView=b.dataset.view;document.querySelectorAll("#adminTabs button").forEach(x=>x.classList.toggle("active",x===b));renderList()});

$("#editorCategories").innerHTML=SK.CATEGORY_DEFS.map(c=>'<label class="admin-category category-'+c.id+'"><input type="checkbox" name="categories" value="'+c.id+'"><span><i class="fas '+c.icon+'"></i>'+c.label+'</span></label>').join("");

function openEditor(id){
 const e=events.find(x=>x.id===id);if(!e)return;const f=$("#editorForm"),d=firstDate(e);
 f.elements.id.value=e.id;f.elements.title.value=e.title||"";f.elements.from.value=d.starts_on||"";f.elements.to.value=d.ends_on||d.starts_on||"";f.elements.time.value=d.starts_at||e.time_start||"";f.elements.endTime.value=d.ends_at||e.time_end||"";f.elements.city.value=e.city||"";f.elements.place.value=e.place||"";f.elements.region.value=e.region||"";f.elements.description.value=e.description||"";f.elements.source.value=(e.sources&&e.sources.find(s=>Number(s.is_primary))?.url)||(e.sources&&e.sources[0]?.url)||e.public_url||"";f.elements.editorState.value=e.status||"active";f.elements.reviewStatus.value=e.review_status||"automatic";
 f.querySelectorAll('[name="categories"]').forEach(x=>x.checked=(e.categories||[]).includes(x.value));$("#editorTitle").textContent=SK.stripEmoji(e.title);$("#editorPublicLink").href="detail.html?id="+encodeURIComponent(e.id);$("#adminEditor").hidden=false;document.body.classList.add("admin-modal-open")
}
function closeEditor(){$("#adminEditor").hidden=true;document.body.classList.remove("admin-modal-open")}
$("#editorClose").onclick=closeEditor;$("#adminEditor").onclick=e=>{if(e.target===$("#adminEditor"))closeEditor()};
$("#markReviewed").onclick=()=>{$("#editorForm").elements.reviewStatus.value="human_reviewed"};

$("#editorForm").onsubmit=async e=>{
 e.preventDefault();const f=e.currentTarget,id=f.elements.id.value;
 const payload={title:f.elements.title.value.trim(),description:f.elements.description.value.trim(),city:f.elements.city.value.trim()||null,place:f.elements.place.value.trim()||null,region:f.elements.region.value.trim()||null,public_url:f.elements.source.value.trim()||null,status:f.elements.editorState.value,review_status:f.elements.reviewStatus.value,categories:[...f.querySelectorAll('[name="categories"]:checked')].map(x=>x.value),dates:f.elements.from.value?[{starts_on:f.elements.from.value,ends_on:f.elements.to.value||f.elements.from.value,starts_at:f.elements.time.value||null,ends_at:f.elements.endTime.value||null}]:[]};
 try{const {event}=await api("api/admin/event.php?id="+encodeURIComponent(id),{method:"PUT",body:JSON.stringify(payload)});events=events.map(x=>x.id===id?event:x);closeEditor();renderList()}
 catch(err){alert("Uložení se nepodařilo. Zkus to znovu.")}
};

const requested=new URLSearchParams(location.search).get("event");
loadSession().then(()=>{if(requested&&events.length)openEditor(requested)});
