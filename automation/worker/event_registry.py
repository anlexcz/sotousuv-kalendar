from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from detail_enrichment_test import build_d1


def parse_categories(raw: str | None) -> list[str]:
    if not raw:
        return []
    value = raw.strip()
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            pass
    return [x.strip() for x in value.replace(",", ";").split(";") if x.strip()]


def build_registry() -> dict:
    d1 = build_d1()
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    events = d1.query(
        "SELECT event_id,title,description,municipality,place,region,country,route,organizer,"
        "all_day,event_state,review_state,categories,public_source_id,publish,editorial_state,"
        "origin_type,origin_ref,is_active,row_version,created_at,created_by,updated_at,updated_by,note "
        "FROM events WHERE is_active='ANO' ORDER BY event_id"
    ).rows

    terms = d1.query(
        "SELECT term_id,event_id,date_from,date_to,term_state,replacement_term_id,is_active,row_version,note "
        "FROM terms ORDER BY event_id,date_from,date_to,term_id"
    ).rows

    sources = d1.query(
        "SELECT es.event_id,es.link_id,es.source_role,es.active AS link_active,s.source_id,s.url,s.label,"
        "s.source_type,s.source_scope,s.active AS source_active "
        "FROM event_sources es JOIN sources s ON s.source_id=es.source_id "
        "ORDER BY es.event_id,es.link_id"
    ).rows

    findings = d1.query(
        "SELECT finding_id,status,event_id,resolution,resolved_at,resolved_by,source_id,title_hint "
        "FROM findings WHERE event_id IS NOT NULL ORDER BY event_id,finding_id"
    ).rows

    autos = d1.query(
        "SELECT event_id,title,description,municipality,place,region,country,route,organizer,all_day,event_state,"
        "categories,auto_updated_at,run_id,source_presence,source_missing_since,note "
        "FROM event_auto ORDER BY event_id"
    ).rows

    overrides = d1.query(
        "SELECT entity_id,COUNT(*) AS count FROM overrides "
        "WHERE entity_type='EVENT' AND active='ANO' GROUP BY entity_id"
    ).rows

    alerts = d1.query(
        "SELECT event_id,COUNT(*) AS count FROM alerts WHERE status='OPEN' AND event_id IS NOT NULL GROUP BY event_id"
    ).rows

    history_counts = d1.query(
        "SELECT entity_id,COUNT(*) AS count FROM history WHERE entity_type='EVENT' GROUP BY entity_id"
    ).rows

    terms_by_event: dict[int, list[dict]] = {}
    for row in terms:
        terms_by_event.setdefault(int(row["event_id"]), []).append(row)

    sources_by_event: dict[int, list[dict]] = {}
    for row in sources:
        sources_by_event.setdefault(int(row["event_id"]), []).append(row)

    findings_by_event: dict[int, list[dict]] = {}
    for row in findings:
        findings_by_event.setdefault(int(row["event_id"]), []).append(row)

    autos_by_event = {int(row["event_id"]): row for row in autos}
    overrides_by_event = {int(row["entity_id"]): int(row["count"]) for row in overrides}
    alerts_by_event = {int(row["event_id"]): int(row["count"]) for row in alerts}
    history_by_event = {int(row["entity_id"]): int(row["count"]) for row in history_counts}

    registry_events: list[dict] = []
    for event in events:
        event_id = int(event["event_id"])
        event_terms = terms_by_event.get(event_id, [])
        active_terms = [t for t in event_terms if t.get("is_active") == "ANO"]
        inactive_terms = [t for t in event_terms if t.get("is_active") != "ANO"]
        active_dates = sorted((t["date_from"], t["date_to"]) for t in active_terms)
        upcoming = [t for t in active_terms if t["date_to"] >= today]
        upcoming.sort(key=lambda t: (t["date_from"], t["date_to"], t["term_id"]))

        event_sources = sources_by_event.get(event_id, [])
        active_source_links = [s for s in event_sources if s.get("link_active") == "ANO"]
        origin_findings = findings_by_event.get(event_id, [])

        attention: list[str] = []
        if not active_terms:
            attention.append("NO_ACTIVE_TERM")
        if not active_source_links:
            attention.append("NO_ACTIVE_SOURCE_LINK")
        if event.get("review_state") != "ZKONTROLOVANO":
            attention.append("NEEDS_REVIEW")
        if event.get("editorial_state") != "READY":
            attention.append("NOT_READY")
        if event.get("publish") != "ANO":
            attention.append("UNPUBLISHED")
        if alerts_by_event.get(event_id, 0):
            attention.append("OPEN_ALERT")

        registry_events.append({
            "event_id": event_id,
            "title": event["title"],
            "description": event.get("description") or "",
            "location": {
                "municipality": event.get("municipality") or "",
                "place": event.get("place") or "",
                "region": event.get("region") or "",
                "country": event.get("country") or "",
            },
            "route": event.get("route") or "",
            "organizer": event.get("organizer") or "",
            "all_day": event.get("all_day"),
            "categories": parse_categories(event.get("categories")),
            "states": {
                "event_state": event.get("event_state"),
                "review_state": event.get("review_state"),
                "editorial_state": event.get("editorial_state"),
                "publish": event.get("publish"),
            },
            "terms_summary": {
                "active_count": len(active_terms),
                "inactive_count": len(inactive_terms),
                "first_active_date": active_dates[0][0] if active_dates else None,
                "last_active_date": active_dates[-1][1] if active_dates else None,
                "next_or_current_term": upcoming[0] if upcoming else None,
            },
            "terms": event_terms,
            "sources": active_source_links,
            "origin": {
                "origin_type": event.get("origin_type"),
                "origin_ref": event.get("origin_ref"),
                "findings": origin_findings,
            },
            "auto": autos_by_event.get(event_id),
            "editorial": {
                "active_overrides": overrides_by_event.get(event_id, 0),
                "open_alerts": alerts_by_event.get(event_id, 0),
                "history_entries": history_by_event.get(event_id, 0),
                "row_version": event.get("row_version"),
                "created_at": event.get("created_at"),
                "created_by": event.get("created_by"),
                "updated_at": event.get("updated_at"),
                "updated_by": event.get("updated_by"),
                "note": event.get("note"),
            },
            "attention": attention,
        })

    summary = {
        "event_count": len(registry_events),
        "needs_review": sum(1 for e in registry_events if "NEEDS_REVIEW" in e["attention"]),
        "ready": sum(1 for e in registry_events if e["states"]["editorial_state"] == "READY"),
        "published": sum(1 for e in registry_events if e["states"]["publish"] == "ANO"),
        "with_open_alerts": sum(1 for e in registry_events if e["editorial"]["open_alerts"] > 0),
        "active_terms": sum(e["terms_summary"]["active_count"] for e in registry_events),
    }

    return {
        "mode": "EVENT_REGISTRY_READ_ONLY",
        "read_only": True,
        "generated_at": now.isoformat(),
        "summary": summary,
        "events": registry_events,
    }


def main() -> int:
    output_path = os.environ.get("EVENT_REGISTRY_PATH", "../../data/event_registry.json")
    payload = build_registry()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    compact = {
        "ok": True,
        "mode": payload["mode"],
        "read_only": True,
        "output_path": str(path),
        "summary": payload["summary"],
        "events": [
            {
                "event_id": e["event_id"],
                "title": e["title"],
                "categories": e["categories"],
                "states": e["states"],
                "terms_summary": e["terms_summary"],
                "attention": e["attention"],
            }
            for e in payload["events"]
        ],
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
