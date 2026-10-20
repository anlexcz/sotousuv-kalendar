from __future__ import annotations

import materialize_hybrid_test as base

_original_ai_candidate = base.ai_candidate


def guarded_ai_candidate(api_key: str, finding: dict) -> dict:
    result = _original_ai_candidate(api_key, finding)
    ai = result.get("ai") or {}
    if result.get("status") == "READY_AI" and ai.get("term_semantics") == "RECURRENCE":
        return {
            "status": "SKIPPED_RECURRENCE_UNSUPPORTED",
            "ai": ai,
            "recurrence_type": ai.get("recurrence_type"),
            "recurrence_date_from": ai.get("recurrence_date_from"),
            "recurrence_date_to": ai.get("recurrence_date_to"),
            "recurrence_description": ai.get("recurrence_description"),
        }
    return result


base.ai_candidate = guarded_ai_candidate

if __name__ == "__main__":
    raise SystemExit(base.main())
