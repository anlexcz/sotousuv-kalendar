/*
 * Šotoušův kalendář – synchronizace listu Akce do webové DB.
 * Vlož do Apps Script projektu tabulky Dopravní akce.
 * Script Properties:
 *   SK_SYNC_URL   = https://domena.cz/api/sync/google-sheet.php
 *   SK_SYNC_TOKEN = stejný dlouhý secret jako SK_SHEET_SYNC_TOKEN na webu
 */
function syncSotousuvKalendar() {
  const props = PropertiesService.getScriptProperties();
  const url = props.getProperty('SK_SYNC_URL');
  const token = props.getProperty('SK_SYNC_TOKEN');
  if (!url || !token) throw new Error('Chybí SK_SYNC_URL nebo SK_SYNC_TOKEN v Script Properties.');

  const sh = SpreadsheetApp.getActive().getSheetByName('Akce');
  const values = sh.getDataRange().getValues();
  if (values.length < 2) return;
  const headers = values[0].map(String);
  const rows = values.slice(1).filter(r => String(r[0] || '').trim() && String(r[1] || '').trim()).map(r => {
    const o = {}; headers.forEach((h, i) => o[h] = serializeCell_(r[i]));
    o['Termíny'] = normalizeTerms_(String(o['Termíny'] || o['Termíny série'] || ''), o['Datum od'], o['Datum do']);
    return o;
  });

  const chunkSize = 150;
  const summary = {created:0, updated:0, proposals:0, skipped:0, warnings:[]};
  for (let i=0; i<rows.length; i+=chunkSize) {
    const res = UrlFetchApp.fetch(url, {
      method:'post', contentType:'application/json',
      headers:{'X-Sync-Token':token},
      payload:JSON.stringify({rows:rows.slice(i,i+chunkSize)}), muteHttpExceptions:true
    });
    if (res.getResponseCode() >= 300) throw new Error('Sync HTTP '+res.getResponseCode()+': '+res.getContentText());
    const data = JSON.parse(res.getContentText());
    ['created','updated','proposals','skipped'].forEach(k => summary[k] += Number(data[k]||0));
    summary.warnings.push(...(data.warnings||[]));
  }
  console.log(JSON.stringify(summary));
  return summary;
}

function serializeCell_(v) {
  if (v instanceof Date) return Utilities.formatDate(v, 'Europe/Prague', 'yyyy-MM-dd');
  return v === null || v === undefined ? '' : String(v).trim();
}
function pad2_(n){ return ('0'+Number(n)).slice(-2); }
function iso_(y,m,d){ return y+'-'+pad2_(m)+'-'+pad2_(d); }

// Převádí dnešní lidský český zápis na jediný importní formát:
// YYYY-MM-DD; YYYY-MM-DD..YYYY-MM-DD
function normalizeTerms_(raw, fallbackFrom, fallbackTo) {
  raw = String(raw||'').trim();
  if (!raw) return fallbackFrom ? String(fallbackFrom)+(fallbackTo && fallbackTo!==fallbackFrom ? '..'+String(fallbackTo) : '') : '';
  if (/^\d{4}-\d{2}-\d{2}(?:\.\.\d{4}-\d{2}-\d{2})?(?:\s*;\s*\d{4}-\d{2}-\d{2}(?:\.\.\d{4}-\d{2}-\d{2})?)*$/.test(raw)) return raw;
  const out=[];
  raw.replace(/[–—]/g,'-').split(';').map(s=>s.trim()).filter(Boolean).forEach(seg=>{
    let m;
    // 31. 7.-2. 8. 2026
    if ((m=seg.match(/^(\d{1,2})\.\s*(\d{1,2})\.\s*-\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$/))) {
      out.push(iso_(m[5],m[2],m[1])+'..'+iso_(m[5],m[4],m[3])); return;
    }
    // 1. 8. 2026
    if ((m=seg.match(/^(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$/))) { out.push(iso_(m[3],m[2],m[1])); return; }
    // vše se společným měsícem/rokem: 1.-2., 8.-9., 15. a 22. 8. 2026
    const tail=seg.match(/(\d{1,2})\.\s*(\d{4})$/);
    if (tail) {
      const month=tail[1],year=tail[2],prefix=seg.slice(0,tail.index).replace(/\s+a\s+/g,', ');
      const rx=/(\d{1,2})\.\s*(?:-\s*(\d{1,2})\.)?/g; let x;
      while((x=rx.exec(prefix))){ const a=iso_(year,month,x[1]); out.push(x[2]?a+'..'+iso_(year,month,x[2]):a); }
    }
  });
  if (!out.length && fallbackFrom) out.push(String(fallbackFrom)+(fallbackTo && fallbackTo!==fallbackFrom?'..'+String(fallbackTo):''));
  return [...new Set(out)].join('; ');
}

// Volitelně lze spouštět např. každou hodinu přes Apps Script trigger.
function installHourlySyncTrigger() {
  ScriptApp.getProjectTriggers().filter(t=>t.getHandlerFunction()==='syncSotousuvKalendar').forEach(t=>ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('syncSotousuvKalendar').timeBased().everyHours(1).create();
}
