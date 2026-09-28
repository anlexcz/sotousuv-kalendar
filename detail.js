const {escapeHtml:esc,stripEmoji,CATEGORY_BY_ID}=SK;
const pathId=location.pathname.match(/\/akce\/([0-9]+)\/?$/)?.[1];
const id=pathId||new URLSearchParams(location.search).get('id');
const root=document.querySelector('#detail');

const categoryTags=e=>(e.categories||[]).map(key=>{const def=CATEGORY_BY_ID[key]||CATEGORY_BY_ID.other;return '<span class="category category-'+esc(key)+'"><i class="fas '+def.icon+'" aria-hidden="true"></i>'+esc(def.label)+'</span>'}).join('');
const place=e=>[e.city,e.place].filter(Boolean).join(' · ')||e.region||'';
const dateObj=s=>new Date(s+'T00:00:00');
const fmtDate=s=>s?dateObj(s).toLocaleDateString('cs-CZ',{day:'numeric',month:'long',year:'numeric'}):'';
const fmtDM=s=>s?dateObj(s).toLocaleDateString('cs-CZ',{day:'numeric',month:'numeric'}):'';
const fmtRangeShort=d=>d.ends_on&&d.ends_on!==d.starts_on?fmtDM(d.starts_on)+'–'+fmtDM(d.ends_on):fmtDM(d.starts_on);
const dayAfter=(a,b)=>(dateObj(b)-dateObj(a))===86400000;
const monthKey=s=>s.slice(0,7);
const monthLabel=s=>dateObj(s+'-01').toLocaleDateString('cs-CZ',{month:'long',year:'numeric'});

function sortedDates(e){return [...(e.dates||[])].filter(d=>d&&d.starts_on).sort((a,b)=>a.starts_on.localeCompare(b.starts_on));}
function mergeRanges(dates){
  const out=[];
  for(const d of dates){
    const item={...d,ends_on:d.ends_on||d.starts_on,_wasRange:!!(d.ends_on&&d.ends_on!==d.starts_on)};
    const prev=out[out.length-1];
    const compatible=prev&&!prev.starts_at&&!prev.ends_at&&!item.starts_at&&!item.ends_at&&(prev._wasRange||item._wasRange);
    const touches=compatible&&(item.starts_on<=prev.ends_on||dayAfter(prev.ends_on,item.starts_on));
    if(touches){if(item.ends_on>prev.ends_on)prev.ends_on=item.ends_on;prev._wasRange=true;}else out.push(item);
  }
  return out;
}
function termText(d){
  const span=d.ends_on&&d.ends_on!==d.starts_on?fmtDate(d.starts_on)+' – '+fmtDate(d.ends_on):fmtDate(d.starts_on);
  const t=d.starts_at?(String(d.starts_at).slice(0,5)+(d.ends_at?'–'+String(d.ends_at).slice(0,5):'')):'';
  return [span,t].filter(Boolean).join(' · ');
}
function relevantTerm(dates){
  const today=new Date();today.setHours(0,0,0,0);
  return dates.find(d=>dateObj(d.ends_on||d.starts_on)>=today)||dates[0];
}
function isRange(d){return (d.ends_on||d.starts_on)!==d.starts_on;}

function groupTerms(terms){
  const groups=new Map();
  for(const t of terms){
    const key=monthKey(t.starts_on);
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(t);
  }
  return [...groups.entries()].map(([key,list])=>({key,label:monthLabel(key),list}));
}
function chipHtml(t){
  if(isRange(t))return '<span class="term-chip range-chip"><strong>'+esc(fmtRangeShort(t))+'</strong></span>';
  const d=dateObj(t.starts_on);
  const wd=d.toLocaleDateString('cs-CZ',{weekday:'short'}).replace('.','');
  return '<span class="term-chip"><strong>'+d.getDate()+'.</strong><small>'+esc(wd)+'</small></span>';
}
function monthHtml(group,index){
  const density=Math.min(10,Math.max(1,group.list.length));
  return '<section class="term-month-group" data-month-index="'+index+'" style="--month-density:'+density+'">'
    +'<h3>'+esc(group.label)+'</h3><div class="term-chip-row">'+group.list.map(chipHtml).join('')+'</div></section>';
}

