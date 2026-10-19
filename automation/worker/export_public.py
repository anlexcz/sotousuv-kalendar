from __future__ import annotations

import json
from pathlib import Path

from d1 import D1Adapter


def build_public_export(adapter: D1Adapter) -> dict:
    events = adapter.query(
        "SELECT event_id, title, description, municipality, place, region, country, route, organizer, "
        "all_day, event_state, categories, public_source_id "
        "FROM events WHERE publish = 'ANO' AND is_active = 'ANO' AND event_state <> 'SKRYTA' "
        "ORDER BY event_id"
    ).rows

    terms = adapter.query(
        "SELECT term_id, event_id, date_from, date_to, term_state, replacement_term_id "
        "FROM terms WHERE is_active = 'ANO' ORDER BY event_id, date_from, term_id"
    ).rows

    source_rows = adapter.query(
        "SELECT es.event_id, s.source_id, s.url, es.source_role "
        "FROM event_sources es JOIN sources s ON s.source_id = es.source_id "
        "WHERE es.active = 'ANO' AND s.active = 'ANO' ORDER BY es.event_id, es.link_id"
    ).rows

    terms_by_event: dict[str, list[dict]] = {}
    for term in terms:
        terms_by_event.setdefault(str(term["event_id"]), []).append(term)

    sources_by_event: dict[str, list[dict]] = {}
    for source in source_rows:
        sources_by_event.setdefault(str(source["event_id"]), []).append(
            {
                "source_id": source["source_id"],
                "url": source["url"],
                "role": source["source_role"],
            }
        )

    public_events = []
    for event in events:
        event_id = str(event["event_id"])
        categories = [item.strip() for item in (event.get("categories") or "").split(";") if item.strip()]
        public_events.append(
            {
                "event_id": event["event_id"],
                "title": event["title"],
                "description": event.get("description") or "",
                "municipality": event.get("municipality") or "",
                "place": event.get("place") or "",
                "region": event.get("region") or "",
                "country": event.get("country") or "",
                "route": event.get("route") or "",
                "organizer": event.get("organizer") or "",
                "all_day": event["all_day"],
                "event_state": event["event_state"],
                "categories": categories,
                "terms": terms_by_event.get(event_id, []),
                "sources": sources_by_event.get(event_id, []),
            }
        )

    return {"schema_version": 2, "events": public_events}


def write_public_export(adapter: D1Adapter, output_path: str) -> None:
    payload = build_public_export(adapter)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
