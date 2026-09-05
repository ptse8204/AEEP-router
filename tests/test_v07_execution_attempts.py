from __future__ import annotations

import hashlib
import sys
from datetime import UTC, datetime, timedelta

import pytest

from aeep.attempts import AttemptService, ExecutionAttempt, ExecutionAttemptState
from aeep.capacity import CapacityObservation, CapacityWindow
from aeep.errors import ConfigurationError
from aeep.executors.base import BaseExecutor, ExecutionContext
from aeep.hosts import HostModel, HostProbe, HostProbeStatus, ManagedHostExecutionContext
from aeep.models import (
    ActionRequest,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    Manifest,
    RawExecution,
    SideEffect,
    SubscriptionResource,
)
from aeep.router import Router
from aeep.store import ReceiptStore

NOW = datetime(2030, 1, 1, tzinfo=UTC)
DIGEST = f"sha256:{hashlib.sha256(b'fixture').hexdigest()}"


def attempt(attempt_id: str = "attempt-fixture") -> ExecutionAttempt:
    return ExecutionAttempt(
        attempt_id=attempt_id,
        decision_id="decision-fixture",
        action_digest=DIGEST,
        executor_id="executor-fixture",
        executor_fingerprint=DIGEST,
        side_effect=SideEffect.READ,
        idempotent=True,
        retry_eligible=True,
        created_at=NOW,
        updated_at=NOW,
    )


def advance(
    store: ReceiptStore, current: ExecutionAttempt, target: ExecutionAttemptState
) -> ExecutionAttempt:
    kwargs = (
        {"invocation_start_digest": DIGEST}
        if target is ExecutionAttemptState.INVOKING
        else {}
    )
    return store.transition_execution_attempt(
        current.attempt_id,
        expected_state=current.state,
        expected_version=current.version,
        target_state=target,
        updated_at=current.updated_at + timedelta(seconds=1),
        **kwargs,
    )


@pytest.mark.parametrize(
    "stop",
    [
        ExecutionAttemptState.CREATED,
        ExecutionAttemptState.CLAIMED,
        ExecutionAttemptState.RESERVED,
        ExecutionAttemptState.INVOKING,
        ExecutionAttemptState.VALIDATING,
        ExecutionAttemptState.SETTLING,
        ExecutionAttemptState.COMPLETED,
    ],
)
def test_fault_at_every_state_is_durable(tmp_path, stop: ExecutionAttemptState):
    path = tmp_path / f"{stop.value}.sqlite3"
    store = ReceiptStore(path)
    current = store.create_execution_attempt(attempt())
    if stop is not ExecutionAttemptState.CREATED:
        current = store.claim_execution_attempt(
            current.attempt_id,
            owner_id="worker-a",
            claimed_at=NOW,
            lease_expires_at=NOW + timedelta(minutes=1),
        )
    for target in (
        ExecutionAttemptState.RESERVED,
        ExecutionAttemptState.INVOKING,
        ExecutionAttemptState.VALIDATING,
        ExecutionAttemptState.SETTLING,
        ExecutionAttemptState.COMPLETED,
    ):
        if stop in {ExecutionAttemptState.CREATED, ExecutionAttemptState.CLAIMED}:
            break
        current = advance(store, current, target)
        if target is stop:
            break
    store.close()
    reopened = ReceiptStore(path)
    try:
        assert reopened.get_execution_attempt("attempt-fixture").state is stop
    finally:
        reopened.close()


def test_two_workers_cannot_claim_and_stale_cas_fails(tmp_path):
    path = tmp_path / "claims.sqlite3"
    first = ReceiptStore(path)
    second = ReceiptStore(path)
    try:
        created = first.create_execution_attempt(attempt())
        claimed = first.claim_execution_attempt(
            created.attempt_id,
            owner_id="worker-a",
            claimed_at=NOW,
            lease_expires_at=NOW + timedelta(minutes=1),
        )
        with pytest.raises(ConfigurationError, match="already claimed"):
            second.claim_execution_attempt(
                created.attempt_id,
                owner_id="worker-b",
                claimed_at=NOW,
                lease_expires_at=NOW + timedelta(minutes=1),
            )
        advanced = advance(first, claimed, ExecutionAttemptState.RESERVED)
        with pytest.raises(ConfigurationError, match="compare-and-set"):
            first.transition_execution_attempt(
                created.attempt_id,
                expected_state=ExecutionAttemptState.CLAIMED,
                expected_version=claimed.version,
                target_state=ExecutionAttemptState.RESERVED,
                updated_at=NOW + timedelta(seconds=2),
            )
        assert advanced.version == 2
    finally:
        first.close()
        second.close()