function compactTermBlock(e){
  const raw=sortedDates(e);
  const terms=mergeRanges(raw);
  if(!terms.length)return '';

  if(terms.length===1){
    return '<div class="event-term compact single-date"><div class="term-label">Datum</div><div class="term-primary">'+esc(termText(terms[0]))+'</div></div>';
  }

  const first=relevantTerm(terms);
  const groups=groupTerms(terms);
  const firstMonth=monthKey(first.starts_on);
  const activeIndex=Math.max(0,groups.findIndex(g=>g.key===firstMonth));

  return '<div class="event-term compact multiple-dates">'
    +'<div class="term-label">Nejbližší datum</div><div class="term-primary">'+esc(termText(first))+'</div>'
    +'<div class="term-browser" data-active-index="'+activeIndex+'">'
    +'<button class="term-browser-nav prev" type="button" aria-label="Předchozí měsíc"><i class="fas fa-chevron-left"></i></button>'
    +'<div class="term-month-viewport"><div class="term-month-track">'+groups.map(monthHtml).join('')+'</div></div>'
    +'<button class="term-browser-nav next" type="button" aria-label="Další měsíc"><i class="fas fa-chevron-right"></i></button>'
    +'</div></div>';
}

function initTermBrowser(){
  const browser=root.querySelector('.term-browser');
  if(!browser)return;
  const track=browser.querySelector('.term-month-track');
  const groups=[...browser.querySelectorAll('.term-month-group')];
  const prev=browser.querySelector('.term-browser-nav.prev');
  const next=browser.querySelector('.term-browser-nav.next');
  let index=Math.min(groups.length-1,Math.max(0,Number(browser.dataset.activeIndex)||0));

  function mobile(){return matchMedia('(max-width:650px)').matches;}
  function update(){
    if(mobile()){
      groups.forEach((g,i)=>g.classList.toggle('active',i===index));
      track.style.transform='translateX('+(index*-100)+'%)';
      prev.disabled=index===0;
      next.disabled=index===groups.length-1;
    }else{
      groups.forEach(g=>g.classList.remove('active'));
      track.style.transform='';
      const viewport=browser.querySelector('.term-month-viewport');
      const max=Math.max(0,track.scrollWidth-viewport.clientWidth);
      const left=viewport.scrollLeft;
      prev.disabled=left<=2;
      next.disabled=left>=max-2;
    }
  }
  function scrollDesktop(dir){
    const viewport=browser.querySelector('.term-month-viewport');
    const amount=Math.max(220,Math.round(viewport.clientWidth*.72));
    viewport.scrollBy({left:dir*amount,behavior:'smooth'});
    setTimeout(update,220);
  }
  prev.addEventListener('click',()=>{if(mobile()){if(index>0){index--;update();}}else scrollDesktop(-1);});
  next.addEventListener('click',()=>{if(mobile()){if(index<groups.length-1){index++;update();}}else scrollDesktop(1);});
  browser.querySelector('.term-month-viewport').addEventListener('scroll',()=>{if(!mobile())requestAnimationFrame(update)},{passive:true});
  addEventListener('resize',update,{passive:true});
  update();
}

