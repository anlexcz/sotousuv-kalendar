const ADMIN_SESSION_KEY="sk-admin-session",ADMIN_EDITS_KEY="sk-admin-edits";
const $=s=>document.querySelector(s),esc=SK.escapeHtml;
const getEdits=()=>{try{return JSON.parse(localStorage.getItem(ADMIN_EDITS_KEY)||"{}")}catch{return {}}};
const saveEdits=x=>localStorage.setItem(ADMIN_EDITS_KEY,JSON.stringify(x));
const stateOf=e=>e.editorState||((String(e.status||"").toLowerCase().includes("zruš"))?"cancelled":"active");
const reviewOf=e=>e.reviewStatus==="human_reviewed"||e.reviewed===true?"human_reviewed":"automatic";
const mergedEvents=()=>{const edits=getEdits();return EVENTS.map(e=>({...e,...(edits[e.id]||{})}))};
function setSession(on){on?localStorage.setItem(ADMIN_SESSION_KEY,"1"):localStorage.removeItem(ADMIN_SESSION_KEY);renderSession()}
function renderSession(){const on=localStorage.getItem(ADMIN_SESSION_KEY)==="1";$("#adminLogin").hidden=on;$("#adminApp").hidden=!on;if(on)renderList()}
$("#adminLoginButton").onclick=()=>setSession(true);$("#adminLogout").onclick=()=>setSession(false);
$("#editorCategories").innerHTML=SK.CATEGORY_DEFS.map(c=>'<label class="admin-category category-'+c.id+'"><input type="checkbox" name="categories" value="'+c.id+'"><span><i class="fas '+c.icon+'"></i>'+c.label+'</span></label>').join("");
function renderList(){const q=$("#adminSearch").value.trim().toLowerCase(),state=$("#adminState").value,review=$("#adminReview").value,all=mergedEvents();const filtered=all.filter(e=>{const hay=[e.title,e.city,e.place,e.region].join(" ").toLowerCase();return (!q||hay.includes(q))&&(!state||stateOf(e)===state)&&(!review||reviewOf(e)===review)});
 const counts={active:0,cancelled:0,hidden:0,automatic:0};all.forEach(e=>{counts[stateOf(e)]++;if(reviewOf(e)==="automatic")counts.automatic++});
 $("#adminStats").innerHTML='<span><b>'+all.length+'</b> akcí</span><span><b>'+counts.automatic+'</b> automatických</span><span><b>'+counts.cancelled+'</b> zrušených</span><span><b>'+counts.hidden+'</b> skrytých</span>';
 $("#adminList").innerHTML=filtered.length?filtered.map(e=>{const s=stateOf(e),r=reviewOf(e);return '<button class="admin-row" data-id="'+esc(e.id)+'"><div><strong>'+esc(SK.stripEmoji(e.title))+'</strong><small>'+esc([e.from,SK.displayLocation(e)].filter(Boolean).join(" · "))+'</small></div><div class="admin-row-flags"><span class="admin-status '+s+'">'+({active:"Aktivní",cancelled:"Zrušená",hidden:"Skrytá"}[s])+'</span><span class="admin-review '+r+'"><i class="fas '+(r==="human_reviewed"?"fa-user-check":"fa-robot")+'"></i>'+(r==="human_reviewed"?"Zkontrolovaná":"Automatická")+'</span></div></button>'}).join(""):'<div class="admin-empty">Žádné akce neodpovídají filtru.</div>';
 document.querySelectorAll(".admin-row").forEach(b=>b.onclick=()=>openEditor(b.dataset.id))
}
["adminSearch","adminState","adminReview"].forEach(id=>$("#"+id).addEventListener(id==="adminSearch"?"input":"change",renderList));
function openEditor(id){const e=mergedEvents().find(x=>x.id===id);if(!e)return;const f=$("#editorForm");for(const n of ["id","title","from","to","time","endTime","city","place","region","description","source"])f.elements[n].value=e[n]||"";f.elements.editorState.value=stateOf(e);f.elements.reviewStatus.value=reviewOf(e);f.querySelectorAll('[name="categories"]').forEach(x=>x.checked=SK.categoryIds(e).includes(x.value));$("#editorTitle").textContent=SK.stripEmoji(e.title);$("#editorPublicLink").href="detail.html?id="+encodeURIComponent(e.id);$("#adminEditor").hidden=false;document.body.classList.add("admin-modal-open")}
function closeEditor(){$("#adminEditor").hidden=true;document.body.classList.remove("admin-modal-open")}
$("#editorClose").onclick=closeEditor;$("#adminEditor").onclick=e=>{if(e.target===$("#adminEditor"))closeEditor()};
$("#markReviewed").onclick=()=>{$("#editorForm").elements.reviewStatus.value="human_reviewed"};
$("#editorForm").onsubmit=e=>{e.preventDefault();const f=e.currentTarget,id=f.elements.id.value,edits=getEdits();edits[id]={title:f.elements.title.value.trim(),from:f.elements.from.value.trim(),to:f.elements.to.value.trim(),time:f.elements.time.value.trim(),endTime:f.elements.endTime.value.trim(),city:f.elements.city.value.trim(),place:f.elements.place.value.trim(),region:f.elements.region.value.trim(),description:f.elements.description.value.trim(),source:f.elements.source.value.trim(),categories:[...f.querySelectorAll('[name="categories"]:checked')].map(x=>x.value),editorState:f.elements.editorState.value,reviewStatus:f.elements.reviewStatus.value,editedAt:new Date().toISOString()};saveEdits(edits);closeEditor();renderList()};
const requested=new URLSearchParams(location.search).get("event");renderSession();if(requested&&localStorage.getItem(ADMIN_SESSION_KEY)==="1")openEditor(requested);
