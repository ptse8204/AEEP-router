"""SQLite persistence for route decisions and execution receipts."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Iterable

from .errors import ConfigurationError
from .models import ExecutionReceipt, RouteDecision


class ReceiptStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            target = Path(self.path).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            self.path = str(target)
        try:
            self._connection = sqlite3.connect(
                self.path,
                check_same_thread=False,
                timeout=30.0,
            )
        except sqlite3.Error as exc:
            raise ConfigurationError(f"cannot open AEEP database {self.path!r}: {exc}") from exc
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_decisions_capability_created
                    ON decisions(capability, created_at DESC);

                CREATE TABLE IF NOT EXISTS receipts (
                    receipt_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    executor_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_receipts_executor_started
                    ON receipts(executor_id, started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_receipts_decision
                    ON receipts(decision_id, started_at);

                CREATE TABLE IF NOT EXISTS external_reports (
                    decision_id TEXT NOT NULL,
                    executor_id TEXT NOT NULL,
                    receipt_id TEXT NOT NULL UNIQUE,
                    PRIMARY KEY (decision_id, executor_id)
                );
                """
            )

    def save_decision(self, decision: RouteDecision) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO decisions
                    (decision_id, action_id, capability, created_at, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    decision.action.action_id,
                    decision.action.capability,
                    decision.created_at.isoformat(),
                    decision.model_dump_json(),
                ),
            )

    def save_receipt(self, receipt: ExecutionReceipt) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO receipts
                    (receipt_id, decision_id, action_id, capability, executor_id,
                     status, started_at, ended_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.receipt_id,
                    receipt.decision_id,
                    receipt.action_id,
                    receipt.capability,
                    receipt.executor_id,
                    receipt.status.value,
                    receipt.started_at.isoformat(),
                    receipt.ended_at.isoformat(),
                    receipt.model_dump_json(),
                ),
            )

    def save_external_receipt_once(self, receipt: ExecutionReceipt) -> None:
        """Atomically reserve and persist one external report per decision/route."""

        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO external_reports (decision_id, executor_id, receipt_id)
                    VALUES (?, ?, ?)
                    """,
                    (receipt.decision_id, receipt.executor_id, receipt.receipt_id),
                )
                self._connection.execute(
                    """
                    INSERT INTO receipts
                        (receipt_id, decision_id, action_id, capability, executor_id,
                         status, started_at, ended_at, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        receipt.receipt_id,
                        receipt.decision_id,
                        receipt.action_id,
                        receipt.capability,
                        receipt.executor_id,
                        receipt.status.value,
                        receipt.started_at.isoformat(),
                        receipt.ended_at.isoformat(),
                        receipt.model_dump_json(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ConfigurationError(
                f"an external outcome was already reported for decision "
                f"{receipt.decision_id!r} and executor {receipt.executor_id!r}"
            ) from exc

    def get_decision(self, decision_id: str) -> RouteDecision | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM decisions WHERE decision_id = ?", (decision_id,)
            ).fetchone()
        return RouteDecision.model_validate_json(row[0]) if row else None

    def get_receipt(self, receipt_id: str) -> ExecutionReceipt | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM receipts WHERE receipt_id = ?", (receipt_id,)
            ).fetchone()
        return ExecutionReceipt.model_validate_json(row[0]) if row else None

    def list_receipts(
        self,
        *,
        limit: int = 50,
        executor_id: str | None = None,
        capability: str | None = None,
        decision_id: str | None = None,
    ) -> list[ExecutionReceipt]:
        clauses: list[str] = []
        parameters: list[object] = []
        if executor_id:
            clauses.append("executor_id = ?")
            parameters.append(executor_id)
        if capability:
            clauses.append("capability = ?")
            parameters.append(capability)
        if decision_id:
            clauses.append("decision_id = ?")
            parameters.append(decision_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(1, min(limit, 10_000)))
        with self._lock:
            rows = self._connection.execute(
                f"SELECT payload_json FROM receipts {where} ORDER BY started_at DESC LIMIT ?",
                parameters,
            ).fetchall()
        return [ExecutionReceipt.model_validate_json(row[0]) for row in rows]

    def receipts_for_executor(self, executor_id: str, *, limit: int = 200) -> list[ExecutionReceipt]:
        receipts = self.list_receipts(limit=limit, executor_id=executor_id)
        receipts.reverse()
        return receipts

    def list_decisions(self, *, limit: int = 50) -> list[RouteDecision]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM decisions ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 10_000)),),
            ).fetchall()
        return [RouteDecision.model_validate_json(row[0]) for row in rows]

    def save_receipts(self, receipts: Iterable[ExecutionReceipt]) -> None:
        for receipt in receipts:
            self.save_receipt(receipt)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "ReceiptStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
