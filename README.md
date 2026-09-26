# Šotoušův kalendář

Webová aplikace pro přehled dopravních a šotoušských akcí.

## Stav projektu

Projekt je v návrhové fázi. Větve `prototype/*` slouží k ověřování UX a vizuálního směru před volbou finálního technického řešení.

### První prototyp

Statický prototyp homepage používá pouze HTML/CSS/JS a ukázková data. Je záměrně bez frameworku a databáze: cílem je nejdříve rozhodnout, jak má web fungovat a vypadat.

Otevřete `index.html` v prohlížeči.


## Aktuální produktová specifikace – září 2026

### Veřejná struktura
Čtyři hlavní sekce: **Akce**, **Kalendář**, **Přidat**, **O projektu**. Mobil používá fixní spodní navigaci; desktop horní navigaci.

### Rozdělení rolí
- **Akce = co a kde:** chronologický feed budoucích akcí.
- **Kalendář = kdy:** měsíční mřížka pro orientaci podle konkrétního dne.
- **Hledání:** samostatné fulltextové hledání; na mobilu se otevírá lupou v hlavičce.
- **Filtr:** pouze dopravní kategorie a oblast. Datum ani textové hledání do filtru nepatří.

### Dopravní kategorie
Jedna akce může mít více kategorií:
`rail` Železnice, `bus` Autobus, `tram` Tramvaj, `trolleybus` Trolejbus, `metro` Metro, `water` Loď, `air` Letadlo, `cableway` Lanovka, `other` Ostatní.

Typ akce (např. den otevřených dveří) není dopravní kategorií. Kategorie mají vlastní barevnou identitu.

### Filtr
Doprava je barevný multiselect. Neaktivní položka zůstává světle ve své kategorické barvě, aktivní je sytější a obsahuje fajfku. Více kategorií funguje jako OR. Oblast je rozbalovací multiselect s moderními checkboxy. Změny se aplikují okamžitě; panel ukazuje počet aktivních voleb a umožňuje jejich hromadné vymazání.

### Feed
Zobrazuje akce se začátkem dnes nebo později. Starší akce se nemažou z dat. Karta obsahuje název, kategorie a město/místo; region je filtrovací/detailový údaj. Celá karta je klikací a datum dne je sticky.

### Kalendář a termíny
Kalendář je klasická měsíční mřížka Po–Ne. Kliknutí na den zobrazí jeho akce. Skutečná vícedenní akce patří do všech dnů svého intervalu. U opakované akce se však musí používat konkrétní výskyty; rozmezí mezi prvním a posledním termínem nesmí znamenat každodenní konání.

### Design
Mobile-first. Montserrat pro UI, Audiowide pouze pro značku. Hlavní akcent `#87CEFA`, tmavě šedá hlavička, světlé plochy. Cílem je informačně hutný vzhled blízký jízdnímu řádu/editorialu, nikoli generický dashboard.

## Datový a technický směr MVP

Cílový tok:
`automatický sběr → surová Google tabulka → redakční zpracování → Akce pro web → JSON → veřejný web`.

MVP nepotřebuje serverovou databázi, vlastní administraci ani obousměrnou synchronizaci. JSON má být stabilní rozhraní, které lze později nahradit API bez zásadního přepisu frontendu.

Současný `events.js` je přechodný prototypový formát. Cílově má jedna akce stabilní ID, 1 až N konkrétních termínů, 0 až N lokalitních štítků, 1 až N zdrojů a 1 až N dopravních kategorií.

## Vývoj

`main` má zůstat stabilní. Nové a rizikové změny se ověřují na beta/prototypové větvi. Produkční nasazení až po výslovném schválení.

Aktuální prototyp: `prototype/homepage-v1`.

### Technický dluh
- po stabilizaci vzhledu uklidit nahromaděné CSS override vrstvy;
- přesunout opakovanou logiku kategorií a termínů do sdílených utilit;
- stabilizovat finální JSON schéma;
- dopracovat detail akce;
- doplnit testy pro termíny, opakované akce a kombinace filtrů.

### Detail akce

Detail je záměrně minimalistický a funguje jako rozcestník, nikoli jako náhrada webu pořadatele. Veřejně zobrazuje pouze název, pořadatele, datum/termín, čas pokud je známý, odkaz na oficiální informace a krátký popis. Interní metadata, stav ověření, kompletní program, ceny, jízdní řády, mapy a organizační pokyny se na detail standardně nepřenášejí. Oficiální odkaz je před popisem a je hlavním pokračováním uživatelské cesty.
