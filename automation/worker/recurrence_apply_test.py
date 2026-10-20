from __future__ import annotations

import json
from datetime import date

from detail_enrichment_test import build_d1, extract_dates, fetch_page
from materialize_test import now_iso, q1
from recurrence_expand_test import expand_weekends_holidays

TARGET_EVENT_ID = 4
TARGET_FINDING_ID = "FND-B251B8DA2D0B4B88"
OLD_TERM_ID = "TRM-000004-001"
EXPECTED_START = "2026-03-28"
EXPECTED_END = "2026-11-17"
EXPECTED_COUNT = 76
ACTOR = "recurrence-apply-test"
REQUEST_ID = "recurrence-apply-test:event-4:v1"
RUN_ID = "RUN-RECUR-000004-V1"


def main() -> int:
    d1 = build_d1()

    settings = {r["key"]: r.get("value") for r in d1.query(
        "SELECT key,value FROM settings WHERE key IN ('event_creation_enabled','scheduler_enabled','production_status')"
    ).rows}
    if settings.get("event_creation_enabled") != "NE":
        raise RuntimeError("recurrence-apply-test requires event_creation_enabled=NE")
    if settings.get("scheduler_enabled") != "NE":
        raise RuntimeError("recurrence-apply-test requires scheduler_enabled=NE")
    if settings.get("production_status") != "DISABLED":
        raise RuntimeError("recurrence-apply-test requires production_status=DISABLED")

    event = q1(
        d1,
        "SELECT event_id,title,publish,editorial_state,review_state,origin_ref FROM events WHERE event_id=?",
        [TARGET_EVENT_ID],
    )
    if not event or event.get("origin_ref") != TARGET_FINDING_ID:
        raise RuntimeError(f"target event/finding mismatch: {event}")
    if event.get("publish") != "NE" or event.get("editorial_state") != "DRAFT":
        raise RuntimeError(f"target event is not safely unpublished draft: {event}")

    start = date.fromisoformat(EXPECTED_START)
    end = date.fromisoformat(EXPECTED_END)
    expanded, weekends, holiday_only = expand_weekends_holidays(start, end)
    dates = [d.isoformat() for d in expanded]
    if len(dates) != EXPECTED_COUNT or dates[0] != EXPECTED_START or dates[-1] != EXPECTED_END:
        raise RuntimeError(f"deterministic recurrence expansion changed unexpectedly: count={len(dates)}")

    # Reconfirm both recurrence boundaries still occur explicitly on the current source page.
    detail = q1(
        d1,
        "SELECT value FROM observations WHERE finding_id=? AND field_key='detail_url' AND value_state='VALUE' "
        "ORDER BY observed_at DESC LIMIT 1",
        [TARGET_FINDING_ID],
    )
    if not detail or not detail.get("value"):
        raise RuntimeError("target finding has no detail_url observation")
    response, _html, visible = fetch_page(detail["value"])
    source_dates = {x["date"] for x in extract_dates(event["title"] + " " + visible)}
    if EXPECTED_START not in source_dates or EXPECTED_END not in source_dates:
        raise RuntimeError(f"source no longer confirms approved recurrence boundaries: {sorted(source_dates)}")

    active_before = d1.query(
        "SELECT term_id,date_from,date_to,term_state,is_active FROM terms WHERE event_id=? AND is_active='ANO' ORDER BY term_id",
        [TARGET_EVENT_ID],
    ).rows

    # Idempotent read path: already repaired exactly as approved.
    active_dates_before = [r["date_from"] for r in active_before if r.get("date_from") == r.get("date_to")]
    old_after_prior_apply = q1(
        d1,
        "SELECT term_id,is_active FROM terms WHERE term_id=? AND event_id=?",
        [OLD_TERM_ID, TARGET_EVENT_ID],
    )
    if (
        len(active_before) == EXPECTED_COUNT
        and active_dates_before == dates
        and old_after_prior_apply
        and old_after_prior_apply.get("is_active") == "NE"
    ):
        print(json.dumps({
            "ok": True,
            "mode": "RECURRENCE_APPLY_TEST_IDEMPOTENT",
            "already_applied": True,
            "event": event,
            "active_term_count": len(active_before),
            "old_interval_inactive": True,
            "publish": event.get("publish"),
        }, ensure_ascii=False, indent=2))
        return 0

    if active_before != [{
        "term_id": OLD_TERM_ID,
        "date_from": EXPECTED_START,
        "date_to": EXPECTED_END,
        "term_state": "AKTIVNI",
        "is_active": "ANO",
    }]:
        raise RuntimeError(f"refusing write because current active terms differ from approved pre-state: {active_before}")

    ts = now_iso()
    statements: list[tuple[str, list]] = [
        (
            "INSERT INTO runs(run_id,run_type,started_at,status,input_count,actor,note) VALUES (?,? ,?,'STARTED',1,?,?)",
            [RUN_ID, "RECURRENCE_APPLY_TEST", ts, ACTOR, TARGET_FINDING_ID],
        ),
        (
            "UPDATE terms SET is_active='NE', row_version=row_version+1, updated_at=?, updated_by=?, "
            "note=? WHERE term_id=? AND event_id=? AND is_active='ANO' AND date_from=? AND date_to=?",
            [ts, ACTOR, "Superseded by deterministic recurrence expansion", OLD_TERM_ID, TARGET_EVENT_ID, EXPECTED_START, EXPECTED_END],
        ),
        (
            "DELETE FROM term_auto WHERE term_id=? AND event_id=?",
            [OLD_TERM_ID, TARGET_EVENT_ID],
        ),
        (
            "INSERT INTO history(history_id,entity_type,entity_id,field_key,old_value,new_value,origin,actor_id,action,run_id,request_id,reference_id,created_at,note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                "HIS-RECUR-000004-OLD",
                "TERM",
                OLD_TERM_ID,
                "is_active",
                "ANO",
                "NE",
                "AUTO",
                ACTOR,
                "SUPERSEDE",
                RUN_ID,
                REQUEST_ID,
                TARGET_FINDING_ID,
                ts,
                "Continuous interval replaced by approved WEEKENDS_HOLIDAYS expansion",
            ],
        ),
    ]

    for idx, day in enumerate(dates, start=2):
        term_id = f"TRM-{TARGET_EVENT_ID:06d}-{idx:03d}"
        statements.extend([
            (
                "INSERT INTO terms(term_id,event_id,date_from,date_to,term_state,is_active,created_at,created_by,updated_at,updated_by,note) "
                "VALUES (?,?,?,?,'AKTIVNI','ANO',?,?,?,?,?)",
                [term_id, TARGET_EVENT_ID, day, day, ts, ACTOR, ts, ACTOR, "Expanded from WEEKENDS_HOLIDAYS recurrence"],
            ),
            (
                "INSERT INTO term_auto(term_id,event_id,date_from,date_to,term_state,auto_updated_at,run_id,note) "
                "VALUES (?,?,?,?,'AKTIVNI',?,?,?)",
                [term_id, TARGET_EVENT_ID, day, day, ts, RUN_ID, "Expanded from WEEKENDS_HOLIDAYS recurrence"],
            ),
            (
                "INSERT INTO history(history_id,entity_type,entity_id,field_key,old_value,new_value,origin,actor_id,action,run_id,request_id,reference_id,created_at,note) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    f"HIS-RECUR-000004-{idx:03d}",
                    "TERM",
                    term_id,
                    None,
                    None,
                    day,
                    "AUTO",
                    ACTOR,
                    "CREATE",
                    RUN_ID,
                    REQUEST_ID,
                    TARGET_FINDING_ID,
                    ts,
                    "Created by deterministic recurrence expansion",
                ],
            ),
        ])

    statements.extend([
        (
            "INSERT INTO history(history_id,entity_type,entity_id,field_key,old_value,new_value,origin,actor_id,action,run_id,request_id,reference_id,created_at,note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                "HIS-RECUR-000004-SUMMARY",
                "EVENT",
                str(TARGET_EVENT_ID),
                "terms",
                f"{EXPECTED_START}..{EXPECTED_END}",
                f"WEEKENDS_HOLIDAYS:{EXPECTED_COUNT}_single_day_terms",
                "AUTO",
                ACTOR,
                "EXPAND_RECURRENCE",
                RUN_ID,
                REQUEST_ID,
                TARGET_FINDING_ID,
                ts,
                "Approved deterministic expansion; event remains unpublished",
            ],
        ),
        (
            "UPDATE runs SET finished_at=?, status='SUCCESS', updated_fields=? WHERE run_id=?",
            [ts, EXPECTED_COUNT + 1, RUN_ID],
        ),
    ])

    d1.execute_idempotent_request(
        request_id=REQUEST_ID,
        operation="RECURRENCE_APPLY_TEST",
        entity_type="EVENT",
        entity_id=str(TARGET_EVENT_ID),
        statements=statements,
        actor=ACTOR,
    )

    active_after = d1.query(
        "SELECT term_id,date_from,date_to,term_state,is_active FROM terms WHERE event_id=? AND is_active='ANO' ORDER BY date_from,term_id",
        [TARGET_EVENT_ID],
    ).rows
    old_after = q1(
        d1,
        "SELECT term_id,date_from,date_to,term_state,is_active FROM terms WHERE term_id=?",
        [OLD_TERM_ID],
    )
    auto_after = d1.query(
        "SELECT term_id,date_from,date_to,term_state FROM term_auto WHERE event_id=? ORDER BY date_from,term_id",
        [TARGET_EVENT_ID],
    ).rows
    event_after = q1(
        d1,
        "SELECT event_id,title,publish,editorial_state,review_state FROM events WHERE event_id=?",
        [TARGET_EVENT_ID],
    )

    active_dates_after = [r["date_from"] for r in active_after]
    if len(active_after) != EXPECTED_COUNT or active_dates_after != dates:
        raise RuntimeError("read-back failed: active recurrence terms do not match approved expansion")
    if any(r["date_from"] != r["date_to"] for r in active_after):
        raise RuntimeError("read-back failed: a new recurrence term is not single-day")
    if not old_after or old_after.get("is_active") != "NE":
        raise RuntimeError(f"read-back failed: old interval is not inactive: {old_after}")
    if len(auto_after) != EXPECTED_COUNT or [r["date_from"] for r in auto_after] != dates:
        raise RuntimeError("read-back failed: term_auto does not match active recurrence terms")
    if not event_after or event_after.get("publish") != "NE" or event_after.get("editorial_state") != "DRAFT":
        raise RuntimeError(f"event safety state changed unexpectedly: {event_after}")

    print(json.dumps({
        "ok": True,
        "mode": "RECURRENCE_APPLY_TEST_WRITE",
        "request_id": REQUEST_ID,
        "event": event_after,
        "recurrence": {
            "type": "WEEKENDS_HOLIDAYS",
            "date_from": EXPECTED_START,
            "date_to": EXPECTED_END,
            "active_term_count": len(active_after),
            "weekend_date_count": len(weekends),
            "weekday_public_holiday_count": len(holiday_only),
            "first_active_term": active_after[0],
            "last_active_term": active_after[-1],
        },
        "old_interval": old_after,
        "term_auto_count": len(auto_after),
        "safety": {
            "atomic_request": True,
            "old_interval_preserved_but_inactive": True,
            "publish": event_after.get("publish"),
            "editorial_state": event_after.get("editorial_state"),
            "scheduler_enabled": settings.get("scheduler_enabled"),
            "production_status": settings.get("production_status"),
            "read_back_verified": True,
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
