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

function expandedTerms(terms){
  const groups=new Map();
  for(const t of terms){
    const key=monthKey(t.starts_on);
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(t);
  }
  return [...groups.entries()].map(([key,list])=>{
    const chips=list.map(t=>{
      if(isRange(t)) return '<span class="term-chip range-chip"><strong>'+esc(fmtRangeShort(t))+'</strong></span>';
      const d=dateObj(t.starts_on);
      const wd=d.toLocaleDateString('cs-CZ',{weekday:'short'}).replace('.','');
      return '<span class="term-chip"><strong>'+d.getDate()+'.</strong><small>'+esc(wd)+'</small></span>';
    }).join('');
    return '<section class="term-month-group"><h3>'+esc(monthLabel(key))+'</h3><div class="term-chip-row">'+chips+'</div></section>';
  }).join('');
}

function compactTermBlock(e){
  const raw=sortedDates(e);
  const terms=mergeRanges(raw);
  if(!terms.length)return '';
  const first=relevantTerm(terms);
  const firstIndex=Math.max(0,terms.indexOf(first));
  const next=terms.slice(firstIndex+1,firstIndex+4);
  const remaining=Math.max(0,terms.length-firstIndex-1-next.length);
  const secondary=next.map(fmtRangeShort).join(' · ')+(remaining?(next.length?' · ':'')+'+'+remaining:'');
  const expandable=terms.length>1;

  return '<div class="event-term compact">'
    +'<div class="term-summary-row"><div class="term-copy">'
    +'<div class="term-label">Nejbližší termín:</div>'
    +'<div class="term-primary">'+esc(termText(first))+'</div>'
    +(secondary?'<div class="term-secondary">'+esc(secondary)+'</div>':'')
    +'</div>'
    +(expandable?'<button class="term-list-toggle" type="button" aria-expanded="false"><span>Všechny termíny</span><i class="fas fa-chevron-down"></i></button>':'')
    +'</div>'
    +(expandable?'<div class="term-list-collapse"><div class="term-list-inner">'+expandedTerms(terms)+'</div></div>':'')
    +'</div>';
}

function initTermToggle(){
  const btn=root.querySelector('.term-list-toggle');
  const box=root.querySelector('.term-list-collapse');
  if(!btn||!box)return;
  btn.addEventListener('click',()=>{
    const open=box.classList.toggle('open');
    btn.classList.toggle('open',open);
    btn.setAttribute('aria-expanded',String(open));
  });
}

(function addTermStyles(){
  const style=document.createElement('style');
  style.textContent=`
    .event-detail-head>small{display:none}
    .event-term.compact{padding:14px 0 12px}
    .term-summary-row{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;min-width:0}
    .term-copy{min-width:0;flex:1 1 auto}
    .term-label{margin-bottom:3px;font-size:9px;line-height:1.2;font-weight:700;color:#888e91;text-transform:uppercase;letter-spacing:.045em}
    .term-primary{font-size:17px;line-height:1.28;font-weight:800;color:#303437}
    .term-secondary{margin-top:4px;font-size:11px;line-height:1.3;font-weight:600;color:#7a8083;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .term-list-toggle{flex:0 0 auto;min-height:31px;padding:5px 9px;border:1px solid #d5dadd;border-radius:3px;background:#fff;color:#4b7f98;display:inline-flex;align-items:center;gap:7px;font:700 10.5px 'Montserrat',sans-serif;cursor:pointer}
    .term-list-toggle:hover{background:#f8fbfc;border-color:#bdd7e3}
    .term-list-toggle i{font-size:7px;transition:transform .16s ease}
    .term-list-toggle.open i{transform:rotate(180deg)}
    .term-list-collapse{display:grid;grid-template-rows:0fr;opacity:0;transition:grid-template-rows .18s ease,opacity .14s ease}
    .term-list-collapse.open{grid-template-rows:1fr;opacity:1}
    .term-list-inner{overflow:hidden;padding-top:0;display:flex;flex-wrap:wrap;gap:10px 18px}
    .term-list-collapse.open .term-list-inner{padding-top:12px}
    .term-month-group{margin:0;min-width:0;flex:1 1 250px}
    .term-month-group h3{margin:0 0 6px;font-size:10px;line-height:1.2;font-weight:800;color:#72787b;text-transform:capitalize}
    .term-chip-row{display:flex;flex-wrap:wrap;gap:5px}
    .term-chip{min-width:39px;height:34px;padding:4px 7px;border:1px solid #dfe3e5;border-radius:4px;background:#fff;display:inline-flex;flex-direction:column;align-items:center;justify-content:center;line-height:1}
    .term-chip strong{font-size:11px;font-weight:800;color:#3f4548}
    .term-chip small{margin-top:2px;font-size:7.5px;font-weight:700;color:#92979a;text-transform:uppercase}
    .term-chip.range-chip{height:30px;min-width:auto;flex-direction:row;padding:5px 8px;background:#f8fafb}
    .term-chip.range-chip strong{font-size:10px}
    @media(max-width:650px){
      .event-term.compact{padding:12px 0 10px}
      .term-summary-row{gap:10px}
      .term-label{font-size:8.5px;margin-bottom:2px}
      .term-primary{font-size:15.5px}
      .term-secondary{font-size:10px;margin-top:3px}
      .term-list-toggle{min-height:29px;padding:5px 7px;font-size:9.5px;white-space:nowrap}
      .term-list-inner{gap:9px 12px}
      .term-month-group{flex:1 1 100%}
      .term-month-group h3{font-size:9.5px;margin-bottom:5px}
      .term-chip-row{gap:4px}
      .term-chip{min-width:36px;height:31px;padding:3px 6px}
      .term-chip strong{font-size:10.5px}
      .term-chip small{font-size:7px}
      .term-chip.range-chip{height:28px;padding:4px 7px}
    }
    @media(max-width:390px){
      .term-list-toggle span{display:none}
      .term-list-toggle{width:30px;justify-content:center;padding:0}
      .term-list-toggle:before{content:'+';font-size:15px;font-weight:600}
      .term-list-toggle i{display:none}
      .term-list-toggle.open:before{content:'−'}
    }
    @media(prefers-reduced-motion:reduce){.term-list-collapse,.term-list-toggle i{transition:none!important}}
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
    initTermToggle();
  }catch{missing()}
}
function missing(){root.innerHTML='<div class="detail-missing"><h1>Akce nenalezena</h1><p>Odkaz už nemusí být platný nebo akce není dostupná.</p></div>'}
load();
