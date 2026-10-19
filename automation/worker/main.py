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


def main() -> int:
    parser = argparse.ArgumentParser(description="Šotoušův kalendář worker")
    parser.add_argument("command", choices=["health", "export"])
    args = parser.parse_args()

    settings = load_settings()

    if args.command == "health":
        return cmd_health(settings)
    if args.command == "export":
        return cmd_export(settings)
    return 1


if __name__ == "__main__":
    sys.exit(main())