(function addTermStyles(){
  const style=document.createElement('style');
  style.textContent=`
    .event-detail-head>small{display:none}
    .event-term.compact{padding:14px 0 12px}
    .term-label{margin-bottom:3px;font-size:9px;line-height:1.2;font-weight:700;color:#888e91;text-transform:uppercase;letter-spacing:.045em}
    .term-primary{font-size:17px;line-height:1.28;font-weight:800;color:#303437}
    .term-browser{display:grid;grid-template-columns:28px minmax(0,1fr) 28px;align-items:stretch;gap:5px;margin-top:12px}
    .term-browser-nav{width:28px;min-height:48px;border:0;background:transparent;color:#748085;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:8px;border-radius:3px}
    .term-browser-nav:hover:not(:disabled){background:#eef7fb;color:#397e9e}
    .term-browser-nav:disabled{opacity:.18;cursor:default}
    .term-month-viewport{min-width:0;overflow-x:auto;overflow-y:hidden;scrollbar-width:none;scroll-behavior:smooth}
    .term-month-viewport::-webkit-scrollbar{display:none}
    .term-month-track{display:flex;align-items:flex-start;gap:14px;min-width:max-content;transition:transform .18s ease}
    .term-month-group{margin:0;flex:0 0 auto;width:clamp(105px,calc(80px + var(--month-density)*20px),290px)}
    .term-month-group h3{margin:0 0 6px;font-size:10px;line-height:1.2;font-weight:800;color:#72787b;text-transform:capitalize;white-space:nowrap}
    .term-chip-row{display:flex;flex-wrap:wrap;gap:5px}
    .term-chip{min-width:39px;height:34px;padding:4px 7px;border:1px solid #dfe3e5;border-radius:4px;background:#fff;display:inline-flex;flex-direction:column;align-items:center;justify-content:center;line-height:1}
    .term-chip strong{font-size:11px;font-weight:800;color:#3f4548}
    .term-chip small{margin-top:2px;font-size:7.5px;font-weight:700;color:#92979a;text-transform:uppercase}
    .term-chip.range-chip{height:30px;min-width:auto;flex-direction:row;padding:5px 8px;background:#f8fafb}
    .term-chip.range-chip strong{font-size:10px}
    @media(min-width:1100px){
      .term-month-group{width:clamp(100px,calc(72px + var(--month-density)*18px),250px)}
      .term-month-track{gap:18px}
    }
    @media(max-width:650px){
      .event-term.compact{padding:12px 0 10px}
      .term-label{font-size:8.5px;margin-bottom:2px}
      .term-primary{font-size:15.5px}
      .term-browser{grid-template-columns:28px minmax(0,1fr) 28px;gap:3px;margin-top:10px;align-items:start}
      .term-browser-nav{width:28px;min-height:68px;font-size:8px}
      .term-month-viewport{overflow:hidden}
      .term-month-track{gap:0;min-width:100%;width:100%}
      .term-month-group{width:100%;flex:0 0 100%;padding:0 2px;opacity:.25;transition:opacity .16s ease}
      .term-month-group.active{opacity:1}
      .term-month-group h3{text-align:center;font-size:10px;margin-bottom:6px}
      .term-chip-row{justify-content:center;gap:4px}
      .term-chip{min-width:36px;height:31px;padding:3px 6px}
      .term-chip strong{font-size:10.5px}
      .term-chip small{font-size:7px}
      .term-chip.range-chip{height:28px;padding:4px 7px}
    }
    @media(prefers-reduced-motion:reduce){.term-month-track{transition:none!important;scroll-behavior:auto}}
  `;
  document.head.appendChild(style);
})();

async function load(){
  if(!id){missing();return}
  try{
    const e=await SK_RUNTIME.event(id);
    if(!e||e.status==='hidden')throw 0;
    document.title=stripEmoji(e.title)+' – Šotoušův kalendář';
    const source=e.sources?.find(s=>Number(s.is_primary))?.url||e.sources?.[0]?.url||e.public_url;
    root.innerHTML='<header class="event-detail-head">'
      +((e.categories||[]).length||place(e)?'<div class="detail-meta">'+((e.categories||[]).length?'<div class="detail-categories">'+categoryTags(e)+'</div>':'')+(place(e)?'<span class="detail-place"><i class="fas fa-map-marker-alt"></i>'+esc(place(e))+'</span>':'')+'</div>':'')
      +'<h1>'+esc(stripEmoji(e.title))+'</h1></header>'
      +compactTermBlock(e)
      +(source?'<a class="official-link" href="'+esc(source)+'" target="_blank" rel="noopener"><span>Odkaz na akci</span><i class="fas fa-external-link-alt"></i></a>':'')
      +(e.description?'<section class="event-description"><h2>O akci</h2><p>'+esc(e.description)+'</p></section>':'')
      +(e.review_status!=='human_reviewed'?'<aside class="auto-note"><i class="fas fa-robot"></i><p><strong>Tady pracoval robot.</strong> Občas mu něco ujede, takže před cestou raději mrkni na odkaz na akci.</p></aside>':'');
    initTermBrowser();
  }catch{missing()}
}
function missing(){root.innerHTML='<div class="detail-missing"><h1>Akce nenalezena</h1><p>Odkaz už nemusí být platný nebo akce není dostupná.</p></div>'}
load();
