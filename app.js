const $=s=>document.querySelector(s);let period="all";
const parse=s=>{const m=String(s).match(/(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})/);return m?new Date(+m[3],+m[2]-1,+m[1]):new Date(9999,0,1)};
const fmt=s=>{const d=parse(s);return {date:d.toLocaleDateString("cs-CZ",{day:"numeric",month:"long",year:"numeric"}),weekday:d.toLocaleDateString("cs-CZ",{weekday:"long"})}};
const esc=s=>String(s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const stripEmoji=s=>String(s||"").replace(/[\p{Extended_Pictographic}\uFE0F]/gu,"").replace(/\s{2,}/g," ").trim();

const CATEGORY_DEFS=[
 {id:"rail",label:"Železnice",icon:"fa-train",keys:["želez","vlak","motorá","úzkokole","dráha","rail"]},
 {id:"mhd",label:"MHD",icon:"fa-tram",keys:["tram","trolej","autobus","bus","metro","mhd"]},
 {id:"road",label:"Silnice",icon:"fa-car",keys:["automobil","silnič","auto ","veterán"]},
 {id:"water",label:"Lodě",icon:"fa-ship",keys:["loď","lod","plav","parník"]},
 {id:"air",label:"Letectví",icon:"fa-plane",keys:["letad","letec","leteck"]},
];
function categories(e){
 if(Array.isArray(e.categories)&&e.categories.length){const byId=Object.fromEntries(CATEGORY_DEFS.map(c=>[c.id,c]));byId.other={id:"other",label:"Ostatní",icon:"fa-compass"};return e.categories.map(id=>byId[id]).filter(Boolean)}
 const hay=[e.transport,e.type,e.title].join(" ").toLowerCase(),out=[];
 CATEGORY_DEFS.forEach(c=>{if(c.keys.some(k=>hay.includes(k)))out.push(c)});
 return out.length?out:[{id:"other",label:"Ostatní",icon:"fa-compass"}];
}
const categoryHtml=e=>categories(e).map(c=>'<span class="category category-'+c.id+'"><i class="fas '+c.icon+'" aria-hidden="true"></i>'+c.label+'</span>').join("");
function displayLocation(e){
 const raw=String(e.city||e.place||"").trim();
 if(!raw)return "";
 return raw.split(/\s*\/\s*|\s*;\s*/).map(x=>x.trim()).filter(Boolean).join(", ");
}
const regions=[...new Set(EVENTS.flatMap(e=>(e.region||"").split("/").map(x=>x.trim())).filter(Boolean))].sort();
$("#region").innerHTML+=regions.map(x=>'<option>'+esc(x)+'</option>').join("");
function render(){
 let q=$("#search").value.toLowerCase(),r=$("#region").value,t=$("#transport").value;
 let a=EVENTS.filter(e=>{let hay=[e.title,e.city,e.region,e.organizer,e.type,e.transport].join(" ").toLowerCase(),ok=!q||hay.includes(q);ok=ok&&(!r||(e.region||"").includes(r));ok=ok&&(!t||(e.transport||"").toLowerCase().includes(t));if(period==="october")ok=ok&&parse(e.from).getMonth()===9;if(period==="weekend"){let d=parse(e.from);ok=ok&&d>=new Date(2026,8,25)&&d<=new Date(2026,8,27,23,59)}return ok}).sort((x,y)=>parse(x.from)-parse(y.from));
 $("#count").textContent=a.length+" akcí";let groups={};a.forEach(e=>(groups[e.from]??=[]).push(e));
 $("#events").innerHTML=Object.entries(groups).map(([d,es])=>'<section class="day"><div class="date"><strong>'+fmt(d).date+'</strong><span>'+fmt(d).weekday+'</span></div><div class="cards">'+es.map(e=>{const loc=displayLocation(e);return '<a class="event" href="detail.html?id='+encodeURIComponent(e.id)+'"><div class="event-main"><h2>'+esc(stripEmoji(e.title))+'</h2><div class="event-info"><div class="categories">'+categoryHtml(e)+'</div>'+(loc?'<div class="location-meta" title="'+esc(e.region||"")+'"><i class="fas fa-map-marker-alt" aria-hidden="true"></i><span>'+esc(loc)+'</span></div>':"")+'</div></div></a>'}).join("")+'</div></section>').join("")||'<p class="empty">Žádné akce neodpovídají filtru.</p>';
}
["search","region","transport"].forEach(id=>$("#"+id).addEventListener("input",render));
document.querySelectorAll("[data-period]").forEach(b=>b.onclick=()=>{document.querySelectorAll("[data-period]").forEach(x=>x.classList.remove("active"));b.classList.add("active");period=b.dataset.period;render()});render();
const filterToggle=$("#filterToggle"),filterbar=$("#filterbar");filterToggle.addEventListener("click",()=>{const open=filterbar.classList.toggle("open");filterbar.classList.toggle("collapsed",!open);filterToggle.setAttribute("aria-expanded",open);filterToggle.querySelector("span").textContent=open?"⌃":"⌄"});