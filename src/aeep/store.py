"""SQLite persistence for route decisions and execution receipts."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

from .errors import ConfigurationError
from .models import (
    ExecutionReceipt,
    LedgerEvent,
    Observation,
    PaymentCapture,
    PaymentRefund,
    PaymentReservation,
    QuotaObservation,
    Quote,
    QuoteAcceptance,
    RateCardSnapshot,
    RouteDecision,
)
from .qualification import QualificationReport, RouteCandidate


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

                CREATE TABLE IF NOT EXISTS quotes (
                    quote_id TEXT PRIMARY KEY,
                    expires_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quote_acceptances (
                    acceptance_id TEXT PRIMARY KEY,
                    quote_id TEXT NOT NULL UNIQUE,
                    accepted_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS payment_objects (
                    object_id TEXT PRIMARY KEY,
                    object_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ledger_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ledger_occurred
                    ON ledger_events(occurred_at DESC);
                CREATE TABLE IF NOT EXISTS observations (
                    observation_id TEXT PRIMARY KEY,
                    provider_id TEXT,
                    capability TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_observations_provider_capability
                    ON observations(provider_id, capability, observed_at DESC);
                CREATE TABLE IF NOT EXISTS idempotency_records (
                    idempotency_key TEXT PRIMARY KEY,
                    request_hash TEXT NOT NULL,
                    state TEXT NOT NULL,
                    decision_id TEXT,
                    status TEXT,
                    receipt_ids_json TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS quota_observations (
                    observation_id TEXT PRIMARY KEY,
                    resource_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_quota_resource_observed
                    ON quota_observations(resource_id, observed_at DESC);
                CREATE TABLE IF NOT EXISTS route_candidates (
                    executor_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qualification_reports (
                    report_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rate_card_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                    workflow_id TEXT PRIMARY KEY,
                    workflow_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    waiting_step_id TEXT,
                    waiting_decision_id TEXT
                );
                """
            )

    def save_route_candidate(self, candidate: RouteCandidate) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO route_candidates
                    (executor_id, source_id, fingerprint, status, payload_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(executor_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    fingerprint = excluded.fingerprint,
                    status = excluded.status,
                    payload_json = excluded.payload_json
                """,
                (
                    candidate.executor_id,
                    candidate.source_id,
                    candidate.behavior_fingerprint,
                    candidate.status.value,
                    candidate.model_dump_json(),
                ),
            )

    def get_route_candidate(self, executor_id: str) -> RouteCandidate | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM route_candidates WHERE executor_id = ?",
                (executor_id,),
            ).fetchone()
        return RouteCandidate.model_validate_json(row[0]) if row else None

    def list_route_candidates(self) -> list[RouteCandidate]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM route_candidates ORDER BY executor_id"
            ).fetchall()
        return [RouteCandidate.model_validate_json(row[0]) for row in rows]

    def save_qualification_report(self, report: QualificationReport) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO qualification_reports
                    (report_id, candidate_id, fingerprint, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    report.report_id,
                    report.candidate_id,
                    report.behavior_fingerprint,
                    report.model_dump_json(),
                ),
            )

    def get_qualification_report(self, report_id: str) -> QualificationReport | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM qualification_reports WHERE report_id = ?",
                (report_id,),
            ).fetchone()
        return QualificationReport.model_validate_json(row[0]) if row else None

    def save_rate_card_snapshot(self, snapshot: RateCardSnapshot) -> None:
        if snapshot.snapshot_id is None:  # pragma: no cover - model validator derives it
            raise ConfigurationError("rate-card snapshot has no digest")
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT payload_json FROM rate_card_snapshots WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            ).fetchone()
            payload = snapshot.model_dump_json()
            if row is not None and row[0] != payload:
                raise ConfigurationError("immutable rate-card snapshot digest collision")
            self._connection.execute(
                "INSERT OR IGNORE INTO rate_card_snapshots (snapshot_id, payload_json) VALUES (?, ?)",
                (snapshot.snapshot_id, payload),
            )

    def get_rate_card_snapshot(self, snapshot_id: str) -> RateCardSnapshot | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM rate_card_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        return RateCardSnapshot.model_validate_json(row[0]) if row else None

    def save_workflow_checkpoint(
        self,
        *,
        workflow_id: str,
        workflow_hash: str,
        status: str,
        waiting_step_id: str | None = None,
        waiting_decision_id: str | None = None,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO workflow_checkpoints
                    (workflow_id, workflow_hash, status, waiting_step_id, waiting_decision_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    workflow_hash = excluded.workflow_hash,
                    status = excluded.status,
                    waiting_step_id = excluded.waiting_step_id,
                    waiting_decision_id = excluded.waiting_decision_id
                """,
                (workflow_id, workflow_hash, status, waiting_step_id, waiting_decision_id),
            )

    def get_workflow_checkpoint(self, workflow_id: str) -> dict[str, str | None] | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT workflow_hash, status, waiting_step_id, waiting_decision_id
                FROM workflow_checkpoints WHERE workflow_id = ?
                """,
                (workflow_id,),
            ).fetchone()
        return dict(row) if row else None

    def claim_idempotency(self, key: str, request_hash: str) -> dict[str, object] | None:
        """Claim a key atomically; return its existing record on duplicate."""

        # ponytail: pending records fail closed after a crash; add expiring leases
        # when multi-process recovery is required.

        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO idempotency_records (idempotency_key, request_hash, state)
                    VALUES (?, ?, 'claimed')
                    """,
                    (key, request_hash),
                )
            return None
        except sqlite3.IntegrityError:
            with self._lock:
                row = self._connection.execute(
                    """
                    SELECT request_hash, state, decision_id, status, receipt_ids_json
                    FROM idempotency_records WHERE idempotency_key = ?
                    """,
                    (key,),
                ).fetchone()
            if row is None:  # pragma: no cover - protected by the unique constraint
                raise ConfigurationError("idempotency record disappeared during lookup") from None
            if row["request_hash"] != request_hash:
                raise ConfigurationError(
                    f"idempotency key {key!r} was already used for a different action"
                ) from None
            return {
                "state": row["state"],
                "decision_id": row["decision_id"],
                "status": row["status"],
                "receipt_ids": json.loads(row["receipt_ids_json"]),
            }

    def complete_idempotency(
        self,
        key: str,
        *,
        decision_id: str,
        status: str,
        receipt_ids: list[str],
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE idempotency_records
                SET state = 'complete', decision_id = ?, status = ?, receipt_ids_json = ?
                WHERE idempotency_key = ? AND state IN ('claimed', 'executing')
                """,
                (decision_id, status, json.dumps(receipt_ids), key),
            )

    def abandon_idempotency(self, key: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM idempotency_records WHERE idempotency_key = ? AND state = 'claimed'",
                (key,),
            )

    def mark_idempotency_executing(self, key: str) -> None:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE idempotency_records SET state = 'executing'
                WHERE idempotency_key = ? AND state = 'claimed'
                """,
                (key,),
            )
            if cursor.rowcount != 1:
                raise ConfigurationError("idempotency claim is not executable")

    def mark_idempotency_indeterminate(self, key: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE idempotency_records SET state = 'indeterminate'
                WHERE idempotency_key = ? AND state = 'executing'
                """,
                (key,),
            )

    def save_quota_observation(self, observation: QuotaObservation) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO quota_observations
                    (observation_id, resource_id, observed_at, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    observation.observation_id,
                    observation.resource_id,
                    observation.observed_at.isoformat(),
                    observation.model_dump_json(),
                ),
            )

    def latest_quota_observation(self, resource_id: str) -> QuotaObservation | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT payload_json FROM quota_observations
                WHERE resource_id = ? ORDER BY observed_at DESC LIMIT 1
                """,
                (resource_id,),
            ).fetchone()
        return QuotaObservation.model_validate_json(row[0]) if row else None

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

    def receipts_for_executor(
        self, executor_id: str, *, limit: int = 200
    ) -> list[ExecutionReceipt]:
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

    def save_quote(self, quote: Quote) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO quotes (quote_id, expires_at, payload_json) VALUES (?, ?, ?)",
                (quote.quote_id, quote.expires_at.isoformat(), quote.model_dump_json()),
            )

    def get_quote(self, quote_id: str) -> Quote | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM quotes WHERE quote_id = ?", (quote_id,)
            ).fetchone()
        return Quote.model_validate_json(row[0]) if row else None

    def save_quote_acceptance(self, acceptance: QuoteAcceptance) -> None:
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO quote_acceptances
                        (acceptance_id, quote_id, accepted_at, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        acceptance.acceptance_id,
                        acceptance.quote_id,
                        acceptance.accepted_at.isoformat(),
                        acceptance.model_dump_json(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ConfigurationError(f"quote {acceptance.quote_id!r} was already accepted") from exc

    def save_payment_object(
        self, value: PaymentReservation | PaymentCapture | PaymentRefund
    ) -> None:
        object_id = (
            value.reservation_id
            if isinstance(value, PaymentReservation)
            else value.capture_id
            if isinstance(value, PaymentCapture)
            else value.refund_id
        )
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO payment_objects (object_id, object_type, payload_json) VALUES (?, ?, ?)",
                (object_id, type(value).__name__, value.model_dump_json()),
            )

    def get_payment_reservation(self, reservation_id: str) -> PaymentReservation | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM payment_objects WHERE object_id = ? AND object_type = ?",
                (reservation_id, "PaymentReservation"),
            ).fetchone()
        return PaymentReservation.model_validate_json(row[0]) if row else None

    def get_payment_capture(self, capture_id: str) -> PaymentCapture | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM payment_objects WHERE object_id = ? AND object_type = ?",
                (capture_id, "PaymentCapture"),
            ).fetchone()
        return PaymentCapture.model_validate_json(row[0]) if row else None

    def save_ledger_event(self, event: LedgerEvent) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO ledger_events (event_id, event_type, occurred_at, payload_json) VALUES (?, ?, ?, ?)",
                (
                    event.event_id,
                    event.event_type,
                    event.occurred_at.isoformat(),
                    event.model_dump_json(),
                ),
            )

    def list_ledger_events(self, *, limit: int = 10_000) -> list[LedgerEvent]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM ledger_events ORDER BY occurred_at DESC LIMIT ?",
                (max(1, min(limit, 10_000)),),
            ).fetchall()
        return [LedgerEvent.model_validate_json(row[0]) for row in rows]

    def save_observation(self, observation: Observation) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO observations
                    (observation_id, provider_id, capability, observed_at, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    observation.observation_id,
                    observation.provider_id,
                    observation.capability,
                    observation.observed_at.isoformat(),
                    observation.model_dump_json(),
                ),
            )

    def list_observations(
        self,
        *,
        provider_id: str | None = None,
        capability: str | None = None,
        limit: int = 10_000,
    ) -> list[Observation]:
        clauses: list[str] = []
        parameters: list[object] = []
        if provider_id is not None:
            clauses.append("provider_id = ?")
            parameters.append(provider_id)
        if capability is not None:
            clauses.append("capability = ?")
            parameters.append(capability)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(1, min(limit, 10_000)))
        with self._lock:
            rows = self._connection.execute(
                f"SELECT payload_json FROM observations {where} ORDER BY observed_at DESC LIMIT ?",
                parameters,
            ).fetchall()
        return [Observation.model_validate_json(row[0]) for row in rows]

    def save_receipts(self, receipts: Iterable[ExecutionReceipt]) -> None:
        for receipt in receipts:
            self.save_receipt(receipt)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> ReceiptStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
