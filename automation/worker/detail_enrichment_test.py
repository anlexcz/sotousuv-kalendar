from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from d1 import D1Adapter

USER_AGENT = "SotousuvKalendarBot/0.1 (+https://github.com/anlexcz/sotousuv-kalendar)"
MAX_FINDINGS = 12

MONTHS = {
    "ledna": 1,
    "unora": 2,
    "brezna": 3,
    "dubna": 4,
    "kvetna": 5,
    "cervna": 6,
    "cervence": 7,
    "srpna": 8,
    "zari": 9,
    "rijna": 10,
    "listopadu": 11,
    "prosince": 12,
}

NEGATIVE_TITLE_HINTS = (
    "dodavka ", "dodávka ", "poptavk", "poptávk", "vyberove rizeni", "výběrové řízení",
    "verejna zakazka", "veřejná zakázka", "omezeni dopravy", "omezení dopravy",
    "trvale zmeny", "trvalé změny", "pracovni nabidka", "pracovní nabídka",
    "skoleni", "školení", "prvni mesic v provozu", "první měsíc v provozu",
    "profesni zivot", "profesní život", "zeleznicni soutez", "železniční soutěž",
    "darci krve", "dárci krve",
)


def build_d1() -> D1Adapter:
    return D1Adapter(
        account_id=os.environ["CLOUDFLARE_ACCOUNT_ID"],
        database_id=os.environ["CLOUDFLARE_D1_DATABASE_ID"],
        api_token=os.environ["CLOUDFLARE_API_TOKEN"],
    )


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    return re.sub(r"\s+", " ", value).strip()


def valid_http_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        p = urlsplit(value)
        return p.scheme in {"http", "https"} and bool(p.netloc)
    except Exception:
        return False


