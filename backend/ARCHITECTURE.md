# Šotoušův kalendář – aktuální architektura

## Fáze projektu

Projekt je nyní provozován v testovacím sandboxu na GitHub Pages. Cílem této fáze je doladit sběr dat, deduplikaci, schvalovací tok, datový model, vzhled a UX bez zásahu do hostingu Metrobusu.

Produkční nasazení bude později používat existující sdílenou databázi Metrobusu. Šotoušův kalendář nebude zakládat vlastní databázi; jeho tabulky mají prefix `sk_`.

## Pracovní datový tok

`Zdroje → automatický sběr → Nálezy → schválení → Akce → JSON export → GitHub Pages`

Google tabulka **Šotoušův kalendář – automatický sběr** obsahuje:

- `Zdroje` – rotační seznam webů a pořadatelů ke kontrole,
- `Nálezy` – staging/inbox nových akcí a návrhů změn,
- `Akce` – kanonický stav publikovatelných akcí,
- `Běhy` – log automatizace,
- `Nastavení` – parametry sběru a zpracování.

Stará tabulka **Dopravní akce** je pouze legacy/migrační zdroj a není běžným provozním zdrojem pravdy.

## Nálezy

Každý nález má stabilní ID `FND-XXXXXX` (např. `FND-000001`). ID se nikdy nerecykluje.

Nové akce i zjištěné změny se vždy nejprve zapisují do `Nálezy`:

- `NOVÁ` = kandidát na novou akci,
- `ZMĚNA` = návrh změny existující akce.

Nález se smí promítnout do `Akce` pouze při `Stav zpracování = SCHVÁLENO`. `ZAMÍTNUTO` se nikdy nepromítá. Po úspěšném promítnutí se nález označí `ZPRACOVÁNO`.

## Kanonický list Akce

Jeden řádek = jedna logická akce.

Základní sloupce:

`ID, Název, Popis, Obec, Místo, Kraj / region, Stát, Trasa, Pořadatel, Celodenní, Stav akce, Stav ověření, Zdroj vzniku, Kategorie, Termíny, Hlavní zdroj, Ověřovací zdroj, Veřejná URL, Publikovat, Poslední kontrola, Datum prvního nálezu, Vytvořeno, Aktualizováno, Původní ID, Zdrojový nález, Režim správy, Poslední editor, Poznámka`.

### Identita

- `ID` je stabilní číselné veřejné ID.
- Nové ID = další dosud nepoužité číslo.
- ID se nerecykluje.
- `Původní ID` je pouze migrační vazba a není veřejnou identitou.
- `Zdrojový nález` odkazuje na stabilní `FND-XXXXXX`, ne na číslo řádku.

### Termíny

Technická série ani recurrence rule neexistuje.

`Termíny` používají explicitní zápis:

- jednodenní: `YYYY-MM-DD`,
- vícedenní blok: `YYYY-MM-DD..YYYY-MM-DD`,
- více samostatných termínů: položky oddělené středníkem.

Pokud se jeden konkrétní výskyt podstatně liší názvem, programem, místem nebo trasou, jde o samostatnou akci.

### Kategorie

Používají se technická ID:

`rail,bus,tram,trolleybus,metro,water,air,cableway,other`

Jedna akce může mít více kategorií, oddělených čárkou.

### Publikace

Do sandbox exportu patří pouze řádky s `Publikovat = ANO`.

`Režim správy` rozlišuje automatický a lidský stav. Automatika nesmí potichu přepsat lidsky spravovanou hodnotu mimo explicitně schválený návrh změny.

## GitHub sandbox

Sandboxová větev používá `data/events.json` jako transportní kopii kanonického listu `Akce`. `Nálezy` se nikdy neexportují přímo na veřejný web.

Frontend umí v sandboxu číst JSON a v produkci později přejít na API bez změny veřejného datového významu.

GitHub Pages slouží pouze pro testovací provoz. PHP backend ani MariaDB v sandboxu neběží.

## Budoucí produkce

Produkce na hostingu Metrobusu používá sdílenou MariaDB/MySQL. Všechny tabulky projektu mají prefix `sk_`, například:

- `sk_users`,
- `sk_events`,
- `sk_event_dates`,
- `sk_event_categories`,
- `sk_event_locations`,
- `sk_event_sources`,
- `sk_event_relations`,
- `sk_event_revisions`,
- `sk_event_change_proposals`.

Logický model má odpovídat sandboxu: jedna akce, 1 až N explicitních termínů, stabilní číselné ID, více kategorií, zdroje, lidská ochrana a návrhy změn.

## Veřejné URL

Kanonické URL nemají příponu `.html`:

- `/`
- `/kalendar`
- `/pridat`
- `/o-projektu`
- `/akce/48963`
- `/admin`

Na GitHub Pages se stejné cesty technicky obsluhují jako statické adresáře pod `/sotousuv-kalendar/`. V produkci budou na kořeni cílové domény.
