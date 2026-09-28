const {escapeHtml:esc,stripEmoji,CATEGORY_BY_ID}=SK;
const pathId=location.pathname.match(/\/akce\/([0-9]+)\/?$/)?.[1];
const id=pathId||new URLSearchParams(location.search).get('id');
const root=document.querySelector('#detail');

const categoryTags=e=>(e.categories||[]).map(key=>{const def=CATEGORY_BY_ID[key]||CATEGORY_BY_ID.other;return '<span class="category category-'+esc(key)+'"><i class="fas '+def.icon+'" aria-hidden="true"></i>'+esc(def.label)+'</span>'}).join('');
const place=e=>[e.city,e.place].filter(Boolean).join(' · ')||e.region||'';
const dateObj=s=>new Date(s+'T00:00:00');
const iso=d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
const fmtDate=s=>s?dateObj(s).toLocaleDateString('cs-CZ',{day:'numeric',month:'long',year:'numeric'}):'';
const fmtDM=s=>s?dateObj(s).toLocaleDateString('cs-CZ',{day:'numeric',month:'numeric'}):'';
const dayAfter=(a,b)=>(dateObj(b)-dateObj(a))===86400000;

function sortedDates(e){
  return [...(e.dates||[])].filter(d=>d&&d.starts_on).sort((a,b)=>a.starts_on.localeCompare(b.starts_on));
}
function mergeRanges(dates){
  const out=[];
  for(const d of dates){
    const item={...d,ends_on:d.ends_on||d.starts_on,_wasRange:!!(d.ends_on&&d.ends_on!==d.starts_on)};
    const prev=out[out.length-1];
    const compatible=prev&&!prev.starts_at&&!prev.ends_at&&!item.starts_at&&!item.ends_at&&(prev._wasRange||item._wasRange);
    const touches=compatible&&(item.starts_on<=prev.ends_on||dayAfter(prev.ends_on,item.starts_on));
    if(touches){
      if(item.ends_on>prev.ends_on)prev.ends_on=item.ends_on;
      prev._wasRange=true;
    }else out.push(item);
  }
  return out;
}
function termText(d){
  const span=d.ends_on&&d.ends_on!==d.starts_on?fmtDate(d.starts_on)+' – '+fmtDate(d.ends_on):fmtDate(d.starts_on);
  const t=d.starts_at?(String(d.starts_at).slice(0,5)+(d.ends_at?'–'+String(d.ends_at).slice(0,5):'')):'';
  return [span,t].filter(Boolean).join(' · ');
}
function monthStart(s){const d=dateObj(s);return new Date(d.getFullYear(),d.getMonth(),1)}
function monthIndex(d){return d.getFullYear()*12+d.getMonth()}
function sameMonth(a,b){return a.getFullYear()===b.getFullYear()&&a.getMonth()===b.getMonth()}
function addMonth(d,n){return new Date(d.getFullYear(),d.getMonth()+n,1)}
function monthTitle(d){return d.toLocaleDateString('cs-CZ',{month:'long',year:'numeric'})}

function eventDaySet(dates){
  const set=new Set();
  for(const t of dates){
    let d=dateObj(t.starts_on),end=dateObj(t.ends_on||t.starts_on),guard=0;
    while(d<=end&&guard<740){set.add(iso(d));d=new Date(d.getFullYear(),d.getMonth(),d.getDate()+1);guard++}
  }
  return set;
}
function relevantTerm(dates){
  const today=iso(new Date());
  return dates.find(d=>(d.ends_on||d.starts_on)>=today)||dates[0];
}

function compactTermBlock(e){
  const raw=sortedDates(e);
  const terms=mergeRanges(raw);
  if(!terms.length)return '';
  const first=relevantTerm(terms);
  const firstIndex=Math.max(0,terms.indexOf(first));
  const next=terms.slice(firstIndex+1,firstIndex+4);
  const remaining=Math.max(0,terms.length-firstIndex-1-next.length);
  const secondary=next.map(d=>fmtDM(d.starts_on)).join(' · ')+(remaining?(next.length?' · ':'')+'+'+remaining:'');
  const calendarNeeded=raw.length>1||((raw[0].ends_on||raw[0].starts_on)!==raw[0].starts_on);
  return '<div class="event-term compact">'
    +'<div class="term-primary">'+esc(termText(first))+'</div>'
    +(secondary?'<div class="term-secondary">'+esc(secondary)+'</div>':'')
    +(calendarNeeded?'<button class="term-calendar-toggle" type="button" aria-expanded="false"><i class="far fa-calendar-alt"></i><span>Všechny termíny</span><i class="fas fa-chevron-down term-toggle-chevron"></i></button><div class="term-calendar-collapse"><div class="term-calendar-inner"><div class="mini-calendar" aria-label="Kalendář termínů"></div></div></div>':'')
    +'</div>';
}

