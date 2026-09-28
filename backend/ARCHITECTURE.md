# Backend – aktuální architektura

## Základní rozhodnutí

- Autoritativní webová data jsou v MariaDB/MySQL.
- Google tabulka **Dopravní akce / Akce** je vstupní a průzkumná vrstva, ne runtime databáze webu.
- `events.js` je pouze historický snapshot prototypu a backend jej nepoužívá.
- Veřejné i redakční ID akce je prosté číselné `events.id` (`AUTO_INCREMENT`).
- Původní ID z Google tabulky zůstává skryté v `source_external_id` pouze pro synchronizaci.

## Akce a termíny

Technický pojem série neexistuje.

`events` = jedna obsahová akce.

`event_dates` = 1 až N explicitních termínů této akce. Jeden termín může být jednodenní nebo skutečně vícedenní.

Neukládáme:

- RRULE,
- weekday/day bitmask,
- „každý víkend“ jako pravidlo,
- occurrence overrides.

Automatický sběr vždy převede známé pravidlo pořadatele na konkrétní seznam termínů.

Pokud jeden termín potřebuje jiné podstatné veřejné údaje, jde o samostatnou akci. Volitelná `event_relations` slouží pouze k redakčnímu propojení.

## Synchronizace

`ChatGPT / automatický sběr → Dopravní akce → Apps Script → sync API → DB`

Nová zdrojová akce se vytvoří automaticky. Čistě automatickou akci lze aktualizovat. Jakmile byla webová akce ručně upravena nebo lidsky zkontrolována, další rozdíl ze zdroje se ukládá do `event_change_proposals` a čeká na rozhodnutí redaktora.

Akce s dalšími budoucími termíny se průběžně znovu ověřují, hlavně před nejbližšími výskyty.

## Administrace

`/admin` pracuje přímo s API a DB. Umí:

- session login,
- hledání i podle číselného ID,
- vytvořit novou akci,
- upravit veřejná pole,
- přidat/odebrat libovolný počet explicitních termínů,
- stav Aktivní / Zrušená / Skrytá,
- Robot / Zkontrolovaná člověkem,
- přijmout/odmítnout návrh změny ze synchronizace,
- otevřít veřejný detail `/akce/ID`.

Každá ruční změna vytváří revizní snapshot.

## Veřejné URL

Kanonické URL nemají příponu `.html`:

- `/`
- `/kalendar`
- `/pridat`
- `/o-projektu`
- `/akce/48963`
- `/admin`

Fyzické HTML soubory mohou dál sloužit jako jednoduché šablony za Apache rewrite pravidly.
