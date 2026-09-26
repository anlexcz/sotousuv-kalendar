const $=s=>document.querySelector(s);let period="all";
const parse=s=>{const m=String(s).match(/(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})/);return m?new Date(+m[3],+m[2]-1,+m[1]):new Date(9999,0,1)};
const fmt=s=>parse(s).toLocaleDateString("cs-CZ",{weekday:"long",day:"numeric",month:"long"});
const esc=s=>String(s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const stripEmoji=s=>String(s||"").replace(/[\p{Extended_Pictographic}\uFE0F]/gu,"").replace(/\s{2,}/g," ").trim();
const categoryDefs=[
  ["tramvaje","fa-tram",["tram"]],
  ["trolejbusy","fa-bus",["trolej"]],
  ["autobusy","fa-bus",["autobus","bus"]],
  ["metro","fa-subway",["metro"]],
  ["lodní doprava","fa-ship",["loď","lod","plav","parník"]],
  ["letectví","fa-plane",["letad","letec","leteck"]],
  ["lanové dráhy","fa-mountain",["lanov","funikul"]],
  ["silniční doprava","fa-car",["automobil","silnič","auto ","veterán"]],
  ["železnice","fa-train",["želez","vlak","motorá","úzkokole","dráha","rail"]]
];
function categories(e){
 const hay=[e.transport,e.type,e.title].join(" ").toLowerCase(),out=[];
 categoryDefs.forEach(([label,icon,keys])=>{if(keys.some(k=>hay.includes(k))&&!out.some(x=>x[0]===label))out.push([label,icon])});
 return out.length?out:[["ostatní","fa-compass"]];
}
const categoryHtml=e=>{const cats=categories(e),shown=cats.slice(0,3),more=cats.length-shown.length;return shown.map(([label,icon])=>'<span class="category"><i class="fas '+icon+'" aria-hidden="true"></i>'+esc(label)+'</span>').join('<span class="cat-sep"></span>')+(more>0?'<span class="category-more">+'+more+'</span>':"")};
const regions=[...new Set(EVENTS.flatMap(e=>(e.region||"").split("/").map(x=>x.trim())).filter(Boolean))].sort();
$("#region").innerHTML+=regions.map(x=>'<option>'+esc(x)+'</option>').join("");
function render(){
 let q=$("#search").value.toLowerCase(),r=$("#region").value,t=$("#transport").value;
 let a=EVENTS.filter(e=>{let hay=[e.title,e.city,e.region,e.organizer,e.type,e.transport].join(" ").toLowerCase(),ok=!q||hay.includes(q);ok=ok&&(!r||(e.region||"").includes(r));ok=ok&&(!t||(e.transport||"").toLowerCase().includes(t));if(period==="october")ok=ok&&parse(e.from).getMonth()===9;if(period==="weekend"){let d=parse(e.from);ok=ok&&d>=new Date(2026,8,25)&&d<=new Date(2026,8,27,23,59)}return ok}).sort((x,y)=>parse(x.from)-parse(y.from));
 $("#count").textContent=a.length+" akcí";let groups={};a.forEach(e=>(groups[e.from]??=[]).push(e));
 $("#events").innerHTML=Object.entries(groups).map(([d,es])=>'<section class="day"><div class="date"><strong>'+fmt(d)+'</strong></div><div class="cards">'+es.map(e=>'<a class="event" href="detail.html?id='+encodeURIComponent(e.id)+'"><div class="event-main"><div class="categories">'+categoryHtml(e)+'</div><h2>'+esc(stripEmoji(e.title))+'</h2><div class="location-meta">'+(e.city||e.place?'<span><i class="fas fa-map-marker-alt" aria-hidden="true"></i>'+esc(e.city||e.place)+'</span>':"")+(e.region?'<span><i class="fas fa-map" aria-hidden="true"></i>'+esc(e.region)+'</span>':"")+'</div></div><span class="arrow">›</span></a>').join("")+'</div></section>').join("")||'<p class="empty">Žádné akce neodpovídají filtru.</p>';
}
["search","region","transport"].forEach(id=>$("#"+id).addEventListener("input",render));
document.querySelectorAll("[data-period]").forEach(b=>b.onclick=()=>{document.querySelectorAll("[data-period]").forEach(x=>x.classList.remove("active"));b.classList.add("active");period=b.dataset.period;render()});render();
const filterToggle=$("#filterToggle"),filterbar=$("#filterbar");filterToggle.addEventListener("click",()=>{const open=filterbar.classList.toggle("open");filterbar.classList.toggle("collapsed",!open);filterToggle.setAttribute("aria-expanded",open);filterToggle.querySelector("span").textContent=open?"⌃":"⌄"});