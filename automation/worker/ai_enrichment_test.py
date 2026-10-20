from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import requests

from d1 import D1Adapter
from detail_enrichment_test import (
    build_d1,
    classify,
    extract_dates,
    fetch_page,
    load_findings,
    normalize,
)

MODEL = "gemini-3.8-flash"
API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MAX_AI_CASES = 8
ALLOWED_CATEGORIES = {"rail", "bus", "tram", "trolleybus", "metro", "water", "air", "cableway", "other"}
ALLOWED_RECURRENCE = {"NONE", "WEEKENDS", "WEEKDAYS", "WEEKLY", "WEEKENDS_HOLIDAYS", "OTHER", "UNKNOWN"}

SCHEMA = {
    "type": "object",
    "properties": {
        "relevance": {"type": "string", "enum": ["EVENT", "NON_EVENT", "UNCERTAIN"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "term_semantics": {"type": "string", "enum": ["SINGLE", "MULTIPLE", "INTERVAL", "RECURRENCE", "NONE", "UNCERTAIN"]},
        "terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "format": "date"},
                    "date_to": {"type": "string", "format": "date"},
                },
                "required": ["date_from", "date_to"],
                "additionalProperties": False,
            },
            "maxItems": 30,
        },
        "recurrence_type": {"type": "string", "enum": sorted(ALLOWED_RECURRENCE)},
        "recurrence_date_from": {"type": "string"},
        "recurrence_date_to": {"type": "string"},
        "recurrence_description": {"type": "string"},
        "categories": {
            "type": "array",
            "items": {"type": "string", "enum": sorted(ALLOWED_CATEGORIES)},
            "maxItems": 9,
        },
        "reason": {"type": "string"},
    },
    "required": [
        "relevance", "confidence", "term_semantics", "terms",
        "recurrence_type", "recurrence_date_from", "recurrence_date_to", "recurrence_description",
        "categories", "reason"
    ],
    "additionalProperties": False,
}


def extract_output_text(payload: dict) -> str:
    for step in payload.get("steps", []):
        if not isinstance(step, dict):
            continue
        for item in step.get("content", []) or []:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                return item["text"]
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    raise RuntimeError("Gemini response did not contain text output")


