from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from aeep.attempts import ExecutionAttempt, ExecutionAttemptState
from aeep.capacity import CapacityObservation, CapacityReservation, CapacityWindow
from aeep.errors import ConfigurationError, NoRouteError
from aeep.hosts import HostProbe, HostProbeStatus
from aeep.models import (
    ActionRequest,
    ExecutionStatus,
    ExecutorSpec,
    Manifest,
    RawExecution,
    SideEffect,
)
from aeep.router import Router
from aeep.store import ReceiptStore

NOW = datetime(2030, 1, 1, tzinfo=UTC)


class Host:
    def __init__(self, *, remaining="1", status=ExecutionStatus.SUCCESS):
        self.remaining = remaining
        self.status = status
        self.started = asyncio.Event()
        self.finish = asyncio.Event()
        self.calls = 0

    async def probe(self):
        return HostProbe(adapter_id="fixture", status=HostProbeStatus.READY)

    async def snapshot_capacity(self):
        return CapacityObservation(
            resource_id="pool",
            source="fixture",
            observed_at=NOW,
            windows=(CapacityWindow(window_id="primary", remaining=self.remaining),),
        )

    async def execute(self, context):
        self.calls += 1
        self.started.set()
        await self.finish.wait()
        return RawExecution(status=self.status, output={"ok": True})

    async def close(self):
        pass


