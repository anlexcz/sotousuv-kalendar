# Šotoušův kalendář

Webová aplikace pro přehled dopravních a šotoušských akcí.

## Stav projektu

Projekt je v návrhové fázi. Větve `prototype/*` slouží k ověřování UX a vizuálního směru před volbou finálního technického řešení.

### První prototyp

Statický prototyp homepage používá pouze HTML/CSS/JS a ukázková data. Je záměrně bez frameworku a databáze: cílem je nejdříve rozhodnout, jak má web fungovat a vypadat.

Otevřete `index.html` v prohlížeči.


## Aktuální produktová specifikace – září 2026

### Veřejná struktura
Čtyři hlavní sekce: **Akce**, **Kalendář**, **Přidat**, **O projektu**. Mobil používá fixní spodní navigaci; desktop horní navigaci. Všechny stránky zakončuje nenápadná patička s hláškou **„Konečná! Prosíme, vystupte.“**, označením Metrobus a odkazy na Kontakt a Administraci. Kontakt vede na sekci v O projektu; kontaktní e-mail je `anlex@metrobus.cz`.

### Rozdělení rolí
- **Akce = co a kde:** chronologický feed budoucích akcí.
- **Kalendář = kdy:** měsíční mřížka pro orientaci podle konkrétního dne.
- **Hledání:** samostatné fulltextové hledání; na desktopu je vyhledávací pole v hlavičce stále viditelné, na mobilu se kvůli prostoru otevírá lupou.
- **Filtr:** pouze dopravní kategorie a oblast. Datum ani textové hledání do filtru nepatří.

### Dopravní kategorie
Jedna akce může mít více kategorií:
`rail` Železnice, `bus` Autobus, `tram` Tramvaj, `trolleybus` Trolejbus, `metro` Metro, `water` Loď, `air` Letadlo, `cableway` Lanovka, `other` Ostatní.

Typ akce (např. den otevřených dveří) není dopravní kategorií. Kategorie mají vlastní barevnou identitu.

### Filtr
Doprava je barevný multiselect. Neaktivní položka zůstává světle ve své kategorické barvě, aktivní je sytější a obsahuje fajfku. Více kategorií funguje jako OR. Oblast je rozbalovací multiselect s moderními checkboxy. Změny se aplikují okamžitě; panel ukazuje počet aktivních voleb a umožňuje jejich hromadné vymazání.

### Feed
Zobrazuje akce se začátkem dnes nebo později. Feed používá lazy rendering po blocích 12 celých dnů s akcemi; další blok se automaticky vykreslí při přiblížení ke konci seznamu. Aktuální statický prototyp má data stále načtená v `events.js`, takže nejde ještě o síťové stránkování z databáze. Patička homepage se zobrazí až po vykreslení posledního bloku.

 Starší akce se nemažou z dat. Karta obsahuje název, kategorie a město/místo; region je filtrovací/detailový údaj. Celá karta je klikací a datum dne je sticky.

### Kalendář a termíny
Kalendář je klasická měsíční mřížka Po–Ne. Kliknutí na den zobrazí jeho akce. Skutečná vícedenní akce patří do všech dnů svého intervalu. U opakované akce se však musí používat konkrétní výskyty; rozmezí mezi prvním a posledním termínem nesmí znamenat každodenní konání.

### Design
Mobile-first. Montserrat pro UI, Audiowide pouze pro značku. Pod názvem ŠOTOUŠŮV KALENDÁŘ je v hlavičce těsně umístěný drobný podpis METROBUS, rovněž v Audiowide. Šotoušův kalendář je projekt Metrobusu. Hlavní akcent `#87CEFA`, tmavě šedá hlavička, světlé plochy. Cílem je informačně hutný vzhled blízký jízdnímu řádu/editorialu, nikoli generický dashboard.

## Datový a technický směr MVP

Cílový tok:
`automatický sběr → surová Google tabulka → redakční zpracování → Akce pro web → JSON → veřejný web`.

Aktuální cílový návrh počítá se serverovou databází a jednoduchou mobilně použitelnou administrací. Google tabulka zůstává vstupní frontou zdrojových nálezů; databáze je autoritativní stav webu. Automatický import může nové akce publikovat i bez ručního zásahu, ale ruční redakční změny mají před automatickým přepisem přednost.

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

Detail je záměrně minimalistický a funguje jako rozcestník, nikoli jako náhrada webu pořadatele. Veřejně zobrazuje dopravní kategorii/kategorie a město nad názvem, název, datum/termín, čas pokud je známý, výrazný odkaz na akci a krátký popis. Samostatný textový údaj „Zdroj“ se na detailu nezobrazuje; zdroj reprezentuje cílový odkaz. Pořadatel není povinný údaj a na veřejném detailu se standardně nezobrazuje. Interní metadata, stav ověření, kompletní program, ceny, jízdní řády, mapy a organizační pokyny se na detail standardně nepřenášejí. Odkaz na akci je před popisem, je hlavním pokračováním uživatelské cesty a používá brandovou modrou jako primární CTA. Zdroj se na detailu identifikuje bezpečně podle domény odkazu, pokud nemáme samostatně ověřený název zdroje.


### Automatické verze, redakční kontrola a administrace

Každá publikovaná podoba akce musí nést informaci, zda je pouze automatická, nebo prošla lidskou kontrolou. První verze vytvořená automatickým importem může být zveřejněna bez zásahu člověka. Pokud redaktor pole ručně upraví, tato publikovaná hodnota má přednost a další automatická aktualizace ji nesmí potichu přepsat.

Automatika však ručně upravená pole dál sleduje. Pokud zdroj přinese novou hodnotu, uloží se jako návrh nové verze a administrace akci označí jako vyžadující pozornost. Redaktor může změnu přijmout, odmítnout nebo vytvořit vlastní novou verzi. Významné změny, zejména zrušení, změna termínu nebo místa, mají být v administraci zvýrazněny.

Administrace musí umožnit minimálně upravit, skrýt či zrušit akci, kontrolovat navržené aktualizace a označit automatickou akci jako zkontrolovanou. Po lidské úpravě nebo schválení je aktuální publikovaná verze považována za lidsky zkontrolovanou.

### Transparentnost automatického zpracování

Pokud aktuální publikovaná verze ještě neprošla lidskou kontrolou, detail dole zobrazí nenápadnou patičku oddělenou tenkou linkou s ikonou robota: **„Tady pracoval robot. Občas mu něco ujede, takže před cestou raději mrkni na odkaz na akci.“** Po lidské kontrole poznámka zmizí. Stav se tedy vztahuje ke konkrétní publikované verzi, nikoli trvale k celé akci.
