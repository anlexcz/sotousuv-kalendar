from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

WORKER_DIR = Path(__file__).resolve().parent
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

from d1 import D1Adapter
from structured_sources import StructuredCandidate, stable_finding_id, stable_observation_id

USER_AGENT = "SotousuvKalendarBot/0.1 (+https://github.com/anlexcz/sotousuv-kalendar)"
TARGET_PER_STRATEGY = 2
MAX_SOURCE_ATTEMPTS_PER_STRATEGY = 8
MAX_ITEMS_PER_SOURCE = 5

EVENT_HINTS = (
    "akce", "jízda", "jizda", "jízdy", "jizdy", "výstava", "vystava", "výročí", "vyroci",
    "festival", "slavnost", "den otevřených dveří", "den otevrenych dveri", "setkání", "setkani",
    "sraz", "parní", "parni", "nostalg", "historick", "speciální", "specialni", "mimořád", "mimorad",
    "veranstaltung", "sonderfahrt", "fahrt", "fest", "tag der offenen tür", "museumstag", "jubiläum", "jubilaum",
)
TRANSPORT_HINTS = (
    "tram", "trolejbus", "autobus", "bus", "vlak", "železn", "zelezn", "lokomotiv", "dráh", "drah",
    "úzkokolej", "uzkokolej", "metro", "lanovk", "doprav", "mhd", "eisenbahn", "bahn", "zug", "straßenbahn",
    "strassenbahn", "omnibus", "parkbahn", "lokomotive",
)
SOURCE_TRANSPORT_HINTS = (
    "doprav", "mhd", "tram", "trolejbus", "autobus", "bus", "vlak", "želez", "zelez", "dráh", "drah",
    "úzkokolej", "uzkokolej", "eisenbahn", "bahn", "parkbahn", "lokomotiv", "lanovk", "metro",
)
NEGATIVE_HINTS = (
    "spenden", "donate", "darujte", "pronájem", "pronajem", "poptávkové řízení", "poptavkove rizeni",
    "výběrové řízení", "vyberove rizeni", "veřejná zakázka", "verejna zakazka", "kariéra", "kariera",
    "pracovní nabídka", "pracovni nabidka", "volné místo", "volne misto", "kontakt", "gdpr", "cookies",
)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def build_d1() -> D1Adapter:
    return D1Adapter(
        account_id=os.environ["CLOUDFLARE_ACCOUNT_ID"],
        database_id=os.environ["CLOUDFLARE_D1_DATABASE_ID"],
        api_token=os.environ["CLOUDFLARE_API_TOKEN"],
    )


def cleanup_previous_test_data(d1: D1Adapter) -> dict[str, int]:
    rows = d1.query("SELECT finding_id FROM findings WHERE note LIKE '%\"wp_html_source_test\": true%'").rows
    ids = [str(row["finding_id"]) for row in rows]
    obs_deleted = 0
    findings_deleted = 0
    for finding_id in ids:
        result = d1.query("DELETE FROM observations WHERE finding_id = ?", [finding_id])
        obs_deleted += int(getattr(result, "changes", 0) or 0)
        result = d1.query("DELETE FROM findings WHERE finding_id = ?", [finding_id])
        findings_deleted += int(getattr(result, "changes", 0) or 0)
    return {"findings_deleted": findings_deleted, "observations_deleted": obs_deleted}


def fetch(url: str, accept: str = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1") -> tuple[requests.Response, str]:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
        timeout=30,
        allow_redirects=True,
    )
    response.raise_for_status()
    if response.encoding is None or response.encoding.lower() in {"iso-8859-1", "latin-1"}:
        response.encoding = response.apparent_encoding or "utf-8"
    return response, response.text


def wordpress_rest_url(page_url: str) -> str:
    parts = urlsplit(page_url)
    root = f"{parts.scheme}://{parts.netloc}"
    return root + "/wp-json/wp/v2/posts?per_page=10&orderby=date&order=desc&_fields=id,date,modified,link,title"


def parse_wordpress_rest(payload: object) -> list[StructuredCandidate]:
    if not isinstance(payload, list):
        raise ValueError("WordPress REST response is not a list")
    out: list[StructuredCandidate] = []
    for item in payload[:10]:
        if not isinstance(item, dict):
            continue
        title_obj = item.get("title") or {}
        rendered = title_obj.get("rendered") if isinstance(title_obj, dict) else None
        title = BeautifulSoup(html.unescape(rendered or ""), "html.parser").get_text(" ", strip=True)
        link = str(item.get("link") or "").strip()
        item_id = item.get("id")
        if not title or not link:
            continue
        out.append(
            StructuredCandidate(
                identity=f"wp:{item_id}" if item_id is not None else link,
                title=re.sub(r"\s+", " ", title).strip(),
                detail_url=link,
                event_date_from=None,
                event_date_to=None,
                published_at=str(item.get("date") or item.get("modified") or "") or None,
                raw_kind="WORDPRESS_REST",
            )
        )
    return out