def call_gemini(api_key: str, title: str, url: str, visible_text: str, candidate_dates: list[str]) -> dict:
    prompt = f"""You are a conservative extraction component for a public-transport enthusiast event calendar.
Interpret only the supplied source text. Do not use outside knowledge.

Task:
1. Decide whether the page describes a calendar-worthy event (special ride, open day, exhibition, transport festival, anniversary event, museum event, special transport product, etc.), a NON_EVENT (news, procurement, construction update, regular disruption, policy/tariff information, ordinary operations), or UNCERTAIN.
2. Interpret event dates. You may ONLY use dates from CANDIDATE_DATES below. Never invent or infer another date.
3. Distinguish SINGLE, MULTIPLE, continuous INTERVAL, and RECURRENCE. RECURRENCE means the event operates only on selected repeated days within a wider validity period, such as weekends, weekdays, weekly, or weekends plus public holidays. Never represent recurrence as one continuous interval.
4. If term_semantics is RECURRENCE, set recurrence_type and recurrence_date_from/to. Those boundary dates must come from CANDIDATE_DATES. Put a short source-grounded rule into recurrence_description. Otherwise set recurrence_type=NONE and the recurrence date strings/description to empty strings.
5. Return transport categories only when supported by the source. Use 'other' if event relevance is clear but mode is not.
6. Be conservative. When meaning is unclear, return UNCERTAIN and lower confidence.

TITLE: {title}
URL: {url}
CANDIDATE_DATES: {json.dumps(candidate_dates, ensure_ascii=False)}

SOURCE_TEXT:
{visible_text[:14000]}
"""
    body = {
        "model": MODEL,
        "input": prompt,
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": SCHEMA,
        },
    }
    response = requests.post(
        API_URL,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    response.raise_for_status()
    raw = extract_output_text(response.json())
    return json.loads(raw)


def validate_ai(result: dict, candidate_dates: set[str]) -> tuple[bool, list[str], dict]:
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

    seen_terms: set[tuple[str, str]] = set()
    valid_terms: list[dict] = []
    for term in terms:
        if not isinstance(term, dict):
            errors.append("invalid_term_object")
            continue
        date_from = str(term.get("date_from") or "")
        date_to = str(term.get("date_to") or "")
        if date_from not in candidate_dates or date_to not in candidate_dates:
            errors.append(f"date_not_in_source:{date_from}:{date_to}")
            continue
        if date_to < date_from:
            errors.append(f"reversed_term:{date_from}:{date_to}")
            continue
        key = (date_from, date_to)
        if key not in seen_terms:
            seen_terms.add(key)
            valid_terms.append({"date_from": date_from, "date_to": date_to})

    bad_categories = [c for c in categories if c not in ALLOWED_CATEGORIES]
    if bad_categories:
        errors.append("invalid_categories")
    clean["terms"] = valid_terms
    clean["categories"] = [c for c in categories if c in ALLOWED_CATEGORIES]

    if semantics == "RECURRENCE":
        if recurrence_type in {"NONE", "UNKNOWN", None}:
            errors.append("recurrence_type_required")
        if recurrence_from not in candidate_dates or recurrence_to not in candidate_dates:
            errors.append("recurrence_boundary_not_in_source")
        elif recurrence_to < recurrence_from:
            errors.append("reversed_recurrence_window")
    else:
        if recurrence_type not in {"NONE", None}:
            errors.append("unexpected_recurrence_type")

    if relevance == "EVENT" and float(confidence or 0) >= 0.8 and not valid_terms and semantics != "RECURRENCE":
        errors.append("confident_event_without_valid_term")
    if semantics == "SINGLE" and len(valid_terms) != 1:
        errors.append("single_semantics_term_count")
    if semantics == "INTERVAL" and (len(valid_terms) != 1 or valid_terms[0]["date_from"] == valid_terms[0]["date_to"]):
        errors.append("interval_semantics_invalid")
    if semantics == "MULTIPLE" and len(valid_terms) < 2:
        errors.append("multiple_semantics_term_count")

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

    deterministic = []
    ai_cases = []
    for finding in load_findings(d1):
        d = classify(finding)
        deterministic.append(d)
        if d.get("decision") not in {"AMBIGUOUS", "NO_EXPLICIT_DATE"}:
            continue
        if len(ai_cases) >= MAX_AI_CASES:
            break
        try:
            response, _html, visible = fetch_page(finding["detail_url"])
            dates = sorted({x["date"] for x in extract_dates(finding["title"] + " " + visible)})
            if not dates:
                ai_cases.append({**finding, "ai_status": "SKIPPED_NO_CANDIDATE_DATES"})
                continue
            model_result = call_gemini(api_key, finding["title"], response.url, visible, dates)
            valid, validation_errors, clean = validate_ai(model_result, set(dates))
            disposition = "AI_UNCERTAIN"
            if valid and clean.get("relevance") == "EVENT" and float(clean.get("confidence", 0)) >= 0.8:
                disposition = "AI_RECURRENCE_PROPOSAL" if clean.get("term_semantics") == "RECURRENCE" else "AI_EVENT_PROPOSAL"
            elif valid and clean.get("relevance") == "NON_EVENT" and float(clean.get("confidence", 0)) >= 0.8:
                disposition = "AI_NON_EVENT_PROPOSAL"
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
            ai_cases.append({**finding, "ai_status": "AI_ERROR", "error": str(exc)[:800]})

    after_events = int(d1.query("SELECT COUNT(*) AS count FROM events").rows[0]["count"])
    safe = (
        settings.get("event_creation_enabled") == "NE"
        and settings.get("scheduler_enabled") == "NE"
        and before_events == after_events
    )

    counts: dict[str, int] = {}
    for row in ai_cases:
        key = row.get("ai_status", "UNKNOWN")
        counts[key] = counts.get(key, 0) + 1

    output = {
        "ok": safe,
        "mode": "AI_ENRICHMENT_DRY_RUN_RECURRENCE_SCHEMA",
        "model": MODEL,
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
            "writes_findings": False,
            "writes_observations": False,
            "writes_events": False,
            "publishes": False,
            "ai_can_only_use_dates_seen_in_source": True,
            "recurrence_is_not_materialized_as_continuous_interval": True,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if safe else 17


if __name__ == "__main__":
    raise SystemExit(main())
