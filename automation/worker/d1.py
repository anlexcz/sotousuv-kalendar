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

    def query(self, sql: str, params: Iterable[Any] | None = None) -> D1Result:
        payload: dict[str, Any] = {"sql": sql}
        if params is not None:
            payload["params"] = list(params)

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
        if not result:
            return D1Result(rows=[], meta={})

        first = result[0]
        if not first.get("success", False):
            raise RuntimeError(f"D1 query failed: {first}")
        return D1Result(rows=first.get("results") or [], meta=first.get("meta") or {})

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
        """Apply a request at most once.

        This is intentionally conservative. The first production implementation should
        execute the ledger reservation + domain mutation transactionally. D1 supports
        multiple statements/batches; this method is a guardrail skeleton until the
        repository layer for individual entities is implemented and tested.
        """
        existing = self.query(
            "SELECT status FROM requests WHERE request_id = ? LIMIT 1",
            [request_id],
        ).rows
        if existing:
            if existing[0].get("status") == "SUCCESS":
                return
            raise RuntimeError(f"request_id {request_id} already exists with non-success status")

        self.query(
            "INSERT INTO requests (request_id, operation, entity_type, entity_id, status, started_at, actor) "
            "VALUES (?, ?, ?, ?, 'STARTED', datetime('now'), ?)",
            [request_id, operation, entity_type, entity_id, actor],
        )
        try:
            for sql, params in statements:
                self.query(sql, params)
            self.query(
                "UPDATE requests SET status = 'SUCCESS', finished_at = datetime('now') WHERE request_id = ?",
                [request_id],
            )
        except Exception as exc:
            try:
                self.query(
                    "UPDATE requests SET status = 'FAILED', finished_at = datetime('now'), error = ? "
                    "WHERE request_id = ?",
                    [str(exc)[:2000], request_id],
                )
            finally:
                raise
