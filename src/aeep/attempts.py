"""Provider-neutral durable execution-attempt state."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import Field, model_validator

from .models import SideEffect, StrictModel, new_id, utc_now


class ExecutionAttemptState(StrEnum):
    CREATED = "CREATED"
    CLAIMED = "CLAIMED"
    RESERVED = "RESERVED"
    INVOKING = "INVOKING"
    VALIDATING = "VALIDATING"
    SETTLING = "SETTLING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    INDETERMINATE = "INDETERMINATE"
    DISPUTED = "DISPUTED"


_TRANSITIONS: dict[ExecutionAttemptState, frozenset[ExecutionAttemptState]] = {
    ExecutionAttemptState.CREATED: frozenset(
        {
            ExecutionAttemptState.CLAIMED,
            ExecutionAttemptState.CANCELLED,
            ExecutionAttemptState.REJECTED,
            ExecutionAttemptState.FAILED,
        }
    ),
    ExecutionAttemptState.CLAIMED: frozenset(
        {
            ExecutionAttemptState.RESERVED,
            ExecutionAttemptState.CANCELLED,
            ExecutionAttemptState.FAILED,
        }
    ),
    ExecutionAttemptState.RESERVED: frozenset(
        {
            ExecutionAttemptState.INVOKING,
            ExecutionAttemptState.CANCELLED,
            ExecutionAttemptState.FAILED,
            ExecutionAttemptState.INDETERMINATE,
        }
    ),
    ExecutionAttemptState.INVOKING: frozenset(
        {
            ExecutionAttemptState.VALIDATING,
            ExecutionAttemptState.FAILED,
            ExecutionAttemptState.INDETERMINATE,
            ExecutionAttemptState.DISPUTED,
        }
    ),
    ExecutionAttemptState.VALIDATING: frozenset(
        {
            ExecutionAttemptState.SETTLING,
            ExecutionAttemptState.FAILED,
            ExecutionAttemptState.REJECTED,
            ExecutionAttemptState.INDETERMINATE,
        }
    ),
    ExecutionAttemptState.SETTLING: frozenset(
        {
            ExecutionAttemptState.COMPLETED,
            ExecutionAttemptState.FAILED,
            ExecutionAttemptState.REJECTED,
            ExecutionAttemptState.INDETERMINATE,
            ExecutionAttemptState.DISPUTED,
        }
    ),
    ExecutionAttemptState.INDETERMINATE: frozenset(
        {ExecutionAttemptState.SETTLING, ExecutionAttemptState.DISPUTED}
    ),
    ExecutionAttemptState.DISPUTED: frozenset({ExecutionAttemptState.SETTLING}),
    ExecutionAttemptState.COMPLETED: frozenset(),
    ExecutionAttemptState.FAILED: frozenset(),
    ExecutionAttemptState.REJECTED: frozenset(),
    ExecutionAttemptState.CANCELLED: frozenset(),
}


class ExecutionAttempt(StrictModel):
    attempt_id: str = Field(default_factory=lambda: new_id("attempt"), min_length=1, max_length=200)
    decision_id: str = Field(min_length=1, max_length=200)
    prepared_id: str | None = Field(default=None, max_length=200)
    action_digest: str = Field(pattern=r"^(?:sha256:)?[a-f0-9]{64}$")
    executor_id: str = Field(min_length=1, max_length=200)
    executor_fingerprint: str = Field(pattern=r"^(?:sha256:)?[a-f0-9]{64}$")
    side_effect: SideEffect
    idempotent: bool
    owner_id: str | None = Field(default=None, max_length=200)
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    version: int = Field(default=0, ge=0)
    state: ExecutionAttemptState = ExecutionAttemptState.CREATED
    external_attempt_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    external_thread_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    external_turn_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    cash_reservation_ids: tuple[str, ...] = ()
    capacity_reservation_ids: tuple[str, ...] = ()
    invocation_start_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    retry_eligible: bool = False
    recovery_reason: str | None = Field(default=None, max_length=2000)
    terminal_receipt_ids: tuple[str, ...] = ()
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def valid_attempt(self) -> ExecutionAttempt:
        for value in (
            self.created_at,
            self.updated_at,
            self.lease_expires_at,
            self.heartbeat_at,
        ):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("execution-attempt times must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("execution attempt cannot be updated before creation")
        if self.state is not ExecutionAttemptState.CREATED and self.owner_id is None:
            raise ValueError("claimed execution attempts require an owner")
        if self.state is ExecutionAttemptState.INVOKING and self.invocation_start_digest is None:
            raise ValueError("INVOKING requires durable invocation-start evidence")
        if self.retry_eligible and (not self.idempotent or self.side_effect.rank > SideEffect.READ.rank):
            raise ValueError("only idempotent read-or-safer attempts may be retry eligible")
        if len(self.cash_reservation_ids) != len(set(self.cash_reservation_ids)):
            raise ValueError("cash reservation IDs must be unique")
        if len(self.capacity_reservation_ids) != len(set(self.capacity_reservation_ids)):
            raise ValueError("capacity reservation IDs must be unique")
        return self

    def can_transition_to(self, state: ExecutionAttemptState) -> bool:
        return state in _TRANSITIONS[self.state]


class AttemptRepository(Protocol):
    def create_execution_attempt(self, attempt: ExecutionAttempt) -> ExecutionAttempt: ...

    def get_execution_attempt(self, attempt_id: str) -> ExecutionAttempt | None: ...

    def claim_execution_attempt(
        self,
        attempt_id: str,
        *,
        owner_id: str,
        claimed_at: datetime,
        lease_expires_at: datetime,
    ) -> ExecutionAttempt: ...

    def transition_execution_attempt(
        self,
        attempt_id: str,
        *,
        expected_state: ExecutionAttemptState,
        expected_version: int,
        target_state: ExecutionAttemptState,
        updated_at: datetime,
        reason: str | None = None,
        cash_reservation_ids: tuple[str, ...] | None = None,
        capacity_reservation_ids: tuple[str, ...] | None = None,
        invocation_start_digest: str | None = None,
        external_attempt_digest: str | None = None,
        external_thread_digest: str | None = None,
        external_turn_digest: str | None = None,
        terminal_receipt_ids: tuple[str, ...] | None = None,
    ) -> ExecutionAttempt: ...


class AttemptService:
    def __init__(self, repository: AttemptRepository) -> None:
        self.repository = repository

    def recover_after_lease(
        self,
        attempt_id: str,
        *,
        inspected_external_status: str | None,
        now: datetime,
    ) -> ExecutionAttempt:
        attempt = self.repository.get_execution_attempt(attempt_id)
        if attempt is None:
            raise ValueError("execution attempt does not exist")
        if attempt.lease_expires_at is None or attempt.lease_expires_at > now:
            raise ValueError("execution attempt lease is still active")
        if attempt.state is ExecutionAttemptState.INVOKING:
            reason = (
                f"external status inspected: {inspected_external_status}"
                if inspected_external_status is not None
                else "external status unavailable after invocation boundary"
            )
            return self.repository.transition_execution_attempt(
                attempt_id,
                expected_state=attempt.state,
                expected_version=attempt.version,
                target_state=ExecutionAttemptState.INDETERMINATE,
                updated_at=now,
                reason=reason,
            )
        raise ValueError("only an expired INVOKING attempt uses external recovery inspection")
