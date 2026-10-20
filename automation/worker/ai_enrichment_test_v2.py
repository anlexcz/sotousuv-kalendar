from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import requests

from d1 import D1Adapter
from detail_enrichment_test import build_d1, classify, extract_dates, fetch_page, load_findings, normalize
from ai_enrichment_test import SCHEMA, ALLOWED_CATEGORIES, ALLOWED_RECURRENCE

MODEL = "gemini-3.5-flash-lite"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
MAX_AI_CASES = 8
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def extract_generate_content_text(payload: dict) -> str:
    for candidate in payload.get("candidates", []) or []:
        content = candidate.get("content") or {}
        for part in content.get("parts", []) or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                return part["text"]
    raise RuntimeError("Gemini generateContent response did not contain text output")


def call_gemini(api_key: str, title: str, url: str, visible_text: str, candidate_dates: list[str]) -> dict:
    prompt = f"""You are a conservative extraction component for a public-transport enthusiast event calendar.
Interpret only the supplied source text. Do not use outside knowledge.

Task:
1. Decide whether the page describes a calendar-worthy event (special ride, open day, exhibition, transport festival, anniversary event, museum event, special transport product, etc.), a NON_EVENT (news, procurement, construction update, regular disruption, policy/tariff information, ordinary operations), or UNCERTAIN.
2. Interpret event dates. You may ONLY use dates from CANDIDATE_DATES below. Never invent or infer another date.
3. Distinguish SINGLE, MULTIPLE, continuous INTERVAL, and RECURRENCE. RECURRENCE means the event occurs only on selected repeated days inside a wider validity period, for example weekends, weekdays, weekly, or weekends and public holidays. Never turn recurrence into one continuous interval.
4. If term_semantics is RECURRENCE, set recurrence_type and recurrence_date_from/to. Those boundary dates must come from CANDIDATE_DATES. Put the rule as stated by the source into recurrence_description. For non-recurring cases set recurrence_type=NONE and the recurrence date strings/description to empty strings.
5. For exhibitions, an opening date / opening ceremony / vernissage date is NOT automatically the full duration of the exhibition. If the end or duration is unclear, return UNCERTAIN rather than a one-day event.
6. Return transport categories only when supported by the source. Use 'other' if event relevance is clear but mode is not.
7. Be conservative. When meaning is unclear, return UNCERTAIN and lower confidence.

TITLE: {title}
URL: {url}
CANDIDATE_DATES: {json.dumps(candidate_dates, ensure_ascii=False)}

SOURCE_TEXT:
{visible_text[:10000]}
"""
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseFormat": {
                "text": {
                    "mimeType": "APPLICATION_JSON",
                    "schema": SCHEMA,
                }
            },
            "maxOutputTokens": 1400,
        },
    }

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            response = requests.post(
                API_URL,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=body,
                timeout=30,
            )
            if response.status_code in RETRYABLE_STATUS:
                detail = response.text[:1000]
                raise requests.HTTPError(
                    f"retryable HTTP {response.status_code}: {detail}",
                    response=response,
                )
            if not response.ok:
                raise RuntimeError(
                    f"Gemini HTTP {response.status_code}: {response.text[:1200]}"
                )
            return json.loads(extract_generate_content_text(response.json()))
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            last_exc = exc
            retryable = isinstance(exc, (requests.Timeout, requests.ConnectionError)) or (
                isinstance(exc, requests.HTTPError)
                and exc.response is not None
                and exc.response.status_code in RETRYABLE_STATUS
            )
            if not retryable or attempt == 1:
                raise
            time.sleep(2)
    raise last_exc or RuntimeError("Gemini request failed")