def test_recovery_inspects_external_state_and_never_retries_invoking_attempt():
    store = ReceiptStore(":memory:")
    created = store.create_execution_attempt(
        attempt().model_copy(
            update={
                "created_at": NOW - timedelta(minutes=3),
                "updated_at": NOW - timedelta(minutes=3),
            }
        )
    )
    claimed = store.claim_execution_attempt(
        created.attempt_id,
        owner_id="worker-a",
        claimed_at=NOW - timedelta(minutes=2),
        lease_expires_at=NOW - timedelta(minutes=1),
    )
    reserved = advance(store, claimed, ExecutionAttemptState.RESERVED)
    invoking = advance(store, reserved, ExecutionAttemptState.INVOKING)
    recovered = AttemptService(store).recover_after_lease(
        invoking.attempt_id,
        inspected_external_status=None,
        now=NOW,
    )
    assert recovered.state is ExecutionAttemptState.INDETERMINATE
    assert recovered.retry_eligible
    assert "unavailable" in recovered.recovery_reason


class LocalExecutor(BaseExecutor):
    async def execute(self, context: ExecutionContext) -> RawExecution:
        return RawExecution(status=ExecutionStatus.SUCCESS, output={"ok": True})


@pytest.mark.asyncio
async def test_ordinary_execution_uses_complete_attempt_chain():
    spec = ExecutorSpec(
        id="local",
        capability="fixture.attempt@1",
        kind=ExecutorKind.COMMAND,
        description="fixture",
        config={"argv": [sys.executable, "-V"]},
    )
    router = Router(
        Manifest(database=":memory:", executors=[spec]),
        executor_overrides={ExecutorKind.COMMAND: LocalExecutor()},
        clock=lambda: NOW,
    )
    try:
        outcome = await router.execute(
            ActionRequest(capability="fixture.attempt@1", input={"private": "not-stored"})
        )
        stored = router.store.execution_attempt_for_decision(outcome.decision.decision_id)
        assert stored is not None and stored.state is ExecutionAttemptState.COMPLETED
        assert stored.terminal_receipt_ids == (outcome.receipts[0].receipt_id,)
        assert "not-stored" not in stored.model_dump_json()
    finally:
        await router.close()


class CrashingManagedHost:
    def __init__(self) -> None:
        self.calls = 0

    async def probe(self) -> HostProbe:
        return HostProbe(adapter_id="crash-host", status=HostProbeStatus.READY)

    async def snapshot_capacity(self) -> CapacityObservation:
        return CapacityObservation(
            resource_id="crash-capacity",
            source="fixture",
            windows=(CapacityWindow(window_id="primary", used_percent=1),),
        )

    async def list_models(self) -> list[HostModel]:
        return [HostModel(id="fixture-model")]

    async def execute(self, context: ManagedHostExecutionContext) -> RawExecution:
        self.calls += 1
        raise RuntimeError("simulated crash after turn start")

    async def interrupt(self, attempt_id: str) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_managed_crash_is_indeterminate_and_same_decision_cannot_duplicate():
    host = CrashingManagedHost()
    spec = ExecutorSpec(
        id="managed",
        capability="fixture.crash@1",
        kind=ExecutorKind.MANAGED_HOST,
        description="fixture",
        resource_pool="crash-capacity",
        config={
            "adapter_id": "crash-host",
            "argv": [sys.executable, "fixture"],
            "instructions": "Bounded fixture {input.value}",
        },
    )
    router = Router(
        Manifest(
            database=":memory:",
            resources=[
                SubscriptionResource(
                    id="crash-capacity", provider="fixture", product="fixture"
                )
            ],
            executors=[spec],
        ),
        managed_host_adapters={"crash-host": host},
        clock=lambda: NOW,
    )
    request = ActionRequest(capability="fixture.crash@1", input={"value": 1})
    try:
        decision = await router.route_with_discovery(request)
        with pytest.raises(RuntimeError, match="simulated crash"):
            await router.execute(decision)
        stored = router.store.execution_attempt_for_decision(decision.decision_id)
        assert stored is not None and stored.state is ExecutionAttemptState.INDETERMINATE
        with pytest.raises(ConfigurationError, match="blind retry denied"):
            await router.execute(decision)
        assert host.calls == 1
    finally:
        await router.close()
