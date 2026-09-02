from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from aeep.capacity import CapacityObservation, CapacityWindow
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
from aeep.proofs import HostNativeRoutingReport
from aeep.router import Router

REPORT = Path(__file__).parents[1] / "reports" / "v07" / "host-native-routing.json"


class ExactLocalExecutor(BaseExecutor):
    async def execute(self, context: ExecutionContext) -> RawExecution:
        return RawExecution(
            status=ExecutionStatus.SUCCESS,
            output={"characters": len(str(context.request.input["text"]))},
        )


class BoundedManagedHost:
    def __init__(self) -> None:
        self.contexts: list[ManagedHostExecutionContext] = []

    async def probe(self) -> HostProbe:
        return HostProbe(adapter_id="bounded", status=HostProbeStatus.READY)

    async def snapshot_capacity(self) -> CapacityObservation:
        return CapacityObservation(
            resource_id="fixture-plan",
            source="fixture",
            windows=(CapacityWindow(window_id="primary", used_percent=10),),
        )

    async def list_models(self) -> list[HostModel]:
        return [HostModel(id="runtime-discovered-model")]

    async def execute(self, context: ManagedHostExecutionContext) -> RawExecution:
        self.contexts.append(context)
        return RawExecution(
            status=ExecutionStatus.SUCCESS,
            output={"characters": len(str(context.request.input["text"]))},
            metadata={
                "model_turn_count": 1,
                "tool_selection_rounds": 1,
                "implementation_schema_bytes": 0,
                "result_bytes": 16,
            },
        )

    async def interrupt(self, attempt_id: str) -> None:
        return None

    async def close(self) -> None:
        return None


def local_spec() -> ExecutorSpec:
    return ExecutorSpec(
        id="exact-local",
        capability="text.length@1",
        kind=ExecutorKind.PYTHON,
        description="Exact local fixture",
        side_effect=SideEffect.NONE,
        config={"callable": "fixture:exact"},
    )


def managed_spec() -> ExecutorSpec:
    return ExecutorSpec(
        id="managed-judgment",
        capability="text.judgment@1",
        kind=ExecutorKind.MANAGED_HOST,
        description="Bounded managed fixture",
        side_effect=SideEffect.NONE,
        resource_pool="fixture-plan",
        config={
            "adapter_id": "bounded",
            "argv": [sys.executable, "fixture-app-server"],
            "instructions": "Judge only the supplied value: {input.text}",
            "approval_ceiling": "read",
            "output_mode": "json",
            "store_prompt": False,
            "store_output": False,
        },
    )


@pytest.mark.asyncio
async def test_exact_local_bypass_makes_no_model_call():
    router = Router(
        Manifest(database=":memory:", executors=[local_spec()]),
        executor_overrides={ExecutorKind.PYTHON: ExactLocalExecutor()},
    )
    try:
        result = await router.execute(
            ActionRequest(capability="text.length@1", input={"text": "abc"})
        )
        assert result.output == {"characters": 3}
        assert "model_turn_count" not in result.receipts[0].metadata
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_native_tool_search_passes_only_bounded_action():
    host = BoundedManagedHost()
    router = Router(
        Manifest(
            database=":memory:",
            resources=[
                SubscriptionResource(
                    id="fixture-plan", provider="fixture", product="subscription"
                )
            ],
            executors=[managed_spec()],
        ),
        managed_host_adapters={"bounded": host},
    )
    try:
        result = await router.execute(
            ActionRequest(capability="text.judgment@1", input={"text": "abc"})
        )
        assert result.ok and len(host.contexts) == 1
        context = host.contexts[0]
        assert context.request.capability == "text.judgment@1"
        assert "managed-judgment" not in context.instruction
        assert "fixture-app-server" not in context.instruction
        assert result.receipts[0].metadata["implementation_schema_bytes"] == 0
        assert result.receipts[0].metadata["model_turn_count"] == 1
    finally:
        await router.close()


def test_meta_router_negative_control_is_rejected_as_default():
    report = HostNativeRoutingReport.model_validate(json.loads(REPORT.read_text()))
    negative = next(
        item for item in report.campaigns if item.name == "negative-control-meta-router"
    )
    assert not negative.default_path
    assert negative.routing_model_rounds == 1
    assert not report.universal_token_savings_claimed
