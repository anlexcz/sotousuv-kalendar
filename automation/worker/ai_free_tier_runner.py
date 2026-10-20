from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import requests

from ai_enrichment_test_v2 import MODEL, call_gemini, validate_ai
from detail_enrichment_test import build_d1, classify, extract_dates, fetch_page, load_findings
from structured_sources import stable_observation_id

DAILY_LIMIT = max(1, int(os.environ.get("AI_FREE_DAILY_LIMIT", "6")))
SCAN_LIMIT = max(1, int(os.environ.get("AI_FREE_SCAN_LIMIT", "25")))


def _persist_observation(d1, finding: dict, field_key: str, value: dict, method: str, note: str) -> None:
    source_id = str(finding.get("source_id") or "")
    if not source_id:
        return
    finding_id = str(finding["finding_id"])
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    observation_id = stable_observation_id(source_id, finding_id, field_key, encoded)
    d1.query(
        "INSERT OR IGNORE INTO observations (observation_id,source_id,subject_type,subject_ref,finding_id,"
        "field_key,value_state,value,observed_at,extraction_method,evidence_ref,note) "
        "VALUES (?,?,'FINDING',?,?,?,'VALUE',?,datetime('now'),?,?,?)",
        [
            observation_id,
            source_id,
            finding_id,
            finding_id,
            field_key,
            encoded,
            method,
            finding.get("detail_url"),
            note,
        ],
    )


def _processed_ids(d1) -> set[str]:
    rows = d1.query(
        "SELECT DISTINCT finding_id FROM observations WHERE finding_id IS NOT NULL "
        "AND field_key IN ('auto_triage_result','ai_free_result')"
    ).rows
    return {str(r["finding_id"]) for r in rows if r.get("finding_id")}


def _attempts_today(d1) -> int:
    rows = d1.query(
        "SELECT COUNT(*) AS count FROM observations WHERE field_key='ai_free_attempt' "
        "AND date(observed_at)=date('now')"
    ).rows
    return int(rows[0]["count"] if rows else 0)


def _record_attempt(d1, finding: dict) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    _persist_observation(
        d1,
        finding,
        "ai_free_attempt",
        {"at": stamp, "model": MODEL},
        "LLM",
        "Counts a Gemini free-tier attempt against the local daily safety budget.",
    )


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print(json.dumps({"ok": False, "error": "missing_GEMINI_API_KEY"}, ensure_ascii=False, indent=2))
        return 41

    d1 = build_d1()
    settings = {r["key"]: r.get("value") for r in d1.query(
        "SELECT key,value FROM settings WHERE key IN ('event_creation_enabled','production_status')"
    ).rows}
    before_events = int(d1.query("SELECT COUNT(*) AS count FROM events").rows[0]["count"])

    attempts_before = _attempts_today(d1)
    if attempts_before >= DAILY_LIMIT:
        print(json.dumps({
            "ok": True,
            "mode": "AI_FREE_TIER",
            "model": MODEL,
            "status": "DAILY_LIMIT_REACHED",
            "attempts_today": attempts_before,
            "daily_limit": DAILY_LIMIT,
            "ai_requests_made": 0,
            "creates_events": False,
            "publishes": False,
        }, ensure_ascii=False, indent=2))
        return 0

    processed = _processed_ids(d1)
    scanned = 0
    deterministic_processed = 0
    ai_result = None

    for finding in load_findings(d1):
        if finding["finding_id"] in processed:
            continue
        scanned += 1
        if scanned > SCAN_LIMIT:
            break

        decision = classify(finding)
        if decision.get("decision") not in {"AMBIGUOUS", "NO_EXPLICIT_DATE"}:
            _persist_observation(
                d1,
                finding,
                "auto_triage_result",
                {
                    "decision": decision.get("decision"),
                    "reason": decision.get("reason"),
                    "date_from": decision.get("date_from"),
                    "date_to": decision.get("date_to"),
                },
                "DETERMINISTIC",
                "Free-tier runner deterministic pre-triage; no event mutation.",
            )
            deterministic_processed += 1
            continue

        try:
            response, _html, visible = fetch_page(finding["detail_url"])
            dates = sorted({x["date"] for x in extract_dates(finding["title"] + " " + visible)})
            if not dates:
                _persist_observation(
                    d1,
                    finding,
                    "auto_triage_result",
                    {"decision": "NO_CANDIDATE_DATES", "reason": decision.get("reason")},
                    "DETERMINISTIC",
                    "No explicit candidate date available, so Gemini was not called.",
                )
                deterministic_processed += 1
                continue

            _record_attempt(d1, finding)
            model_result = call_gemini(api_key, finding["title"], response.url, visible, dates)
            valid, errors, clean = validate_ai(model_result, set(dates), finding["title"], visible)
            disposition = "AI_UNCERTAIN"
            if valid and clean.get("relevance") == "EVENT" and float(clean.get("confidence", 0)) >= 0.8:
                disposition = "AI_RECURRENCE_PROPOSAL" if clean.get("term_semantics") == "RECURRENCE" else "AI_EVENT_PROPOSAL"
            elif valid and clean.get("relevance") == "NON_EVENT" and float(clean.get("confidence", 0)) >= 0.8:
                disposition = "AI_NON_EVENT_PROPOSAL"
            elif not valid:
                disposition = "AI_REJECTED_BY_VALIDATOR"

            ai_result = {
                "finding_id": finding["finding_id"],
                "title": finding["title"],
                "disposition": disposition,
                "validation_ok": valid,
                "validation_errors": errors,
                "candidate_dates": dates,
                "ai": clean,
                "model": MODEL,
            }
            _persist_observation(
                d1,
                finding,
                "ai_free_result",
                ai_result,
                "LLM",
                "Gemini free-tier test result; proposal only, never materializes an event.",
            )
            break
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in {429, 500, 502, 503, 504}:
                ai_result = {
                    "finding_id": finding["finding_id"],
                    "title": finding["title"],
                    "disposition": "AI_DEFERRED",
                    "http_status": status,
                    "error": str(exc)[:500],
                    "model": MODEL,
                }
                break
            raise
        except Exception as exc:
            ai_result = {
                "finding_id": finding["finding_id"],
                "title": finding["title"],
                "disposition": "AI_ERROR",
                "error": str(exc)[:700],
                "model": MODEL,
            }
            break

    after_events = int(d1.query("SELECT COUNT(*) AS count FROM events").rows[0]["count"])
    safe = before_events == after_events and settings.get("event_creation_enabled") == "NE" and settings.get("production_status") == "DISABLED"

    print(json.dumps({
        "ok": safe,
        "mode": "AI_FREE_TIER",
        "model": MODEL,
        "daily_limit": DAILY_LIMIT,
        "attempts_today_before": attempts_before,
        "attempts_today_after": _attempts_today(d1),
        "scanned_findings": scanned,
        "deterministic_processed": deterministic_processed,
        "ai_requests_made": 1 if ai_result and ai_result.get("disposition") not in {None} else 0,
        "result": ai_result,
        "safety": {
            "events_before": before_events,
            "events_after": after_events,
            "creates_events": False,
            "publishes": False,
            "event_creation_enabled": settings.get("event_creation_enabled"),
            "production_status": settings.get("production_status"),
            "max_one_gemini_attempt_per_run": True,
            "daily_attempt_cap": DAILY_LIMIT,
        },
    }, ensure_ascii=False, indent=2))
    return 0 if safe else 42


if __name__ == "__main__":
    raise SystemExit(main())
