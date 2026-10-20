from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from d1 import D1Adapter
from parsers.dpp_museum import parse_current_events
from structured_sources import (
    StructuredCandidate,
    fetch_text,
    parse_ical,
    parse_rss_atom,
    stable_finding_id,
    stable_observation_id,
)
from wp_html_source_test import (
    fetch as fetch_html,
    filter_relevant,
    parse_html_articles,
    parse_wordpress_rest,
    wordpress_rest_url,
)

ACTOR = "source-collector"
BATCH_SIZE = int(os.environ.get("COLLECT_BATCH_SIZE", "20"))
MAX_ITEMS_PER_SOURCE = int(os.environ.get("COLLECT_MAX_ITEMS_PER_SOURCE", "10"))
SUPPORTED_STRATEGIES = {
    "RSS_ATOM_FIRST",
    "ICAL_FIRST",
    "WORDPRESS_REST_OR_HTML",
    "HTML_PARSER",
}
IMPORTABLE_STATUSES = {"MIGRATE", "MIGRATE_INACTIVE", "FALLBACK_ONLY", "ALREADY_PILOT"}


@dataclass
class FetchResult:
    candidates: list[StructuredCandidate]
    evidence_ref: str
    status_code: int
    body: str
    headers: dict[str, str]
    endpoint_state: str
    raw_items: int
    rejected_items: int = 0


def build_d1() -> D1Adapter:
    return D1Adapter(
        account_id=os.environ["CLOUDFLARE_ACCOUNT_ID"],
        database_id=os.environ["CLOUDFLARE_D1_DATABASE_ID"],
        api_token=os.environ["CLOUDFLARE_API_TOKEN"],
    )


def select_batch(d1: D1Adapter) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in IMPORTABLE_STATUSES)
    params: list[Any] = [*sorted(IMPORTABLE_STATUSES), BATCH_SIZE]
    return d1.query(
        "SELECT source_id,label,url,parser_key,fetch_strategy,feed_url,calendar_url,priority,migration_status,"
        "active,last_checked_at,last_success_at,consecutive_errors,source_group,platform,area "
        f"FROM sources WHERE migration_status IN ({placeholders}) "
        "AND url IS NOT NULL AND TRIM(url)<>'' "
        "ORDER BY CASE WHEN last_checked_at IS NULL THEN 0 ELSE 1 END, "
        "COALESCE(last_checked_at,''), COALESCE(priority,999), source_id LIMIT ?",
        params,
    ).rows


def _fetch_rss(row: dict[str, Any]) -> FetchResult:
    url = str(row.get("feed_url") or "").strip()
    if not url:
        raise RuntimeError("RSS_ATOM_FIRST without feed_url")
    text, status, headers = fetch_text(
        url,
        "application/rss+xml,application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.1",
    )
    candidates = parse_rss_atom(text, url, limit=MAX_ITEMS_PER_SOURCE)
    return FetchResult(candidates, url, status, text, headers, "RSS_ATOM", len(candidates))


def _fetch_ical(row: dict[str, Any]) -> FetchResult:
    url = str(row.get("calendar_url") or "").strip()
    if not url:
        raise RuntimeError("ICAL_FIRST without calendar_url")
    text, status, headers = fetch_text(url, "text/calendar,text/plain;q=0.9,*/*;q=0.1")
    if "BEGIN:VCALENDAR" not in text.upper():
        raise RuntimeError("calendar_url did not return VCALENDAR")
    candidates = parse_ical(text, url, limit=MAX_ITEMS_PER_SOURCE)
    return FetchResult(candidates, url, status, text, headers, "ICAL", len(candidates))


