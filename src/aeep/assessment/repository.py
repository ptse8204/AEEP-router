"""Assessment persistence using the receipt store's existing transaction boundary."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from typing import Any

from ..errors import ConfigurationError
from ..models import ResourceAccounting, ResourceVector, StrictModel, utc_now
from ..store import ReceiptStore
from .models import (
    AssessmentAuthorization,
    AssessmentBudgetAmendment,
    AssessmentLimits,
    AssessmentOperation,
    AssessmentOperationLedger,
    AssessmentPlan,
    AssessmentPlanningRequest,
    AssessmentScopeAmendment,
    ConformanceProbeRequest,
    RecipeMaterializationRequest,
    ScopedAdmission,
    content_digest,
)


class AssessmentRepository:
    def __init__(self, store: ReceiptStore) -> None:
        self.store = store

    def put(self, kind: str, identity: str, value: StrictModel) -> str:
        with self.store._immediate_transaction() as connection:
            return self._put(connection, kind, identity, value)

    @staticmethod
    def _put(connection: sqlite3.Connection, kind: str, identity: str, value: StrictModel) -> str:
        digest = content_digest(value)
        existing = connection.execute(
            "SELECT digest FROM assessment_records WHERE kind=? AND id=?", (kind, identity)
        ).fetchone()
        if existing is not None and existing[0] != digest:
            raise ConfigurationError("assessment record identity is immutable")
        connection.execute(
            "INSERT OR IGNORE INTO assessment_records VALUES (?, ?, ?, ?)",
            (kind, identity, digest, value.model_dump_json()),
        )
        return digest

    def get(self, kind: str, identity: str) -> dict[str, Any]:
        with self.store._lock:
            row = self.store._connection.execute(
                "SELECT payload_json FROM assessment_records WHERE kind=? AND (id=? OR digest=?)",
                (kind, identity, identity),
            ).fetchone()
        if row is None:
            raise ConfigurationError(f"unknown assessment {kind}")
        result: dict[str, Any] = json.loads(row[0])
        return result

    def review(self, digest: str, *, revoke: bool = False) -> None:
        with self.store._immediate_transaction() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM assessment_records WHERE digest=?", (digest,)
                ).fetchone()
                is None
            ):
                raise ConfigurationError("review requires a stored exact definition")
            connection.execute(
                "INSERT INTO assessment_reviews VALUES (?, ?, ?) ON CONFLICT(digest) DO UPDATE SET revoked=excluded.revoked, approved_at=excluded.approved_at",
                (digest, utc_now().isoformat(), int(revoke)),
            )

    def grant(self, grant: AssessmentAuthorization) -> None:
        with self.store._immediate_transaction() as connection:
            self._put(connection, "authorization", grant.authorization_id, grant)
            connection.execute(
                "INSERT OR IGNORE INTO assessment_grants(id) VALUES (?)", (grant.authorization_id,)
            )

    def approve_bundle(
        self, grant: AssessmentAuthorization | AssessmentScopeAmendment,
        definitions: dict[str, Any],
        *, budget_amendment: AssessmentBudgetAmendment | None = None,
    ) -> None:
        """Validate the complete bundle before committing any review or authority."""
        with self.store._immediate_transaction() as connection:
            if budget_amendment is not None:
                if budget_amendment.authorization_id != grant.authorization_id:
                    raise ConfigurationError("budget amendment must use the bundle's root authorization")
                self._approve_budget_amendment(connection, budget_amendment)
            for digest, definition in definitions.items():
                row = connection.execute(
                    "SELECT payload_json FROM assessment_records WHERE digest=?", (digest,)
                ).fetchone()
                if (content_digest(definition) != digest or row is None
                        or content_digest(json.loads(row[0])) != digest):
                    raise ConfigurationError("review bundle definition is changed or unavailable")
            if isinstance(grant, AssessmentScopeAmendment):
                original = AssessmentAuthorization.model_validate(self.get("authorization", grant.authorization_id))
                state = connection.execute("SELECT revoked FROM assessment_grants WHERE id=?", (grant.authorization_id,)).fetchone()
                effective = self.effective_grant(grant.authorization_id)
                if (state is None or state[0] or not effective.issued_at <= utc_now() < effective.expires_at
                        or content_digest(original) != grant.authorization_digest):
                    raise ConfigurationError("amendment requires its current unrevoked root authorization")
                required = {*grant.subject_digests, *grant.recipe_digests,
                            *grant.environment_digests, *grant.reviewed_digests}
                if not required.issubset(definitions):
                    raise ConfigurationError("amendment requires all scoped and reviewed definitions")
                kind, identity = "scope_amendment", grant.amendment_id
            else:
                required = {*grant.subject_digests, *grant.recipe_digests, *grant.environment_digests}
                if not required.issubset(definitions):
                    raise ConfigurationError("authorization bundle omits a scoped definition")
                kind, identity = "authorization", grant.authorization_id
            digest = content_digest(grant)
            previous = connection.execute("SELECT digest FROM assessment_records WHERE kind=? AND id=?", (kind, identity)).fetchone()
            if previous is not None and previous[0] != digest:
                raise ConfigurationError("assessment authority identity is immutable")
            for reviewed in definitions:
                connection.execute(
                    "INSERT INTO assessment_reviews VALUES (?, ?, 0) ON CONFLICT(digest) DO UPDATE SET revoked=0, approved_at=excluded.approved_at",
                    (reviewed, utc_now().isoformat()),
                )
            connection.execute("INSERT OR IGNORE INTO assessment_records VALUES (?, ?, ?, ?)",
                               (kind, identity, digest, grant.model_dump_json()))
            if isinstance(grant, AssessmentAuthorization):
                connection.execute("INSERT OR IGNORE INTO assessment_grants(id) VALUES (?)", (grant.authorization_id,))

    def approve_budget_amendment(self, amendment: AssessmentBudgetAmendment) -> None:
        """Operator entry point. Never exposed through model-facing tools."""
        with self.store._immediate_transaction() as connection:
            self._approve_budget_amendment(connection, amendment)

    def _approve_budget_amendment(self, connection: sqlite3.Connection, amendment: AssessmentBudgetAmendment) -> None:
        root = AssessmentAuthorization.model_validate(self.get("authorization", amendment.authorization_id))
        state = connection.execute("SELECT revoked FROM assessment_grants WHERE id=?", (root.authorization_id,)).fetchone()
        if state is None or state[0] or content_digest(root) != amendment.authorization_digest:
            raise ConfigurationError("budget amendment requires its unrevoked root authorization")
        existing = connection.execute("SELECT digest FROM assessment_records WHERE kind='budget_amendment' AND id=?", (amendment.amendment_id,)).fetchone()
        if existing is not None:
            if existing[0] != content_digest(amendment):
                raise ConfigurationError("budget amendment identity is immutable")
            return
        latest = connection.execute(
            "SELECT digest FROM assessment_records WHERE kind='budget_amendment' AND json_extract(payload_json, '$.authorization_id')=? ORDER BY rowid DESC LIMIT 1",
            (root.authorization_id,),
        ).fetchone()
        if amendment.previous_amendment_digest != (latest[0] if latest else None):
            raise ConfigurationError("budget amendment predecessor is stale")
        effective = self.effective_grant(root.authorization_id)
        if (amendment.issued_at > utc_now() or amendment.expires_at <= utc_now()
                or amendment.expires_at < effective.expires_at
                or any(getattr(amendment.limits, field) < getattr(effective.limits, field)
                       for field in AssessmentLimits.model_fields)):
            raise ConfigurationError("budget amendment must preserve existing ceilings and expiry")
        self._put(connection, "budget_amendment", amendment.amendment_id, amendment)

    def effective_grant(self, authorization_id: str) -> AssessmentAuthorization:
        grant = AssessmentAuthorization.model_validate(self.get("authorization", authorization_id))
        root_digest = content_digest(grant)
        with self.store._lock:
            rows = self.store._connection.execute(
                "SELECT payload_json FROM assessment_records WHERE kind='scope_amendment' AND json_extract(payload_json, '$.authorization_id')=? ORDER BY id",
                (authorization_id,),
            ).fetchall()
        for row in rows:
            amendment = AssessmentScopeAmendment.model_validate_json(row[0])
            if amendment.authorization_digest != root_digest:
                raise ConfigurationError("amendment root authorization changed")
            grant.subject_digests = sorted(set(grant.subject_digests) | set(amendment.subject_digests))
            grant.recipe_digests = sorted(set(grant.recipe_digests) | set(amendment.recipe_digests))
            grant.environment_digests = sorted(set(grant.environment_digests) | set(amendment.environment_digests))
        with self.store._lock:
            budgets = self.store._connection.execute(
                "SELECT payload_json FROM assessment_records WHERE kind='budget_amendment' AND json_extract(payload_json, '$.authorization_id')=? ORDER BY rowid",
                (authorization_id,),
            ).fetchall()
        predecessor = None
        for row in budgets:
            budget = AssessmentBudgetAmendment.model_validate_json(row[0])
            if budget.authorization_digest != root_digest or budget.previous_amendment_digest != predecessor:
                raise ConfigurationError("budget amendment lineage changed")
            grant.limits = budget.limits
            grant.expires_at = budget.expires_at
            predecessor = content_digest(budget)
        return grant

    def revoke(self, authorization_id: str) -> None:
        with self.store._immediate_transaction() as connection:
            connection.execute(
                "UPDATE assessment_grants SET revoked=1 WHERE id=?", (authorization_id,)
            )

            # The admission marker is retained: revocation must never turn a scoped route into an unrestricted route.
            connection.execute(
                "UPDATE assessment_admissions SET revoked=1, revoked_at=? WHERE admission_id IN (SELECT id FROM assessment_records WHERE kind='admission' AND json_extract(payload_json, '$.authorization_id')=?)",
                (utc_now().isoformat(), authorization_id),
            )

    def revoke_admission(self, executor_id: str) -> None:
        with self.store._immediate_transaction() as connection:
            connection.execute("UPDATE assessment_admissions SET revoked=1, revoked_at=? WHERE executor_id=?", (utc_now().isoformat(), executor_id))

    def current_grant(self, authorization_id: str) -> AssessmentAuthorization:
        grant = self.effective_grant(authorization_id)
        with self.store._lock:
            state = self.store._connection.execute(
                "SELECT revoked FROM assessment_grants WHERE id=?", (grant.authorization_id,)
            ).fetchone()
            if state is None or state[0] or not grant.issued_at <= utc_now() < grant.expires_at:
                raise ConfigurationError("assessment authorization is absent, revoked or expired")
        return grant

    def authorize(self, plan: AssessmentPlan | AssessmentPlanningRequest | RecipeMaterializationRequest | ConformanceProbeRequest | ScopedAdmission) -> AssessmentAuthorization:
        with self.store._lock:
            grant = self.current_grant(plan.authorization_id)
            connection = self.store._connection
            if (
                plan.subject_digest not in grant.subject_digests
                or plan.recipe_digest not in grant.recipe_digests
                or plan.environment_digest not in grant.environment_digests
            ):
                raise ConfigurationError("assessment exceeds authorization scope")
            for digest in {
                *plan.definition_digests,
                plan.recipe_digest,
                plan.mapping_digest,
                plan.environment_digest,
            }:
                review = connection.execute(
                    "SELECT revoked FROM assessment_reviews WHERE digest=?", (digest,)
                ).fetchone()
                if review is None or review[0]:
                    raise ConfigurationError(
                        "assessment definition requires current operator review"
                    )
        return grant

    def reserve(self, plan: AssessmentPlan | AssessmentPlanningRequest | RecipeMaterializationRequest | ConformanceProbeRequest, operation_id: str, limits: AssessmentLimits, *, stage: str = "operation") -> None:
        # Recheck grant and review state while holding the same write transaction as the debit.
        with self.store._immediate_transaction() as connection:
            grant = self.authorize(plan)
            job = connection.execute(
                "SELECT state FROM assessment_jobs WHERE plan_id=? ORDER BY rowid DESC LIMIT 1",
                (plan.plan_id,),
            ).fetchone()
            if job is not None and job[0] in {"cancelled", "indeterminate"}:
                raise ConfigurationError("assessment stopped; no further operations permitted")
            if connection.execute(
                "SELECT 1 FROM assessment_operations WHERE id=?", (operation_id,)
            ).fetchone():
                raise ConfigurationError(
                    "assessment operation already reserved; blind retry denied"
                )
            row = connection.execute(
                "SELECT operations, model_turns, elapsed_seconds, cash_usd FROM assessment_grants WHERE id=?",
                (grant.authorization_id,),
            ).fetchone()
            assert row is not None
            operations = row[0] + limits.max_operations
            turns = row[1] + limits.max_model_turns
            elapsed = row[2] + limits.max_elapsed_seconds
            cash = Decimal(row[3]) + Decimal(str(limits.max_cash_usd))
            if (
                operations > grant.limits.max_operations
                or turns > grant.limits.max_model_turns
                or elapsed > grant.limits.max_elapsed_seconds
                or cash > Decimal(str(grant.limits.max_cash_usd))
            ):
                raise ConfigurationError("assessment budget exhausted")
            connection.execute(
                "UPDATE assessment_grants SET operations=?, model_turns=?, elapsed_seconds=?, cash_usd=? WHERE id=?",
                (operations, turns, elapsed, str(cash), grant.authorization_id),
            )
            connection.execute(
                "INSERT INTO assessment_operations VALUES (?, ?, 'reserved', ?)",
                (operation_id, grant.authorization_id, limits.model_dump_json()),
            )
            operation = AssessmentOperation(operation_id=operation_id, plan_id=plan.plan_id, stage=stage, reserved=limits)
            connection.execute(
                "INSERT INTO assessment_records VALUES ('operation_start', ?, ?, ?)",
                (operation_id, content_digest(operation), operation.model_dump_json()),
            )

    def finish_operation(self, operation_id: str, *, elapsed_seconds: float, accounting: ResourceAccounting | None = None, resources: ResourceVector | None = None) -> None:
        if not 0 <= elapsed_seconds < float("inf"):
            raise ConfigurationError("invalid operation measurement")
        with self.store._immediate_transaction() as connection:
            row = connection.execute(
                "SELECT grant_id, state, reserved_json FROM assessment_operations WHERE id=?",
                (operation_id,),
            ).fetchone()
            if row is None or row[1] != "reserved":
                raise ConfigurationError("operation is absent or already terminal")
            reserved = AssessmentLimits.model_validate_json(row[2])
            if accounting is not None:
                actual_cash = accounting.cash.actual_cash_cost("USD")
                if actual_cash is not None and actual_cash > reserved.max_cash_usd:
                    current_cash = Decimal(connection.execute("SELECT cash_usd FROM assessment_grants WHERE id=?", (row[0],)).fetchone()[0])
                    connection.execute("UPDATE assessment_grants SET revoked=1, cash_usd=? WHERE id=?", (str(current_cash + actual_cash - reserved.max_cash_usd), row[0]))
                elif actual_cash is None and reserved.max_cash_usd > 0:
                    connection.execute("UPDATE assessment_grants SET revoked=1 WHERE id=?", (row[0],))
            if elapsed_seconds > reserved.max_elapsed_seconds:
                connection.execute("UPDATE assessment_grants SET revoked=1 WHERE id=?", (row[0],))
            connection.execute(
                "UPDATE assessment_grants SET elapsed_seconds=max(0, elapsed_seconds-?) WHERE id=?",
                (reserved.max_elapsed_seconds - elapsed_seconds, row[0]),
            )
            connection.execute(
                "UPDATE assessment_operations SET state='complete' WHERE id=?", (operation_id,)
            )
            operation = AssessmentOperation.model_validate(self.get("operation_start", operation_id))
            operation.elapsed_seconds = elapsed_seconds
            operation.accounting = accounting
            operation.resources = resources
            connection.execute(
                "INSERT INTO assessment_records VALUES ('operation_measurement', ?, ?, ?)",
                (operation_id, content_digest(operation), operation.model_dump_json()),
            )

    def operation_ledger(self, plan_id: str, include_ids: list[str] | None = None, source_plan_ids: list[str] | None = None) -> AssessmentOperationLedger:
        identities = include_ids or []
        plans = [plan_id, *(source_plan_ids or [])]
        with self.store._lock:
            rows = self.store._connection.execute(
                "SELECT COALESCE(measured.payload_json, started.payload_json) "
                "FROM assessment_records started LEFT JOIN assessment_records measured "
                "ON measured.kind='operation_measurement' AND measured.id=started.id "
                f"WHERE started.kind='operation_start' AND (json_extract(started.payload_json, '$.plan_id') IN ({','.join('?' for _ in plans)}) "
                f"OR started.id IN ({','.join('?' for _ in identities)})) "
                "ORDER BY started.id", (*plans, *identities),
            ).fetchall()
        return AssessmentOperationLedger(plan_id=plan_id, operations=[AssessmentOperation.model_validate_json(row[0]) for row in rows])