def parse_date_value(day: int, month: int, year: int) -> str | None:
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def extract_dates(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()

    # Numeric Czech/European dates: 30. 10. 2026 / 30.10.2026
    for m in re.finditer(r"(?<!\d)(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})(?!\d)", text):
        value = parse_date_value(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if value and value not in seen:
            seen.add(value)
            out.append({"date": value, "raw": m.group(0), "kind": "NUMERIC"})

    # Czech textual dates: 30. října 2026. Normalize only for matching while preserving raw span approximately.
    norm = normalize(text)
    months_pattern = "|".join(MONTHS.keys())
    for m in re.finditer(rf"(?<!\d)(\d{{1,2}})\.\s*({months_pattern})\s+(20\d{{2}})(?!\d)", norm):
        value = parse_date_value(int(m.group(1)), MONTHS[m.group(2)], int(m.group(3)))
        if value and value not in seen:
            seen.add(value)
            out.append({"date": value, "raw": m.group(0), "kind": "CZECH_TEXT"})

    return out


def fetch_page(url: str) -> tuple[requests.Response, str, str]:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1"},
        timeout=30,
        allow_redirects=True,
    )
    response.raise_for_status()
    if response.encoding is None or response.encoding.lower() in {"iso-8859-1", "latin-1"}:
        response.encoding = response.apparent_encoding or "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    main = soup.find("main") or soup.find("article") or soup.body or soup
    visible = main.get_text(" ", strip=True)
    return response, response.text, visible


def load_findings(d1: D1Adapter) -> list[dict]:
    rows = d1.query(
        "SELECT f.finding_id, f.title_hint, f.source_id, f.note, s.label AS source_label "
        "FROM findings f LEFT JOIN sources s ON s.source_id=f.source_id "
        "WHERE f.status='OPEN' ORDER BY f.last_seen_at DESC, f.finding_id"
    ).rows

    observations = d1.query(
        "SELECT finding_id, field_key, value, observed_at FROM observations "
        "WHERE subject_type='FINDING' AND finding_id IS NOT NULL AND value_state='VALUE' "
        "ORDER BY observed_at DESC"
    ).rows
    by_finding: dict[str, dict[str, str]] = {}
    for row in observations:
        fid = str(row.get("finding_id") or "")
        key = str(row.get("field_key") or "")
        if not fid or not key:
            continue
        by_finding.setdefault(fid, {})
        by_finding[fid].setdefault(key, str(row.get("value") or ""))

    result: list[dict] = []
    for row in rows:
        fid = row["finding_id"]
        vals = by_finding.get(fid, {})
        if vals.get("date_from"):
            continue
        detail_url = vals.get("detail_url")
        if not detail_url and row.get("note"):
            try:
                note = json.loads(row["note"])
                detail_url = note.get("detail_url")
            except Exception:
                pass
        title = vals.get("title") or row.get("title_hint") or ""
        if not valid_http_url(detail_url):
            continue
        result.append({
            "finding_id": fid,
            "title": title.strip(),
            "detail_url": detail_url,
            "source_id": row.get("source_id"),
            "source_label": row.get("source_label"),
        })
    return result[:MAX_FINDINGS]


def classify(f: dict) -> dict:
    title = f["title"]
    title_norm = normalize(title)

    if any(h in title_norm for h in [normalize(x) for x in NEGATIVE_TITLE_HINTS]):
        return {**f, "decision": "IRRELEVANT", "reason": "obvious_non_event_title"}

    title_dates = extract_dates(title)
    if len(title_dates) == 1:
        return {
            **f,
            "decision": "DATE_FOUND",
            "reason": "single_explicit_date_in_title",
            "date_from": title_dates[0]["date"],
            "date_to": title_dates[0]["date"],
            "date_evidence": title_dates,
            "http_status": None,
        }
    if len(title_dates) > 1:
        return {**f, "decision": "AMBIGUOUS", "reason": "multiple_dates_in_title", "date_evidence": title_dates}

    try:
        response, _html, visible = fetch_page(f["detail_url"])
    except Exception as exc:
        return {**f, "decision": "FETCH_ERROR", "reason": str(exc)[:500]}

    body_dates = extract_dates(visible)
    today = datetime.now(timezone.utc).date().isoformat()
    future_dates = [d for d in body_dates if d["date"] >= today]

    # Never pick a date from body when more than one future date is present.
    if len(future_dates) == 1:
        return {
            **f,
            "decision": "DATE_FOUND",
            "reason": "single_explicit_future_date_in_detail",
            "date_from": future_dates[0]["date"],
            "date_to": future_dates[0]["date"],
            "date_evidence": future_dates,
            "all_dates_seen": body_dates[:20],
            "http_status": response.status_code,
            "final_url": response.url,
        }
    if len(future_dates) > 1:
        return {
            **f,
            "decision": "AMBIGUOUS",
            "reason": "multiple_future_dates_in_detail",
            "date_evidence": future_dates[:20],
            "http_status": response.status_code,
            "final_url": response.url,
        }

    return {
        **f,
        "decision": "NO_EXPLICIT_DATE",
        "reason": "no_unique_explicit_future_date_found",
        "all_dates_seen": body_dates[:20],
        "http_status": response.status_code,
        "final_url": response.url,
    }


def main() -> int:
    d1 = build_d1()
    settings = {r["key"]: r.get("value") for r in d1.query(
        "SELECT key,value FROM settings WHERE key IN ('event_creation_enabled','scheduler_enabled','production_status')"
    ).rows}
    before_events = int(d1.query("SELECT COUNT(*) AS count FROM events").rows[0]["count"])

    findings = load_findings(d1)
    results = [classify(f) for f in findings]

    after_events = int(d1.query("SELECT COUNT(*) AS count FROM events").rows[0]["count"])
    counts: dict[str, int] = {}
    for row in results:
        counts[row["decision"]] = counts.get(row["decision"], 0) + 1

    safe = (
        settings.get("event_creation_enabled") == "NE"
        and settings.get("scheduler_enabled") == "NE"
        and before_events == after_events
    )

    output = {
        "ok": safe,
        "mode": "DETAIL_ENRICHMENT_DRY_RUN",
        "findings_checked": len(findings),
        "decision_counts": counts,
        "date_found": [r for r in results if r["decision"] == "DATE_FOUND"],
        "ambiguous": [r for r in results if r["decision"] == "AMBIGUOUS"],
        "irrelevant": [r for r in results if r["decision"] == "IRRELEVANT"],
        "unresolved": [r for r in results if r["decision"] in {"NO_EXPLICIT_DATE", "FETCH_ERROR"}],
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
            "calls_llm": False,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if safe else 15


if __name__ == "__main__":
    raise SystemExit(main())
