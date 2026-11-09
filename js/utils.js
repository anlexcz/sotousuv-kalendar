(function(global){
 const escapeHtml=s=>String(s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const stripEmoji=s=>String(s||"").replace(/[\p{Extended_Pictographic}\uFE0F]/gu,"").replace(/\s{2,}/g," ").trim();
 global.SK=Object.assign(global.SK||{},{escapeHtml,stripEmoji});
})(window);
