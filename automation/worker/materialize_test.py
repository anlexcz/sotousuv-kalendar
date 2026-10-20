from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from detail_enrichment_test import build_d1, extract_dates, fetch_page
from resolver_test import infer_categories, load_findings

TARGET_FINDING_ID = "FND-F319A56F7F78FA92"
ACTOR = "materialize-test"
REQUEST_ID = f"materialize-test:{TARGET_FINDING_ID}:v1"
TIME_RE = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def q1(d1, sql: str, params=None):
    rows = d1.query(sql, params or []).rows
    return rows[0] if rows else None


def ensure_allocator(d1) -> None:
    count = int(q1(d1, "SELECT COUNT(*) AS c FROM events")["c"])
    counter = q1(d1, "SELECT value FROM settings WHERE key='next_event_id'")
    status = q1(d1, "SELECT value FROM settings WHERE key='event_id_counter_status'")

    if counter and status:
        if status["value"] != "INITIALIZED":
            raise RuntimeError("event_id counter exists but is not INITIALIZED")
        return

    if count != 0:
        raise RuntimeError("cannot initialize event_id counter because events table is not empty")

    d1.query(
        "INSERT OR IGNORE INTO settings(key,value,description) VALUES "
        "('next_event_id','1','Next never-used numeric event_id'),"
        "('event_id_counter_status','INITIALIZED','Central event_id allocator status')"
    )


def allocate_event_id(d1) -> int:
    row = q1(
        d1,
        "UPDATE settings SET value=CAST(value AS INTEGER)+1 "
        "WHERE key='next_event_id' "
        "AND EXISTS (SELECT 1 FROM settings s2 WHERE s2.key='event_id_counter_status' AND s2.value='INITIALIZED') "
        "RETURNING CAST(value AS INTEGER)-1 AS event_id"
    )
    if not row:
        raise RuntimeError("event_id allocation failed")
    return int(row["event_id"])


