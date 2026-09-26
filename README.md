# Šotoušův kalendář

Webová aplikace pro přehled dopravních a šotoušských akcí.

## Stav projektu

Projekt je ve fázi funkčního beta/prototypu. Větve `prototype/*` slouží k bezpečnému ověřování UX, technického refaktoru a dalších změn před jejich případným převzetím do stabilní větve.

### První prototyp

Statický beta prototyp používá HTML/CSS/JS bez frameworku. Obsahuje importovaná data akcí v přechodném `events.js`; serverová databáze a administrace jsou cílová další architektura.

Otevřete `index.html` v prohlížeči.


## Aktuální produktová specifikace – září 2026

### Veřejná struktura
Čtyři hlavní sekce: **Akce**, **Kalendář**, **Přidat**, **O projektu**. Mobil používá fixní spodní navigaci; desktop horní navigaci. Všechny stránky zakončuje nenápadná patička s hláškou **„Konečná! Prosíme, vystupte.“**, označením Metrobus a odkazy na Kontakt a Administraci. Kontakt vede na sekci v O projektu; kontaktní e-mail je `anlex@metrobus.cz`.

### Rozdělení rolí
- **Akce = co a kde:** chronologický feed budoucích akcí.
- **Kalendář = kdy:** měsíční mřížka pro orientaci podle konkrétního dne.
- **Hledání:** samostatné fulltextové hledání; na desktopu je vyhledávací pole v hlavičce stále viditelné, na mobilu se kvůli prostoru otevírá lupou. Mobilní hledání nemá tlačítko Zpět: křížek při vyplněném poli nejprve smaže dotaz, při prázdném poli zavře hledání. Placeholder je „Hledat akci nebo místo…“.
- **Filtr:** pouze dopravní kategorie a oblast. Datum ani textové hledání do filtru nepatří.

### Dopravní kategorie
Jedna akce může mít více kategorií:
`rail` Železnice, `bus` Autobus, `tram` Tramvaj, `trolleybus` Trolejbus, `metro` Metro, `water` Loď, `air` Letadlo, `cableway` Lanovka, `other` Ostatní.

Typ akce (např. den otevřených dveří) není dopravní kategorií. Kategorie mají vlastní barevnou identitu.

### Filtr
Doprava je barevný multiselect. Neaktivní položka zůstává světle ve své kategorické barvě, aktivní je sytější. Více kategorií funguje jako OR. Oblast je rozbalovací multiselect s moderními checkboxy. Změny se aplikují okamžitě; panel ukazuje počet aktivních voleb a umožňuje jejich hromadné vymazání.

### Feed
Zobrazuje akce se začátkem dnes nebo později. Feed používá lazy rendering po blocích 12 celých dnů s akcemi; další blok se automaticky vykreslí při přiblížení ke konci seznamu. Aktuální statický prototyp má data stále načtená v `events.js`, takže nejde ještě o síťové stránkování z databáze. Patička homepage se zobrazí až po vykreslení posledního bloku.

 Starší akce se nemažou z dat. Karta obsahuje název, kategorie a město/místo; region je filtrovací/detailový údaj. Celá karta je klikací a datum dne je sticky.

### Kalendář a termíny
Kalendář je klasická měsíční mřížka Po–Ne. Kliknutí na den zobrazí jeho akce. Skutečná vícedenní akce patří do všech dnů svého intervalu. U opakované akce se však musí používat konkrétní výskyty; rozmezí mezi prvním a posledním termínem nesmí znamenat každodenní konání.

### Design
Mobile-first. Montserrat pro UI, Audiowide pouze pro značku. Pod názvem ŠOTOUŠŮV KALENDÁŘ je v hlavičce těsně umístěný drobný podpis METROBUS, rovněž v Audiowide; podpis je samostatný odkaz na `metrobus.cz`. Metrobus v patičce vede na stejný web. Šotoušův kalendář je projekt Metrobusu. Hlavní akcent `#87CEFA`, tmavě šedá hlavička, světlé plochy. Cílem je informačně hutný vzhled blízký jízdnímu řádu/editorialu, nikoli generický dashboard.

## Datový a technický směr MVP

Cílový tok:
`automatický sběr → Google tabulka jako vstupní fronta → automatický import/synchronizace → webová databáze → veřejný web / administrace`.

Aktuální cílový návrh počítá se serverovou databází a jednoduchou mobilně použitelnou administrací. Google tabulka zůstává vstupní frontou zdrojových nálezů; databáze je autoritativní stav webu. Automatický import může nové akce publikovat i bez ručního zásahu, ale ruční redakční změny mají před automatickým přepisem přednost.