def router(path, host):
    spec = ExecutorSpec(
        id="managed",
        capability="fixture@1",
        kind="host_managed",
        description="fixture",
        resource_pool="pool",
        estimate={"resources": {"subscription_units": 1, "monetary_usd": 0}},
        config={
            "adapter_id": "fixture",
            "argv": [sys.executable, "fixture"],
            "instructions": "Bounded action",
        },
    )
    return Router(
        Manifest(
            database=str(path),
            executors=[spec],
            resources=[{"id": "pool", "provider": "fixture", "product": "fixture"}],
        ),
        managed_host_adapters={"fixture": host},
        clock=lambda: NOW,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("prepared", [False, True])
async def test_shared_capacity_blocks_concurrent_invocation_and_releases(tmp_path, prepared):
    host = Host()
    first = router(tmp_path / "shared.db", host)
    second = router(tmp_path / "shared.db", host)
    request = ActionRequest(capability="fixture@1")

    async def run(instance):
        if prepared:
            decision = await instance.prepare_route(request)
            return await instance.execute_prepared(decision.prepared_id)
        return await instance.execute(request)

    task = asyncio.create_task(run(first))
    try:
        await asyncio.wait_for(host.started.wait(), 3)
        hold = first.store.list_capacity_reservations()[0]
        attempt = first.store.get_execution_attempt(hold.execution_id)
        assert hold.status.value == "claimed"
        assert attempt.state is ExecutionAttemptState.INVOKING
        assert attempt.capacity_reservation_ids == (hold.reservation_id,)
        with pytest.raises(ConfigurationError, match="exceeds known"):
            await run(second)
        assert host.calls == 1
        host.finish.set()
        assert (await task).ok
        assert first.store.get_capacity_reservation(hold.reservation_id).status.value == "released"
        assert (await run(second)).ok
    finally:
        host.finish.set()
        await asyncio.gather(task, return_exceptions=True)
        await first.close()
        await second.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("prepared", [False, True])
async def test_uncertain_managed_execution_keeps_capacity_beyond_expiry(tmp_path, prepared):
    host = Host(status=ExecutionStatus.TIMEOUT)
    host.finish.set()
    instance = router(tmp_path / "uncertain.db", host)
    try:
        request = ActionRequest(capability="fixture@1")
        if prepared:
            decision = await instance.prepare_route(request)
            await instance.execute_prepared(decision.prepared_id)
        else:
            await instance.execute(request)
        hold = instance.store.list_capacity_reservations()[0]
        attempt = instance.store.get_execution_attempt(hold.execution_id)
        assert attempt.state is ExecutionAttemptState.INDETERMINATE
        assert hold.status.value == "claimed"
        with pytest.raises(ConfigurationError, match="exceeds known"):
            instance.store.reserve_capacity(
                hold.model_copy(
                    update={
                        "reservation_id": "new",
                        "idempotency_key": "new",
                        "expires_at": NOW + timedelta(days=2),
                    }
                ),
                known_available=Decimal(1),
                now=NOW + timedelta(days=1),
            )
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_unknown_capacity_is_not_invented_and_cancellation_retains_known_hold(tmp_path):
    unknown = Host(remaining=None)
    unknown.finish.set()
    instance = router(tmp_path / "unknown.db", unknown)
    try:
        assert (await instance.execute(ActionRequest(capability="fixture@1"))).ok
        assert not instance.store.list_capacity_reservations()
    finally:
        await instance.close()
    known = Host()
    instance = router(tmp_path / "cancelled.db", known)
    task = asyncio.create_task(instance.execute(ActionRequest(capability="fixture@1")))
    try:
        await asyncio.wait_for(known.started.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        hold = instance.store.list_capacity_reservations()[0]
        assert hold.status.value == "claimed"
        assert (
            instance.store.get_execution_attempt(hold.execution_id).state
            is ExecutionAttemptState.INDETERMINATE
        )
    finally:
        await instance.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "usage, message",
    [
        ({"resources": {"subscription_units": 0}}, "positive usage estimate"),
        (
            {
                "subscription_usage": [
                    {
                        "resource_pool": "pool",
                        "provider": "fixture",
                        "unit": "other",
                        "consumed": 1,
                        "source": {
                            "status": "complete",
                            "source": "operator_report",
                            "trust": "self_asserted",
                        },
                    }
                ]
            },
            "No executor is feasible",
        ),
    ],
)
async def test_quantified_capacity_requires_a_matching_positive_estimate(tmp_path, usage, message):
    from aeep.models import RouteEstimate

    host = Host()
    instance = router(tmp_path / "invalid.db", host)
    instance.registry.get("managed").estimate = RouteEstimate.model_validate(usage)
    try:
        with pytest.raises((ConfigurationError, NoRouteError), match=message):
            await instance.execute(ActionRequest(capability="fixture@1"))
        assert host.calls == 0
        assert not instance.store.list_capacity_reservations()
    finally:
        await instance.close()


def test_reservation_store_conflicts_and_expired_claims(tmp_path):
    with ReceiptStore(tmp_path / "store.db") as store:
        hold = CapacityReservation(
            resource_id="pool",
            execution_id="attempt",
            maximum_quantity=1,
            unit="turn",
            expires_at=NOW + timedelta(seconds=1),
            idempotency_key="key",
        )
        for available in (Decimal("NaN"), Decimal(-1)):
            with pytest.raises(ConfigurationError, match="finite"):
                store.reserve_capacity(hold, known_available=available, now=NOW)
        store.reserve_capacity(hold, known_available=Decimal(1), now=NOW)
        with pytest.raises(ConfigurationError, match="different data"):
            store.reserve_capacity(
                hold.model_copy(update={"unit": "other"}), known_available=Decimal(1), now=NOW
            )
        for identity, version, at, message in (
            ("missing", 0, NOW, "does not exist"),
            (hold.reservation_id, 8, NOW, "compare-and-set"),
            (hold.reservation_id, 0, NOW + timedelta(seconds=2), "expired"),
        ):
            with pytest.raises(ConfigurationError, match=message):
                store.claim_capacity_reservation(
                    identity, claim_token="worker", expected_version=version, now=at
                )
        claimed = store.claim_capacity_reservation(
            hold.reservation_id, claim_token="worker", expected_version=0, now=NOW
        )
        with pytest.raises(ConfigurationError, match="another worker"):
            store.claim_capacity_reservation(
                hold.reservation_id, claim_token="other", expected_version=1, now=NOW
            )
        for identity, version, message in (
            ("missing", 0, "does not exist"),
            (hold.reservation_id, 9, "compare-and-set"),
        ):
            with pytest.raises(ConfigurationError, match=message):
                store.release_capacity_reservation(identity, expected_version=version, now=NOW)
        store.release_capacity_reservation(
            hold.reservation_id, expected_version=claimed.version, now=NOW
        )
        with pytest.raises(ConfigurationError, match="cannot claim"):
            store.claim_capacity_reservation(
                hold.reservation_id, claim_token="worker", expected_version=2, now=NOW
            )
        store._connection.execute("UPDATE capacity_reservations SET state='consumed'")
        store._connection.commit()
        with pytest.raises(ConfigurationError, match="cannot release"):
            store.release_capacity_reservation(hold.reservation_id, expected_version=2, now=NOW)


def test_attempt_capacity_binding_and_invocation_are_atomic(tmp_path):
    with ReceiptStore(tmp_path / "atomic.db") as store:
        attempt = store.create_execution_attempt(
            ExecutionAttempt(
                attempt_id="attempt",
                decision_id="decision",
                action_digest="a" * 64,
                executor_id="managed",
                executor_fingerprint="b" * 64,
                side_effect=SideEffect.READ,
                idempotent=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        attempt = store.claim_execution_attempt(
            attempt.attempt_id,
            owner_id="worker",
            claimed_at=NOW,
            lease_expires_at=NOW + timedelta(hours=1),
        )

        def advance(target, **kwargs):
            return store.transition_execution_attempt(
                attempt.attempt_id,
                expected_state=attempt.state,
                expected_version=attempt.version,
                target_state=target,
                updated_at=NOW,
                **kwargs,
            )

        with pytest.raises(ConfigurationError, match="does not belong"):
            advance(ExecutionAttemptState.RESERVED, capacity_reservation_ids=("missing",))
        hold = store.reserve_capacity(
            CapacityReservation(
                resource_id="pool",
                execution_id="attempt",
                maximum_quantity=1,
                unit="turn",
                expires_at=NOW + timedelta(seconds=1),
                idempotency_key="key",
            ),
            known_available=Decimal(1),
            now=NOW,
        )
        attempt = advance(
            ExecutionAttemptState.RESERVED, capacity_reservation_ids=(hold.reservation_id,)
        )
        with pytest.raises(ConfigurationError, match="immutable"):
            advance(
                ExecutionAttemptState.INVOKING,
                invocation_start_digest="sha256:" + "c" * 64,
                capacity_reservation_ids=(),
            )
        with pytest.raises(ConfigurationError, match="not available"):
            store.transition_execution_attempt(
                attempt.attempt_id,
                expected_state=attempt.state,
                expected_version=attempt.version,
                target_state=ExecutionAttemptState.INVOKING,
                invocation_start_digest="sha256:" + "c" * 64,
                updated_at=NOW + timedelta(seconds=2),
            )
        assert (
            store.get_execution_attempt(attempt.attempt_id).state is ExecutionAttemptState.RESERVED
        )
        assert store.get_capacity_reservation(hold.reservation_id).status.value == "reserved"
        attempt = advance(ExecutionAttemptState.FAILED)
        assert store.get_capacity_reservation(hold.reservation_id).status.value == "released"