def _fetch_wordpress(row: dict[str, Any]) -> FetchResult:
    page_url = str(row["url"])
    rest_url = wordpress_rest_url(page_url)
    try:
        response, text = fetch_html(rest_url, "application/json,*/*;q=0.1")
        raw = parse_wordpress_rest(response.json())
        if not raw:
            raise RuntimeError("WordPress REST returned zero usable posts")
        endpoint_state = "WP_REST"
        evidence_ref = rest_url
    except Exception:
        response, text = fetch_html(page_url)
        raw = parse_html_articles(text, response.url)
        endpoint_state = "HTML_FALLBACK"
        evidence_ref = response.url

    accepted, rejected = filter_relevant(raw, str(row.get("label") or ""))
    accepted = accepted[:MAX_ITEMS_PER_SOURCE]
    return FetchResult(
        accepted,
        evidence_ref,
        response.status_code,
        text,
        dict(response.headers),
        endpoint_state,
        len(raw),
        len(rejected),
    )


def _fetch_html(row: dict[str, Any]) -> FetchResult:
    response, text = fetch_html(str(row["url"]))
    raw = parse_html_articles(text, response.url)
    accepted, rejected = filter_relevant(raw, str(row.get("label") or ""))
    accepted = accepted[:MAX_ITEMS_PER_SOURCE]
    return FetchResult(
        accepted,
        response.url,
        response.status_code,
        text,
        dict(response.headers),
        "HTML",
        len(raw),
        len(rejected),
    )


def _fetch_dpp(row: dict[str, Any]) -> FetchResult:
    response, text = fetch_html(str(row["url"]))
    parsed = parse_current_events(text, response.url)
    candidates = [
        StructuredCandidate(
            identity=c.detail_url or c.raw_heading,
            title=c.title,
            detail_url=c.detail_url,
            event_date_from=c.date_from,
            event_date_to=c.date_from,
            published_at=None,
            raw_kind="DPP_MUSEUM_CALENDAR",
        )
        for c in parsed[:MAX_ITEMS_PER_SOURCE]
    ]
    return FetchResult(
        candidates,
        response.url,
        response.status_code,
        text,
        dict(response.headers),
        "DPP_MUSEUM_CALENDAR",
        len(parsed),
    )


def fetch_source(row: dict[str, Any]) -> FetchResult:
    if row.get("parser_key") == "DPP_MUSEUM_CALENDAR":
        return _fetch_dpp(row)
    strategy = str(row.get("fetch_strategy") or "").strip()
    if strategy == "RSS_ATOM_FIRST":
        return _fetch_rss(row)
    if strategy == "ICAL_FIRST":
        return _fetch_ical(row)
    if strategy == "WORDPRESS_REST_OR_HTML":
        return _fetch_wordpress(row)
    if strategy == "HTML_PARSER":
        return _fetch_html(row)
    raise RuntimeError(f"unsupported fetch_strategy: {strategy or '<empty>'}")


def _candidate_statements(
    source_id: str,
    candidate: StructuredCandidate,
    observed_at: str,
    evidence_ref: str,
) -> tuple[str, list[tuple[str, list[Any]]]]:
    finding_id = stable_finding_id(source_id, candidate.identity)
    note = json.dumps(
        {
            "detail_url": candidate.detail_url,
            "published_at": candidate.published_at,
            "raw_kind": candidate.raw_kind,
            "collector": ACTOR,
        },
        ensure_ascii=False,
    )
    statements: list[tuple[str, list[Any]]] = [
        (
            "INSERT INTO findings (finding_id,finding_type,status,title_hint,source_id,first_seen_at,last_seen_at,"
            "next_check_at,updated_at,note) VALUES (?, 'DISCOVERY_CANDIDATE', 'OPEN', ?, ?, ?, ?, datetime(?, '+7 days'), ?, ?) "
            "ON CONFLICT(finding_id) DO UPDATE SET title_hint=excluded.title_hint,last_seen_at=excluded.last_seen_at,"
            "next_check_at=excluded.next_check_at,updated_at=excluded.updated_at,note=excluded.note",
            [finding_id, candidate.title, source_id, observed_at, observed_at, observed_at, observed_at, note],
        )
    ]

    fields: list[tuple[str, str]] = [("title", candidate.title)]
    if candidate.detail_url:
        fields.append(("detail_url", candidate.detail_url))
    if candidate.event_date_from:
        fields.append(("date_from", candidate.event_date_from))
    if candidate.event_date_to:
        fields.append(("date_to", candidate.event_date_to))

    for field_key, value in fields:
        observation_id = stable_observation_id(source_id, finding_id, field_key, value)
        statements.append(
            (
                "INSERT OR IGNORE INTO observations (observation_id,source_id,subject_type,subject_ref,finding_id,"
                "field_key,value_state,value,observed_at,source_published_at,extraction_method,evidence_ref,note) "
                "VALUES (?,?,'FINDING',?,?,?,'VALUE',?,?,?,?,?,?)",
                [
                    observation_id,
                    source_id,
                    finding_id,
                    finding_id,
                    field_key,
                    value,
                    observed_at,
                    candidate.published_at,
                    "DETERMINISTIC",
                    evidence_ref,
                    f"Collected by {ACTOR} from {candidate.raw_kind}",
                ],
            )
        )
    return finding_id, statements


