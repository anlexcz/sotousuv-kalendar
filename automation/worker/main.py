from __future__ import annotations

import argparse
import json
import sys

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


def main() -> int:
    parser = argparse.ArgumentParser(description="Šotoušův kalendář worker")
    parser.add_argument("command", choices=["health", "export", "smoke-test"])
    args = parser.parse_args()

    settings = load_settings()

    if args.command == "health":
        return cmd_health(settings)
    if args.command == "export":
        return cmd_export(settings)
    if args.command == "smoke-test":
        return cmd_smoke_test(settings)
    return 1


if __name__ == "__main__":
    sys.exit(main())
