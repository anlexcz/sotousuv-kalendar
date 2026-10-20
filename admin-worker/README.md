# Šotoušův kalendář – prototyp webu a adminu

Worker poskytuje:

- `/` – jednoduchý přehled eventů z D1;
- `/admin` – celý admin chráněný heslem;
- 30denní přihlášení přes `HttpOnly; Secure; SameSite=Lax` session cookie;
- přehled eventů včetně času poslední automatické kontroly/aktualizace;
- přehled zdrojů včetně poslední kontroly, posledního úspěchu, `next_check_at`, HTTP stavu a počtu chyb;
- přehled posledních GitHub Actions runů;
- zobrazení job logu konkrétního runu;
- ruční `collect-batch`;
- ruční `collect-source` pro konkrétní `source_id`.

Admin sám nemění eventy a nezapíná jejich publikování.

## GitHub repository secrets potřebné pro deploy

Existující:

- `CALENDAR_CLOUDFLARE_ACCOUNT_ID`
- `CALENDAR_CLOUDFLARE_D1_DATABASE_ID`

Nové:

- `CALENDAR_CLOUDFLARE_WORKERS_API_TOKEN` – Cloudflare API token s oprávněním nasadit Worker v daném účtu;
- `CALENDAR_ADMIN_PASSWORD` – prototypové heslo; doporučená výchozí hodnota je `SotousuvKalendar!2026`;
- `CALENDAR_ADMIN_SESSION_SECRET` – dlouhý náhodný řetězec, doporučeně alespoň 32 náhodných bajtů/64 hex znaků;
- `CALENDAR_ADMIN_GITHUB_TOKEN` – fine-grained GitHub PAT omezený na repozitář `anlexcz/sotousuv-kalendar`, s repository permission **Actions: Read and write** a **Metadata: Read**.

Heslo ani tokeny se nikdy nevkládají do HTML/JavaScriptu posílaného do prohlížeče.

## Deploy

Po přidání secretů spusť ručně workflow **Deploy calendar admin**.

Workflow vytvoří `wrangler.toml` s D1 bindingem, nasadí Worker `sotousuv-kalendar-admin` a následně nastaví tři runtime secrets (`ADMIN_PASSWORD`, `ADMIN_SESSION_SECRET`, `GITHUB_TOKEN`).

## Automatické kontroly zdrojů

Workflow `Calendar worker` má cron každou hodinu v minutě 17. Scheduled run nastaví `COLLECT_DUE_ONLY=1`, takže collector neprojíždí stále celý registr, ale vybírá jen zdroje, jejichž `next_check_at` je prázdné nebo splatné.

Ruční `collect-source` ignoruje splatnost a zkontroluje zadaný konkrétní zdroj. Ani scheduled ani ruční collect cesta nevytváří eventy a nic nepublikuje.
