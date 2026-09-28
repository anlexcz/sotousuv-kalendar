# Import z Google tabulky Dopravní akce

Zdroj pravdy pro první naplnění a následnou synchronizaci je nativní Google tabulka **Dopravní akce**, list **Akce**. `events.js` se do databáze neimportuje.

## Identita

Webová databáze používá jednoduché číselné `events.id` (`BIGINT AUTO_INCREMENT`), např. `48963`.

Původní hodnota ze sloupce `ID` v Google tabulce je pouze skrytý synchronizační klíč:

- `events.source_system = 'google_sheet'`
- `events.source_external_id = <původní ID z tabulky>`

Uživatel ani běžná administrace s tímto starým identifikátorem nemusí pracovat.

## Termíny – pouze explicitně

Backend neobsahuje technický pojem série, recurrence rule ani weekday bitmask.

Jedna akce může mít 1 až N explicitních termínů v `event_dates`:

- jednodenní termín: `starts_on = ends_on`,
- skutečná vícedenní akce: jeden termín s rozdílným `starts_on` a `ends_on`,
- opakovaná akce: více konkrétních řádků,
- kombinace jednotlivých dní a vícedenních bloků je povolena.

Autoritativní zdroj je sloupec **Termíny**. Staré sloupce `LEGACY – typ opakování`, `LEGACY – pravidlo opakování` a `LEGACY – ID série v kalendáři` zůstávají jen jako historický/pomocný kontext.

Google Apps Script před odesláním normalizuje dnešní české zápisy na importní formát:

```text
2026-08-01..2026-08-02; 2026-08-08..2026-08-09; 2026-08-15
```

Původní lidský zápis v tabulce může zůstat např. `1.–2., 8.–9. a 15. 8. 2026`.

## Speciální den s jinými veřejnými údaji

Pokud konkrétní termín potřebuje jiný veřejný název, popis, místo, zdroj nebo jinou podstatnou informaci, vyčlení se jako **samostatná akce** s vlastním číselným ID. Z původní akce se tento termín odebere.

Volitelně lze mezi oběma akcemi vytvořit `event_relations` (`related`, `variant`, `replacement`). Jde o redakční vazbu; veřejný web ji nemusí zobrazovat.

## Mapování hlavních polí

- Název akce → `events.title`
- Stručný popis → `events.description`
- Obec → `events.city`
- Místo → `events.place`
- Kraj / region → `events.region`
- Stát → `events.country`
- Trasa → `events.route`
- Pořadatel → `events.organizer`
- Čas od / Čas do → `events.time_start` / `events.time_end` a výchozí časy termínů
- Celodenní → `events.all_day`
- Hlavní zdroj → primární `event_sources`
- Ověřovací zdroj → další `event_sources`
- Druh dopravy → normalizované `event_categories`

## Synchronizace

Tok je:

`ChatGPT / automatický průzkum → Dopravní akce → Apps Script → /api/sync/google-sheet.php → DB → web/admin`

Pro každý řádek:

1. Najdi `(source_system='google_sheet', source_external_id=<ID>)`.
2. Pokud neexistuje, vytvoř novou akci a přiděl číselné ID.
3. Pokud existuje, porovnej normalizovaný snapshot zdroje se současným stavem.
4. Čistě automatickou akci lze aktualizovat automaticky.
5. Pokud byla akce ručně změněna nebo lidsky zkontrolována, změna ze zdroje vytvoří `event_change_proposals`.
6. Změna termínů, místa nebo stavu je `severity='important'`.
7. Redaktor návrh v `/admin` přijme nebo odmítne.

## Průběžné ověřování ChatGPT

Akce s více budoucími termíny se nesmí po prvním nálezu považovat za definitivně ověřené. Automatický sběr má původní zdroj znovu kontrolovat zejména před nejbližšími budoucími termíny.

Praktické pravidlo pro sběr:

- pokud je další termín do 7 dnů, zdroj znovu ověř;
- pokud je další termín za 8–30 dnů a poslední kontrola je starší, ověř znovu;
- při změně zdroje vždy znovu sestav **celý seznam zbývajících explicitních termínů**, ne pouze nejbližší datum;
- pokud se jeden konkrétní den začne veřejnými údaji podstatně lišit, vyčleň jej jako samostatnou akci.

Tím lze zachytit například změnu zářijových jízd zveřejněnou až v polovině srpna bez recurrence enginu na webu.
