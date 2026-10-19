# Šotoušův kalendář worker

Tato vrstva je provozní automatizace nad Google Sheets backendem schema_version = 2.

## Zásady

- GitHub Actions je plánovač a provozní prostředí, nikoli finální webhosting.
- Google Sheets je v testovací fázi provozní backend.
- Provozní přístup používá service account a Google Sheets API.
- ChatGPT konektor není součástí automatické zapisovací cesty.
- Každý budoucí zápis musí mít request_id, idempotenci a read-back kontrolu.
- Worker se nesmí spoléhat na čísla řádků jako na identitu.
- LLM pouze vytváří strukturovaná Pozorování; finální mutace provádí deterministický kód.

## Aktuálně implementováno

- `health`: pouze čte metadata a Nastavení a ověří přítomnost povinných listů schema v2.
- `export`: pouze čte veřejná data a vytvoří `data/events.json`.
- žádný scheduler ani automatické mutace zatím nejsou aktivní.

## GitHub Secrets

Workflow očekává:

- `CALENDAR_GOOGLE_SHEET_ID`
- `CALENDAR_GOOGLE_SERVICE_ACCOUNT_JSON`

Service account má mít přístup pouze k backendovému sešitu Šotoušova kalendáře.

## Custom hosting

`data/events.json` je transportní veřejný kontrakt, nikoli GitHub-Pages-specific formát. Po ověření lze přidat samostatný deploy krok, který stejný soubor pošle na custom hosting například přes SFTP/SSH/rsync nebo hostingové API. Web tak nemusí běžet na GitHub Pages a nemusí mít přístup k Google service accountu.

Doporučený budoucí tok:

`Google Sheets -> worker -> data/events.json -> deploy adapter -> custom hosting`

Deploy adapter musí být oddělený od sběru a resolveru. Selhání uploadu na hosting nesmí poškodit backendová data a musí být vidět jako samostatné selhání běhu.

## Další implementační kroky

1. vytvořit service account a nasdílet mu pouze backendový sešit;
2. vložit oba GitHub Secrets;
3. ručně spustit `Calendar worker` s příkazem `health`;
4. ručně otestovat `export`;
5. přidat idempotency ledger a bezpečný testovací zápis do listu Požadavky;
6. implementovat scheduler `next_check_at` a discovery;
7. až po testech zapnout cron;
8. následně přidat deploy adapter pro custom hosting.
