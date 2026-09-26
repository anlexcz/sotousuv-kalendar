(function(){
 const body=document.body;
 const page=body.dataset.page||"events";
 const search=page==="events"?'<button class="header-search-toggle" id="searchToggle" aria-label="Hledat"><i class="fas fa-search"></i></button><div class="header-search" id="headerSearch"><input id="search" type="search" placeholder="Hledat akci nebo místo…" autocomplete="off"><button id="searchClear" aria-label="Smazat hledání"><i class="fas fa-times"></i></button></div>':"";
 const nav='<nav class="main-nav"><a href="index.html">Akce</a><a href="calendar.html">Kalendář</a><a href="add.html">Přidat akci</a><a href="about.html">O projektu</a></nav>';
 const header='<header class="topbar"><div class="brand"><a class="brand-home" href="index.html"><img src="assets/metrobus-symbol.svg" alt=""><span class="brand-copy"><span>ŠOTOUŠŮV KALENDÁŘ</span></span></a><a class="brand-metrobus" href="https://metrobus.cz/" target="_blank" rel="noopener">METROBUS</a></div>'+search+nav+'</header>';
 const footer='<footer class="site-footer'+(page==="events"?" feed-footer"+(body.classList.contains("feed-complete")?" feed-footer-ready":""):"")+'"><div class="footer-fun">Konečná! Prosíme, vystupte.</div><div class="footer-brand"><a href="https://metrobus.cz/" target="_blank" rel="noopener">Metrobus</a> · <span class="footer-year">2026</span></div><div class="footer-links"><a href="about.html#kontakt">Kontakt</a><a href="admin.html">Administrace</a></div></footer>';
 const mobile='<nav class="mobile-nav" aria-label="Hlavní navigace"><a href="index.html" data-nav="events"><i class="fas fa-list" aria-hidden="true"></i><span>Akce</span></a><a href="calendar.html" data-nav="calendar"><i class="fas fa-calendar-alt" aria-hidden="true"></i><span>Kalendář</span></a><a href="add.html" data-nav="add"><i class="fas fa-plus-circle" aria-hidden="true"></i><span>Přidat</span></a><a href="about.html" data-nav="about"><i class="fas fa-info-circle" aria-hidden="true"></i><span>O projektu</span></a></nav>';
 const top=document.querySelector('[data-layout="header"]'),bottom=document.querySelector('[data-layout="footer"]');
 if(top)top.outerHTML=header;
 if(bottom)bottom.outerHTML=footer+mobile;
 document.querySelectorAll('.main-nav a,.mobile-nav a').forEach(a=>{
  const target=a.dataset.nav||({index:"events",calendar:"calendar",add:"add",about:"about"}[a.getAttribute("href")?.replace(".html","")]||"");
  const active=target===page||(page==="detail"&&target==="events");
  if(active){a.classList.add("active");a.setAttribute("aria-current","page")}
 });
})();
