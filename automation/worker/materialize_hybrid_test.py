from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

from ai_enrichment_test_v2 import call_gemini, validate_ai
from detail_enrichment_test import build_d1, extract_dates, fetch_page
from materialize_test import allocate_event_id, ensure_allocator, now_iso, q1
from resolver_test import infer_categories, load_findings

ACTOR = "materialize-hybrid-test"
MAX_EVENTS = 5
TIME_RE = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)")


def existing_by_origin(d1, finding_id: str):
    return q1(d1, "SELECT event_id,title,publish,editorial_state FROM events WHERE origin_ref=? LIMIT 1", [finding_id])


def duplicate_by_title_date(d1, title: str, date_from: str):
    return q1(
        d1,
        "SELECT e.event_id,e.title FROM events e JOIN terms t ON t.event_id=e.event_id "
        "WHERE lower(e.title)=lower(?) AND t.date_from=? AND e.is_active='ANO' AND t.is_active='ANO' LIMIT 1",
        [title, date_from],
    )


def ai_candidate(api_key: str, finding: dict) -> dict:
    title = (finding.get("title") or "").strip()
    detail_url = finding.get("detail_url")
    if not title or not detail_url:
        return {"status": "SKIPPED_MISSING_REQUIRED_DATA"}

    response, _html, visible = fetch_page(detail_url)
    if response.status_code != 200:
        return {"status": "SKIPPED_HTTP", "http_status": response.status_code}

    dates = sorted({x["date"] for x in extract_dates(title + " " + visible)})
    if not dates:
        return {"status": "SKIPPED_NO_CANDIDATE_DATES"}

    model_result = call_gemini(api_key, title, response.url, visible, dates)
    valid, errors, clean = validate_ai(model_result, set(dates), title, visible)
    if not valid:
        return {"status": "SKIPPED_AI_VALIDATION", "errors": errors, "ai": clean}
    if clean.get("relevance") != "EVENT" or float(clean.get("confidence", 0)) < 0.9:
        return {"status": "SKIPPED_AI_NOT_CONFIDENT_EVENT", "ai": clean}

    terms = clean.get("terms") or []
    today = datetime.now(timezone.utc).date().isoformat()
    if not terms or max(t["date_to"] for t in terms) < today:
        return {"status": "SKIPPED_HISTORICAL", "ai": clean}

    if not TIME_RE.search(visible):
        return {"status": "SKIPPED_NO_EXPLICIT_TIME", "ai": clean}

    categories = clean.get("categories") or infer_categories(title)
    return {
        "status": "READY_AI",
        "title": title,
        "terms": terms,
        "categories": categories,
        "all_day": "NE",
        "final_url": response.url,
        "ai": clean,
    }


def deterministic_candidate(finding: dict) -> dict:
    title = (finding.get("title") or "").strip()
    date_from = finding.get("date_from")
    date_to = finding.get("date_to") or date_from
    detail_url = finding.get("detail_url")
    if not title or not date_from or not detail_url:
        return {"status": "NOT_DETERMINISTIC_READY"}

    response, _html, visible = fetch_page(detail_url)
    if response.status_code != 200:
        return {"status": "SKIPPED_HTTP", "http_status": response.status_code}

    seen_dates = {x["date"] for x in extract_dates(title + " " + visible)}
    if date_from not in seen_dates or date_to not in seen_dates:
        return {"status": "SKIPPED_TERM_NOT_RECONFIRMED"}
    if date_to < datetime.now(timezone.utc).date().isoformat():
        return {"status": "SKIPPED_HISTORICAL"}
    if not TIME_RE.search(visible):
        return {"status": "SKIPPED_NO_EXPLICIT_TIME"}

    return {
        "status": "READY_DETERMINISTIC",
        "title": title,
        "terms": [{"date_from": date_from, "date_to": date_to}],
        "categories": infer_categories(title),
        "all_day": "NE",
        "final_url": response.url,
    }


