# Import z Google tabulky Dopravní akce

Zdroj pravdy pro první naplnění a následnou synchronizaci je nativní Google tabulka **Dopravní akce**, list **Akce**.

`events.js` se do databáze neimportuje.

## Identita

Webová databáze používá krátké číselné `events.id` (`BIGINT AUTO_INCREMENT`).

Původní hodnota ze sloupce `ID` v Google tabulce se ukládá pouze do:

- `events.source_system = 'google_sheet'`
- `events.source_external_id = <ID z tabulky>`

Kombinace `(source_system, source_external_id)` je unikátní a slouží synchronizátoru k bezpečnému párování řádku s existující webovou akcí.

## Termíny

Backend neobsahuje technický pojem série ani recurrence rule.

Jedna akce může mít 1 až N explicitních termínů v `event_dates`.

Import musí vždy převést zdrojová data na konkrétní výskyty:

- jednodenní termín: `starts_on = ends_on`,
- skutečná vícedenní akce: jeden termín s rozdílným `starts_on` a `ends_on`,
- opakovaná akce: více konkrétních řádků v `event_dates`,
- kombinace samostatných dní a vícedenních bloků je povolena.

Sloupce `Opakující se`, `Typ opakování`, `Pravidlo opakování` mohou při importu sloužit jen jako pomocný kontext pro parser. Autoritativním výsledkem jsou explicitní termíny, primárně z `Termíny série`, pokud jsou vyplněné.

Příklad zdroje:

`1.–2. 8. 2026; 8.–9. 8. 2026; 15. 8. 2026`

Výsledek:

- 2026-08-01 → 2026-08-02
- 2026-08-08 → 2026-08-09
- 2026-08-15 → 2026-08-15

## Speciální den s jinými údaji

Pokud jeden konkrétní den potřebuje jiný veřejný název, popis, místo, zdroj nebo jinou podstatnou veřejnou informaci, nevytváří se occurrence override.

Místo toho se daný termín odebere z původní akce a založí se jako samostatná akce s vlastním číselným ID.

Volitelně lze mezi oběma akcemi vytvořit `event_relations` s typem `variant` nebo `related`. Tato vazba je redakční a veřejný web ji nemusí zobrazovat.

## Mapování hlavních polí

- Název akce → `events.title`
- Stručný popis → `events.description`
- Obec → `events.city`
- Místo → `events.place`
- Kraj / region → `events.region`
- Stát → `events.country`
- Trasa → `events.route`
- Pořadatel → `events.organizer`
- Čas od / Čas do → výchozí `events.time_start` / `events.time_end`, případně termínové časy v `event_dates`
- Celodenní → `events.all_day`
- Hlavní zdroj → primární `event_sources`
- Ověřovací zdroj → další `event_sources`
- Druh dopravy → normalizované `event_categories`

## Synchronizace

Pro každý řádek tabulky:

1. Najdi `(source_system='google_sheet', source_external_id=<ID>)`.
2. Pokud neexistuje, vytvoř novou akci a přiděl číselné ID.
3. Pokud existuje, porovnej normalizovaný snapshot zdroje se současným stavem.
4. Pole bez ruční redakční ochrany lze aktualizovat automaticky.
5. Konflikt s ručně změněným polem vytvoří `event_change_proposals` místo tichého přepsání.
6. Významné změny termínu, místa nebo zrušení mají `severity='important'`.

## Průběžné ověřování

Akce s více budoucími termíny se nesmí po prvním importu považovat za trvale ověřené.

Automatický sběr má pravidelně znovu kontrolovat původní zdroj, zejména když se blíží nejbližší budoucí termín. Změny v pozdější části stejné akce (např. změna zářijových jízd zjištěná v srpnu) se musí propsat do další synchronizace nebo do change proposal podle redakční ochrany.