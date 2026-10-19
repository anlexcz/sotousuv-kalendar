from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from d1 import D1Adapter


def build_d1() -> D1Adapter:
    return D1Adapter(
        account_id=os.environ["CLOUDFLARE_ACCOUNT_ID"],
        database_id=os.environ["CLOUDFLARE_D1_DATABASE_ID"],
        api_token=os.environ["CLOUDFLARE_API_TOKEN"],
    )


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def canonical_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        p = urlsplit(value.strip())
        if not p.scheme or not p.netloc:
            return value.strip()
        path = p.path.rstrip("/") or "/"
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, p.query, ""))
    except Exception:
        return value.strip()


def infer_categories(title: str) -> list[str]:
    t = f" {normalize_text(title)} "
    rules = [
        ("tram", [" tram ", " tramvaj", " streetcar"]),
        ("trolleybus", [" trolejbus", " trolleybus"]),
        ("bus", [" autobus", " bus ", " skoda 706", " rto "]),
        ("metro", [" metro "]),
        ("cableway", [" lanovk", " funicular", " cable car"]),
        ("rail", [" vlak", " zelezn", " railway", " railroad", " lokomotiv", " parni "]),
        ("water", [" lod", " parnik", " boat", " ship"]),
        ("air", [" letec", " letadl", " aviation", " aircraft"]),
    ]
    found: list[str] = []
    for category, needles in rules:
        if any(needle in t for needle in needles):
            found.append(category)
    return found or ["other"]


IRRELEVANT_PATTERNS = [
    r"\bverejn[aá] zak[aá]zka\b",
    r"\bpopt[aá]vkov[eé] r[ií]zen[ií]\b",
    r"\bpron[aá]jem\b",
    r"\bv[oó]ip\b",
    r"\btelefon[uůy]?\b",
    r"\bskolen[ií]\b",
    r"\bpracovn[ií] nab[ií]dka\b",
    r"\bvoln[eé] pozice\b",
    r"\bv[yý]b[eě]rov[eé] r[ií]zen[ií]\b",
    r"\bomezen[ií] dopravy\b",
    r"\btrval[eé] zm[eě]ny\b",
    r"\bj[ií]zdn[ií] [rř][aá]dy\b",
    r"\bprvn[ií] m[eě]s[ií]c v provozu\b",
    r"\bcel[yý] profesn[ií] [zž]ivot\b",
]


def irrelevant_reason(title: str) -> str | None:
    t = normalize_text(title)
    for pattern in IRRELEVANT_PATTERNS:
        if re.search(pattern, t):
            return "obvious_non_event_title"
    return None


def _parse_note(note: str | None) -> dict:
    if not note:
        return {}
    try:
        obj = json.loads(note)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def load_findings(d1: D1Adapter) -> list[dict]:
    findings = d1.query(
        "SELECT f.finding_id, f.finding_type, f.status, f.title_hint, f.source_id, f.first_seen_at, f.last_seen_at, f.note, "
        "s.url AS source_url, s.label AS source_label, s.source_scope, s.active AS source_active "
        "FROM findings f LEFT JOIN sources s ON s.source_id=f.source_id "
        "WHERE f.status='OPEN' ORDER BY f.last_seen_at DESC, f.finding_id"
    ).rows

    obs = d1.query(
        "SELECT finding_id, field_key, value, value_state, observed_at, evidence_ref FROM observations "
        "WHERE subject_type='FINDING' AND finding_id IS NOT NULL AND value_state='VALUE' "
        "ORDER BY observed_at DESC"
    ).rows

    by_finding: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in obs:
        fid = row.get("finding_id")
        key = row.get("field_key")
        if fid and key and key not in by_finding[fid]:
            by_finding[fid][key] = row

    out: list[dict] = []
    for f in findings:
        values = by_finding.get(f["finding_id"], {})
        note = _parse_note(f.get("note"))
        title = (values.get("title") or {}).get("value") or f.get("title_hint") or ""
        detail_url = (values.get("detail_url") or {}).get("value") or note.get("detail_url")
        out.append({
            **f,
            "title": title.strip(),
            "date_from": (values.get("date_from") or {}).get("value"),
            "date_to": (values.get("date_to") or {}).get("value"),
            "detail_url": detail_url,
            "title_evidence": (values.get("title") or {}).get("evidence_ref"),
            "date_evidence": (values.get("date_from") or {}).get("evidence_ref"),
        })
    return out


def load_existing_identities(d1: D1Adapter) -> set[tuple[str, str]]:
    rows = d1.query(
        "SELECT e.title, t.date_from FROM events e JOIN terms t ON t.event_id=e.event_id "
        "WHERE e.is_active='ANO' AND t.is_active='ANO'"
    ).rows
    return {(normalize_text(r.get("title") or ""), r.get("date_from") or "") for r in rows}


