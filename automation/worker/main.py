from __future__ import annotations

import argparse
import json
import sys

from config import load_settings
from export_public import write_public_export
from sheets import SheetsAdapter


def cmd_health(adapter: SheetsAdapter) -> int:
    metadata = adapter.metadata()
    sheet_titles = [sheet["properties"]["title"] for sheet in metadata.get("sheets", [])]
    required = {
        "Akce",
        "AUTO",
        "Výjimky",
        "Zdroje",
        "Vazby zdrojů",
        "Pozorování",
        "Termíny",
        "AUTO Termíny",
        "Nálezy",
        "Historie",
        "Upozornění",
        "Běhy",
        "Požadavky",
        "Nastavení",
        "Katalog polí",
    }
    missing = sorted(required - set(sheet_titles))

    settings_rows = adapter.read_values("Nastavení!A1:C80")
    settings = {row[0]: row[1] for row in settings_rows[1:] if len(row) >= 2}

    result = {
        "spreadsheet_title": metadata.get("properties", {}).get("title"),
        "schema_version": settings.get("schema_version"),
        "production_status": settings.get("production_status"),
        "sync_enabled": settings.get("sync_enabled"),
        "scheduler_enabled": settings.get("scheduler_enabled"),
        "discovery_enabled": settings.get("discovery_enabled"),
        "missing_sheets": missing,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if missing:
        return 2
    if settings.get("schema_version") != "2":
        return 3
    return 0


def cmd_export(adapter: SheetsAdapter, output_path: str) -> int:
    write_public_export(adapter, output_path)
    print(f"Public export written to {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Šotoušův kalendář worker")
    parser.add_argument("command", choices=["health", "export"])
    args = parser.parse_args()

    settings = load_settings()
    adapter = SheetsAdapter.from_service_account(
        spreadsheet_id=settings.spreadsheet_id,
        service_account_info=settings.service_account_info,
    )

    if args.command == "health":
        return cmd_health(adapter)
    if args.command == "export":
        return cmd_export(adapter, settings.public_export_path)
    return 1


if __name__ == "__main__":
    sys.exit(main())
