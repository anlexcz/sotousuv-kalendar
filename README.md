# Šotoušův kalendář — POZASTAVENO

> **Projekt je pozastaven (9. 11. 2026) a čeká na zásadní revizi.** Dosavadní automatický sběr, AI zpracování, produkční backend a automatická nasazení jsou vyřazeny z hlavní větve. Současný repozitář uchovává zejména **design a statický prototyp webu** jako podklad pro budoucí přepracování. Zobrazená data jsou pouze historická/ukázková a **nejsou průběžně aktualizována**.

## Co je zachováno

- Stránky, mobilní/desktopová navigace, CSS a JavaScript původního prototypu.
- Přechodná statická data `events.js` potřebná pro zobrazení původního rozhraní; neslouží jako aktuální kalendář akcí.
- Prototyp administrace je pouze ukázka rozhraní, nikoli funkční bezpečná produkční administrace.

## Co už neběží

- Plánované GitHub Actions pro sběr zdrojů a testy AI.
- Automatické nasazování administračního Cloudflare Workeru z této větve.

**Pozor:** Již nasazené externí Cloudflare služby či případné hostované kopie webu se změnou repozitáře samy neodstraní. Starší implementace zůstává dostupná v archivační větvi `archive/pre-pause-20261109`; další historické prototypy jsou v původních větvích.

## Budoucí pokračování

Nejdřív znovu navrhnout datový model, správu zdrojů a ověřování akcí. Teprve potom obnovovat sběr dat a veřejné publikování. Bez automatického zapnutí starého řešení.
