(function(global){
 const DAY=86400000;
 const CATEGORY_DEFS=[
  {id:"rail",label:"Železnice",icon:"fa-train",color:"#4f9b64"},
  {id:"bus",label:"Autobus",icon:"fa-bus",color:"#55add7"},
  {id:"tram",label:"Tramvaj",icon:"fa-tram",color:"#cf7180"},
  {id:"trolleybus",label:"Trolejbus",icon:"fa-bus-alt",color:"#718fbe"},
  {id:"metro",label:"Metro",icon:"fa-subway",color:"#9c70b8"},
  {id:"water",label:"Loď",icon:"fa-ship",color:"#4fa69d"},
  {id:"air",label:"Letadlo",icon:"fa-plane",color:"#8b79bd"},
  {id:"cableway",label:"Lanovka",icon:"fa-mountain",color:"#b28259"},
  {id:"other",label:"Ostatní",icon:"fa-compass",color:"#7b8084"}
 ];
 const CATEGORY_BY_ID=Object.fromEntries(CATEGORY_DEFS.map(c=>[c.id,c]));
 const parseDate=s=>{const m=String(s||"").match(/(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})/);return m?new Date(+m[3],+m[2]-1,+m[1]):null};
 const dayStart=d=>new Date(d.getFullYear(),d.getMonth(),d.getDate());
 const dateKey=d=>d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");
 const escapeHtml=s=>String(s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const stripEmoji=s=>String(s||"").replace(/[\p{Extended_Pictographic}\uFE0F]/gu,"").replace(/\s{2,}/g," ").trim();
 const categoryIds=e=>{const raw=Array.isArray(e.categories)&&e.categories.length?e.categories:(e.category?[e.category]:["other"]);const ids=raw.filter(id=>CATEGORY_BY_ID[id]);return ids.length?ids:["other"]};
 const categories=e=>categoryIds(e).map(id=>CATEGORY_BY_ID[id]);
 const displayLocation=e=>String(e.city||e.place||"").trim().split(/\s*\/\s*|\s*;\s*/).filter(Boolean).join(", ");
 const durationDays=e=>{const a=parseDate(e.from),b=parseDate(e.to||e.from);if(!a||!b)return 1;return Math.max(1,Math.round((dayStart(b)-dayStart(a))/DAY)+1)};
 const isLongTerm=e=>durationDays(e)>7&&(String(e.type||"").toLowerCase().includes("výstava")||!e.recurring);
 const occursOn=(e,d)=>{const a=dayStart(parseDate(e.from)),b=dayStart(parseDate(e.to||e.from));return d>=a&&d<=b};
 function occurrenceDates(e){
  const dates=[],add=(y,m,d)=>{const x=new Date(+y,+m-1,+d);if(!isNaN(x))dates.push(x)};
  if(e.recurring&&e.seriesDates){
   for(const raw of e.seriesDates.split(";")){
    const p=raw.trim();let m;
    if((m=p.match(/^(\d{1,2})\.\s*(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$/))){let a=new Date(+m[5],+m[2]-1,+m[1]),b=new Date(+m[5],+m[4]-1,+m[3]);for(let d=new Date(a);d<=b;d.setDate(d.getDate()+1))dates.push(new Date(d));continue}
    if((m=p.match(/^(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$/))){for(let d=+m[1];d<=+m[2];d++)add(m[4],m[3],d);continue}
    if((m=p.match(/^(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$/))){add(m[3],m[2],m[1]);continue}
    if((m=p.match(/^(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.,?\s*(\d{1,2})\.\s*(\d{4})$/))){for(let d=+m[1];d<=+m[2];d++)add(m[4],m[3],d);continue}
   }
   if(dates.length)return dates;
  }
  const a=parseDate(e.from),b=parseDate(e.to||e.from);if(!a)return dates;
  const end=b||a;for(let d=new Date(a);d<=end;d.setDate(d.getDate()+1))dates.push(new Date(d));return dates
 }
 global.SK={DAY,CATEGORY_DEFS,CATEGORY_BY_ID,parseDate,dayStart,dateKey,escapeHtml,stripEmoji,categoryIds,categories,displayLocation,durationDays,isLongTerm,occursOn,occurrenceDates};
})(window);