def main() -> int:
    d1 = build_d1()
    today = datetime.now(timezone.utc).date().isoformat()

    settings_rows = d1.query(
        "SELECT key, value FROM settings WHERE key IN ('event_creation_enabled','scheduler_enabled','production_status')"
    ).rows
    settings = {r["key"]: r.get("value") for r in settings_rows}
    before_events = int(d1.query("SELECT COUNT(*) AS count FROM events").rows[0]["count"])

    findings = load_findings(d1)
    existing = load_existing_identities(d1)

    url_leaders: dict[str, str] = {}
    identity_leaders: dict[tuple[str, str], str] = {}
    proposals: list[dict] = []

    for f in findings:
        title = f["title"]
        date_from = f.get("date_from")
        date_to = f.get("date_to") or date_from
        detail = canonical_url(f.get("detail_url"))
        source_url = canonical_url(f.get("source_url"))
        usable_url = detail or source_url
        title_norm = normalize_text(title)

        decision = "KEEP_FINDING"
        reason = "missing_explicit_date"
        duplicate_of = None

        non_event = irrelevant_reason(title)
        if not title_norm:
            reason = "missing_title"
        elif non_event:
            decision = "IRRELEVANT_CANDIDATE"
            reason = non_event
        elif not usable_url:
            reason = "missing_usable_source_url"
        elif date_from and date_from < today:
            reason = "explicit_term_is_historical"
        elif detail and detail in url_leaders:
            decision = "DUPLICATE_CANDIDATE"
            reason = "same_detail_url"
            duplicate_of = url_leaders[detail]
        elif date_from and (title_norm, date_from) in identity_leaders:
            decision = "DUPLICATE_CANDIDATE"
            reason = "exact_normalized_title_and_date"
            duplicate_of = identity_leaders[(title_norm, date_from)]
        elif date_from and (title_norm, date_from) in existing:
            decision = "DUPLICATE_EXISTING_EVENT"
            reason = "exact_existing_event_title_and_date"
        elif date_from:
            decision = "READY_FOR_EVENT"
            reason = "explicit_date_title_and_source"

        if decision != "IRRELEVANT_CANDIDATE":
            if detail and detail not in url_leaders:
                url_leaders[detail] = f["finding_id"]
            if date_from and (title_norm, date_from) not in identity_leaders:
                identity_leaders[(title_norm, date_from)] = f["finding_id"]

        proposal = {
            "finding_id": f["finding_id"],
            "source_id": f.get("source_id"),
            "source_label": f.get("source_label"),
            "decision": decision,
            "reason": reason,
            "duplicate_of": duplicate_of,
            "candidate": {
                "title": title,
                "date_from": date_from,
                "date_to": date_to,
                "source_url": usable_url,
                "categories": infer_categories(title) if decision == "READY_FOR_EVENT" else None,
                "all_day": None,
                "event_state": "AKTIVNI" if decision == "READY_FOR_EVENT" else None,
                "review_state": "NEZKONTROLOVANO" if decision == "READY_FOR_EVENT" else None,
                "publish": "NE",
            },
        }
        proposals.append(proposal)

    after_events = int(d1.query("SELECT COUNT(*) AS count FROM events").rows[0]["count"])
    counts: dict[str, int] = defaultdict(int)
    for p in proposals:
        counts[p["decision"]] += 1

    safe = (
        settings.get("event_creation_enabled") == "NE"
        and before_events == after_events
        and settings.get("scheduler_enabled") == "NE"
    )

    result = {
        "ok": safe,
        "mode": "DRY_RUN_V2",
        "open_findings": len(findings),
        "decision_counts": dict(sorted(counts.items())),
        "ready_for_event": [p for p in proposals if p["decision"] == "READY_FOR_EVENT"],
        "duplicates": [p for p in proposals if p["decision"].startswith("DUPLICATE")],
        "irrelevant_candidates": [p for p in proposals if p["decision"] == "IRRELEVANT_CANDIDATE"],
        "kept_findings_sample": [p for p in proposals if p["decision"] == "KEEP_FINDING"][:10],
        "safety": {
            "event_creation_enabled": settings.get("event_creation_enabled"),
            "scheduler_enabled": settings.get("scheduler_enabled"),
            "production_status": settings.get("production_status"),
            "events_before": before_events,
            "events_after": after_events,
            "writes_events": False,
            "writes_event_auto": False,
            "writes_terms": False,
            "changes_finding_status": False,
            "publishes": False,
            "calls_llm": False,
            "all_day_is_never_guessed": True,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if safe else 14


if __name__ == "__main__":
    raise SystemExit(main())
