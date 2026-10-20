from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from detail_enrichment_test import build_d1, extract_dates, fetch_page
from materialize_test import allocate_event_id, ensure_allocator, now_iso, q1
from resolver_test import infer_categories, load_findings

ACTOR = "materialize-batch-test"
MAX_EVENTS = 5
TIME_RE = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)")


def existing_by_origin(d1, finding_id: str):
    return q1(
        d1,
        "SELECT event_id,title,publish,editorial_state FROM events WHERE origin_ref=? LIMIT 1",
        [finding_id],
    )


def duplicate_by_title_date(d1, title: str, date_from: str):
    return q1(
        d1,
        "SELECT e.event_id,e.title FROM events e JOIN terms t ON t.event_id=e.event_id "
        "WHERE lower(e.title)=lower(?) AND t.date_from=? AND e.is_active='ANO' AND t.is_active='ANO' LIMIT 1",
        [title, date_from],
    )


def materialize_one(d1, finding: dict) -> dict:
    finding_id = finding["finding_id"]
    request_id = f"materialize-batch-test:{finding_id}:v1"

    existing = existing_by_origin(d1, finding_id)
    if existing:
        return {
            "finding_id": finding_id,
            "status": "SKIPPED_ALREADY_MATERIALIZED",
            "event": existing,
        }

    title = (finding.get("title") or "").strip()
    date_from = finding.get("date_from")
    date_to = finding.get("date_to") or date_from
    detail_url = finding.get("detail_url")
    source_id = finding.get("source_id")

    if not title or not date_from or not detail_url or not source_id:
        return {"finding_id": finding_id, "status": "SKIPPED_MISSING_REQUIRED_DATA"}

    today = datetime.now(timezone.utc).date().isoformat()
    if date_to < today:
        return {"finding_id": finding_id, "status": "SKIPPED_HISTORICAL"}

    response, _html, visible = fetch_page(detail_url)
    if response.status_code != 200:
        return {
            "finding_id": finding_id,
            "status": "SKIPPED_HTTP",
            "http_status": response.status_code,
        }

    seen_dates = {x["date"] for x in extract_dates(title + " " + visible)}
    if date_from not in seen_dates or date_to not in seen_dates:
        return {
            "finding_id": finding_id,
            "status": "SKIPPED_TERM_NOT_RECONFIRMED",
            "date_from": date_from,
            "date_to": date_to,
        }

    if not TIME_RE.search(visible):
        return {
            "finding_id": finding_id,
            "status": "SKIPPED_NO_EXPLICIT_TIME",
        }

    duplicate = duplicate_by_title_date(d1, title, date_from)
    if duplicate:
        return {
            "finding_id": finding_id,
            "status": "SKIPPED_DUPLICATE",
            "duplicate": duplicate,
        }

    categories = infer_categories(title)
    all_day = "NE"

    ensure_allocator(d1)
    event_id = allocate_event_id(d1)
    term_id = f"TRM-{event_id:06d}-001"
    link_id = f"ELS-{event_id:06d}-{source_id}"
    run_id = f"RUN-MATBATCH-{event_id:06d}"
    ts = now_iso()
    categories_json = json.dumps(categories, ensure_ascii=False, separators=(",", ":"))

    statements = [
        (
            "INSERT INTO runs(run_id,run_type,started_at,status,input_count,actor,note) VALUES (?,? ,?,'STARTED',1,?,?)",
            [run_id, "MATERIALIZE_BATCH_TEST", ts, ACTOR, finding_id],
        ),
        (
            "INSERT INTO events(event_id,title,all_day,event_state,review_state,categories,public_source_id,publish,editorial_state,origin_type,origin_ref,is_active,created_at,created_by,updated_at,updated_by,note) "
            "VALUES (?,?,?,'AKTIVNI','NEZKONTROLOVANO',?,?,'NE','DRAFT','AUTO',?,'ANO',?,?,?,?,?)",
            [event_id, title, all_day, categories_json, source_id, finding_id, ts, ACTOR, ts, ACTOR, "Controlled batch materialization; unpublished"],
        ),
        (
            "INSERT INTO event_auto(event_id,title,all_day,event_state,categories,auto_updated_at,run_id,note) VALUES (?,?,?,'AKTIVNI',?,?,?,?)",
            [event_id, title, all_day, categories_json, ts, run_id, "Batch materialized from explicit finding"],
        ),
        (
            "INSERT INTO terms(term_id,event_id,date_from,date_to,term_state,is_active,created_at,created_by,updated_at,updated_by,note) "
            "VALUES (?,?,?,?,'AKTIVNI','ANO',?,?,?,?,?)",
            [term_id, event_id, date_from, date_to, ts, ACTOR, ts, ACTOR, "Controlled batch materialization"],
        ),
        (
            "INSERT INTO term_auto(term_id,event_id,date_from,date_to,term_state,auto_updated_at,run_id,note) VALUES (?,?,?,?,'AKTIVNI',?,?,?)",
            [term_id, event_id, date_from, date_to, ts, run_id, "Batch materialized from explicit finding"],
        ),
        (
            "INSERT INTO event_sources(link_id,event_id,source_id,source_role,active,first_seen_at,created_at,created_by,note) "
            "VALUES (?,?,?,'OTHER','ANO',?,?,?,?)",
            [link_id, event_id, source_id, finding.get("first_seen_at") or ts, ts, ACTOR, "Source attached during batch materialization test"],
        ),
        (
            "INSERT INTO history(history_id,entity_type,entity_id,field_key,old_value,new_value,origin,actor_id,action,run_id,request_id,reference_id,created_at,note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [f"HIS-MBAT-{event_id:06d}-E", "EVENT", str(event_id), None, None, title, "AUTO", ACTOR, "CREATE", run_id, request_id, finding_id, ts, "Controlled batch materialization"],
        ),
        (
            "INSERT INTO history(history_id,entity_type,entity_id,field_key,old_value,new_value,origin,actor_id,action,run_id,request_id,reference_id,created_at,note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [f"HIS-MBAT-{event_id:06d}-T", "TERM", term_id, None, None, f"{date_from}..{date_to}", "AUTO", ACTOR, "CREATE", run_id, request_id, finding_id, ts, "Controlled batch materialization"],
        ),
        (
            "UPDATE findings SET status='RESOLVED', event_id=?, resolution='MATERIALIZED_BATCH_TEST', resolved_at=?, resolved_by=?, updated_at=? WHERE finding_id=? AND status='OPEN'",
            [event_id, ts, ACTOR, ts, finding_id],
        ),
        (
            "UPDATE runs SET finished_at=?, status='SUCCESS', created_events=1 WHERE run_id=?",
            [ts, run_id],
        ),
    ]

    d1.execute_idempotent_request(
        request_id=request_id,
        operation="MATERIALIZE_BATCH_TEST",
        entity_type="EVENT",
        entity_id=str(event_id),
        statements=statements,
        actor=ACTOR,
    )

    event = q1(
        d1,
        "SELECT event_id,title,all_day,event_state,review_state,categories,public_source_id,publish,editorial_state,origin_type,origin_ref FROM events WHERE event_id=?",
        [event_id],
    )
    term = q1(
        d1,
        "SELECT term_id,event_id,date_from,date_to,term_state,is_active FROM terms WHERE event_id=?",
        [event_id],
    )
    auto = q1(
        d1,
        "SELECT event_id,title,all_day,event_state,categories,run_id FROM event_auto WHERE event_id=?",
        [event_id],
    )
    finding_after = q1(
        d1,
        "SELECT finding_id,status,event_id,resolution FROM findings WHERE finding_id=?",
        [finding_id],
    )

    if not event or not term or not auto or not finding_after:
        raise RuntimeError(f"read-back verification failed for finding {finding_id}")
    if event["publish"] != "NE" or event["editorial_state"] != "DRAFT" or event["review_state"] != "NEZKONTROLOVANO":
        raise RuntimeError(f"read-back safety verification failed for event {event_id}: {event}")
    if finding_after.get("status") != "RESOLVED" or int(finding_after.get("event_id")) != event_id:
        raise RuntimeError(f"finding resolution verification failed for {finding_id}: {finding_after}")

    return {
        "finding_id": finding_id,
        "status": "MATERIALIZED",
        "request_id": request_id,
        "event": event,
        "term": term,
        "event_auto": auto,
        "finding": finding_after,
        "read_back_verified": True,
    }


