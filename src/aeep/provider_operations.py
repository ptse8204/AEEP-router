"""Durable provider-side idempotency records for the reference SDK."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from .errors import ConfigurationError

OperationKind = Literal[
    "quote_request",
    "execution_attempt",
    "usage",
    "reconciliation",
]


class SQLiteProviderOperationStore:
    """Small local durable store; production multi-host deployments need Postgres."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = RLock()
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_operations (
                operation_kind TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                result_json TEXT,
                PRIMARY KEY (operation_kind, operation_id)
            )
            """
        )
        self._connection.commit()

    def _claim(self, kind: OperationKind, operation_id: str, digest: str) -> bool:
        with self._lock, self._connection:
            row = self._connection.execute(
                """
                SELECT request_digest FROM provider_operations
                WHERE operation_kind = ? AND operation_id = ?
                """,
                (kind, operation_id),
            ).fetchone()
            if row is not None:
                if row[0] != digest:
                    raise ConfigurationError(
                        f"{kind} ID is already claimed with different content"
                    )
                return False
            self._connection.execute(
                """
                INSERT INTO provider_operations(
                    operation_kind, operation_id, request_digest, result_json
                ) VALUES (?, ?, ?, NULL)
                """,
                (kind, operation_id, digest),
            )
            return True

    def _store(
        self,
        kind: OperationKind,
        operation_id: str,
        digest: str,
        result: dict[str, Any],
    ) -> None:
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._lock, self._connection:
            row = self._connection.execute(
                """
                SELECT request_digest, result_json FROM provider_operations
                WHERE operation_kind = ? AND operation_id = ?
                """,
                (kind, operation_id),
            ).fetchone()
            if row is None or row[0] != digest:
                raise ConfigurationError(f"{kind} result has no matching claim")
            if row[1] is not None and row[1] != encoded:
                raise ConfigurationError(f"{kind} result is immutable")
            self._connection.execute(
                """
                UPDATE provider_operations SET result_json = ?
                WHERE operation_kind = ? AND operation_id = ?
                """,
                (encoded, kind, operation_id),
            )

    def _lookup(self, kind: OperationKind, operation_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT result_json FROM provider_operations
                WHERE operation_kind = ? AND operation_id = ?
                """,
                (kind, operation_id),
            ).fetchone()
        return json.loads(row[0]) if row is not None and row[0] is not None else None

    def claim_quote_request(self, request_id: str, digest: str) -> bool:
        return self._claim("quote_request", request_id, digest)

    def store_quote_result(
        self, request_id: str, digest: str, result: dict[str, Any]
    ) -> None:
        self._store("quote_request", request_id, digest, result)

    def lookup_quote_request(self, request_id: str) -> dict[str, Any] | None:
        return self._lookup("quote_request", request_id)

    def claim_execution_attempt(self, attempt_id: str, digest: str) -> bool:
        return self._claim("execution_attempt", attempt_id, digest)

    def store_execution_result(
        self, attempt_id: str, digest: str, result: dict[str, Any]
    ) -> None:
        self._store("execution_attempt", attempt_id, digest, result)

    def lookup_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        return self._lookup("execution_attempt", attempt_id)

    def store_usage(self, usage_id: str, digest: str, result: dict[str, Any]) -> None:
        self._claim("usage", usage_id, digest)
        self._store("usage", usage_id, digest, result)

    def store_reconciliation(
        self, reconciliation_id: str, digest: str, result: dict[str, Any]
    ) -> None:
        self._claim("reconciliation", reconciliation_id, digest)
        self._store("reconciliation", reconciliation_id, digest, result)

    def close(self) -> None:
        self._connection.close()