def persist_success(d1: D1Adapter, row: dict[str, Any], fetched: FetchResult) -> dict[str, Any]:
    observed_at = datetime.now(timezone.utc).isoformat()
    source_id = str(row["source_id"])
    content_hash = hashlib.sha256(fetched.body.encode("utf-8", errors="replace")).hexdigest()
    request_id = f"collect:{source_id}:{content_hash[:20]}"
    next_check_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    statements: list[tuple[str, list[Any]]] = []
    finding_ids: list[str] = []
    for candidate in fetched.candidates:
        finding_id, candidate_statements = _candidate_statements(
            source_id, candidate, observed_at, fetched.evidence_ref
        )
        finding_ids.append(finding_id)
        statements.extend(candidate_statements)

    statements.append(
        (
            "UPDATE sources SET last_checked_at=?,last_success_at=?,last_http_status=?,consecutive_errors=0,"
            "content_hash=?,etag=?,last_modified=?,next_check_at=? WHERE source_id=?",
            [
                observed_at,
                observed_at,
                fetched.status_code,
                content_hash,
                fetched.headers.get("ETag"),
                fetched.headers.get("Last-Modified"),
                next_check_at,
                source_id,
            ],
        )
    )

    d1.execute_idempotent_request(
        request_id=request_id,
        operation="COLLECT_SOURCE",
        entity_type="SOURCE",
        entity_id=source_id,
        statements=statements,
        actor=ACTOR,
    )

    return {
        "source_id": source_id,
        "label": row.get("label"),
        "strategy": row.get("fetch_strategy"),
        "parser_key": row.get("parser_key"),
        "endpoint_state": fetched.endpoint_state,
        "status_code": fetched.status_code,
        "raw_items": fetched.raw_items,
        "accepted_items": len(fetched.candidates),
        "rejected_items": fetched.rejected_items,
        "finding_ids": finding_ids,
        "request_id": request_id,
        "sample": [
            {
                "title": c.title,
                "date_from": c.event_date_from,
                "date_to": c.event_date_to,
                "detail_url": c.detail_url,
                "kind": c.raw_kind,
            }
            for c in fetched.candidates[:3]
        ],
    }


def persist_failure(d1: D1Adapter, row: dict[str, Any], exc: Exception) -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    status = None
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
    d1.query(
        "UPDATE sources SET last_checked_at=?,last_http_status=COALESCE(?,last_http_status),"
        "consecutive_errors=COALESCE(consecutive_errors,0)+1,next_check_at=? WHERE source_id=?",
        [checked_at, status, (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), row["source_id"]],
    )
    return {
        "source_id": row.get("source_id"),
        "label": row.get("label"),
        "strategy": row.get("fetch_strategy"),
        "parser_key": row.get("parser_key"),
        "status": "ERROR",
        "http_status": status,
        "error": str(exc)[:700],
    }


