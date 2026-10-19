from __future__ import annotations

import csv
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "SotousuvKalendarSourceAudit/0.1 (+https://github.com/anlexcz/sotousuv-kalendar)"
MAX_BYTES = 2_000_000
TIMEOUT = (6, 18)
MAX_WORKERS = 4

_HOST_LOCKS: dict[str, threading.Lock] = {}
_HOST_LOCKS_GUARD = threading.Lock()


def _host_lock(url: str) -> threading.Lock:
    host = (urlparse(url).hostname or "").lower()
    with _HOST_LOCKS_GUARD:
        return _HOST_LOCKS.setdefault(host, threading.Lock())


def load_legacy_sources(base_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(base_dir.glob("legacy_sources_*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    rows.sort(key=lambda row: int(row["legacy_row"]))
    return rows


def _platform_guess(html_lower: str, url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "facebook.com" in host:
        return "FACEBOOK"
    if "instagram.com" in host:
        return "INSTAGRAM"
    if "webnode." in host or "webnode" in html_lower:
        return "WEBNODE"
    if "estranky." in host or "e-stranky" in html_lower:
        return "ESTRANKY"
    if "websnadno." in host or "websnadno" in html_lower:
        return "WEBSNADNO"
    if "wp-content/" in html_lower or "wp-includes/" in html_lower or "wordpress" in html_lower:
        return "WORDPRESS"
    if "joomla" in html_lower or "option=com_" in html_lower:
        return "JOOMLA"
    if "drupal" in html_lower:
        return "DRUPAL"
    return "HTML"


def _extract_links(html: str, base_url: str) -> tuple[list[str], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    feeds: set[str] = set()
    calendars: set[str] = set()

    for link in soup.find_all("link", href=True):
        rel = " ".join(link.get("rel") or []).lower()
        typ = (link.get("type") or "").lower()
        href = urljoin(base_url, link["href"])
        if "alternate" in rel and typ in {"application/rss+xml", "application/atom+xml", "application/feed+json"}:
            feeds.add(href)
        if typ == "text/calendar" or href.lower().endswith(".ics"):
            calendars.add(href)

    for anchor in soup.find_all("a", href=True):
        href_raw = anchor["href"].strip()
        href = urljoin(base_url, href_raw)
        low = href.lower()
        if low.startswith("webcal:") or ".ics" in low:
            calendars.add(href)

    return sorted(feeds), sorted(calendars)


def _recommend(platform: str, feeds: list[str], calendars: list[str], status_code: int | None) -> str:
    if platform in {"FACEBOOK", "INSTAGRAM"}:
        return "SOCIAL_FALLBACK"
    if status_code in {401, 403, 429}:
        return "BLOCKED_OR_RATE_LIMITED"
    if status_code is None or status_code >= 500:
        return "RETRY_BACKOFF"
    if calendars:
        return "ICAL_FIRST"
    if feeds:
        return "RSS_ATOM_FIRST"
    if platform == "WORDPRESS":
        return "WORDPRESS_REST_OR_HTML"
    return "HTML_PARSER"


def audit_one(source: dict[str, str]) -> dict:
    url = source["url"].strip()
    started = time.perf_counter()
    result = {
        **source,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "status_code": None,
        "final_url": None,
        "content_type": None,
        "bytes_read": 0,
        "elapsed_ms": None,
        "platform": None,
        "feed_links": [],
        "calendar_links": [],
        "etag": None,
        "last_modified": None,
        "recommendation": None,
        "error": None,
    }

    lock = _host_lock(url)
    try:
        with lock:
            time.sleep(0.2)
            with requests.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.3",
                },
                timeout=TIMEOUT,
                allow_redirects=True,
                stream=True,
            ) as response:
                result["status_code"] = response.status_code
                result["final_url"] = response.url
                result["content_type"] = response.headers.get("Content-Type")
                result["etag"] = response.headers.get("ETag")
                result["last_modified"] = response.headers.get("Last-Modified")

                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    remaining = MAX_BYTES - total
                    if remaining <= 0:
                        break
                    piece = chunk[:remaining]
                    chunks.append(piece)
                    total += len(piece)
                    if total >= MAX_BYTES:
                        break

                body = b"".join(chunks)
                result["bytes_read"] = len(body)
                encoding = response.encoding or "utf-8"
                html = body.decode(encoding, errors="replace")
                html_lower = html.lower()
                platform = _platform_guess(html_lower, response.url)
                result["platform"] = platform

                content_type = (result["content_type"] or "").lower()
                if "html" in content_type or "xhtml" in content_type or "<html" in html_lower[:5000]:
                    feeds, calendars = _extract_links(html, response.url)
                    result["feed_links"] = feeds
                    result["calendar_links"] = calendars

                result["ok"] = 200 <= response.status_code < 400
                result["recommendation"] = _recommend(
                    platform,
                    result["feed_links"],
                    result["calendar_links"],
                    response.status_code,
                )
    except Exception as exc:
        result["platform"] = _platform_guess("", url)
        result["recommendation"] = _recommend(result["platform"], [], [], None)
        result["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
    finally:
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)

    return result


def summarize(results: list[dict]) -> dict:
    summary = {
        "total": len(results),
        "ok": sum(1 for row in results if row["ok"]),
        "failed": sum(1 for row in results if not row["ok"]),
        "platforms": {},
        "recommendations": {},
        "http_statuses": {},
    }
    for row in results:
        platform = row.get("platform") or "UNKNOWN"
        summary["platforms"][platform] = summary["platforms"].get(platform, 0) + 1
        rec = row.get("recommendation") or "UNKNOWN"
        summary["recommendations"][rec] = summary["recommendations"].get(rec, 0) + 1
        status = str(row.get("status_code") or "ERROR")
        summary["http_statuses"][status] = summary["http_statuses"].get(status, 0) + 1
    return summary


def write_csv(results: list[dict], path: Path) -> None:
    fields = [
        "legacy_row", "name", "url", "area", "legacy_status", "ok", "status_code",
        "final_url", "content_type", "bytes_read", "elapsed_ms", "platform",
        "recommendation", "feed_links", "calendar_links", "etag", "last_modified", "error",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in results:
            out = {key: row.get(key) for key in fields}
            out["feed_links"] = " | ".join(row.get("feed_links") or [])
            out["calendar_links"] = " | ".join(row.get("calendar_links") or [])
            writer.writerow(out)


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    sources = load_legacy_sources(base_dir)
    if not sources:
        raise RuntimeError("No legacy source CSV files found")

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(audit_one, source): source for source in sources}
        for future in as_completed(futures):
            row = future.result()
            results.append(row)
            print(
                f"[{row['legacy_row']}/{sources[-1]['legacy_row']}] "
                f"{row['name']}: {row.get('status_code') or 'ERR'} -> {row.get('recommendation')}"
            )

    results.sort(key=lambda row: int(row["legacy_row"]))
    summary = summarize(results)

    output_dir = Path("audit_output")
    output_dir.mkdir(exist_ok=True)
    json_path = output_dir / "source-audit.json"
    csv_path = output_dir / "source-audit.csv"
    summary_path = output_dir / "source-audit-summary.json"

    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(results, csv_path)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
