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
    +'<div class="term-summary-row"><div class="term-copy">'
    +'<div class="term-label">Nejbližší termín:</div>'
    +'<div class="term-primary">'+esc(termText(first))+'</div>'
    +(secondary?'<div class="term-secondary">'+esc(secondary)+'</div>':'')
    +'</div>'
    +(calendarNeeded?'<button class="term-calendar-toggle" type="button" aria-expanded="false"><i class="far fa-calendar-alt"></i><span>Všechny termíny</span><i class="fas fa-chevron-down term-toggle-chevron"></i></button>':'')
    +'</div>'
    +(calendarNeeded?'<div class="term-calendar-collapse"><div class="term-calendar-inner"><div class="mini-calendar" aria-label="Kalendář termínů"></div></div></div>':'')
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
      setTimeout(()=>old.remove(),175);
    }else box.innerHTML=html;
    const view=box.querySelector('.mini-calendar-view:last-child');
    view?.querySelector('.prev')?.addEventListener('click',()=>{if(canPrev){current=addMonth(current,-1);render(-1)}});
    view?.querySelector('.next')?.addEventListener('click',()=>{if(canNext){current=addMonth(current,1);render(1)}});
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
    .event-term.compact{position:relative;padding:15px 0 13px}
    .term-summary-row{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;min-width:0}
    .term-copy{min-width:0;flex:1 1 auto}
    .term-label{margin-bottom:3px;font-size:9px;line-height:1.2;font-weight:700;color:#888e91;text-transform:uppercase;letter-spacing:.045em}
    .term-primary{font-size:17px;line-height:1.28;font-weight:800;color:#303437}
    .term-secondary{margin-top:4px;font-size:11px;line-height:1.3;font-weight:600;color:#7a8083;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .term-calendar-toggle{flex:0 0 auto;margin:0 0 1px;min-height:31px;padding:5px 9px;border:1px solid #d5dadd;border-radius:3px;background:#fff;color:#4b7f98;display:inline-flex;align-items:center;gap:7px;font:700 10.5px 'Montserrat',sans-serif;cursor:pointer}
    .term-calendar-toggle:hover{background:#f8fbfc;border-color:#bdd7e3}
    .term-calendar-toggle .term-toggle-chevron{font-size:7px;margin-left:2px;transition:transform .15s ease}
    .term-calendar-toggle.open .term-toggle-chevron{transform:rotate(180deg)}
    .term-calendar-collapse{position:absolute;right:0;top:calc(100% - 4px);z-index:12;width:320px;pointer-events:none;opacity:0;transform:translateY(-5px) scale(.985);transform-origin:top right;transition:opacity .15s ease,transform .17s ease}
    .term-calendar-collapse.open{pointer-events:auto;opacity:1;transform:translateY(0) scale(1)}
    .term-calendar-inner{overflow:hidden;border-radius:5px;box-shadow:0 10px 30px rgba(34,42,46,.14),0 2px 7px rgba(34,42,46,.08)}
    .mini-calendar{position:relative;width:100%;overflow:hidden;border:1px solid #dfe2e4;border-radius:5px;background:#fff}
    .mini-calendar-view{padding:8px 9px 9px;transition:transform .17s ease,opacity .17s ease;background:#fff}
    .mini-calendar-view.incoming.from-right{position:absolute;inset:0;transform:translateX(12px);opacity:0}
    .mini-calendar-view.incoming.from-left{position:absolute;inset:0;transform:translateX(-12px);opacity:0}
    .mini-calendar-view.settled{position:relative;transform:translateX(0);opacity:1}
    .mini-calendar-view.out-left{position:absolute;inset:0;transform:translateX(-12px);opacity:0}
    .mini-calendar-view.out-right{position:absolute;inset:0;transform:translateX(12px);opacity:0}
    .cal-head{height:28px;display:grid;grid-template-columns:28px 1fr 28px;align-items:center;margin-bottom:3px}
    .cal-head strong{text-align:center;text-transform:capitalize;font-size:10.5px;font-weight:800;color:#444a4d}
    .cal-nav{width:26px;height:26px;border:0;border-radius:50%;background:transparent;color:#6d7376;cursor:pointer;font-size:8px}
    .cal-nav:hover:not(:disabled){background:#eef7fb;color:#397e9e}
    .cal-nav:disabled{opacity:.2;cursor:default}
    .cal-weekdays,.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);text-align:center}
    .cal-weekdays{margin-bottom:1px;color:#92979a;font-size:7.5px;font-weight:700;text-transform:uppercase}
    .cal-weekdays span{height:18px;display:flex;align-items:center;justify-content:center}
    .cal-day{height:31px;min-width:0;display:flex;align-items:center;justify-content:center;font-size:9.5px;font-weight:600;color:#5e6467}
    .cal-day>span{width:25px;height:25px;display:flex;align-items:center;justify-content:center;border-radius:50%;transition:transform .12s ease,background .12s ease}
    .cal-day.has-event>span{background:var(--accent);color:#243b46;font-weight:800}
    .cal-day.has-event:hover>span{transform:scale(1.06)}
    .cal-day.is-today>span{box-shadow:inset 0 0 0 1.4px #6f777b}
    .cal-day.cal-empty{visibility:hidden}
    @media(max-width:650px){
      .event-term.compact{padding:12px 0 11px}
      .term-summary-row{gap:10px;align-items:flex-end}
      .term-label{font-size:8.5px;margin-bottom:2px}
      .term-primary{font-size:15.5px}
      .term-secondary{font-size:10px;margin-top:3px}
      .term-calendar-toggle{min-height:29px;padding:5px 7px;gap:6px;font-size:9.5px;white-space:nowrap}
      .term-calendar-toggle .term-toggle-chevron{display:none}
      .term-calendar-collapse{position:static;width:100%;display:grid;grid-template-rows:0fr;opacity:0;transform:none;pointer-events:auto;transition:grid-template-rows .17s ease,opacity .13s ease}
      .term-calendar-collapse.open{grid-template-rows:1fr;opacity:1}
      .term-calendar-inner{overflow:hidden;box-shadow:none;border-radius:4px}
      .mini-calendar{margin-top:8px;width:100%;border-radius:4px}
      .mini-calendar-view{padding:6px 6px 7px}
      .cal-head{height:26px;margin-bottom:1px;grid-template-columns:26px 1fr 26px}
      .cal-head strong{font-size:10px}
      .cal-nav{width:24px;height:24px}
      .cal-weekdays span{height:16px}
      .cal-day{height:28px;font-size:9.5px}
      .cal-day>span{width:24px;height:24px}
    }
    @media(max-width:390px){
      .term-summary-row{gap:7px}
      .term-calendar-toggle span{display:none}
      .term-calendar-toggle{width:30px;justify-content:center;padding:0}
      .term-calendar-toggle i:first-child{font-size:11px}
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
