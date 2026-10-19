from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKER_DIR = Path(__file__).resolve().parent
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

from d1 import D1Adapter
from structured_sources import (
    StructuredCandidate,
    fetch_text,
    parse_ical,
    parse_rss_atom,
    stable_finding_id,
    stable_observation_id,
)

TARGET_PER_STRATEGY = 2
MAX_SOURCE_ATTEMPTS_PER_STRATEGY = 8
MAX_ITEMS_PER_SOURCE = 5

ICAL_FIXTURE = """BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Sotousuv Kalendar//Test//CS\r\nBEGIN:VEVENT\r\nUID:test-ical-parser-001\r\nSUMMARY:Testovací kalendářová akce\r\nDTSTART;VALUE=DATE:20300115\r\nDTEND;VALUE=DATE:20300116\r\nURL:https://example.invalid/test-event\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"""


def build_d1() -> D1Adapter:
    return D1Adapter(
        account_id=os.environ["CLOUDFLARE_ACCOUNT_ID"],
        database_id=os.environ["CLOUDFLARE_D1_DATABASE_ID"],
        api_token=os.environ["CLOUDFLARE_API_TOKEN"],
    )


def store_candidate(
    d1: D1Adapter,
    source_id: str,
    candidate: StructuredCandidate,
    observed_at: str,
    evidence_ref: str,
) -> str:
    finding_id = stable_finding_id(source_id, candidate.identity)
    note = {
        "detail_url": candidate.detail_url,
        "published_at": candidate.published_at,
        "raw_kind": candidate.raw_kind,
        "structured_source_test": True,
    }

    d1.query(
        "INSERT INTO findings (finding_id, finding_type, status, title_hint, source_id, first_seen_at, "
        "last_seen_at, next_check_at, updated_at, note) "
        "VALUES (?, 'STRUCTURED_SOURCE_ITEM', 'OPEN', ?, ?, ?, ?, datetime(?, '+7 days'), ?, ?) "
        "ON CONFLICT(finding_id) DO UPDATE SET title_hint = excluded.title_hint, last_seen_at = excluded.last_seen_at, "
        "next_check_at = excluded.next_check_at, updated_at = excluded.updated_at, note = excluded.note",
        [finding_id, candidate.title, source_id, observed_at, observed_at, observed_at, observed_at,
         json.dumps(note, ensure_ascii=False)],
    )

    fields: list[tuple[str, str]] = [("title", candidate.title)]
    if candidate.detail_url:
        fields.append(("detail_url", candidate.detail_url))
    if candidate.event_date_from:
        fields.append(("date_from", candidate.event_date_from))
    if candidate.event_date_to:
        fields.append(("date_to", candidate.event_date_to))
    if candidate.published_at:
        fields.append(("source_published_at", candidate.published_at))

    for field_key, value in fields:
        observation_id = stable_observation_id(source_id, finding_id, field_key, value)
        d1.query(
            "INSERT OR IGNORE INTO observations (observation_id, source_id, subject_type, subject_ref, finding_id, "
            "field_key, value_state, value, observed_at, extraction_method, evidence_ref, note) "
            "VALUES (?, ?, 'FINDING', ?, ?, ?, 'VALUE', ?, ?, 'STRUCTURED_FEED', ?, ?)",
            [observation_id, source_id, finding_id, finding_id, field_key, value, observed_at,
             evidence_ref, f"Parsed deterministically from {candidate.raw_kind}; no LLM"],
        )
    return finding_id


def _looks_like_valid_ical(text: str) -> bool:
    upper = text.lstrip("\ufeff\r\n \t").upper()
    return "BEGIN:VCALENDAR" in upper and "END:VCALENDAR" in upper


def _ical_parser_self_test() -> bool:
    parsed = parse_ical(ICAL_FIXTURE, "https://example.invalid/calendar.ics", limit=5)
    return bool(
        len(parsed) == 1
        and parsed[0].title == "Testovací kalendářová akce"
        and parsed[0].event_date_from == "2030-01-15"
    )


