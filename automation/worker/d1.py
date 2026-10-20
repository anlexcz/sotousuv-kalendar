from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import requests


@dataclass(frozen=True)
class D1Result:
    rows: list[dict[str, Any]]
    meta: dict[str, Any]


class D1Adapter:
    """Minimal Cloudflare D1 REST adapter.

    Canonical writes belong here, never directly in crawler/LLM code.
    The API token should have only the D1 permissions required by the worker.
    """

    def __init__(self, account_id: str, database_id: str, api_token: str, timeout: int = 30):
        self.account_id = account_id
        self.database_id = database_id
        self.api_token = api_token
        self.timeout = timeout
        self.base_url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
            f"/d1/database/{database_id}/query"
        )

    def _post(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        response = requests.post(
            self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("success"):
            raise RuntimeError(f"D1 API request failed: {body.get('errors')}")

        result = body.get("result") or []
        for idx, item in enumerate(result):
            if not item.get("success", False):
                raise RuntimeError(f"D1 statement {idx} failed: {item}")
        return result

    def query(self, sql: str, params: Iterable[Any] | None = None) -> D1Result:
        payload: dict[str, Any] = {"sql": sql}
        if params is not None:
            payload["params"] = list(params)

        result = self._post(payload)
        if not result:
            return D1Result(rows=[], meta={})

        first = result[0]
        return D1Result(rows=first.get("results") or [], meta=first.get("meta") or {})

    def batch(self, statements: list[tuple[str, Iterable[Any] | None]]) -> list[D1Result]:
        """Execute statements as one D1 batch transaction.

        D1 batch statements execute sequentially and are transactional: if one
        statement fails, the entire batch is rolled back. This is the canonical
        primitive for multi-table domain writes.
        """
        if not statements:
            return []

        batch_payload: list[dict[str, Any]] = []
        for sql, params in statements:
            item: dict[str, Any] = {"sql": sql}
            if params is not None:
                item["params"] = list(params)
            batch_payload.append(item)

        result = self._post({"batch": batch_payload})
        return [
            D1Result(rows=item.get("results") or [], meta=item.get("meta") or {})
            for item in result
        ]

    def health(self) -> dict[str, Any]:
        result = self.query(
            "SELECT value FROM settings WHERE key = ? LIMIT 1",
            ["schema_version"],
        )
        schema_version = result.rows[0]["value"] if result.rows else None
        return {"schema_version": schema_version}

    def execute_idempotent_request(
        self,
        *,
        request_id: str,
        operation: str,
        entity_type: str | None,
        entity_id: str | None,
        statements: list[tuple[str, list[Any]]],
        actor: str = "worker",
    ) -> None:
        """Apply a domain mutation at most once and atomically.

        A previously successful request is a no-op. For a new request, the request
        ledger reservation, all domain statements, and SUCCESS completion are sent
        in one D1 batch transaction. If any statement fails, none of them persist.
        A retry after an ambiguous network failure is safe: if the first attempt
        actually committed, the SUCCESS ledger row is found and the retry returns.
        """
        existing = self.query(
            "SELECT status FROM requests WHERE request_id = ? LIMIT 1",
            [request_id],
        ).rows
        if existing:
            if existing[0].get("status") == "SUCCESS":
                return
            raise RuntimeError(f"request_id {request_id} already exists with non-success status")

        atomic_statements: list[tuple[str, Iterable[Any] | None]] = [
            (
                "INSERT INTO requests (request_id, operation, entity_type, entity_id, status, started_at, actor) "
                "VALUES (?, ?, ?, ?, 'STARTED', datetime('now'), ?)",
                [request_id, operation, entity_type, entity_id, actor],
            ),
            *statements,
            (
                "UPDATE requests SET status = 'SUCCESS', finished_at = datetime('now') WHERE request_id = ?",
                [request_id],
            ),
        ]
        self.batch(atomic_statements)