def main() -> int:
    d1 = build_d1()

    settings = {r["key"]: r.get("value") for r in d1.query(
        "SELECT key,value FROM settings WHERE key IN ('event_creation_enabled','scheduler_enabled','production_status')"
    ).rows}
    if settings.get("event_creation_enabled") != "NE":
        raise RuntimeError("materialize-batch-test requires event_creation_enabled=NE")
    if settings.get("scheduler_enabled") != "NE":
        raise RuntimeError("materialize-batch-test requires scheduler_enabled=NE")
    if settings.get("production_status") != "DISABLED":
        raise RuntimeError("materialize-batch-test requires production_status=DISABLED")

    before_count = int(q1(d1, "SELECT COUNT(*) AS c FROM events")["c"])
    findings = load_findings(d1)

    eligible = [
        f for f in findings
        if f.get("title") and f.get("date_from") and f.get("detail_url") and f.get("source_id")
    ]

    results = []
    materialized = 0
    for finding in eligible:
        if materialized >= MAX_EVENTS:
            break
        result = materialize_one(d1, finding)
        results.append(result)
        if result.get("status") == "MATERIALIZED":
            materialized += 1

    after_count = int(q1(d1, "SELECT COUNT(*) AS c FROM events")["c"])
    created_delta = after_count - before_count

    if created_delta != materialized:
        raise RuntimeError(
            f"batch count verification failed: created_delta={created_delta}, materialized={materialized}"
        )

    unsafe = d1.query(
        "SELECT event_id,title,publish,editorial_state,review_state FROM events "
        "WHERE origin_ref IS NOT NULL AND (publish<>'NE' OR editorial_state<>'DRAFT' OR review_state<>'NEZKONTROLOVANO')"
    ).rows
    if unsafe:
        raise RuntimeError(f"unsafe materialized events detected: {unsafe}")

    print(json.dumps({
        "ok": True,
        "mode": "MATERIALIZE_BATCH_TEST_WRITE",
        "max_events": MAX_EVENTS,
        "eligible_findings_seen": len(eligible),
        "materialized_count": materialized,
        "events_before": before_count,
        "events_after": after_count,
        "created_delta": created_delta,
        "results": results,
        "safety": {
            "publish": "NE",
            "editorial_state": "DRAFT",
            "review_state": "NEZKONTROLOVANO",
            "scheduler_enabled": settings.get("scheduler_enabled"),
            "production_status": settings.get("production_status"),
            "all_created_rows_read_back_verified": all(
                r.get("read_back_verified") is True
                for r in results
                if r.get("status") == "MATERIALIZED"
            ),
            "batch_count_verified": True,
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
