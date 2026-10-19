# Šotoušův kalendář worker

Tato vrstva je provozní automatizace Šotoušova kalendáře.

## Aktuální architektura

- **Cloudflare D1 je kanonický provozní source of truth.**
- **Google Sheets je redakční a kontrolní rozhraní**, nikoli databáze každého Pozorování a logu.
- GitHub Actions je plánovač a provozní dohled, nikoli finální webhosting.
- Python worker obsahuje deterministickou doménovou logiku.
- Veřejný web dostává stabilní export/API kontrakt nezávislý na GitHub Pages.
- Custom hosting bude řešen samostatným deploy adapterem.

Doporučený tok:

`zdroje -> worker -> D1 -> resolver -> D1 výsledný stav -> Sheets redakce + data/events.json -> deploy adapter -> custom hosting`

## Databáze

První D1 migrace je v `migrations/0001_initial.sql`.

Obsahuje zejména:

- `events`, `event_auto`
- `terms`, `term_auto`
- `sources`, `event_sources`
- `observations`, `findings`
- `overrides`, `history`, `alerts`
- `runs`, `requests`, `settings`

Google Sheets schema_version = 2 zůstává kompatibilní prototyp/redakční projekce stejného doménového modelu.

## Spolehlivost

- Každá budoucí doménová mutace má stabilní `request_id`.
- `requests` slouží jako idempotency ledger.
- Akce a Termíny používají `row_version` pro optimistic locking.
- Číslo řádku v Google Sheets nikdy není identita.
- LLM nikdy samo neprovádí finální databázovou mutaci.
- Selhání synchronizace do Sheets nebo deploye nesmí poškodit kanonický stav v D1.

## Extrakční pořadí

1. API / RSS / iCalendar / WordPress REST
2. deterministický parser strukturovaných dat nebo HTML
3. vlastní textová extrakce
4. volitelný externí reader jako fallback
5. LLM interpretace jako poslední krok

LLM provider je vyměnitelný. První preferovanou variantou může být Gemini Flash; OpenAI zůstává možný fallback.

## Aktuálně implementováno

- `d1.py`: minimální D1 REST adapter a guardrail pro idempotentní requesty
- `migrations/0001_initial.sql`: první SQL návrh schema_version = 2
- `health`: kontrola D1 schema_version a volitelně dostupnosti redakčního Sheetu
- `export`: vytváří `data/events.json` z kanonických dat v D1
- workflow je **pouze ruční**, bez cronu
- žádný crawler, resolver, Sheets write-back ani produkční mutace zatím nejsou aktivní

## GitHub Secrets pro D1

- `CALENDAR_CLOUDFLARE_ACCOUNT_ID`
- `CALENDAR_CLOUDFLARE_D1_DATABASE_ID`
- `CALENDAR_CLOUDFLARE_API_TOKEN`

API token má mít jen potřebná oprávnění k D1.

## Volitelné GitHub Secrets pro redakční Google Sheets

- `CALENDAR_GOOGLE_SHEET_ID`
- `CALENDAR_GOOGLE_SERVICE_ACCOUNT_JSON`

Service account má mít přístup pouze k redakčnímu sešitu Šotoušova kalendáře.

## Custom hosting

`data/events.json` je veřejný transportní kontrakt, ne GitHub-Pages-specific formát. Deploy adapter bude samostatná vrstva, která může stejný export poslat například přes SFTP/SSH/rsync nebo hostingové API.

Selhání deploye se smí bezpečně opakovat a nesmí měnit/rollbackovat platná data v D1.

## Další kroky

1. vytvořit prázdnou Cloudflare D1 databázi;
2. aplikovat a zkontrolovat `migrations/0001_initial.sql` nejprve v testovací databázi;
3. přidat tři D1 secrets do GitHubu;
4. ručně spustit `Calendar worker -> health`;
5. přidat první repository operace a testy idempotence/transakcí;
6. vytvořit Google service account a implementovat D1 <-> Sheets redakční sync;
7. otestovat export z D1 na syntetických datech;
8. implementovat fetch/scheduler/discovery;
9. přidat provider-agnostickou LLM vrstvu;
10. přidat deploy adapter pro custom hosting;
11. až po testech a výslovném schválení přidat cron a produkční mutace.
