from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import pytest

from aeep.capacity import CapacityObservation, CapacityWindow, observation_quota
from aeep.executors.base import BaseExecutor, ExecutionContext
from aeep.hosts import HostModel, HostProbe, HostProbeStatus, ManagedHostExecutionContext
from aeep.models import (
    ActionRequest,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    Manifest,
    MetricWeights,
    PolicyConfig,
    QuotaState,
    RawExecution,
    ResourceVector,
    RouteEstimate,
    SubscriptionResource,
)
from aeep.router import Router
from aeep.scoring import score_candidate

RESOURCE = "fixture-capacity"
NOW = datetime(2030, 1, 1, tzinfo=UTC)


def observation(
    used: int | None, *, exhausted: bool = False, reset_hours: int = 1
) -> CapacityObservation:
    return CapacityObservation(
        resource_id=RESOURCE,
        source="fixture",
        observed_at=NOW,
        windows=(
            CapacityWindow(
                window_id="primary",
                used_percent=used,
                reset_at=NOW + timedelta(hours=reset_hours),
                duration_seconds=7200,
                exhausted=exhausted,
                confidence=1 if used is not None else 0,
            ),
        ),
    )


class CapacityHost:
    def __init__(self, snapshots: list[CapacityObservation]) -> None:
        self.snapshots = snapshots
        self.snapshot_calls = 0
        self.execution_calls = 0

    async def probe(self) -> HostProbe:
        return HostProbe(adapter_id="capacity-host", status=HostProbeStatus.READY)

    async def snapshot_capacity(self) -> CapacityObservation:
        value = self.snapshots[min(self.snapshot_calls, len(self.snapshots) - 1)]
        self.snapshot_calls += 1
        return value.model_copy(update={"observation_id": f"capacity-{self.snapshot_calls}"})

    async def list_models(self) -> list[HostModel]:
        return [HostModel(id="fixture-runtime-model", capabilities=("text",))]

    async def execute(self, context: ManagedHostExecutionContext) -> RawExecution:
        self.execution_calls += 1
        return RawExecution(status=ExecutionStatus.SUCCESS, output={"route": "managed"})

    async def interrupt(self, attempt_id: str) -> None:
        return None

    async def close(self) -> None:
        return None


class LocalExecutor(BaseExecutor):
    async def execute(self, context: ExecutionContext) -> RawExecution:
        return RawExecution(status=ExecutionStatus.SUCCESS, output={"route": "local"})


def specs() -> tuple[ExecutorSpec, ExecutorSpec]:
    local = ExecutorSpec(
        id="local",
        capability="fixture.choose@1",
        kind=ExecutorKind.COMMAND,
        description="Deterministic fixture",
        estimate=RouteEstimate(resources=ResourceVector(latency_ms=5000)),
        config={"argv": [sys.executable, "-V"]},
    )
    managed = ExecutorSpec(
        id="managed",
        capability="fixture.choose@1",
        kind=ExecutorKind.MANAGED_HOST,
        description="Subscription fixture",
        resource_pool=RESOURCE,
        estimate=RouteEstimate(
            resources=ResourceVector(latency_ms=10, subscription_units=1)
        ),
        config={
            "adapter_id": "capacity-host",
            "argv": [sys.executable, "fixture"],
            "instructions": "Return the selected route for {input.value}",
            "model_constraints": {"required_capabilities": ["text"]},
            "working_directory_policy": "inherit",
            "sandbox_policy": "read_only",
            "approval_ceiling": "read",
            "output_mode": "json",
            "timeout_seconds": 2,
            "max_message_bytes": 4096,
        },
    )
    return local, managed


def quota_policy() -> PolicyConfig:
    return PolicyConfig(
        name="quota",
        weights=MetricWeights(
            monetary=0,
            latency=0.2,
            compute=0,
            subscription=0.8,
            reliability=0,
            quality=0,
            risk=0,
        ),
        prefer_local_bonus=0,
    )


