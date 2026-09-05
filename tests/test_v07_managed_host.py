from __future__ import annotations

import sys

import pytest

from aeep.capacity import CapacityObservation, CapacityWindow
from aeep.errors import ConfigurationError
from aeep.hosts import (
    HostModel,
    HostProbe,
    HostProbeStatus,
    ManagedHostExecutionContext,
    ManagedHostRegistry,
)
from aeep.models import (
    ActionRequest,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    Manifest,
    RawExecution,
    ResourceVector,
    SideEffect,
    SubscriptionResource,
)
from aeep.provider_package import PublishedExecutor
from aeep.router import Router


class FakeManagedHost:
    def __init__(self) -> None:
        self.contexts: list[ManagedHostExecutionContext] = []
        self.closed = False

    async def probe(self) -> HostProbe:
        return HostProbe(
            adapter_id="fake",
            status=HostProbeStatus.READY,
            protocol_version="fake-v1",
            supported_features=("execute", "models", "capacity"),
        )

    async def snapshot_capacity(self) -> CapacityObservation:
        return CapacityObservation(
            resource_id="managed-subscription",
            source="fake",
            windows=(CapacityWindow(window_id="primary", used_percent="10"),),
        )

    async def list_models(self) -> list[HostModel]:
        return [HostModel(id="runtime-model", capabilities=("reasoning",))]

    async def execute(self, context: ManagedHostExecutionContext) -> RawExecution:
        self.contexts.append(context)
        text = str(context.request.input["text"])
        return RawExecution(
            status=ExecutionStatus.SUCCESS,
            output={"characters": len(text)},
            resources=ResourceVector(input_tokens=3, output_tokens=1, subscription_units=1),
            metadata={"actual_model": "runtime-model"},
        )

    async def interrupt(self, attempt_id: str) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


def managed_spec() -> ExecutorSpec:
    return ExecutorSpec(
        id="managed",
        capability="text.length@1",
        kind=ExecutorKind.MANAGED_HOST,
        description="Managed host fixture",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"characters": {"type": "integer"}},
            "required": ["characters"],
            "additionalProperties": False,
        },
        side_effect=SideEffect.NONE,
        resource_pool="managed-subscription",
        config={
            "adapter_id": "fake",
            "argv": [sys.executable, "fake-app-server"],
            "instructions": "Count characters in {input.text}",
            "model_constraints": {"required_capabilities": ["reasoning"]},
            "reasoning_efforts": ["low", "medium"],
            "working_directory_policy": "inherit",
            "sandbox_policy": "host_default",
            "approval_ceiling": "read",
            "output_mode": "json",
            "timeout_seconds": 5,
            "max_message_bytes": 4096,
            "store_prompt": False,
            "store_output": False,
            "redaction_policy": "strict",
        },
    )


@pytest.mark.asyncio
async def test_fake_managed_host_executes_through_router():
    adapter = FakeManagedHost()
    manifest = Manifest(
        database=":memory:",
        resources=[
            SubscriptionResource(
                id="managed-subscription", provider="fixture", product="managed"
            )
        ],
        executors=[managed_spec()],
    )
    router = Router(manifest, managed_host_adapters={"fake": adapter})
    outcome = await router.execute(
        ActionRequest(capability="text.length@1", input={"text": "abc"})
    )
    assert outcome.ok and outcome.output == {"characters": 3}
    assert len(adapter.contexts) == 1
    assert adapter.contexts[0].instruction == "Count characters in abc"
    assert outcome.receipts[0].metadata["adapter_id"] == "fake"
    await router.close()
    assert adapter.closed


@pytest.mark.asyncio
async def test_legacy_host_remains_delegated():
    spec = ExecutorSpec(
        id="legacy-host",
        capability="text.length@1",
        kind=ExecutorKind.HOST,
        description="Legacy host",
        resource_pool="managed-subscription",
        config={"instructions": "Count {input.text}"},
    )
    manifest = Manifest(
        database=":memory:",
        resources=[
            SubscriptionResource(
                id="managed-subscription", provider="fixture", product="managed"
            )
        ],
        executors=[spec],
    )
    router = Router(manifest)
    outcome = await router.execute(
        ActionRequest(capability="text.length@1", input={"text": "abc"})
    )
    assert outcome.receipts[0].status is ExecutionStatus.HOST_SELECTED
    await router.close()


def test_managed_host_registry_is_deterministic_and_rejects_collisions():
    registry = ManagedHostRegistry()
    registry.register("z", FakeManagedHost())
    registry.register("a", FakeManagedHost())
    assert registry.ids() == ("a", "z")
    with pytest.raises(ConfigurationError, match="already registered"):
        registry.register("a", FakeManagedHost())


def test_provider_package_cannot_grant_managed_host_authority():
    with pytest.raises(ValueError, match="cannot declare managed-host"):
        PublishedExecutor(
            kind=ExecutorKind.MANAGED_HOST,
            description="not locally authorized",
            config={},
        )


def test_managed_host_requires_complete_local_configuration():
    config = managed_spec().config
    with pytest.raises(ValueError, match="absolute path"):
        ExecutorSpec(
            id="bad",
            capability="text.length@1",
            kind=ExecutorKind.MANAGED_HOST,
            description="bad",
            resource_pool="managed-subscription",
            config={**config, "argv": ["codex", "app-server"]},
        )
