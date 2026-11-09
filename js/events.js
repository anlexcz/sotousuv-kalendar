(function(global){
 const displayLocation=e=>String(e.city||e.place||"").trim().split(/\s*\/\s*|\s*;\s*/).filter(Boolean).join(", ");
 const durationDays=e=>{const a=global.SK.parseDate(e.from),b=global.SK.parseDate(e.to||e.from);if(!a||!b)return 1;return Math.max(1,Math.round((global.SK.dayStart(b)-global.SK.dayStart(a))/global.SK.DAY)+1)};
 const isLongTerm=e=>durationDays(e)>7&&(String(e.type||"").toLowerCase().includes("výstava")||!e.recurring);
 global.SK=Object.assign(global.SK||{},{displayLocation,durationDays,isLongTerm});
})(window);
