from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone

import requests

from config import load_settings
from d1 import D1Adapter
from export_public import write_public_export
from sheets import SheetsAdapter


def _build_d1(settings) -> D1Adapter:
    if not settings.d1_configured:
        raise RuntimeError("D1 is not configured")
    return D1Adapter(
        account_id=settings.cloudflare_account_id,
        database_id=settings.cloudflare_d1_database_id,
        api_token=settings.cloudflare_api_token,
    )


def _sheets_health(settings) -> dict:
    if not settings.sheets_configured:
        return {"configured": False}

    adapter = SheetsAdapter.from_service_account(
        spreadsheet_id=settings.spreadsheet_id,
        service_account_info=settings.service_account_info,
    )
    metadata = adapter.metadata()
    sheet_titles = [sheet["properties"]["title"] for sheet in metadata.get("sheets", [])]
    required = {"Akce", "Termíny", "Upozornění", "Nastavení", "Katalog polí"}
    missing = sorted(required - set(sheet_titles))
    return {
        "configured": True,
        "spreadsheet_title": metadata.get("properties", {}).get("title"),
        "missing_editorial_sheets": missing,
    }


def cmd_health(settings) -> int:
    result = {
        "architecture": "D1_CANONICAL_SHEETS_EDITORIAL",
        "d1": {"configured": settings.d1_configured},
        "sheets": _sheets_health(settings),
    }

    if settings.d1_configured:
        d1 = _build_d1(settings)
        result["d1"].update(d1.health())

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not settings.d1_configured:
        return 2
    if result["d1"].get("schema_version") != "2":
        return 3
    if result["sheets"].get("configured") and result["sheets"].get("missing_editorial_sheets"):
        return 4
    return 0


def cmd_export(settings) -> int:
    adapter = _build_d1(settings)
    write_public_export(adapter, settings.public_export_path)
    print(f"Public export written to {settings.public_export_path}")
    return 0