Současný `events.js` je přechodný prototypový formát. Cílově má jedna akce stabilní ID, 1 až N konkrétních termínů, 0 až N lokalitních štítků, 1 až N zdrojů a 1 až N dopravních kategorií.

## Vývoj

`main` má zůstat stabilní. Nové a rizikové změny se ověřují na beta/prototypové větvi. Produkční nasazení až po výslovném schválení.

Aktuální prototyp: `prototype/homepage-v1`.

### Technický dluh
- doplnit automatické testy pro společnou datovou logiku, termíny a opakované akce;
- postupně nahradit přechodný `events.js` databází/API a skutečným stránkovaným načítáním;
- před databázovou fází dále hlídat, aby se stránková logika znovu neduplikovala.

### Detail akce

Detail je záměrně minimalistický a funguje jako rozcestník, nikoli jako náhrada webu pořadatele. Veřejně zobrazuje dopravní kategorii/kategorie a město nad názvem, název, datum/termín, čas pokud je známý, výrazný odkaz na akci a krátký popis. Samostatný textový údaj „Zdroj“ se na detailu nezobrazuje; zdroj reprezentuje cílový odkaz. Pořadatel není povinný údaj a na veřejném detailu se standardně nezobrazuje. Interní metadata, stav ověření, kompletní program, ceny, jízdní řády, mapy a organizační pokyny se na detail standardně nepřenášejí. Odkaz na akci je před popisem, je hlavním pokračováním uživatelské cesty a používá brandovou modrou jako primární CTA. 

### Automatické verze, redakční kontrola a administrace

Každá publikovaná podoba akce musí nést informaci, zda je pouze automatická, nebo prošla lidskou kontrolou. První verze vytvořená automatickým importem může být zveřejněna bez zásahu člověka. Pokud redaktor pole ručně upraví, tato publikovaná hodnota má přednost a další automatická aktualizace ji nesmí potichu přepsat.

Automatika však ručně upravená pole dál sleduje. Pokud zdroj přinese novou hodnotu, uloží se jako návrh nové verze a administrace akci označí jako vyžadující pozornost. Redaktor může změnu přijmout, odmítnout nebo vytvořit vlastní novou verzi. Významné změny, zejména zrušení, změna termínu nebo místa, mají být v administraci zvýrazněny.

Administrace musí umožnit minimálně upravit, skrýt či zrušit akci, kontrolovat navržené aktualizace a označit automatickou akci jako zkontrolovanou. Po lidské úpravě nebo schválení je aktuální publikovaná verze považována za lidsky zkontrolovanou.

### Transparentnost automatického zpracování

Pokud aktuální publikovaná verze ještě neprošla lidskou kontrolou, detail dole zobrazí nenápadnou patičku oddělenou tenkou linkou s ikonou robota: **„Tady pracoval robot. Občas mu něco ujede, takže před cestou raději mrkni na odkaz na akci.“** Po lidské kontrole poznámka zmizí. Stav se tedy vztahuje ke konkrétní publikované verzi, nikoli trvale k celé akci.

### Struktura společné JavaScript logiky
Společná logika není soustředěna v jednom supersouboru. Je rozdělena podle odpovědnosti:
- `js/utils.js` – obecné pomocné funkce pro text/HTML,
- `js/categories.js` – definice a normalizace kategorií,
- `js/dates.js` – datumy a konkrétní termíny akcí,
- `js/events.js` – obecná logika nad akcí (lokalita, délka, dlouhodobost).

Stránkové skripty mají používat tyto společné moduly místo vlastních kopií stejné logiky. Pořadí načtení je utils → categories → dates → events → stránkový skript.

### Sdílený layout
Hlavička, desktopová navigace, mobilní navigace a patička jsou generovány z `js/layout.js`. Jednotlivé HTML stránky obsahují pouze kotvy `data-layout="header"` a `data-layout="footer"` a identifikují sekci přes `data-page`. Homepage si zachovává vlastní vyhledávání v hlavičce a speciální `feed-footer` chování navázané na lazy rendering.

### JavaScript jednotlivých stránek
Stránková aplikační logika je oddělena od HTML: `app.js` obsluhuje homepage, `calendar.js` kalendář a `detail.js` detail akce. `calendar.html` ani `detail.html` už neobsahují velké inline bloky JavaScriptu. Sdílená logika zůstává v modulech pod `js/`.