def parse_html_articles(text: str, base_url: str) -> list[StructuredCandidate]:
    soup = BeautifulSoup(text, "html.parser")
    candidates: list[StructuredCandidate] = []
    seen: set[str] = set()

    containers = soup.find_all("article")
    if not containers:
        main = soup.find("main") or soup
        containers = main.find_all(["h1", "h2", "h3"], limit=40)

    for container in containers:
        link = container.find("a", href=True) if hasattr(container, "find") else None
        if link is None:
            heading = container.find(["h1", "h2", "h3"]) if hasattr(container, "find") else None
            if heading is not None:
                link = heading.find("a", href=True)
        if link is None:
            continue

        title = link.get_text(" ", strip=True)
        href = (link.get("href") or "").strip()
        if not title or not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        detail = urljoin(base_url, href)
        if detail in seen:
            continue
        seen.add(detail)
        candidates.append(
            StructuredCandidate(
                identity=detail,
                title=re.sub(r"\s+", " ", title).strip(),
                detail_url=detail,
                event_date_from=None,
                event_date_to=None,
                published_at=None,
                raw_kind="HTML_ARTICLE",
            )
        )
    return candidates


def is_transport_specific_source(label: str) -> bool:
    n = norm(label)
    return any(hint in n for hint in SOURCE_TRANSPORT_HINTS)


def relevance(candidate: StructuredCandidate, source_label: str) -> tuple[bool, str]:
    title = norm(candidate.title)
    url = norm(candidate.detail_url or "")
    combined = f"{title} {url}"
    if any(hint in combined for hint in NEGATIVE_HINTS):
        return False, "negative_keyword"

    event_like = any(hint in combined for hint in EVENT_HINTS)
    transport_like = any(hint in combined for hint in TRANSPORT_HINTS)
    source_specific = is_transport_specific_source(source_label)

    if source_specific and event_like:
        return True, "transport_source+event_hint"
    if transport_like and event_like:
        return True, "transport_hint+event_hint"
    return False, "insufficient_relevance"


def filter_relevant(candidates: list[StructuredCandidate], source_label: str) -> tuple[list[StructuredCandidate], list[dict]]:
    accepted: list[StructuredCandidate] = []
    rejected: list[dict] = []
    for candidate in candidates:
        ok, reason = relevance(candidate, source_label)
        if ok and len(accepted) < MAX_ITEMS_PER_SOURCE:
            accepted.append(candidate)
        else:
            rejected.append({"title": candidate.title, "url": candidate.detail_url, "reason": reason})
    return accepted, rejected


def store_candidate(d1: D1Adapter, source_id: str, candidate: StructuredCandidate, observed_at: str, evidence_ref: str) -> str:
    finding_id = stable_finding_id(source_id, candidate.identity)
    note = {
        "detail_url": candidate.detail_url,
        "published_at": candidate.published_at,
        "raw_kind": candidate.raw_kind,
        "wp_html_source_test": True,
        "relevance_filtered": True,
    }
    d1.query(
        "INSERT INTO findings (finding_id, finding_type, status, title_hint, source_id, first_seen_at, last_seen_at, next_check_at, updated_at, note) "
        "VALUES (?, 'WEB_SOURCE_ITEM', 'OPEN', ?, ?, ?, ?, datetime(?, '+7 days'), ?, ?) "
        "ON CONFLICT(finding_id) DO UPDATE SET title_hint=excluded.title_hint, last_seen_at=excluded.last_seen_at, next_check_at=excluded.next_check_at, updated_at=excluded.updated_at, note=excluded.note",
        [finding_id, candidate.title, source_id, observed_at, observed_at, observed_at, observed_at, json.dumps(note, ensure_ascii=False)],
    )

    fields: list[tuple[str, str]] = [("title", candidate.title)]
    if candidate.detail_url:
        fields.append(("detail_url", candidate.detail_url))
    if candidate.published_at:
        fields.append(("source_published_at", candidate.published_at))

    for field_key, value in fields:
        observation_id = stable_observation_id(source_id, finding_id, field_key, value)
        d1.query(
            "INSERT OR IGNORE INTO observations (observation_id, source_id, subject_type, subject_ref, finding_id, field_key, value_state, value, observed_at, extraction_method, evidence_ref, note) "
            "VALUES (?, ?, 'FINDING', ?, ?, ?, 'VALUE', ?, ?, ?, ?, ?)",
            [observation_id, source_id, finding_id, finding_id, field_key, value, observed_at, candidate.raw_kind, evidence_ref,
             "Deterministic extraction + relevance filter; no LLM; publication time is not event date"],
        )
    return finding_id


def update_source_state(d1: D1Adapter, source_id: str, observed_at: str, response: requests.Response, body: str) -> None:
    content_hash = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()
    next_check_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    d1.query(
        "UPDATE sources SET last_checked_at=?, last_success_at=?, last_http_status=?, consecutive_errors=0, content_hash=?, etag=?, last_modified=?, next_check_at=? WHERE source_id=?",
        [observed_at, observed_at, response.status_code, content_hash, response.headers.get("ETag"), response.headers.get("Last-Modified"), next_check_at, source_id],
    )


