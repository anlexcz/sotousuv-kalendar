from __future__ import annotations

import json

from ai_enrichment_test_v2 import call_gemini, validate_ai
from detail_enrichment_test import build_d1, extract_dates, fetch_page
from materialize_test import q1
import os

TARGET_EVENT_ID = 4
TARGET_FINDING_ID = "FND-B251B8DA2D0B4B88"


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("recurrence-test requires GEMINI_API_KEY")

    d1 = build_d1()
    before_events = int(q1(d1, "SELECT COUNT(*) AS c FROM events")["c"])

    event = q1(
        d1,
        "SELECT event_id,title,publish,editorial_state,review_state,origin_ref FROM events WHERE event_id=?",
        [TARGET_EVENT_ID],
    )
    if not event or event.get("origin_ref") != TARGET_FINDING_ID:
        raise RuntimeError(f"target event/finding mismatch: {event}")

    detail = q1(
        d1,
        "SELECT value,evidence_ref FROM observations "
        "WHERE finding_id=? AND field_key='detail_url' AND value_state='VALUE' "
        "ORDER BY observed_at DESC LIMIT 1",
        [TARGET_FINDING_ID],
    )
    if not detail or not detail.get("value"):
        raise RuntimeError("target finding has no detail_url observation")

    response, _html, visible = fetch_page(detail["value"])
    dates = sorted({x["date"] for x in extract_dates(event["title"] + " " + visible)})
    if not dates:
        raise RuntimeError("no explicit candidate dates found on source")

    raw = call_gemini(api_key, event["title"], response.url, visible, dates)
    valid, errors, clean = validate_ai(raw, set(dates), event["title"], visible)

    after_events = int(q1(d1, "SELECT COUNT(*) AS c FROM events")["c"])
    is_recurrence = valid and clean.get("relevance") == "EVENT" and clean.get("term_semantics") == "RECURRENCE"

    print(json.dumps({
        "ok": bool(is_recurrence and before_events == after_events),
        "mode": "RECURRENCE_READ_ONLY_TEST",
        "read_only": True,
        "event": event,
        "detail_url": response.url,
        "candidate_dates": dates,
        "validation_ok": valid,
        "validation_errors": errors,
        "ai": clean,
        "expected": {
            "relevance": "EVENT",
            "term_semantics": "RECURRENCE",
            "materialization_allowed": False,
        },
        "safety": {
            "events_before": before_events,
            "events_after": after_events,
            "writes_performed": False,
        },
    }, ensure_ascii=False, indent=2))
    return 0 if is_recurrence and before_events == after_events else 21


if __name__ == "__main__":
    raise SystemExit(main())
