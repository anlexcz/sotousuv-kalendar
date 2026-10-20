from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import source_collector as base
from structured_sources import parse_rss_atom

COLLECTOR_VERSION = "v2"
MAX_FEED_AGE_DAYS = int(os.environ.get("COLLECT_MAX_FEED_AGE_DAYS", "180"))
SOURCE_RECHECK_HOURS = int(os.environ.get("COLLECT_RECHECK_HOURS", "24"))
FEED_SCAN_LIMIT = max(base.MAX_ITEMS_PER_SOURCE * 3, 30)

_NAVIGATION_JUNK = (
    "galerie dalších fotografií",
    "galerie dalsich fotografii",
    "další fotografie z akce",
    "dalsi fotografie z akce",
    "fotografie z akce zde",
    "fotografie z akce najdete",
    "více fotografií zde",
    "vice fotografii zde",
)

_OBVIOUS_NON_EVENT = (
    "za námi",
    "za nami",
    "fotogalerie",
    "dárkové poukazy",
    "darkove poukazy",
    "změna otevírací doby",
    "zmena oteviraci doby",
    "získalo podporu",
    "ziskalo podporu",
)


def _published_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _explicit_old_year(title: str) -> bool:
    years = [int(x) for x in re.findall(r"(?<!\d)(20\d{2})(?!\d)", title)]
    if not years:
        return False
    return max(years) < datetime.now(timezone.utc).year - 1


def _all_explicit_numeric_dates_are_past(title: str) -> bool:
    matches = re.findall(r"(?<!\d)(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})(?!\d)", title)
    if not matches:
        return False
    parsed = []
    for d, m, y in matches:
        try:
            parsed.append(datetime(int(y), int(m), int(d), tzinfo=timezone.utc).date())
        except ValueError:
            pass
    return bool(parsed) and max(parsed) < datetime.now(timezone.utc).date()


def _obvious_non_event(title: str) -> bool:
    normalized = " ".join(title.lower().split())
    return any(phrase in normalized for phrase in _OBVIOUS_NON_EVENT)


def _filter_feed_freshness(candidates):
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_FEED_AGE_DAYS)
    accepted = []
    rejected = []
    for candidate in candidates:
        published = _published_datetime(candidate.published_at)
        if published is not None and published < cutoff:
            rejected.append((candidate, "stale_publication"))
            continue
        if published is None and _explicit_old_year(candidate.title):
            rejected.append((candidate, "explicit_old_year"))
            continue
        if _all_explicit_numeric_dates_are_past(candidate.title):
            rejected.append((candidate, "explicit_past_event_date"))
            continue
        if _obvious_non_event(candidate.title):
            rejected.append((candidate, "obvious_non_event_title"))
            continue
        accepted.append(candidate)
    return accepted[: base.MAX_ITEMS_PER_SOURCE], rejected


def _is_navigation_junk(title: str) -> bool:
    normalized = " ".join(title.lower().split())
    return any(phrase in normalized for phrase in _NAVIGATION_JUNK)


def _drop_navigation_junk(fetched: base.FetchResult) -> base.FetchResult:
    kept = [candidate for candidate in fetched.candidates if not _is_navigation_junk(candidate.title)]
    removed = len(fetched.candidates) - len(kept)
    fetched.candidates = kept
    fetched.rejected_items += removed
    stats = dict(getattr(fetched, "prefilter_stats", {}) or {})
    stats["navigation_junk_rejected"] = removed
    fetched.prefilter_stats = stats
    return fetched


def _fetch_rss_v2(row: dict[str, Any]) -> base.FetchResult:
    url = str(row.get("feed_url") or "").strip()
    if not url:
        raise RuntimeError("RSS_ATOM_FIRST without feed_url")
    text, status, headers = base.fetch_text(
        url,
        "application/rss+xml,application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.1",
    )
    raw = parse_rss_atom(text, url, limit=FEED_SCAN_LIMIT)
    accepted, rejected = _filter_feed_freshness(raw)
    reasons: dict[str, int] = {}
    for _candidate, reason in rejected:
        reasons[reason] = reasons.get(reason, 0) + 1
    fetched = base.FetchResult(
        accepted,
        url,
        status,
        text,
        headers,
        "RSS_ATOM",
        len(raw),
        len(rejected),
    )
    fetched.prefilter_stats = {
        "rejected_by_reason": reasons,
        "feed_scan_limit": FEED_SCAN_LIMIT,
        "max_feed_age_days": MAX_FEED_AGE_DAYS,
    }
    return fetched


def fetch_source_v2(row: dict[str, Any]) -> base.FetchResult:
    if row.get("parser_key") == "DPP_MUSEUM_CALENDAR":
        return base._fetch_dpp(row)
    strategy = str(row.get("fetch_strategy") or "").strip()
    if strategy == "RSS_ATOM_FIRST":
        return _fetch_rss_v2(row)
    if strategy == "ICAL_FIRST":
        return base._fetch_ical(row)
    if strategy == "WORDPRESS_REST_OR_HTML":
        return _drop_navigation_junk(base._fetch_wordpress(row))
    if strategy == "HTML_PARSER":
        return _drop_navigation_junk(base._fetch_html(row))
    raise RuntimeError(f"unsupported fetch_strategy: {strategy or '<empty>'}")


def persist_success_v2(d1, row: dict[str, Any], fetched: base.FetchResult) -> dict[str, Any]:
    observed_at = datetime.now(timezone.utc).isoformat()
    source_id = str(row["source_id"])
    content_hash = hashlib.sha256(fetched.body.encode("utf-8", errors="replace")).hexdigest()
    request_id = f"collect:{COLLECTOR_VERSION}:{source_id}:{content_hash[:20]}"
    next_check_at = (datetime.now(timezone.utc) + timedelta(hours=SOURCE_RECHECK_HOURS)).isoformat()

    statements = []
    finding_ids = []
    for candidate in fetched.candidates:
        finding_id, candidate_statements = base._candidate_statements(
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
        operation="COLLECT_SOURCE_V2",
        entity_type="SOURCE",
        entity_id=source_id,
        statements=statements,
        actor="source-collector-v2",
    )

    return {
        "source_id": source_id,
        "label": row.get("label"),
        "strategy": row.get("fetch_strategy"),
        "parser_key": row.get("parser_key"),
        "collector_version": COLLECTOR_VERSION,
        "endpoint_state": fetched.endpoint_state,
        "status_code": fetched.status_code,
        "raw_items": fetched.raw_items,
        "accepted_items": len(fetched.candidates),
        "rejected_items": fetched.rejected_items,
        "prefilter": getattr(fetched, "prefilter_stats", {}),
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


base.fetch_source = fetch_source_v2
base.persist_success = persist_success_v2


if __name__ == "__main__":
    raise SystemExit(base.main())