def process_wordpress(d1: D1Adapter, row: dict) -> dict:
    source_id = row["source_id"]
    page_url = row["url"]
    rest_url = wordpress_rest_url(page_url)
    observed_at = datetime.now(timezone.utc).isoformat()

    try:
        response, text = fetch(rest_url, "application/json,*/*;q=0.1")
        raw_candidates = parse_wordpress_rest(response.json())
        if not raw_candidates:
            raise RuntimeError("WordPress REST returned zero usable posts")
        endpoint_state = "WP_REST"
        evidence_ref = rest_url
    except Exception:
        response, text = fetch(page_url)
        raw_candidates = parse_html_articles(text, response.url)
        endpoint_state = "HTML_FALLBACK"
        evidence_ref = response.url

    candidates, rejected = filter_relevant(raw_candidates, str(row.get("label") or ""))
    finding_ids = [store_candidate(d1, source_id, c, observed_at, evidence_ref) for c in candidates]
    update_source_state(d1, source_id, observed_at, response, text)
    return {
        "source_id": source_id,
        "label": row.get("label"),
        "strategy": "WORDPRESS_REST_OR_HTML",
        "endpoint_state": endpoint_state,
        "status_code": response.status_code,
        "raw_items": len(raw_candidates),
        "accepted_items": len(candidates),
        "rejected_items": len(rejected),
        "finding_ids": finding_ids,
        "sample": [{"title": c.title, "url": c.detail_url, "kind": c.raw_kind} for c in candidates[:3]],
        "rejected_sample": rejected[:3],
    }


def process_html(d1: D1Adapter, row: dict) -> dict:
    source_id = row["source_id"]
    observed_at = datetime.now(timezone.utc).isoformat()
    response, text = fetch(row["url"])
    raw_candidates = parse_html_articles(text, response.url)
    candidates, rejected = filter_relevant(raw_candidates, str(row.get("label") or ""))
    finding_ids = [store_candidate(d1, source_id, c, observed_at, response.url) for c in candidates]
    update_source_state(d1, source_id, observed_at, response, text)
    return {
        "source_id": source_id,
        "label": row.get("label"),
        "strategy": "HTML_PARSER",
        "endpoint_state": "HTML_FETCHED",
        "status_code": response.status_code,
        "raw_items": len(raw_candidates),
        "accepted_items": len(candidates),
        "rejected_items": len(rejected),
        "finding_ids": finding_ids,
        "sample": [{"title": c.title, "url": c.detail_url, "kind": c.raw_kind} for c in candidates[:3]],
        "rejected_sample": rejected[:3],
    }


def candidate_sources(d1: D1Adapter, strategy: str) -> list[dict]:
    return d1.query(
        "SELECT source_id, label, url, fetch_strategy, priority, active FROM sources "
        "WHERE fetch_strategy=? AND migration_status IN ('MIGRATE','MIGRATE_INACTIVE','FALLBACK_ONLY','ALREADY_PILOT') "
        "AND url IS NOT NULL AND TRIM(url)<>'' ORDER BY COALESCE(priority,999), source_id LIMIT ?",
        [strategy, MAX_SOURCE_ATTEMPTS_PER_STRATEGY],
    ).rows


def main() -> int:
    d1 = build_d1()
    cleanup = cleanup_previous_test_data(d1)
    successes: list[dict] = []
    errors: list[dict] = []

    for strategy, processor in (("WORDPRESS_REST_OR_HTML", process_wordpress), ("HTML_PARSER", process_html)):
        reached = 0
        for row in candidate_sources(d1, strategy):
            if reached >= TARGET_PER_STRATEGY:
                break
            try:
                result = processor(d1, row)
                successes.append(result)
                reached += 1
            except Exception as exc:
                errors.append({"source_id": row.get("source_id"), "label": row.get("label"), "strategy": strategy, "error": str(exc)[:500]})

    active_rows = d1.query("SELECT COUNT(*) AS count FROM sources WHERE active='ANO'").rows
    active_count = int(active_rows[0]["count"]) if active_rows else 0
    wp_ok = sum(1 for x in successes if x["strategy"] == "WORDPRESS_REST_OR_HTML")
    html_ok = sum(1 for x in successes if x["strategy"] == "HTML_PARSER")
    accepted_total = sum(int(x.get("accepted_items") or 0) for x in successes)

    result = {
        "ok": wp_ok >= 1 and html_ok >= 1 and active_count == 0,
        "cleanup_previous_test_data": cleanup,
        "wordpress_sources_processed": wp_ok,
        "html_sources_processed": html_ok,
        "accepted_candidates_total": accepted_total,
        "successful_sources": successes,
        "skipped_or_failed_sources": errors,
        "active_sources_after_test": active_count,
        "safety": {
            "sources_activated": False,
            "scheduler_enabled": False,
            "creates_events": False,
            "publishes": False,
            "calls_llm": False,
            "relevance_filter_enabled": True,
            "publication_time_never_used_as_event_date": True,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 13


if __name__ == "__main__":
    raise SystemExit(main())