def strategy_inventory(d1: D1Adapter) -> list[dict[str, Any]]:
    return d1.query(
        "SELECT COALESCE(fetch_strategy,'<empty>') AS fetch_strategy,COUNT(*) AS count "
        "FROM sources WHERE migration_status IN ('MIGRATE','MIGRATE_INACTIVE','FALLBACK_ONLY','ALREADY_PILOT') "
        "GROUP BY COALESCE(fetch_strategy,'<empty>') ORDER BY count DESC,fetch_strategy"
    ).rows


def main() -> int:
    d1 = build_d1()
    settings = {
        row["key"]: row.get("value")
        for row in d1.query(
            "SELECT key,value FROM settings WHERE key IN ('event_creation_enabled','scheduler_enabled','production_status')"
        ).rows
    }
    before_events = int(d1.query("SELECT COUNT(*) AS count FROM events").rows[0]["count"])
    before_findings = int(d1.query("SELECT COUNT(*) AS count FROM findings").rows[0]["count"])

    rows = select_batch(d1)
    successes: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []

    for row in rows:
        strategy = str(row.get("fetch_strategy") or "").strip()
        if row.get("parser_key") != "DPP_MUSEUM_CALENDAR" and strategy not in SUPPORTED_STRATEGIES:
            unsupported.append(
                {
                    "source_id": row.get("source_id"),
                    "label": row.get("label"),
                    "fetch_strategy": strategy or None,
                    "status": "UNSUPPORTED_STRATEGY",
                }
            )
            d1.query(
                "UPDATE sources SET last_checked_at=?,next_check_at=? WHERE source_id=?",
                [
                    datetime.now(timezone.utc).isoformat(),
                    (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                    row["source_id"],
                ],
            )
            continue
        try:
            successes.append(persist_success(d1, row, fetch_source(row)))
        except Exception as exc:
            errors.append(persist_failure(d1, row, exc))

    after_events = int(d1.query("SELECT COUNT(*) AS count FROM events").rows[0]["count"])
    after_findings = int(d1.query("SELECT COUNT(*) AS count FROM findings").rows[0]["count"])

    safe = (
        before_events == after_events
        and settings.get("event_creation_enabled") == "NE"
        and settings.get("scheduler_enabled") == "NE"
        and settings.get("production_status") == "DISABLED"
    )

    due_only = os.environ.get("COLLECT_DUE_ONLY", "").strip().lower() in {"1", "true", "ano", "yes"}
    one_source = bool(os.environ.get("COLLECT_SOURCE_ID", "").strip())
    mode = "COLLECT_SOURCE_MANUAL" if one_source else ("COLLECT_BATCH_SCHEDULED" if due_only else "COLLECT_BATCH_MANUAL")

    output = {
        "ok": safe,
        "mode": mode,
        "batch_size": BATCH_SIZE,
        "sources_selected": len(rows),
        "sources_succeeded": len(successes),
        "sources_failed": len(errors),
        "sources_unsupported": len(unsupported),
        "accepted_candidates": sum(int(x.get("accepted_items") or 0) for x in successes),
        "findings_before": before_findings,
        "findings_after": after_findings,
        "new_findings_delta": after_findings - before_findings,
        "results": successes,
        "errors": errors,
        "unsupported": unsupported,
        "strategy_inventory": strategy_inventory(d1),
        "safety": {
            "events_before": before_events,
            "events_after": after_events,
            "creates_events": False,
            "publishes": False,
            "event_creation_enabled": settings.get("event_creation_enabled"),
            "scheduler_enabled": settings.get("scheduler_enabled"),
            "production_status": settings.get("production_status"),
            "source_writes_atomic_on_success": True,
            "manual_only": not due_only,
            "scheduled_source_collection": due_only,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if safe else 31


if __name__ == "__main__":
    raise SystemExit(main())
