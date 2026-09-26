const $=s=>document.querySelector(s);
const {CATEGORY_DEFS,CATEGORY_BY_ID:byId,parseDate:parse,dayStart,escapeHtml:esc,stripEmoji,categories,displayLocation,isLongTerm}=SK;
const categoryHtml=e=>categories(e).map(c=>'<span class="category category-'+c.id+'"><i class="fas '+c.icon+'"></i>'+c.label+'</span>').join("");
const regions=[...new Set(EVENTS.flatMap(e=>String(e.region||"").split("/").map(x=>x.trim())).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"cs"));
const selectedCategories=new Set(),selectedRegions=new Set();
$("#categoryFilter").innerHTML=CATEGORY_DEFS.map(c=>'<button type="button" class="filter-chip category-'+c.id+'" data-category="'+c.id+'" aria-pressed="false"><i class="fas '+c.icon+'"></i><span>'+c.label+'</span></button>').join("");
$("#regionPicker").innerHTML=regions.map(r=>'<button type="button" class="region-option" data-region="'+esc(r)+'" aria-pressed="false"><span class="modern-check"><i class="fas fa-check"></i></span><span>'+esc(r)+'</span></button>').join("");
const todayDate=()=>dayStart(new Date());
const occursOn=(e,d)=>{const a=dayStart(parse(e.from)),b=dayStart(parse(e.to||e.from));return d>=a&&d<=b};
function updateFilterUI(){
 document.querySelectorAll("[data-category]").forEach(b=>{const on=selectedCategories.has(b.dataset.category);b.classList.toggle("active",on);b.setAttribute("aria-pressed",on)});
 document.querySelectorAll("[data-region]").forEach(b=>{const on=selectedRegions.has(b.dataset.region);b.classList.toggle("active",on);b.setAttribute("aria-pressed",on)});
 const n=selectedCategories.size+selectedRegions.size;
 const chosenCats=[...selectedCategories].map(id=>byId[id]).filter(Boolean);
 const chosenRegs=[...selectedRegions];
 const shownCats=chosenCats.slice(0,2),room=Math.max(0,3-shownCats.length),shownRegs=chosenRegs.slice(0,room);
 const hidden=n-shownCats.length-shownRegs.length;
 $("#filterCount").innerHTML=shownCats.map(c=>'<span class="filter-summary-category category-'+c.id+'"><i class="fas '+c.icon+'"></i>'+c.label+'</span>').join("")+shownRegs.map(r=>'<span class="filter-summary-region">'+esc(r)+'</span>').join("")+(hidden?'<span class="filter-summary-more">+'+hidden+'</span>':"");
 $("#clearFilters").classList.toggle("visible",n>0);
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
const LAZY_DAY_BATCH=12;
let visibleDayCount=LAZY_DAY_BATCH,lazyObserver=null;
function render(resetLazy=true){
 if(resetLazy)visibleDayCount=LAZY_DAY_BATCH;
 const q=$("#search").value.trim().toLowerCase(),today=todayDate();
 const matching=EVENTS.filter(e=>eventMatches(e,q));
 const normal=matching.filter(e=>!isLongTerm(e)&&dayStart(parse(e.from))>=today).sort((x,y)=>parse(x.from)-parse(y.from));
 const long=matching.filter(isLongTerm).filter(e=>dayStart(parse(e.to||e.from))>=today);
 const groups={};
 normal.forEach(e=>{const k=e.from;(groups[k]??={date:dayStart(parse(k)),normal:[],long:[]}).normal.push(e)});
 // Long-term events create a day section at start/end and today when currently active.
 long.forEach(e=>{const a=dayStart(parse(e.from)),b=dayStart(parse(e.to||e.from));[a,(today>=a&&today<=b?today:null),b].filter(Boolean).forEach(d=>{if(d>=today){const k=d.toLocaleDateString("cs-CZ"),g=(groups[k]??={date:d,normal:[],long:[]});if(!g.long.some(x=>x.id===e.id))g.long.push(e)}})});
 const ordered=Object.values(groups).sort((a,b)=>a.date-b.date);
 const visible=ordered.slice(0,visibleDayCount),hasMore=visibleDayCount<ordered.length;
 $("#events").innerHTML=visible.map((g,i)=>{
  const dateKey=g.date.toISOString().slice(0,10),longCount=g.long.length;
  const longToggle=longCount?'<button type="button" class="longterm-toggle" data-long-day="'+dateKey+'" aria-expanded="false"><span>Dlouhodobé · '+longCount+'</span><i class="fas fa-chevron-down"></i></button>':"";
  return '<section class="day" data-date="'+dateKey+'"><div class="date"><div class="date-label"><strong>'+g.date.toLocaleDateString("cs-CZ",{day:"numeric",month:"long",year:"numeric"})+'</strong><span>'+g.date.toLocaleDateString("cs-CZ",{weekday:"long"})+'</span></div>'+longToggle+'</div><div class="cards">'+g.normal.map(eventCard).join("")+(longCount?'<div class="longterm-cards" hidden>'+g.long.map(e=>eventCard(e,'longterm-event')).join("")+'</div>':"")+'</div></section>'
 }).join("")+(hasMore?'<div class="lazy-loader" id="lazyLoader" aria-live="polite"><i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i><span>Načítám další akce…</span></div>':"")||'<div class="empty-state"><i class="fas fa-filter"></i><strong>Žádné akce neodpovídají filtru.</strong><button type="button" id="emptyClear">Vymazat filtry</button></div>';
 document.querySelectorAll(".longterm-toggle").forEach(b=>b.onclick=()=>{const box=b.closest(".day").querySelector(".longterm-cards"),open=box.hidden;box.hidden=!open;b.setAttribute("aria-expanded",open);b.classList.toggle("open",open);b.querySelector("i").className="fas "+(open?"fa-chevron-up":"fa-chevron-down")});
 const ec=$("#emptyClear");if(ec)ec.onclick=clearFilters;
 if(lazyObserver)lazyObserver.disconnect();
 const loader=$("#lazyLoader");
 if(loader){lazyObserver=new IntersectionObserver(entries=>{if(entries.some(x=>x.isIntersecting)){lazyObserver.disconnect();visibleDayCount+=LAZY_DAY_BATCH;render(false)}},{rootMargin:"500px 0px"});lazyObserver.observe(loader)}
 document.body.classList.toggle("feed-complete",!hasMore);
}
function clearFilters(){selectedCategories.clear();selectedRegions.clear();updateFilterUI();render()}
document.querySelectorAll("[data-category]").forEach(b=>b.onclick=()=>{selectedCategories.has(b.dataset.category)?selectedCategories.delete(b.dataset.category):selectedCategories.add(b.dataset.category);updateFilterUI();render()});
document.querySelectorAll("[data-region]").forEach(b=>b.onclick=()=>{selectedRegions.has(b.dataset.region)?selectedRegions.delete(b.dataset.region):selectedRegions.add(b.dataset.region);updateFilterUI();render()});
$("#clearFilters").onclick=clearFilters;
$("#regionTrigger").onclick=()=>{const p=$("#regionPicker"),open=p.classList.toggle("open");$("#regionTrigger").setAttribute("aria-expanded",open)};
$("#search").addEventListener("input",render);
$("#searchToggle").onclick=()=>{document.body.classList.add("search-open");$("#search").focus()};
$("#searchClear").onclick=()=>{const input=$("#search");if(input.value){input.value="";input.focus();render()}else{document.body.classList.remove("search-open")}};
const filterToggle=$("#filterToggle"),filterbar=$("#filterbar");filterToggle.onclick=()=>{const open=filterbar.classList.toggle("open");filterbar.classList.toggle("collapsed",!open);filterToggle.setAttribute("aria-expanded",open);filterToggle.querySelector(".filter-caret").classList.toggle("fa-chevron-up",open);filterToggle.querySelector(".filter-caret").classList.toggle("fa-chevron-down",!open)};
updateFilterUI();render();