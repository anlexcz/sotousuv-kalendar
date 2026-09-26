const results=[];
function test(name,fn){try{fn();results.push({name,ok:true})}catch(error){results.push({name,ok:false,error:error.message})}}
function equal(actual,expected){if(actual!==expected)throw new Error("čekáno "+JSON.stringify(expected)+", získáno "+JSON.stringify(actual))}
function deepEqual(actual,expected){equal(JSON.stringify(actual),JSON.stringify(expected))}
const keys=dates=>dates.map(SK.dateKey);

test("parseDate přečte české datum",()=>equal(SK.dateKey(SK.parseDate("7. 10. 2026")),"2026-10-07"));
test("parseDate vrátí null pro chybějící datum",()=>equal(SK.parseDate(""),null));
test("dateKey používá YYYY-MM-DD",()=>equal(SK.dateKey(new Date(2026,8,6)),"2026-09-06"));
test("jednodenní akce má jeden occurrence",()=>deepEqual(keys(SK.occurrenceDates({from:"7. 10. 2026"})),["2026-10-07"]));
test("souvislá třídenní akce má všechny dny",()=>deepEqual(keys(SK.occurrenceDates({from:"7. 10. 2026",to:"9. 10. 2026"})),["2026-10-07","2026-10-08","2026-10-09"]));
test("opakovaná akce používá seriesDates, ne celý interval",()=>deepEqual(keys(SK.occurrenceDates({from:"1. 10. 2026",to:"31. 10. 2026",recurring:true,seriesDates:"3. 10. 2026; 17. 10. 2026"})),["2026-10-03","2026-10-17"]));
test("seriesDates umí rozsah v jednom měsíci",()=>deepEqual(keys(SK.occurrenceDates({recurring:true,seriesDates:"3.–5. 10. 2026"})),["2026-10-03","2026-10-04","2026-10-05"]));
test("durationDays počítá včetně prvního a posledního dne",()=>equal(SK.durationDays({from:"1. 10. 2026",to:"8. 10. 2026"}),8));
test("osm dní je dlouhodobá neperiodická akce",()=>equal(SK.isLongTerm({from:"1. 10. 2026",to:"8. 10. 2026",recurring:false}),true));
test("sedm dní není dlouhodobá akce",()=>equal(SK.isLongTerm({from:"1. 10. 2026",to:"7. 10. 2026",recurring:false}),false));
test("opakovaná dlouhá akce není automaticky dlouhodobá",()=>equal(SK.isLongTerm({from:"1. 10. 2026",to:"31. 10. 2026",recurring:true,type:"jízdy"}),false));
test("výstava delší než týden je dlouhodobá i při recurring",()=>equal(SK.isLongTerm({from:"1. 10. 2026",to:"31. 10. 2026",recurring:true,type:"Výstava"}),true));
test("neznámá kategorie spadne do Ostatní",()=>deepEqual(SK.categoryIds({categories:["unknown"]}),["other"]));
test("více platných kategorií zůstane zachováno",()=>deepEqual(SK.categoryIds({categories:["tram","bus"]}),["tram","bus"]));
test("displayLocation preferuje město před místem",()=>equal(SK.displayLocation({city:"Praha",place:"Vozovna"}),"Praha"));
test("displayLocation sjednotí lomítka",()=>equal(SK.displayLocation({city:"Praha / Brno"}),"Praha, Brno"));
test("escapeHtml escapuje HTML",()=>equal(SK.escapeHtml('<a href="x">&</a>'),"&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;"));
test("stripEmoji odstraní emoji z názvu",()=>equal(SK.stripEmoji("🚋 Tramvajový den"),"Tramvajový den"));

const list=document.querySelector("#results");results.forEach(r=>{const li=document.createElement("li");li.className=r.ok?"pass":"fail";li.textContent=(r.ok?"✓ ":"✗ ")+r.name+(r.ok?"":" — "+r.error);list.appendChild(li)});
const failed=results.filter(r=>!r.ok).length;const summary=document.querySelector("#summary");summary.textContent=failed?results.length+" testů, "+failed+" selhalo.":results.length+" testů, všechny prošly.";summary.className=failed?"fail":"pass";
if(failed)throw new Error(failed+" testů selhalo");
