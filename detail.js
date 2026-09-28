const {escapeHtml:esc,stripEmoji,CATEGORY_BY_ID}=SK;
const pathId=location.pathname.match(/\/akce\/([0-9]+)\/?$/)?.[1];
const id=pathId||new URLSearchParams(location.search).get('id');
const root=document.querySelector('#detail');

const categoryTags=e=>(e.categories||[]).map(key=>{const def=CATEGORY_BY_ID[key]||CATEGORY_BY_ID.other;return '<span class="category category-'+esc(key)+'"><i class="fas '+def.icon+'" aria-hidden="true"></i>'+esc(def.label)+'</span>'}).join('');
const place=e=>[e.city,e.place].filter(Boolean).join(' · ')||e.region||'';
const dateObj=s=>new Date(s+'T00:00:00');
const fmtDate=s=>s?dateObj(s).toLocaleDateString('cs-CZ',{day:'numeric',month:'long',year:'numeric'}):'';
const fmtShort=s=>s?dateObj(s).toLocaleDateString('cs-CZ',{day:'numeric',month:'short'}):'';
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
function monthKey(s){return s.slice(0,7)}
function monthLabel(s){return dateObj(s).toLocaleDateString('cs-CZ',{month:'long',year:'numeric'})}

function compactTermBlock(e){
  const terms=mergeRanges(sortedDates(e));
  if(!terms.length)return '';
  if(terms.length===1)return '<div class="event-term compact"><div class="term-primary">'+esc(termText(terms[0]))+'</div></div>';

  const first=terms[0];
  const shown=terms.slice(1,3);
  const remaining=Math.max(0,terms.length-1-shown.length);
  const shortParts=shown.map(d=>d.ends_on&&d.ends_on!==d.starts_on?fmtShort(d.starts_on)+'–'+fmtShort(d.ends_on):fmtShort(d.starts_on));
  const secondary='Další termíny: '+shortParts.join(', ')+(remaining?' + '+remaining+' dalších':'');

  const groups=new Map();
  for(const d of terms){
    const key=monthKey(d.starts_on);
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(d);
  }
  const groupHtml=[...groups.entries()].map(([key,list])=>{
    const rows=list.map(d=>'<li>'+esc(termText(d))+'</li>').join('');
    return '<details class="term-month"><summary><span>'+esc(monthLabel(key+'-01'))+'</span><small>'+list.length+'×</small></summary><ul>'+rows+'</ul></details>';
  }).join('');

  return '<div class="event-term compact">'
    +'<div class="term-primary">'+esc(termText(first))+'</div>'
    +'<div class="term-secondary">'+esc(secondary)+'</div>'
    +'<details class="term-all"><summary>Zobrazit všechny termíny <span>('+terms.length+')</span></summary><div class="term-groups">'+groupHtml+'</div></details>'
    +'</div>';
}

(function addTermStyles(){
  const style=document.createElement('style');
  style.textContent=`
    .event-term.compact{padding:16px 0 14px}
    .term-primary{font-size:17px;line-height:1.35;font-weight:800;color:#303437}
    .term-secondary{margin-top:4px;font-size:11px;line-height:1.4;font-weight:600;color:#747a7d}
    .term-all{margin-top:8px;font-size:11px;font-weight:700;color:#4d7f96}
    .term-all>summary,.term-month>summary{cursor:pointer;list-style:none;user-select:none}
    .term-all>summary::-webkit-details-marker,.term-month>summary::-webkit-details-marker{display:none}
    .term-all>summary{display:inline-flex;align-items:center;gap:4px;padding:3px 0}
    .term-all>summary:after{content:'▾';font-size:9px;margin-left:3px}
    .term-all[open]>summary:after{content:'▴'}
    .term-all>summary span{font-weight:600;color:#858b8e}
    .term-groups{margin-top:9px;border-top:1px solid #e0e2e3}
    .term-month{border-bottom:1px solid #e0e2e3;color:#3f4548}
    .term-month>summary{min-height:36px;display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:11px;font-weight:800;text-transform:capitalize}
    .term-month>summary:after{content:'+';order:3;color:#858b8e;font-size:13px;font-weight:500}
    .term-month[open]>summary:after{content:'−'}
    .term-month>summary small{margin-left:auto;font-size:9px;font-weight:700;color:#8b9093}
    .term-month ul{margin:0;padding:0 0 9px;list-style:none;display:grid;gap:4px}
    .term-month li{font-size:11px;line-height:1.35;font-weight:600;color:#60666a}
    @media(max-width:650px){
      .event-term.compact{padding:14px 0 12px}
      .term-primary{font-size:16px}
      .term-secondary{font-size:10.5px}
      .term-all{font-size:10.5px}
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
      +'<h1>'+esc(stripEmoji(e.title))+'</h1><small>#'+esc(String(e.id))+'</small></header>'
      +compactTermBlock(e)
      +(source?'<a class="official-link" href="'+esc(source)+'" target="_blank" rel="noopener"><span>Odkaz na akci</span><i class="fas fa-external-link-alt"></i></a>':'')
      +(e.description?'<section class="event-description"><h2>O akci</h2><p>'+esc(e.description)+'</p></section>':'')
      +(e.review_status!=='human_reviewed'?'<aside class="auto-note"><i class="fas fa-robot"></i><p><strong>Tady pracoval robot.</strong> Občas mu něco ujede, takže před cestou raději mrkni na odkaz na akci.</p></aside>':'');
  }catch{missing()}
}
function missing(){root.innerHTML='<div class="detail-missing"><h1>Akce nenalezena</h1><p>Odkaz už nemusí být platný nebo akce není dostupná.</p></div>'}
load();