def cmd_smoke_test(settings) -> int:
    d1 = _build_d1(settings)

    request_id = "SMOKE-REQUEST-001"
    source_id = "SRC-SMOKE-001"
    source_url = "https://example.invalid/sotousuv-kalendar-smoke-test"

    d1.execute_idempotent_request(
        request_id=request_id,
        operation="SMOKE_TEST_SOURCE_UPSERT",
        entity_type="SOURCE",
        entity_id=source_id,
        statements=[
            (
                "INSERT INTO sources (source_id, url, source_type, source_scope, label, active, origin, "
                "parser_key, check_policy, first_seen_at, created_at, created_by, note) "
                "VALUES (?, ?, 'TEST', 'DISCOVERY', 'Smoke test source', 'NE', 'SMOKE_TEST', NULL, "
                "'MANUAL_ONLY', datetime('now'), datetime('now'), 'smoke-test', 'Safe synthetic test record') "
                "ON CONFLICT(source_id) DO NOTHING",
                [source_id, source_url],
            )
        ],
        actor="smoke-test",
    )

    request_rows = d1.query(
        "SELECT request_id, status, operation, entity_id FROM requests WHERE request_id = ? LIMIT 1",
        [request_id],
    ).rows
    source_rows = d1.query(
        "SELECT source_id, url, active, origin, check_policy FROM sources WHERE source_id = ? LIMIT 1",
        [source_id],
    ).rows
    source_count = d1.query(
        "SELECT COUNT(*) AS count FROM sources WHERE source_id = ? OR url = ?",
        [source_id, source_url],
    ).rows

    result = {
        "request": request_rows[0] if request_rows else None,
        "source": source_rows[0] if source_rows else None,
        "matching_source_rows": int(source_count[0]["count"]) if source_count else 0,
        "idempotency_ok": bool(
            request_rows
            and request_rows[0].get("status") == "SUCCESS"
            and source_rows
            and int(source_count[0]["count"]) == 1
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["idempotency_ok"] else 5


def cmd_source_test(settings) -> int:
    d1 = _build_d1(settings)

    source_id = "SRC-PILOT-DPP-MUSEUM"
    source_url = "https://muzeum.dpp.cz/kalendar-akci"
    checked_at = datetime.now(timezone.utc)
    next_check_at = checked_at + timedelta(hours=24)

    previous = d1.query(
        "SELECT content_hash FROM sources WHERE url = ? LIMIT 1",
        [source_url],
    ).rows
    previous_hash = previous[0].get("content_hash") if previous else None

    response = requests.get(
        source_url,
        headers={
            "User-Agent": "SotousuvKalendarBot/0.1 (+https://github.com/anlexcz/sotousuv-kalendar)",
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=30,
    )
    response.raise_for_status()

    content_hash = hashlib.sha256(response.content).hexdigest()
    changed = previous_hash != content_hash
    etag = response.headers.get("ETag")
    last_modified = response.headers.get("Last-Modified")

    if previous:
        d1.query(
            "UPDATE sources SET last_checked_at = ?, last_success_at = ?, last_http_status = ?, "
            "consecutive_errors = 0, etag = ?, last_modified = ?, content_hash = ?, next_check_at = ?, "
            "note = ? WHERE url = ?",
            [
                checked_at.isoformat(),
                checked_at.isoformat(),
                response.status_code,
                etag,
                last_modified,
                content_hash,
                next_check_at.isoformat(),
                "Pilot source fetch; intentionally inactive until scheduler approval",
                source_url,
            ],
        )
    else:
        d1.query(
            "INSERT INTO sources (source_id, url, source_type, source_scope, label, active, origin, parser_key, "
            "check_policy, next_check_at, last_checked_at, last_success_at, last_http_status, consecutive_errors, "
            "etag, last_modified, content_hash, first_seen_at, created_at, created_by, note) "
            "VALUES (?, ?, 'WEB_CALENDAR', 'DISCOVERY', 'Muzeum MHD Praha – kalendář akcí', 'NE', 'PILOT', NULL, "
            "'PILOT_24H', ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, 'source-test', ?)",
            [
                source_id,
                source_url,
                next_check_at.isoformat(),
                checked_at.isoformat(),
                checked_at.isoformat(),
                response.status_code,
                etag,
                last_modified,
                content_hash,
                checked_at.isoformat(),
                checked_at.isoformat(),
                "Pilot source fetch; intentionally inactive until scheduler approval",
            ],
        )

    readback = d1.query(
        "SELECT source_id, url, active, source_scope, check_policy, next_check_at, last_checked_at, "
        "last_http_status, consecutive_errors, etag, last_modified, content_hash FROM sources WHERE url = ? LIMIT 1",
        [source_url],
    ).rows

    if not readback:
        print(json.dumps({"ok": False, "error": "Source read-back failed"}, ensure_ascii=False, indent=2))
        return 6

    row = readback[0]
    ok = (
        row.get("source_id") == source_id
        and row.get("url") == source_url
        and row.get("active") == "NE"
        and int(row.get("last_http_status") or 0) == response.status_code
        and row.get("content_hash") == content_hash
    )

    result = {
        "ok": ok,
        "source": row,
        "fetch": {
            "status_code": response.status_code,
            "bytes": len(response.content),
            "changed_since_previous_check": changed,
            "previous_hash": previous_hash,
            "content_hash": content_hash,
            "etag": etag,
            "last_modified": last_modified,
        },
        "safety": {
            "active": "NE",
            "creates_events": False,
            "calls_llm": False,
            "scheduler_enabled": False,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 7


def main() -> int:
    parser = argparse.ArgumentParser(description="Šotoušův kalendář worker")
    parser.add_argument("command", choices=["health", "export", "smoke-test", "source-test"])
    args = parser.parse_args()

    settings = load_settings()

    if args.command == "health":
        return cmd_health(settings)
    if args.command == "export":
        return cmd_export(settings)
    if args.command == "smoke-test":
        return cmd_smoke_test(settings)
    if args.command == "source-test":
        return cmd_source_test(settings)
    return 1


if __name__ == "__main__":
    sys.exit(main())
