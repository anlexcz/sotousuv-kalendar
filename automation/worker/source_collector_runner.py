from __future__ import annotations

import os
from typing import Any

import source_collector as base
import source_collector_v2  # noqa: F401 - importing activates v2 fetch/persist hooks


ORIGINAL_SELECT_BATCH = base.select_batch


def select_batch(d1) -> list[dict[str, Any]]:
    source_id = os.environ.get("COLLECT_SOURCE_ID", "").strip()
    due_only = os.environ.get("COLLECT_DUE_ONLY", "").strip().lower() in {"1", "true", "ano", "yes"}

    if source_id:
        rows = d1.query(
            "SELECT source_id,label,url,parser_key,fetch_strategy,feed_url,calendar_url,priority,migration_status,"
            "active,last_checked_at,last_success_at,consecutive_errors,source_group,platform,area "
            "FROM sources WHERE source_id=? "
            "AND migration_status IN ('MIGRATE','MIGRATE_INACTIVE','FALLBACK_ONLY','ALREADY_PILOT') LIMIT 1",
            [source_id],
        ).rows
        if not rows:
            raise RuntimeError(f"Unknown or non-operational source_id: {source_id}")
        return rows

    if due_only:
        return d1.query(
            "SELECT source_id,label,url,parser_key,fetch_strategy,feed_url,calendar_url,priority,migration_status,"
            "active,last_checked_at,last_success_at,consecutive_errors,source_group,platform,area "
            "FROM sources WHERE migration_status IN ('MIGRATE','MIGRATE_INACTIVE','FALLBACK_ONLY','ALREADY_PILOT') "
            "AND url IS NOT NULL AND TRIM(url)<>'' "
            "AND (next_check_at IS NULL OR next_check_at='' OR datetime(next_check_at) <= datetime('now')) "
            "ORDER BY CASE WHEN last_checked_at IS NULL THEN 0 ELSE 1 END, "
            "COALESCE(next_check_at,''), COALESCE(last_checked_at,''), COALESCE(priority,999), source_id LIMIT ?",
            [base.BATCH_SIZE],
        ).rows

    return ORIGINAL_SELECT_BATCH(d1)


base.select_batch = select_batch


if __name__ == "__main__":
    raise SystemExit(base.main())