function initCalendar(e){
  const box=root.querySelector('.mini-calendar');
  const toggle=root.querySelector('.term-calendar-toggle');
  const collapse=root.querySelector('.term-calendar-collapse');
  if(!box||!toggle||!collapse)return;
  const dates=sortedDates(e);
  const marked=eventDaySet(dates);
  const firstDate=dateObj(dates[0].starts_on);
  const lastDate=dateObj(dates.reduce((m,d)=>(d.ends_on||d.starts_on)>m?(d.ends_on||d.starts_on):m,dates[0].starts_on));
  const active=relevantTerm(dates);
  let current=monthStart(active.starts_on);
  let direction=1;

  function render(dir=0){
    const old=box.querySelector('.mini-calendar-view');
    const first=new Date(current.getFullYear(),current.getMonth(),1);
    const daysInMonth=new Date(current.getFullYear(),current.getMonth()+1,0).getDate();
    const offset=(first.getDay()+6)%7;
    const today=iso(new Date());
    let cells='';
    for(let i=0;i<offset;i++)cells+='<span class="cal-day cal-empty"></span>';
    for(let day=1;day<=daysInMonth;day++){
      const d=new Date(current.getFullYear(),current.getMonth(),day);
      const key=iso(d),hit=marked.has(key),isToday=key===today;
      cells+='<span class="cal-day'+(hit?' has-event':'')+(isToday?' is-today':'')+'"><span>'+day+'</span></span>';
    }
    const canPrev=monthIndex(current)>monthIndex(monthStart(iso(firstDate)));
    const canNext=monthIndex(current)<monthIndex(monthStart(iso(lastDate)));
    const html='<div class="mini-calendar-view'+(dir?' incoming '+(dir>0?'from-right':'from-left'):'')+'">'
      +'<div class="cal-head"><button class="cal-nav prev" type="button" '+(canPrev?'':'disabled')+' aria-label="Předchozí měsíc"><i class="fas fa-chevron-left"></i></button><strong>'+esc(monthTitle(current))+'</strong><button class="cal-nav next" type="button" '+(canNext?'':'disabled')+' aria-label="Další měsíc"><i class="fas fa-chevron-right"></i></button></div>'
      +'<div class="cal-weekdays"><span>Po</span><span>Út</span><span>St</span><span>Čt</span><span>Pá</span><span>So</span><span>Ne</span></div>'
      +'<div class="cal-grid">'+cells+'</div></div>';
    if(old&&dir){
      const wrap=document.createElement('div');wrap.innerHTML=html;const next=wrap.firstChild;
      box.appendChild(next);
      requestAnimationFrame(()=>{old.classList.add(dir>0?'out-left':'out-right');next.classList.remove('from-right','from-left');next.classList.add('settled')});
      setTimeout(()=>old.remove(),190);
    }else box.innerHTML=html;
    const view=box.querySelector('.mini-calendar-view:last-child');
    view?.querySelector('.prev')?.addEventListener('click',()=>{if(canPrev){direction=-1;current=addMonth(current,-1);render(direction)}});
    view?.querySelector('.next')?.addEventListener('click',()=>{if(canNext){direction=1;current=addMonth(current,1);render(direction)}});
  }

  render();
  toggle.addEventListener('click',()=>{
    const open=collapse.classList.toggle('open');
    toggle.setAttribute('aria-expanded',String(open));
    toggle.classList.toggle('open',open);
  });
}