def process_source(d1: D1Adapter, row: dict, strategy: str) -> dict:
    source_id = row["source_id"]
    fetch_url = row.get("feed_url") if strategy == "RSS_ATOM_FIRST" else row.get("calendar_url")
    if not fetch_url:
        raise RuntimeError("missing structured endpoint")

    accept = (
        "application/rss+xml,application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.1"
        if strategy == "RSS_ATOM_FIRST"
        else "text/calendar,text/plain;q=0.9,*/*;q=0.1"
    )
    text, status_code, headers = fetch_text(fetch_url, accept)
    endpoint_state = "CONTENT"

    if strategy == "RSS_ATOM_FIRST":
        candidates = parse_rss_atom(text, fetch_url, limit=MAX_ITEMS_PER_SOURCE)
        if not candidates:
            raise RuntimeError("RSS/Atom parser returned zero candidates")
    else:
        if not text.strip():
            candidates = []
            endpoint_state = "EMPTY_RESPONSE"
        elif _looks_like_valid_ical(text):
            candidates = parse_ical(text, fetch_url, limit=MAX_ITEMS_PER_SOURCE)
            endpoint_state = "EMPTY_VCALENDAR" if not candidates else "VCALENDAR"
        else:
            preview = " ".join(text[:160].split())
            raise RuntimeError(f"calendar endpoint returned non-iCal content; preview={preview!r}")

    observed_at = datetime.now(timezone.utc).isoformat()
    finding_ids = [store_candidate(d1, source_id, c, observed_at, fetch_url) for c in candidates]
    content_hash = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    next_check_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    d1.query(
        "UPDATE sources SET last_checked_at = ?, last_success_at = ?, last_http_status = ?, consecutive_errors = 0, "
        "content_hash = ?, etag = ?, last_modified = ?, next_check_at = ? WHERE source_id = ?",
        [observed_at, observed_at, status_code, content_hash, headers.get("ETag"),
         headers.get("Last-Modified"), next_check_at, source_id],
    )

    return {
        "source_id": source_id,
        "label": row.get("label"),
        "strategy": strategy,
        "endpoint": fetch_url,
        "status_code": status_code,
        "endpoint_state": endpoint_state,
        "parsed_items": len(candidates),
        "finding_ids": finding_ids,
        "sample": [
            {
                "title": c.title,
                "date_from": c.event_date_from,
                "date_to": c.event_date_to,
                "detail_url": c.detail_url,
                "source_published_at": c.published_at,
                "kind": c.raw_kind,
            }
            for c in candidates[:3]
        ],
    }


def candidate_sources(d1: D1Adapter, strategy: str) -> list[dict]:
    endpoint_col = "feed_url" if strategy == "RSS_ATOM_FIRST" else "calendar_url"
    return d1.query(
        f"SELECT source_id, label, url, feed_url, calendar_url, active, fetch_strategy, priority "
        f"FROM sources WHERE fetch_strategy = ? AND {endpoint_col} IS NOT NULL AND TRIM({endpoint_col}) <> '' "
        "AND migration_status IN ('MIGRATE','MIGRATE_INACTIVE','FALLBACK_ONLY','ALREADY_PILOT') "
        "ORDER BY COALESCE(priority, 999), source_id LIMIT ?",
        [strategy, MAX_SOURCE_ATTEMPTS_PER_STRATEGY],
    ).rows


def main() -> int:
    d1 = build_d1()
    parser_self_test_ok = _ical_parser_self_test()
    successes: list[dict] = []
    errors: list[dict] = []

    for strategy in ("RSS_ATOM_FIRST", "ICAL_FIRST"):
        strategy_successes = 0
        for row in candidate_sources(d1, strategy):
            if strategy_successes >= TARGET_PER_STRATEGY:
                break
            try:
                result = process_source(d1, row, strategy)
                successes.append(result)
                strategy_successes += 1
            except Exception as exc:
                errors.append({
                    "source_id": row.get("source_id"),
                    "label": row.get("label"),
                    "strategy": strategy,
                    "error": str(exc)[:500],
                })

    active_rows = d1.query("SELECT COUNT(*) AS count FROM sources WHERE active = 'ANO'").rows
    active_count = int(active_rows[0]["count"]) if active_rows else 0
    rss_ok = sum(1 for x in successes if x["strategy"] == "RSS_ATOM_FIRST")
    ical_reachable = sum(1 for x in successes if x["strategy"] == "ICAL_FIRST")
    ical_with_items = sum(1 for x in successes if x["strategy"] == "ICAL_FIRST" and x["parsed_items"] > 0)

    result = {
        "ok": rss_ok >= 1 and ical_reachable >= 1 and parser_self_test_ok and active_count == 0,
        "rss_sources_processed": rss_ok,
        "ical_endpoints_reached": ical_reachable,
        "ical_sources_with_items": ical_with_items,
        "ical_parser_self_test_ok": parser_self_test_ok,
        "successful_sources": successes,
        "skipped_or_failed_sources": errors,
        "active_sources_after_test": active_count,
        "safety": {
            "sources_activated": False,
            "scheduler_enabled": False,
            "creates_events": False,
            "publishes": False,
            "calls_llm": False,
            "rss_publication_time_never_used_as_event_date": True,
            "empty_ical_response_is_nonfatal": True,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 12


if __name__ == "__main__":
    raise SystemExit(main())