def router(host: CapacityHost) -> Router:
    local, managed = specs()
    return Router(
        Manifest(
            database=":memory:",
            resources=[
                SubscriptionResource(id=RESOURCE, provider="fixture", product="fixture")
            ],
            executors=[local, managed],
            policies={"quota": quota_policy()},
            default_policy="quota",
        ),
        managed_host_adapters={"capacity-host": host},
        executor_overrides={ExecutorKind.COMMAND: LocalExecutor()},
        clock=lambda: NOW,
    )


def test_multi_window_reduction_uses_hardest_bucket_and_preserves_unknown():
    raw = CapacityObservation(
        resource_id=RESOURCE,
        source="fixture",
        observed_at=NOW,
        windows=(
            CapacityWindow(window_id="primary", used_percent=20, confidence=1),
            CapacityWindow(window_id="secondary", used_percent=90, confidence=0.8),
        ),
    )
    quota = observation_quota(raw, unit="provider_unit", now=NOW)
    unknown = observation_quota(observation(None), unit="provider_unit", now=NOW)
    assert quota.state is QuotaState.CRITICAL
    assert quota.used_percent == 90
    assert quota.window_count == 2
    assert unknown.state is QuotaState.UNKNOWN and unknown.confidence == 0


def test_reset_distance_and_private_value_are_exposed_but_not_cash():
    _, managed = specs()
    policy = quota_policy()
    policy.subscription_rules = [
        {
            "resource_pool": RESOURCE,
            "unit": "provider_unit",
            "policy_value_usd_per_unit": "0.25",
        }
    ]
    near = observation_quota(observation(50, reset_hours=1), unit="provider_unit", now=NOW)
    far = observation_quota(observation(50, reset_hours=2), unit="provider_unit", now=NOW)
    action_context = ActionRequest(
        capability="fixture.choose@1", input={"value": 1}
    ).context
    near_score = score_candidate(managed, managed.estimate, policy, action_context, near).score
    far_score = score_candidate(managed, managed.estimate, policy, action_context, far).score
    assert near_score is not None and far_score is not None
    assert near_score.subscription_reset_factor < far_score.subscription_reset_factor
    assert far_score.subscription > near_score.subscription
    assert near_score.subscription_policy_value_usd == 0.25
    assert managed.estimate.cash.amount_usd is None


@pytest.mark.asyncio
async def test_abundant_quota_selects_managed_and_tight_quota_selects_local():
    abundant_host = CapacityHost([observation(10)])
    tight_host = CapacityHost([observation(95)])
    abundant_router = router(abundant_host)
    tight_router = router(tight_host)
    request = ActionRequest(capability="fixture.choose@1", input={"value": 1})
    try:
        assert (
            await abundant_router.route_with_discovery(request)
        ).selected_executor_id == "managed"
        assert (await tight_router.route_with_discovery(request)).selected_executor_id == "local"
    finally:
        await abundant_router.close()
        await tight_router.close()


@pytest.mark.asyncio
async def test_exhaustion_rejects_and_preinvoke_change_reroutes_without_model_turn():
    exhausted_host = CapacityHost([observation(100, exhausted=True)])
    exhausted_router = router(exhausted_host)
    changing_host = CapacityHost([observation(10), observation(100, exhausted=True)])
    changing_router = router(changing_host)
    request = ActionRequest(capability="fixture.choose@1", input={"value": 1})
    try:
        rejected = await exhausted_router.route_with_discovery(request)
        managed = next(item for item in rejected.candidates if item.executor_id == "managed")
        assert not managed.feasible and "exhausted" in managed.rejection_reasons[0]
        outcome = await changing_router.execute(request)
        assert outcome.ok and outcome.output == {"route": "local"}
        assert changing_host.execution_calls == 0
        assert changing_host.snapshot_calls == 2
    finally:
        await exhausted_router.close()
        await changing_router.close()
