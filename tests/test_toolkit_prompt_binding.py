import hashlib

import pytest
from test_codex_subscription_adapter import adapter, context

from aeep.executors.base import ExecutionContext
from aeep.executors.managed_host import ManagedHostExecutor
from aeep.hosts import ManagedHostRegistry
from aeep.models import ExecutorSpec, RouteEstimate
from aeep.router import Router


@pytest.mark.asyncio
async def test_actual_managed_task_instruction_is_hashed_without_content_retention():
    host = adapter()
    current = context()
    registry = ManagedHostRegistry()
    registry.register(current.config.adapter_id, host)
    executor = ManagedHostExecutor(registry)
    spec = ExecutorSpec(
        id="fixture",
        capability=current.request.capability,
        kind="host_managed",
        description="Synthetic App Server prompt binding fixture",
        resource_pool="fixture-subscription",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        config=current.config.model_dump(mode="json"),
    )
    try:
        raw = await executor.execute(
            ExecutionContext(
                request=current.request, spec=spec, estimate=RouteEstimate(), attempt=1
            )
        )
        expected = hashlib.sha256(b"Count characters in abc").hexdigest()
        assert raw.metadata["task_instruction_sha256"] == expected
        retained = Router._safe_receipt_metadata(raw.metadata)
        assert retained["task_instruction_sha256"] == expected
        assert "abc" not in str(retained) and "Count characters" not in str(retained)
    finally:
        await executor.close()


@pytest.mark.parametrize(
    "value,expected",
    [(True, True), (False, False), (None, None), ("private payload", None), (1, None)],
)
def test_discovery_retention_is_limited_to_boolean_observations(value, expected):
    retained = Router._safe_receipt_metadata(
        {
            "capability_discovery": {
                "exposed": value,
                "invoked": False,
                "retrieved": None,
                "private": "secret",
            },
            "task_input": "private",
        }
    )
    assert retained == {
        "capability_discovery": {"exposed": expected, "retrieved": None, "invoked": False}
    }
