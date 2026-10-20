from __future__ import annotations

import json

from detail_enrichment_test import build_d1

REQUEST_ID = "atomicity-test:v1"
PROBE_KEY = "atomicity_probe_v1"
ACTOR = "atomicity-test"


def main() -> int:
    d1 = build_d1()

    # Clean up only stale leftovers from a previous broken implementation.
    d1.query("DELETE FROM settings WHERE key=?", [PROBE_KEY])
    d1.query("DELETE FROM requests WHERE request_id=?", [REQUEST_ID])

    failed_as_expected = False
    error_text = None
    try:
        d1.execute_idempotent_request(
            request_id=REQUEST_ID,
            operation="ATOMICITY_TEST",
            entity_type="TEST",
            entity_id=PROBE_KEY,
            actor=ACTOR,
            statements=[
                (
                    "INSERT INTO settings(key,value,description) VALUES (?,?,?)",
                    [PROBE_KEY, "SHOULD_ROLL_BACK", "Atomicity probe; must never persist"],
                ),
                # Deliberate CHECK-constraint failure in the requests table.
                (
                    "INSERT INTO requests(request_id,operation,status,started_at,actor) VALUES (?,?,?,datetime('now'),?)",
                    ["atomicity-test:forced-failure", "ATOMICITY_TEST", "INVALID_STATUS", ACTOR],
                ),
            ],
        )
    except Exception as exc:
        failed_as_expected = True
        error_text = str(exc)[:1200]

    probe_rows = d1.query("SELECT key,value FROM settings WHERE key=?", [PROBE_KEY]).rows
    request_rows = d1.query("SELECT request_id,status FROM requests WHERE request_id IN (?,?) ORDER BY request_id", [REQUEST_ID, "atomicity-test:forced-failure"]).rows

    rollback_verified = failed_as_expected and not probe_rows and not request_rows

    # Defensive cleanup if the platform did not roll back as expected.
    if probe_rows:
        d1.query("DELETE FROM settings WHERE key=?", [PROBE_KEY])
    if request_rows:
        d1.query("DELETE FROM requests WHERE request_id IN (?,?)", [REQUEST_ID, "atomicity-test:forced-failure"])

    print(json.dumps({
        "ok": rollback_verified,
        "mode": "D1_ATOMICITY_TEST",
        "failure_triggered": failed_as_expected,
        "rollback_verified": rollback_verified,
        "probe_rows_after_failure": probe_rows,
        "request_rows_after_failure": request_rows,
        "error": error_text,
        "writes_left_after_test": False,
    }, ensure_ascii=False, indent=2))
    return 0 if rollback_verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