(function addTermStyles(){
  const style=document.createElement('style');
  style.textContent=`
    .event-detail-head>small{display:none}
    .event-term.compact{padding:16px 0 13px}
    .term-primary{font-size:17px;line-height:1.3;font-weight:800;color:#303437}
    .term-secondary{margin-top:4px;font-size:11px;line-height:1.35;font-weight:600;color:#7a8083;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .term-calendar-toggle{margin-top:9px;min-height:30px;padding:5px 8px;border:1px solid #d5dadd;border-radius:3px;background:#fff;color:#4b7f98;display:inline-flex;align-items:center;gap:7px;font:700 10.5px 'Montserrat',sans-serif;cursor:pointer}
    .term-calendar-toggle:hover{background:#f8fbfc;border-color:#bdd7e3}
    .term-calendar-toggle .term-toggle-chevron{font-size:7px;margin-left:2px;transition:transform .16s ease}
    .term-calendar-toggle.open .term-toggle-chevron{transform:rotate(180deg)}
    .term-calendar-collapse{display:grid;grid-template-rows:0fr;opacity:0;transition:grid-template-rows .18s ease,opacity .14s ease}
    .term-calendar-collapse.open{grid-template-rows:1fr;opacity:1}
    .term-calendar-inner{overflow:hidden}
    .mini-calendar{position:relative;width:min(100%,390px);min-height:0;margin-top:10px;overflow:hidden;border:1px solid #dfe2e4;border-radius:4px;background:#fff}
    .mini-calendar-view{padding:10px 11px 11px;transition:transform .18s ease,opacity .18s ease}
    .mini-calendar-view.incoming.from-right{position:absolute;inset:0;transform:translateX(14px);opacity:0}
    .mini-calendar-view.incoming.from-left{position:absolute;inset:0;transform:translateX(-14px);opacity:0}
    .mini-calendar-view.settled{position:relative;transform:translateX(0);opacity:1}
    .mini-calendar-view.out-left{position:absolute;inset:0;transform:translateX(-14px);opacity:0}
    .mini-calendar-view.out-right{position:absolute;inset:0;transform:translateX(14px);opacity:0}
    .cal-head{height:30px;display:grid;grid-template-columns:30px 1fr 30px;align-items:center;margin-bottom:5px}
    .cal-head strong{text-align:center;text-transform:capitalize;font-size:11px;font-weight:800;color:#444a4d}
    .cal-nav{width:28px;height:28px;border:0;border-radius:50%;background:transparent;color:#6d7376;cursor:pointer;font-size:9px}
    .cal-nav:hover:not(:disabled){background:#eef7fb;color:#397e9e}
    .cal-nav:disabled{opacity:.22;cursor:default}
    .cal-weekdays,.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);text-align:center}
    .cal-weekdays{margin-bottom:2px;color:#92979a;font-size:8px;font-weight:700;text-transform:uppercase}
    .cal-weekdays span{height:21px;display:flex;align-items:center;justify-content:center}
    .cal-day{aspect-ratio:1;min-width:0;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:600;color:#5e6467}
    .cal-day>span{width:29px;height:29px;display:flex;align-items:center;justify-content:center;border-radius:50%;transition:transform .12s ease,background .12s ease}
    .cal-day.has-event>span{background:var(--accent);color:#243b46;font-weight:800}
    .cal-day.has-event:hover>span{transform:scale(1.06)}
    .cal-day.is-today>span{box-shadow:inset 0 0 0 1.5px #6f777b}
    .cal-day.cal-empty{visibility:hidden}
    @media(max-width:650px){
      .event-term.compact{padding:13px 0 12px}
      .term-primary{font-size:16px}
      .term-secondary{font-size:10.5px}
      .term-calendar-toggle{margin-top:8px;min-height:29px;font-size:10px}
      .mini-calendar{width:100%;max-width:360px}
      .mini-calendar-view{padding:9px 8px 10px}
      .cal-day{font-size:10px}
      .cal-day>span{width:min(30px,8vw);height:min(30px,8vw)}
    }
    @media(prefers-reduced-motion:reduce){
      .term-calendar-collapse,.term-calendar-toggle .term-toggle-chevron,.mini-calendar-view{transition:none!important}
    }
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
    initCalendar(e);
  }catch{missing()}
}
function missing(){root.innerHTML='<div class="detail-missing"><h1>Akce nenalezena</h1><p>Odkaz už nemusí být platný nebo akce není dostupná.</p></div>'}
load();
