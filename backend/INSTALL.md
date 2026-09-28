# Backend MVP – instalace prototypu

Požadavky: Apache s `mod_rewrite`, PHP 8.2+ s PDO MySQL, MariaDB/MySQL.

## 1. Konfigurace

Nastav proměnné podle `.env.example` v konfiguraci serveru/PHP-FPM. Necommituj skutečné heslo ani sync token.

Povinné minimum:

- `SK_APP_URL`
- `SK_DB_HOST`, `SK_DB_NAME`, `SK_DB_USER`, `SK_DB_PASS`
- `SK_SHEET_SYNC_TOKEN` – dlouhý náhodný secret

Apache musí povolit `.htaccess` (`AllowOverride FileInfo` nebo `All`) a `mod_rewrite`.

## 2. Databáze

```bash
php backend/migrate.php
```

První administrátor:

```bash
php backend/create_admin.php anlex@metrobus.cz "Anlex" "DLOUHE-HESLO"
```

Heslo z příkladu samozřejmě nahraď skutečným.

## 3. URL

Veřejné kanonické adresy nemají `.html`:

- `/`
- `/kalendar`
- `/pridat`
- `/o-projektu`
- `/akce/48963`
- `/admin`

Staré adresy s `.html` jsou přes Apache přesměrovány na čisté URL.

## 4. Google tabulka Dopravní akce

Do Apps Script projektu tabulky vlož `backend/google-apps-script.gs`.

V **Project Settings → Script Properties** nastav:

- `SK_SYNC_URL` = `https://tvoje-domena.cz/api/sync/google-sheet.php`
- `SK_SYNC_TOKEN` = stejná hodnota jako `SK_SHEET_SYNC_TOKEN` na serveru

První synchronizaci spusť ručně funkcí `syncSotousuvKalendar()`. Teprve po kontrole výsledku lze spustit `installHourlySyncTrigger()`.

Synchronizátor čte list `Akce`, původní ID používá jen jako skrytý párovací klíč a webové DB přidělí jednoduché číselné ID.

## 5. Kontrola po prvním importu

V `/admin` ověř:

1. počet importovaných akcí,
2. několik jednorázových akcí,
3. několik akcí s více explicitními termíny,
4. vícedenní blok,
5. akci se dvěma dopravními kategoriemi,
6. otevření `/akce/ID`,
7. ruční změnu a následnou synchronizaci – má vzniknout návrh změny místo přepsání.

## Stav prototypu

Jde o backendový MVP prototyp. Před produkcí je potřeba integrační test na cílovém VPS, nastavení záloh DB, HTTPS/cookies a následně CI/regresní testy API.
