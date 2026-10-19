from __future__ import annotations

import json
from pathlib import Path

from sheets import SheetsAdapter


def _rows_to_dicts(rows: list[list[str]]) -> list[dict[str, str]]:
    if not rows:
        return []
    headers = rows[0]
    result: list[dict[str, str]] = []
    for row in rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        result.append(dict(zip(headers, padded)))
    return result


def build_public_export(adapter: SheetsAdapter) -> dict:
    events = _rows_to_dicts(adapter.read_values("Akce!A1:AD5000"))
    terms = _rows_to_dicts(adapter.read_values("Termíny!A1:O10000"))
    sources = _rows_to_dicts(adapter.read_values("Zdroje!A1:X10000"))
    links = _rows_to_dicts(adapter.read_values("Vazby zdrojů!A1:J20000"))

    public_events = []
    terms_by_event: dict[str, list[dict[str, str]]] = {}
    for term in terms:
        if term.get("is_active") != "ANO":
            continue
        terms_by_event.setdefault(term.get("event_id", ""), []).append(term)

    source_by_id = {source.get("source_id", ""): source for source in sources if source.get("active") == "ANO"}
    links_by_event: dict[str, list[dict[str, str]]] = {}
    for link in links:
        if link.get("active") != "ANO":
            continue
        links_by_event.setdefault(link.get("event_id", ""), []).append(link)

    for event in events:
        if event.get("publish") != "ANO" or event.get("is_active") != "ANO" or event.get("event_state") == "SKRYTA":
            continue

        event_id = event.get("event_id", "")
        event_sources = []
        for link in links_by_event.get(event_id, []):
            source = source_by_id.get(link.get("source_id", ""))
            if source:
                event_sources.append({
                    "source_id": source.get("source_id", ""),
                    "url": source.get("url", ""),
                    "role": link.get("source_role", ""),
                })

        public_events.append({
            "event_id": event_id,
            "title": event.get("title", ""),
            "description": event.get("description", ""),
            "municipality": event.get("municipality", ""),
            "place": event.get("place", ""),
            "region": event.get("region", ""),
            "country": event.get("country", ""),
            "route": event.get("route", ""),
            "organizer": event.get("organizer", ""),
            "all_day": event.get("all_day", ""),
            "event_state": event.get("event_state", ""),
            "categories": [item.strip() for item in event.get("categories", "").split(";") if item.strip()],
            "terms": [
                {
                    "term_id": term.get("term_id", ""),
                    "date_from": term.get("date_from", ""),
                    "date_to": term.get("date_to", ""),
                    "term_state": term.get("term_state", ""),
                    "replacement_term_id": term.get("replacement_term_id", ""),
                }
                for term in terms_by_event.get(event_id, [])
            ],
            "sources": event_sources,
        })

    return {
        "schema_version": 2,
        "events": public_events,
    }


def write_public_export(adapter: SheetsAdapter, output_path: str) -> None:
    payload = build_public_export(adapter)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