def materialize_one(d1, finding: dict, candidate: dict) -> dict:
    finding_id = finding["finding_id"]
    source_id = finding.get("source_id")
    if not source_id:
        return {"finding_id": finding_id, "status": "SKIPPED_MISSING_SOURCE"}

    existing = existing_by_origin(d1, finding_id)
    if existing:
        return {"finding_id": finding_id, "status": "SKIPPED_ALREADY_MATERIALIZED", "event": existing}

    title = candidate["title"]
    terms = candidate["terms"]
    first_date = min(t["date_from"] for t in terms)
    duplicate = duplicate_by_title_date(d1, title, first_date)
    if duplicate:
        return {"finding_id": finding_id, "status": "SKIPPED_DUPLICATE", "duplicate": duplicate}

    ensure_allocator(d1)
    event_id = allocate_event_id(d1)
    request_id = f"materialize-hybrid-test:{finding_id}:v1"
    run_id = f"RUN-MATHYB-{event_id:06d}"
    link_id = f"ELS-{event_id:06d}-{source_id}"
    ts = now_iso()
    categories_json = json.dumps(candidate["categories"], ensure_ascii=False, separators=(",", ":"))
    origin_note = "AI validated" if candidate["status"] == "READY_AI" else "Deterministic"

    statements = [
        ("INSERT INTO runs(run_id,run_type,started_at,status,input_count,actor,note) VALUES (?,? ,?,'STARTED',1,?,?)",
         [run_id, "MATERIALIZE_HYBRID_TEST", ts, ACTOR, finding_id]),
        ("INSERT INTO events(event_id,title,all_day,event_state,review_state,categories,public_source_id,publish,editorial_state,origin_type,origin_ref,is_active,created_at,created_by,updated_at,updated_by,note) "
         "VALUES (?,?,?,'AKTIVNI','NEZKONTROLOVANO',?,?,'NE','DRAFT','AUTO',?,'ANO',?,?,?,?,?)",
         [event_id, title, candidate["all_day"], categories_json, source_id, finding_id, ts, ACTOR, ts, ACTOR, f"Controlled hybrid materialization; {origin_note}; unpublished"]),
        ("INSERT INTO event_auto(event_id,title,all_day,event_state,categories,auto_updated_at,run_id,note) VALUES (?,?,?,'AKTIVNI',?,?,?,?)",
         [event_id, title, candidate["all_day"], categories_json, ts, run_id, origin_note]),
        ("INSERT INTO event_sources(link_id,event_id,source_id,source_role,active,first_seen_at,created_at,created_by,note) VALUES (?,?,?,'OTHER','ANO',?,?,?,?)",
         [link_id, event_id, source_id, finding.get("first_seen_at") or ts, ts, ACTOR, "Hybrid materialization source"]),
    ]

    for idx, term in enumerate(terms, 1):
        term_id = f"TRM-{event_id:06d}-{idx:03d}"
        df, dt = term["date_from"], term["date_to"]
        statements.extend([
            ("INSERT INTO terms(term_id,event_id,date_from,date_to,term_state,is_active,created_at,created_by,updated_at,updated_by,note) VALUES (?,?,?,?,'AKTIVNI','ANO',?,?,?,?,?)",
             [term_id, event_id, df, dt, ts, ACTOR, ts, ACTOR, origin_note]),
            ("INSERT INTO term_auto(term_id,event_id,date_from,date_to,term_state,auto_updated_at,run_id,note) VALUES (?,?,?,?,'AKTIVNI',?,?,?)",
             [term_id, event_id, df, dt, ts, run_id, origin_note]),
            ("INSERT INTO history(history_id,entity_type,entity_id,field_key,old_value,new_value,origin,actor_id,action,run_id,request_id,reference_id,created_at,note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
             [f"HIS-MHYB-{event_id:06d}-T{idx:03d}", "TERM", term_id, None, None, f"{df}..{dt}", "AUTO", ACTOR, "CREATE", run_id, request_id, finding_id, ts, origin_note]),
        ])

    statements.extend([
        ("INSERT INTO history(history_id,entity_type,entity_id,field_key,old_value,new_value,origin,actor_id,action,run_id,request_id,reference_id,created_at,note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
         [f"HIS-MHYB-{event_id:06d}-E", "EVENT", str(event_id), None, None, title, "AUTO", ACTOR, "CREATE", run_id, request_id, finding_id, ts, origin_note]),
        ("UPDATE findings SET status='RESOLVED', event_id=?, resolution='MATERIALIZED_HYBRID_TEST', resolved_at=?, resolved_by=?, updated_at=? WHERE finding_id=? AND status='OPEN'",
         [event_id, ts, ACTOR, ts, finding_id]),
        ("UPDATE runs SET finished_at=?, status='SUCCESS', created_events=1 WHERE run_id=?", [ts, run_id]),
    ])

    d1.execute_idempotent_request(
        request_id=request_id,
        operation="MATERIALIZE_HYBRID_TEST",
        entity_type="EVENT",
        entity_id=str(event_id),
        statements=statements,
        actor=ACTOR,
    )

    event = q1(d1, "SELECT event_id,title,all_day,event_state,review_state,categories,public_source_id,publish,editorial_state,origin_type,origin_ref FROM events WHERE event_id=?", [event_id])
    terms_after = d1.query("SELECT term_id,event_id,date_from,date_to,term_state,is_active FROM terms WHERE event_id=? ORDER BY date_from,date_to,term_id", [event_id]).rows
    finding_after = q1(d1, "SELECT finding_id,status,event_id,resolution FROM findings WHERE finding_id=?", [finding_id])

    if not event or len(terms_after) != len(terms) or not finding_after:
        raise RuntimeError(f"read-back verification failed for {finding_id}")
    if event["publish"] != "NE" or event["editorial_state"] != "DRAFT" or event["review_state"] != "NEZKONTROLOVANO":
        raise RuntimeError(f"unsafe event after read-back: {event}")
    if finding_after.get("status") != "RESOLVED" or int(finding_after.get("event_id")) != event_id:
        raise RuntimeError(f"finding resolution verification failed: {finding_after}")

    return {
        "finding_id": finding_id,
        "status": "MATERIALIZED",
        "source_mode": candidate["status"],
        "request_id": request_id,
        "event": event,
        "terms": terms_after,
        "finding": finding_after,
        "read_back_verified": True,
        "ai": candidate.get("ai"),
    }


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("materialize-hybrid-test requires GEMINI_API_KEY")

    d1 = build_d1()
    settings = {r["key"]: r.get("value") for r in d1.query(
        "SELECT key,value FROM settings WHERE key IN ('event_creation_enabled','scheduler_enabled','production_status')"
    ).rows}
    if settings.get("event_creation_enabled") != "NE" or settings.get("scheduler_enabled") != "NE" or settings.get("production_status") != "DISABLED":
        raise RuntimeError(f"unsafe settings for hybrid test: {settings}")

    before_count = int(q1(d1, "SELECT COUNT(*) AS c FROM events")["c"])
    results = []
    materialized = 0

    for finding in load_findings(d1):
        if materialized >= MAX_EVENTS:
            break
        det = deterministic_candidate(finding)
        candidate = det
        if det.get("status") == "NOT_DETERMINISTIC_READY":
            candidate = ai_candidate(api_key, finding)

        if candidate.get("status") not in {"READY_DETERMINISTIC", "READY_AI"}:
            results.append({"finding_id": finding["finding_id"], **candidate})
            continue

        result = materialize_one(d1, finding, candidate)
        results.append(result)
        if result.get("status") == "MATERIALIZED":
            materialized += 1

    after_count = int(q1(d1, "SELECT COUNT(*) AS c FROM events")["c"])
    if after_count - before_count != materialized:
        raise RuntimeError(f"hybrid batch count mismatch: before={before_count} after={after_count} materialized={materialized}")

    unsafe = d1.query(
        "SELECT event_id,title,publish,editorial_state,review_state FROM events "
        "WHERE origin_ref IS NOT NULL AND (publish<>'NE' OR editorial_state<>'DRAFT' OR review_state<>'NEZKONTROLOVANO')"
    ).rows
    if unsafe:
        raise RuntimeError(f"unsafe materialized events detected: {unsafe}")

    print(json.dumps({
        "ok": True,
        "mode": "MATERIALIZE_HYBRID_TEST_WRITE",
        "max_events": MAX_EVENTS,
        "materialized_count": materialized,
        "events_before": before_count,
        "events_after": after_count,
        "created_delta": after_count - before_count,
        "results": results,
        "safety": {
            "publish": "NE",
            "editorial_state": "DRAFT",
            "review_state": "NEZKONTROLOVANO",
            "scheduler_enabled": settings.get("scheduler_enabled"),
            "production_status": settings.get("production_status"),
            "all_day_ne_requires_explicit_clock_time": True,
            "ai_dates_must_exist_in_source": True,
            "all_materialized_rows_read_back_verified": all(r.get("read_back_verified") is True for r in results if r.get("status") == "MATERIALIZED"),
            "batch_count_verified": True,
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
