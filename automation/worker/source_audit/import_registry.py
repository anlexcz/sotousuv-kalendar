from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from d1 import D1Adapter

IMPORTABLE_STATUSES = {
    "MIGRATE",
    "MIGRATE_INACTIVE",
    "FALLBACK_ONLY",
    "ALREADY_PILOT",
}

EXTRA_COLUMNS = {
    "source_class": "TEXT",
    "fetch_strategy": "TEXT",
    "feed_url": "TEXT",
    "calendar_url": "TEXT",
    "priority": "INTEGER",
    "migration_status": "TEXT",
    "source_group": "TEXT",
    "platform": "TEXT",
    "area": "TEXT",
}


def build_d1() -> D1Adapter:
    account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    database_id = os.environ["CLOUDFLARE_D1_DATABASE_ID"]
    api_token = os.environ["CLOUDFLARE_API_TOKEN"]
    return D1Adapter(account_id=account_id, database_id=database_id, api_token=api_token)


def ensure_source_columns(d1: D1Adapter) -> list[str]:
    existing_rows = d1.query("PRAGMA table_info(sources)").rows
    existing = {row["name"] for row in existing_rows}
    added: list[str] = []
    for name, sql_type in EXTRA_COLUMNS.items():
        if name in existing:
            continue
        d1.query(f"ALTER TABLE sources ADD COLUMN {name} {sql_type}")
        added.append(name)
    return added


def normalize(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def main() -> int:
    registry_path = Path("audit_output/migration-registry.csv")
    if not registry_path.exists():
        raise RuntimeError("migration-registry.csv is missing; run audit + registry build first")

    with registry_path.open("r", encoding="utf-8-sig", newline="") as handle:
        registry = list(csv.DictReader(handle))

    d1 = build_d1()
    added_columns = ensure_source_columns(d1)

    imported = 0
    skipped = 0
    errors: list[dict[str, str]] = []

    for row in registry:
        status = row["migration_status"].strip()
        if status not in IMPORTABLE_STATUSES:
            skipped += 1
            continue

        source_id = row["source_id"].strip()
        try:
            d1.query(
                "INSERT INTO sources ("
                "source_id, url, source_type, source_scope, label, active, origin, parser_key, check_policy, "
                "first_seen_at, created_at, created_by, note, source_class, fetch_strategy, feed_url, calendar_url, "
                "priority, migration_status, source_group, platform, area"
                ") VALUES (?, ?, ?, ?, ?, 'NE', 'LEGACY_MIGRATION', ?, ?, datetime('now'), datetime('now'), "
                "'source-registry-import', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(source_id) DO UPDATE SET "
                "url = excluded.url, source_type = excluded.source_type, source_scope = excluded.source_scope, "
                "label = excluded.label, parser_key = excluded.parser_key, check_policy = excluded.check_policy, "
                "note = excluded.note, source_class = excluded.source_class, fetch_strategy = excluded.fetch_strategy, "
                "feed_url = excluded.feed_url, calendar_url = excluded.calendar_url, priority = excluded.priority, "
                "migration_status = excluded.migration_status, source_group = excluded.source_group, "
                "platform = excluded.platform, area = excluded.area",
                [
                    source_id,
                    row["url"].strip(),
                    row["source_type"].strip(),
                    row["source_scope"].strip(),
                    row["label"].strip(),
                    normalize(row.get("parser_key")),
                    row["check_policy"].strip(),
                    row["note"].strip(),
                    row["role"].strip(),
                    row["fetch_strategy"].strip(),
                    normalize(row.get("feed_url")),
                    normalize(row.get("calendar_url")),
                    int(row["priority"]),
                    status,
                    row["source_group"].strip(),
                    normalize(row.get("platform")),
                    normalize(row.get("area")),
                ],
            )
            imported += 1
        except Exception as exc:
            errors.append({"source_id": source_id, "label": row["label"], "error": str(exc)[:500]})

    expected = sum(1 for row in registry if row["migration_status"].strip() in IMPORTABLE_STATUSES)
    readback = d1.query(
        "SELECT COUNT(*) AS count FROM sources WHERE origin = 'LEGACY_MIGRATION' OR source_id = 'SRC-PILOT-DPP-MUSEUM'"
    ).rows
    registry_rows_in_d1 = int(readback[0]["count"]) if readback else 0

    active_rows = d1.query(
        "SELECT COUNT(*) AS count FROM sources WHERE active = 'ANO'"
    ).rows
    active_count = int(active_rows[0]["count"]) if active_rows else 0

    result = {
        "ok": not errors and imported == expected and active_count == 0,
        "registry_rows": len(registry),
        "expected_importable": expected,
        "imported_or_updated": imported,
        "skipped_non_operational": skipped,
        "added_columns": added_columns,
        "registry_rows_visible_in_d1": registry_rows_in_d1,
        "active_sources_after_import": active_count,
        "errors": errors,
        "safety": {
            "all_imports_forced_inactive": True,
            "scheduler_enabled": False,
            "creates_events": False,
            "publishes": False,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 11


if __name__ == "__main__":
    raise SystemExit(main())
