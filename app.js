const $=s=>document.querySelector(s);
const parse=s=>{const m=String(s).match(/(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})/);return m?new Date(+m[3],+m[2]-1,+m[1]):new Date(9999,0,1)};
const fmt=s=>{const d=parse(s);return {date:d.toLocaleDateString("cs-CZ",{day:"numeric",month:"long",year:"numeric"}),weekday:d.toLocaleDateString("cs-CZ",{weekday:"long"})}};
const esc=s=>String(s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const stripEmoji=s=>String(s||"").replace(/[\p{Extended_Pictographic}\uFE0F]/gu,"").replace(/\s{2,}/g," ").trim();
const CATEGORY_DEFS=[
{id:"rail",label:"Železnice",icon:"fa-train"},{id:"bus",label:"Autobus",icon:"fa-bus"},{id:"tram",label:"Tramvaj",icon:"fa-tram"},{id:"trolleybus",label:"Trolejbus",icon:"fa-bus-alt"},{id:"metro",label:"Metro",icon:"fa-subway"},{id:"water",label:"Loď",icon:"fa-ship"},{id:"air",label:"Letadlo",icon:"fa-plane"},{id:"cableway",label:"Lanovka",icon:"fa-mountain"},{id:"other",label:"Ostatní",icon:"fa-compass"}];
const byId=Object.fromEntries(CATEGORY_DEFS.map(c=>[c.id,c]));
const categories=e=>(e.categories||["other"]).map(id=>byId[id]).filter(Boolean);
const categoryHtml=e=>categories(e).map(c=>'<span class="category category-'+c.id+'"><i class="fas '+c.icon+'"></i>'+c.label+'</span>').join("");
const displayLocation=e=>String(e.city||e.place||"").trim().split(/\s*\/\s*|\s*;\s*/).filter(Boolean).join(", ");
const regions=[...new Set(EVENTS.flatMap(e=>String(e.region||"").split("/").map(x=>x.trim())).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"cs"));
const selectedCategories=new Set(),selectedRegions=new Set();
$("#categoryFilter").innerHTML=CATEGORY_DEFS.map(c=>'<button type="button" class="filter-chip category-'+c.id+'" data-category="'+c.id+'" aria-pressed="false"><i class="fas '+c.icon+'"></i><span>'+c.label+'</span></button>').join("");
$("#regionPicker").innerHTML=regions.map(r=>'<button type="button" class="region-option" data-region="'+esc(r)+'" aria-pressed="false"><span class="modern-check"><i class="fas fa-check"></i></span><span>'+esc(r)+'</span></button>').join("");
const DAY=86400000;
const dayStart=d=>new Date(d.getFullYear(),d.getMonth(),d.getDate());
const durationDays=e=>{const a=parse(e.from),b=parse(e.to||e.from);return Math.max(1,Math.round((dayStart(b)-dayStart(a))/DAY)+1)};
const isLongTerm=e=>durationDays(e)>7&&(String(e.type||"").toLowerCase().includes("výstava")||!e.recurring);
const todayDate=()=>dayStart(new Date());
const occursOn=(e,d)=>{const a=dayStart(parse(e.from)),b=dayStart(parse(e.to||e.from));return d>=a&&d<=b};
function updateFilterUI(){
 document.querySelectorAll("[data-category]").forEach(b=>{const on=selectedCategories.has(b.dataset.category);b.classList.toggle("active",on);b.setAttribute("aria-pressed",on)});
 document.querySelectorAll("[data-region]").forEach(b=>{const on=selectedRegions.has(b.dataset.region);b.classList.toggle("active",on);b.setAttribute("aria-pressed",on)});
 const n=selectedCategories.size+selectedRegions.size;$("#filterCount").textContent=n?n+" aktivní":"";$("#clearFilters").classList.toggle("visible",n>0);
 $("#regionSummary").textContent=!selectedRegions.size?"Celá ČR":selectedRegions.size===1?[...selectedRegions][0]:[...selectedRegions][0]+" + "+(selectedRegions.size-1)+" další";
}
const eventMatches=(e,q)=>{
 const hay=[e.title,e.city,e.place,e.region,e.organizer,e.type,e.transport,e.route].join(" ").toLowerCase();
 const catOk=!selectedCategories.size||(e.categories||["other"]).some(c=>selectedCategories.has(c));
 const regParts=String(e.region||"").split("/").map(x=>x.trim());
 const regOk=!selectedRegions.size||regParts.some(r=>selectedRegions.has(r));
 return (!q||hay.includes(q))&&catOk&&regOk;
};
const eventCard=(e,extraClass='')=>{const loc=displayLocation(e);return '<a class="event '+extraClass+'" href="detail.html?id='+encodeURIComponent(e.id)+'"><div class="event-main"><h2>'+esc(stripEmoji(e.title))+'</h2><div class="event-info"><div class="categories">'+categoryHtml(e)+'</div>'+(loc?'<div class="location-meta" title="'+esc(e.region||"")+'"><i class="fas fa-map-marker-alt"></i><span>'+esc(loc)+'</span></div>':"")+'</div></div></a>'};
function render(){
 const q=$("#search").value.trim().toLowerCase(),today=todayDate();
 const matching=EVENTS.filter(e=>eventMatches(e,q));
 const normal=matching.filter(e=>!isLongTerm(e)&&dayStart(parse(e.from))>=today).sort((x,y)=>parse(x.from)-parse(y.from));
 const long=matching.filter(isLongTerm).filter(e=>dayStart(parse(e.to||e.from))>=today);
 const groups={};
 normal.forEach(e=>{const k=e.from;(groups[k]??={date:dayStart(parse(k)),normal:[],long:[]}).normal.push(e)});
 // Long-term events create a day section at start/end and today when currently active.
 long.forEach(e=>{const a=dayStart(parse(e.from)),b=dayStart(parse(e.to||e.from));[a,(today>=a&&today<=b?today:null),b].filter(Boolean).forEach(d=>{if(d>=today){const k=d.toLocaleDateString("cs-CZ");(groups[k]??={date:d,normal:[],long:[]})}})});
 Object.values(groups).forEach(g=>{g.long=long.filter(e=>occursOn(e,g.date))});
 const ordered=Object.values(groups).sort((a,b)=>a.date-b.date);
 $("#events").innerHTML=ordered.map((g,i)=>{
  const dateKey=g.date.toISOString().slice(0,10),longCount=g.long.length;
  const longToggle=longCount?'<button type="button" class="longterm-toggle" data-long-day="'+dateKey+'" aria-expanded="false"><span>Dlouhodobé · '+longCount+'</span><i class="fas fa-chevron-down"></i></button>':"";
  return '<section class="day" data-date="'+dateKey+'"><div class="date"><div class="date-label"><strong>'+g.date.toLocaleDateString("cs-CZ",{day:"numeric",month:"long",year:"numeric"})+'</strong><span>'+g.date.toLocaleDateString("cs-CZ",{weekday:"long"})+'</span></div>'+longToggle+'</div><div class="cards">'+g.normal.map(eventCard).join("")+(longCount?'<div class="longterm-cards" hidden>'+g.long.map(e=>eventCard(e,'longterm-event')).join("")+'</div>':"")+'</div></section>'
 }).join("")||'<div class="empty-state"><i class="fas fa-filter"></i><strong>Žádné akce neodpovídají filtru.</strong><button type="button" id="emptyClear">Vymazat filtry</button></div>';
 document.querySelectorAll(".longterm-toggle").forEach(b=>b.onclick=()=>{const box=b.closest(".day").querySelector(".longterm-cards"),open=box.hidden;box.hidden=!open;b.setAttribute("aria-expanded",open);b.classList.toggle("open",open);b.querySelector("i").className="fas "+(open?"fa-chevron-up":"fa-chevron-down")});
 const ec=$("#emptyClear");if(ec)ec.onclick=clearFilters;
}
function clearFilters(){selectedCategories.clear();selectedRegions.clear();updateFilterUI();render()}
document.querySelectorAll("[data-category]").forEach(b=>b.onclick=()=>{selectedCategories.has(b.dataset.category)?selectedCategories.delete(b.dataset.category):selectedCategories.add(b.dataset.category);updateFilterUI();render()});
document.querySelectorAll("[data-region]").forEach(b=>b.onclick=()=>{selectedRegions.has(b.dataset.region)?selectedRegions.delete(b.dataset.region):selectedRegions.add(b.dataset.region);updateFilterUI();render()});
$("#clearFilters").onclick=clearFilters;
$("#regionTrigger").onclick=()=>{const p=$("#regionPicker"),open=p.classList.toggle("open");$("#regionTrigger").setAttribute("aria-expanded",open)};
$("#search").addEventListener("input",render);
$("#searchToggle").onclick=()=>{document.body.classList.add("search-open");$("#search").focus()};
$("#searchClose").onclick=()=>document.body.classList.remove("search-open");
$("#searchClear").onclick=()=>{$("#search").value="";$("#search").focus();render()};
const filterToggle=$("#filterToggle"),filterbar=$("#filterbar");filterToggle.onclick=()=>{const open=filterbar.classList.toggle("open");filterbar.classList.toggle("collapsed",!open);filterToggle.setAttribute("aria-expanded",open);filterToggle.querySelector(".filter-caret").classList.toggle("fa-chevron-up",open);filterToggle.querySelector(".filter-caret").classList.toggle("fa-chevron-down",!open)};
updateFilterUI();render();