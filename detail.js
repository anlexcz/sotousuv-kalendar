const {escapeHtml:esc,stripEmoji,categoryIds:eventCategories,displayLocation:displayPlace,CATEGORY_BY_ID}=SK;
const id=new URLSearchParams(location.search).get("id");
const e=EVENTS.find(x=>x.id===id);
const root=document.querySelector("#detail");
const categoryTags=e=>eventCategories(e).map(key=>{const def=CATEGORY_BY_ID[key]||CATEGORY_BY_ID.other;return '<span class="category category-'+esc(key)+'"><i class="fas '+def.icon+'" aria-hidden="true"></i>'+esc(def.label)+'</span>'}).join("");
const isHumanReviewed=e=>e.reviewStatus==="human_reviewed"||e.reviewed===true;

function term(e){
 const dates=e.to&&e.to!==e.from?e.from+" – "+e.to:e.from;
 const times=e.time?(e.endTime?e.time+"–"+e.endTime:e.time):"";
 return [dates,times].filter(Boolean).join(" · ");
}

if(!e){
 root.innerHTML='<div class="detail-missing"><h1>Akce nenalezena</h1><p>Odkaz už nemusí být platný nebo akce není v aktuálních datech.</p></div>';
}else{
 document.title=stripEmoji(e.title)+" – Šotoušův kalendář";
 root.innerHTML=
  '<header class="event-detail-head">'+
   (eventCategories(e).length||displayPlace(e)?'<div class="detail-meta">'+(eventCategories(e).length?'<div class="detail-categories">'+categoryTags(e)+'</div>':"")+(displayPlace(e)?'<span class="detail-place"><i class="fas fa-map-marker-alt" aria-hidden="true"></i>'+esc(displayPlace(e))+'</span>':"")+'</div>':"")+
   '<h1>'+esc(stripEmoji(e.title))+'</h1>'+
  '</header>'+
  '<div class="event-term">'+esc(term(e))+'</div>'+
  (e.source?'<a class="official-link" href="'+esc(e.source)+'" target="_blank" rel="noopener"><span>Odkaz na akci</span><i class="fas fa-external-link-alt" aria-hidden="true"></i></a>':"")+
  (e.description?'<section class="event-description"><h2>O akci</h2><p>'+esc(e.description)+'</p></section>':"")+
  (!isHumanReviewed(e)?'<aside class="auto-note"><i class="fas fa-robot" aria-hidden="true"></i><p><strong>Tady pracoval robot.</strong> Občas mu něco ujede, takže před cestou raději mrkni na odkaz na akci.</p></aside>':"");
}