def main() -> int:
    d1 = build_d1()

    settings = {r["key"]: r.get("value") for r in d1.query(
        "SELECT key,value FROM settings WHERE key IN ('event_creation_enabled','scheduler_enabled','production_status')"
    ).rows}
    if settings.get("event_creation_enabled") != "NE":
        raise RuntimeError("materialize-test requires event_creation_enabled=NE")
    if settings.get("scheduler_enabled") != "NE":
        raise RuntimeError("materialize-test requires scheduler_enabled=NE")
    if settings.get("production_status") != "DISABLED":
        raise RuntimeError("materialize-test requires production_status=DISABLED")

    existing = q1(d1, "SELECT event_id,title,publish,editorial_state FROM events WHERE origin_ref=? LIMIT 1", [TARGET_FINDING_ID])
    if existing:
        print(json.dumps({
            "ok": True,
            "mode": "MATERIALIZE_TEST_IDEMPOTENT",
            "already_exists": True,
            "event": existing,
        }, ensure_ascii=False, indent=2))
        return 0

    finding = next((f for f in load_findings(d1) if f["finding_id"] == TARGET_FINDING_ID), None)
    if not finding:
        raise RuntimeError(f"target finding {TARGET_FINDING_ID} is not OPEN or not found")

    title = finding.get("title") or ""
    date_from = finding.get("date_from")
    date_to = finding.get("date_to") or date_from
    detail_url = finding.get("detail_url")
    source_id = finding.get("source_id")
    if not title or not date_from or not detail_url or not source_id:
        raise RuntimeError("target finding is missing title/date/detail_url/source_id")

    categories = infer_categories(title)
    if "bus" not in categories:
        raise RuntimeError(f"target finding is not confidently bus-related: {categories}")

    response, _html, visible = fetch_page(detail_url)
    if response.status_code != 200:
        raise RuntimeError(f"detail page HTTP {response.status_code}")

    seen_dates = {x["date"] for x in extract_dates(title + " " + visible)}
    if date_from not in seen_dates or date_to not in seen_dates:
        raise RuntimeError(f"stored term is not explicitly present on detail page: {date_from}..{date_to}")

    if not TIME_RE.search(visible):
        raise RuntimeError("no explicit clock time found on detail page; refusing to guess all_day=NE")
    all_day = "NE"

    duplicate = q1(
        d1,
        "SELECT e.event_id,e.title FROM events e JOIN terms t ON t.event_id=e.event_id "
        "WHERE lower(e.title)=lower(?) AND t.date_from=? AND e.is_active='ANO' AND t.is_active='ANO' LIMIT 1",
        [title, date_from],
    )
    if duplicate:
        raise RuntimeError(f"possible duplicate existing event: {duplicate}")

    ensure_allocator(d1)
    event_id = allocate_event_id(d1)
    term_id = f"TRM-{event_id:06d}-001"
    link_id = f"ELS-{event_id:06d}-{source_id}"
    run_id = f"RUN-MATERIALIZE-{event_id:06d}"
    ts = now_iso()
    categories_json = json.dumps(categories, ensure_ascii=False, separators=(",", ":"))

    statements = [
        (
            "INSERT INTO runs(run_id,run_type,started_at,status,input_count,actor,note) VALUES (?,? ,?,'STARTED',1,?,?)",
            [run_id, "MATERIALIZE_TEST", ts, ACTOR, TARGET_FINDING_ID],
        ),
        (
            "INSERT INTO events(event_id,title,all_day,event_state,review_state,categories,public_source_id,publish,editorial_state,origin_type,origin_ref,is_active,created_at,created_by,updated_at,updated_by,note) "
            "VALUES (?,?,?,'AKTIVNI','NEZKONTROLOVANO',?,?,'NE','DRAFT','AUTO',?,'ANO',?,?,?,?,?)",
            [event_id, title, all_day, categories_json, source_id, TARGET_FINDING_ID, ts, ACTOR, ts, ACTOR, "Controlled materialize-test; unpublished"],
        ),
        (
            "INSERT INTO event_auto(event_id,title,all_day,event_state,categories,auto_updated_at,run_id,note) VALUES (?,?,?,'AKTIVNI',?,?,?,?)",
            [event_id, title, all_day, categories_json, ts, run_id, "Materialized from explicit finding"],
        ),
        (
            "INSERT INTO terms(term_id,event_id,date_from,date_to,term_state,is_active,created_at,created_by,updated_at,updated_by,note) "
            "VALUES (?,?,?,?,'AKTIVNI','ANO',?,?,?,?,?)",
            [term_id, event_id, date_from, date_to, ts, ACTOR, ts, ACTOR, "Controlled materialize-test"],
        ),
        (
            "INSERT INTO term_auto(term_id,event_id,date_from,date_to,term_state,auto_updated_at,run_id,note) VALUES (?,?,?,?,'AKTIVNI',?,?,?)",
            [term_id, event_id, date_from, date_to, ts, run_id, "Materialized from explicit finding"],
        ),
        (
            "INSERT INTO event_sources(link_id,event_id,source_id,source_role,active,first_seen_at,created_at,created_by,note) "
            "VALUES (?,?,?,'ORGANIZER','ANO',?,?,?,?)",
            [link_id, event_id, source_id, finding.get("first_seen_at") or ts, ts, ACTOR, "Source attached during materialize-test"],
        ),
        (
            "INSERT INTO history(history_id,entity_type,entity_id,field_key,old_value,new_value,origin,actor_id,action,run_id,request_id,reference_id,created_at,note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [f"HIS-MAT-{event_id:06d}-E", "EVENT", str(event_id), None, None, title, "AUTO", ACTOR, "CREATE", run_id, REQUEST_ID, TARGET_FINDING_ID, ts, "Controlled materialize-test"],
        ),
        (
            "INSERT INTO history(history_id,entity_type,entity_id,field_key,old_value,new_value,origin,actor_id,action,run_id,request_id,reference_id,created_at,note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [f"HIS-MAT-{event_id:06d}-T", "TERM", term_id, None, None, f"{date_from}..{date_to}", "AUTO", ACTOR, "CREATE", run_id, REQUEST_ID, TARGET_FINDING_ID, ts, "Controlled materialize-test"],
        ),
        (
            "UPDATE findings SET status='RESOLVED', event_id=?, resolution='MATERIALIZED_TEST', resolved_at=?, resolved_by=?, updated_at=? WHERE finding_id=? AND status='OPEN'",
            [event_id, ts, ACTOR, ts, TARGET_FINDING_ID],
        ),
        (
            "UPDATE runs SET finished_at=?, status='SUCCESS', created_events=1 WHERE run_id=?",
            [ts, run_id],
        ),
    ]

    d1.execute_idempotent_request(
        request_id=REQUEST_ID,
        operation="MATERIALIZE_TEST",
        entity_type="EVENT",
        entity_id=str(event_id),
        statements=statements,
        actor=ACTOR,
    )

    event = q1(d1, "SELECT event_id,title,all_day,event_state,review_state,categories,public_source_id,publish,editorial_state,origin_type,origin_ref FROM events WHERE event_id=?", [event_id])
    term = q1(d1, "SELECT term_id,event_id,date_from,date_to,term_state,is_active FROM terms WHERE event_id=?", [event_id])
    auto = q1(d1, "SELECT event_id,title,all_day,event_state,categories,run_id FROM event_auto WHERE event_id=?", [event_id])
    finding_after = q1(d1, "SELECT finding_id,status,event_id,resolution FROM findings WHERE finding_id=?", [TARGET_FINDING_ID])

    if not event or not term or not auto or not finding_after:
        raise RuntimeError("read-back verification failed: missing materialized rows")
    if event["publish"] != "NE" or event["editorial_state"] != "DRAFT" or event["review_state"] != "NEZKONTROLOVANO":
        raise RuntimeError(f"read-back safety verification failed: {event}")
    if finding_after.get("status") != "RESOLVED" or int(finding_after.get("event_id")) != event_id:
        raise RuntimeError(f"finding resolution verification failed: {finding_after}")

    print(json.dumps({
        "ok": True,
        "mode": "MATERIALIZE_TEST_WRITE",
        "request_id": REQUEST_ID,
        "event": event,
        "term": term,
        "event_auto": auto,
        "finding": finding_after,
        "safety": {
            "publish": event["publish"],
            "editorial_state": event["editorial_state"],
            "review_state": event["review_state"],
            "scheduler_enabled": settings.get("scheduler_enabled"),
            "production_status": settings.get("production_status"),
            "read_back_verified": True,
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