def validate_ai(result: dict, candidate_dates: set[str], title: str, visible_text: str) -> tuple[bool, list[str], dict]:
    errors: list[str] = []
    clean = dict(result)
    relevance = result.get("relevance")
    confidence = result.get("confidence")
    semantics = result.get("term_semantics")
    terms = result.get("terms") or []
    categories = result.get("categories") or []
    recurrence_type = result.get("recurrence_type")
    recurrence_from = str(result.get("recurrence_date_from") or "")
    recurrence_to = str(result.get("recurrence_date_to") or "")

    if relevance not in {"EVENT", "NON_EVENT", "UNCERTAIN"}:
        errors.append("invalid_relevance")
    if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        errors.append("invalid_confidence")
    if semantics not in {"SINGLE", "MULTIPLE", "INTERVAL", "RECURRENCE", "NONE", "UNCERTAIN"}:
        errors.append("invalid_term_semantics")
    if recurrence_type not in ALLOWED_RECURRENCE:
        errors.append("invalid_recurrence_type")

    valid_terms: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for term in terms:
        if not isinstance(term, dict):
            errors.append("invalid_term_object")
            continue
        df = str(term.get("date_from") or "")
        dt = str(term.get("date_to") or "")
        if df not in candidate_dates or dt not in candidate_dates:
            errors.append(f"date_not_in_source:{df}:{dt}")
            continue
        if dt < df:
            errors.append(f"reversed_term:{df}:{dt}")
            continue
        if (df, dt) not in seen:
            seen.add((df, dt))
            valid_terms.append({"date_from": df, "date_to": dt})

    clean["terms"] = valid_terms
    clean["categories"] = [c for c in categories if c in ALLOWED_CATEGORIES]
    if any(c not in ALLOWED_CATEGORIES for c in categories):
        errors.append("invalid_categories")

    if semantics == "RECURRENCE":
        if recurrence_type in {"NONE", "UNKNOWN", None}:
            errors.append("recurrence_type_required")
        if recurrence_from not in candidate_dates or recurrence_to not in candidate_dates:
            errors.append("recurrence_boundary_not_in_source")
        elif recurrence_to < recurrence_from:
            errors.append("reversed_recurrence_window")
    elif recurrence_type not in {"NONE", None}:
        errors.append("unexpected_recurrence_type")

    if relevance == "EVENT" and float(confidence or 0) >= 0.8 and not valid_terms and semantics != "RECURRENCE":
        errors.append("confident_event_without_valid_term")
    if semantics == "SINGLE" and len(valid_terms) != 1:
        errors.append("single_semantics_term_count")
    if semantics == "INTERVAL" and (len(valid_terms) != 1 or valid_terms[0]["date_from"] == valid_terms[0]["date_to"]):
        errors.append("interval_semantics_invalid")
    if semantics == "MULTIPLE" and len(valid_terms) < 2:
        errors.append("multiple_semantics_term_count")

    today = datetime.now(timezone.utc).date().isoformat()
    if semantics == "RECURRENCE":
        if recurrence_to and recurrence_to < today:
            errors.append("historical_recurrence_only")
    elif valid_terms and max(t["date_to"] for t in valid_terms) < today:
        errors.append("historical_term_only")

    nt = normalize(title + " " + visible_text[:5000])
    exhibition_like = any(x in nt for x in ("vystava", "exhibition", "ausstellung"))
    opening_like = any(x in nt for x in ("vernisaz", "zahajeni", "otevreni vystavy", "opening"))
    if exhibition_like and opening_like and semantics == "SINGLE" and len(valid_terms) == 1 and valid_terms[0]["date_from"] == valid_terms[0]["date_to"]:
        errors.append("exhibition_opening_not_duration")

    return not errors, errors, clean


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print(json.dumps({"ok": False, "error": "missing_GEMINI_API_KEY"}, ensure_ascii=False, indent=2))
        return 16

    d1: D1Adapter = build_d1()
    settings = {r["key"]: r.get("value") for r in d1.query(
        "SELECT key,value FROM settings WHERE key IN ('event_creation_enabled','scheduler_enabled','production_status')"
    ).rows}
    before_events = int(d1.query("SELECT COUNT(*) AS count FROM events").rows[0]["count"])

    deterministic: list[dict] = []
    ai_cases: list[dict] = []
    for finding in load_findings(d1):
        d = classify(finding)
        deterministic.append(d)
        if d.get("decision") not in {"AMBIGUOUS", "NO_EXPLICIT_DATE"} or len(ai_cases) >= MAX_AI_CASES:
            continue
        try:
            response, _html, visible = fetch_page(finding["detail_url"])
            dates = sorted({x["date"] for x in extract_dates(finding["title"] + " " + visible)})
            if not dates:
                ai_cases.append({**finding, "ai_status": "SKIPPED_NO_CANDIDATE_DATES"})
                continue
            model_result = call_gemini(api_key, finding["title"], response.url, visible, dates)
            valid, validation_errors, clean = validate_ai(model_result, set(dates), finding["title"], visible)
            disposition = "AI_UNCERTAIN"
            if valid and clean.get("relevance") == "EVENT" and float(clean.get("confidence", 0)) >= 0.8:
                disposition = "AI_RECURRENCE_PROPOSAL" if clean.get("term_semantics") == "RECURRENCE" else "AI_EVENT_PROPOSAL"
            elif valid and clean.get("relevance") == "NON_EVENT" and float(clean.get("confidence", 0)) >= 0.8:
                disposition = "AI_NON_EVENT_PROPOSAL"
            elif not valid:
                disposition = "AI_REJECTED_BY_VALIDATOR"
            ai_cases.append({
                **finding,
                "candidate_dates": dates,
                "ai_status": disposition,
                "validation_ok": valid,
                "validation_errors": validation_errors,
                "ai": clean,
                "http_status": response.status_code,
                "final_url": response.url,
            })
        except Exception as exc:
            ai_cases.append({**finding, "ai_status": "AI_ERROR", "error": str(exc)[:1200]})

    after_events = int(d1.query("SELECT COUNT(*) AS count FROM events").rows[0]["count"])
    safe = settings.get("event_creation_enabled") == "NE" and settings.get("scheduler_enabled") == "NE" and before_events == after_events
    counts: dict[str, int] = {}
    for row in ai_cases:
        key = row.get("ai_status", "UNKNOWN")
        counts[key] = counts.get(key, 0) + 1

    print(json.dumps({
        "ok": safe,
        "mode": "AI_ENRICHMENT_DRY_RUN_V6_RECURRENCE",
        "model": MODEL,
        "api": "generateContent",
        "deterministic_findings_checked": len(deterministic),
        "ai_cases": len(ai_cases),
        "ai_status_counts": counts,
        "results": ai_cases,
        "safety": {
            "event_creation_enabled": settings.get("event_creation_enabled"),
            "scheduler_enabled": settings.get("scheduler_enabled"),
            "production_status": settings.get("production_status"),
            "events_before": before_events,
            "events_after": after_events,
            "writes_events": False,
            "publishes": False,
            "ai_can_only_use_dates_seen_in_source": True,
            "historical_only_proposals_rejected": True,
            "recurrence_is_distinct_from_interval": True,
            "gemini_retries_enabled": True,
        },
    }, ensure_ascii=False, indent=2))
    return 0 if safe else 17


if __name__ == "__main__":
    raise SystemExit(main())
