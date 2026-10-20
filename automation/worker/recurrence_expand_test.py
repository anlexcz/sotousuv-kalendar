from __future__ import annotations

import json
import os
from datetime import date, timedelta

from ai_enrichment_test_v2 import call_gemini, validate_ai
from detail_enrichment_test import build_d1, extract_dates, fetch_page
from materialize_test import q1

TARGET_EVENT_ID = 4
TARGET_FINDING_ID = "FND-B251B8DA2D0B4B88"


def easter_sunday(year: int) -> date:
    # Anonymous Gregorian algorithm.
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def czech_public_holidays(year: int) -> set[date]:
    easter = easter_sunday(year)
    return {
        date(year, 1, 1),
        easter - timedelta(days=2),  # Good Friday
        easter + timedelta(days=1),  # Easter Monday
        date(year, 5, 1),
        date(year, 5, 8),
        date(year, 7, 5),
        date(year, 7, 6),
        date(year, 9, 28),
        date(year, 10, 28),
        date(year, 11, 17),
        date(year, 12, 24),
        date(year, 12, 25),
        date(year, 12, 26),
    }


def expand_weekends_holidays(start: date, end: date) -> tuple[list[date], list[date], list[date]]:
    all_dates: list[date] = []
    weekend_dates: list[date] = []
    holiday_only_dates: list[date] = []

    holidays: set[date] = set()
    for year in range(start.year, end.year + 1):
        holidays |= czech_public_holidays(year)

    current = start
    while current <= end:
        is_weekend = current.weekday() >= 5
        is_holiday = current in holidays
        if is_weekend or is_holiday:
            all_dates.append(current)
            if is_weekend:
                weekend_dates.append(current)
            elif is_holiday:
                holiday_only_dates.append(current)
        current += timedelta(days=1)

    return all_dates, weekend_dates, holiday_only_dates


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("recurrence-expand-test requires GEMINI_API_KEY")

    d1 = build_d1()
    before_events = int(q1(d1, "SELECT COUNT(*) AS c FROM events")["c"])
    before_terms = int(q1(d1, "SELECT COUNT(*) AS c FROM terms")["c"])

    event = q1(
        d1,
        "SELECT event_id,title,publish,editorial_state,review_state,origin_ref FROM events WHERE event_id=?",
        [TARGET_EVENT_ID],
    )
    if not event or event.get("origin_ref") != TARGET_FINDING_ID:
        raise RuntimeError(f"target event/finding mismatch: {event}")

    detail = q1(
        d1,
        "SELECT value FROM observations "
        "WHERE finding_id=? AND field_key='detail_url' AND value_state='VALUE' "
        "ORDER BY observed_at DESC LIMIT 1",
        [TARGET_FINDING_ID],
    )
    if not detail or not detail.get("value"):
        raise RuntimeError("target finding has no detail_url observation")

    response, _html, visible = fetch_page(detail["value"])
    candidate_dates = sorted({x["date"] for x in extract_dates(event["title"] + " " + visible)})
    raw = call_gemini(api_key, event["title"], response.url, visible, candidate_dates)
    valid, errors, clean = validate_ai(raw, set(candidate_dates), event["title"], visible)

    if not valid or clean.get("relevance") != "EVENT" or clean.get("term_semantics") != "RECURRENCE":
        raise RuntimeError(f"AI did not return valid recurrence: errors={errors}, ai={clean}")
    if clean.get("recurrence_type") != "WEEKENDS_HOLIDAYS":
        raise RuntimeError(f"unsupported recurrence type: {clean.get('recurrence_type')}")

    start_raw = clean.get("recurrence_date_from")
    end_raw = clean.get("recurrence_date_to")
    if not start_raw or not end_raw:
        raise RuntimeError("recurrence boundaries missing")

    start = date.fromisoformat(start_raw)
    end = date.fromisoformat(end_raw)
    expanded, weekends, holiday_only = expand_weekends_holidays(start, end)

    stored_terms = d1.query(
        "SELECT term_id,date_from,date_to,term_state,is_active FROM terms WHERE event_id=? ORDER BY date_from,date_to,term_id",
        [TARGET_EVENT_ID],
    ).rows

    after_events = int(q1(d1, "SELECT COUNT(*) AS c FROM events")["c"])
    after_terms = int(q1(d1, "SELECT COUNT(*) AS c FROM terms")["c"])

    safe = before_events == after_events and before_terms == after_terms
    output = {
        "ok": safe and bool(expanded),
        "mode": "RECURRENCE_EXPAND_READ_ONLY_TEST",
        "read_only": True,
        "event": event,
        "ai": clean,
        "expansion": {
            "rule": "WEEKENDS_HOLIDAYS",
            "country": "CZ",
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "term_count": len(expanded),
            "weekend_date_count": len(weekends),
            "weekday_public_holiday_count": len(holiday_only),
            "weekday_public_holidays": [d.isoformat() for d in holiday_only],
            "dates": [d.isoformat() for d in expanded],
        },
        "current_stored_terms": stored_terms,
        "next_step_if_approved": "replace current continuous interval with one single-day term per expanded date, atomically",
        "safety": {
            "events_before": before_events,
            "events_after": after_events,
            "terms_before": before_terms,
            "terms_after": after_terms,
            "writes_performed": False,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["ok"] else 22


if __name__ == "__main__":
    raise SystemExit(main())
