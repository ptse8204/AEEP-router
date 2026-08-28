from __future__ import annotations

import io
import json

import pytest

from aeep.config import write_default_manifest
from aeep.host_bridge import HostBridge, run_host_bridge
from aeep.models import (
    ActionRequest,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    ExternalOutcomeReport,
    Locality,
    Manifest,
    QuotaSource,
    QuotaState,
    ResourceAccounting,
    ResourceVector,
    RouteEstimate,
    SideEffect,
    SubscriptionQuota,
    SubscriptionResource,
    ToolFootprint,
)
from aeep.router import Router


def _host_router() -> Router:
    resource = SubscriptionResource(
        id="dsh.local",
        provider="deepseek",
        product="harness",
        quota=SubscriptionQuota(
            state=QuotaState.ABUNDANT,
            confidence=1,
            source=QuotaSource.HOST,
        ),
    )
    executor = ExecutorSpec(
        id="dsh.web",
        capability="web.page.read@1",
        description="DSH web host route",
        kind=ExecutorKind.HOST,
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
            "additionalProperties": False,
        },
        estimate=RouteEstimate(
            resources=ResourceVector(latency_ms=10, subscription_units=1)
        ),
        side_effect=SideEffect.READ,
        locality=Locality.LOCAL,
        idempotent=True,
        safe_to_auto_execute=True,
        resource_pool=resource.id,
        config={"instructions": "read {input.url}"},
    )
    return Router(Manifest(database=":memory:", resources=[resource], executors=[executor]))


@pytest.mark.asyncio
async def test_bridge_routes_and_records_trusted_pressure() -> None:
    router = _host_router()
    bridge = HostBridge(router)
    routed, close = await bridge.handle(
        {
            "id": "1",
            "op": "route",
            "capability": "web.page.read@1",
            "input": {"url": "https://example.com"},
        }
    )
    assert close is False
    decision = routed["result"]
    assert decision["selected"] == "dsh.web"

    recorded, _ = await bridge.handle(
        {
            "id": "2",
            "op": "record",
            "decision_id": decision["decision_id"],
            "executor_id": "dsh.web",
            "status": "success",
            "resources": {"latency_ms": 20},
            "tool_footprint": {
                "schema_bytes": 100,
                "schema_approx_tokens": 25,
                "raw_result_bytes": 80,
                "raw_result_approx_tokens": 20,
                "filtered_result_bytes": 40,
                "filtered_result_approx_tokens": 10,
                "exposed_to_model": True,
            },
            "preceding_tool_receipt_ids": ["rcpt_tool"],
        }
    )
    receipt = recorded["result"]
    assert receipt["accounting"]["tool_footprint"]["filtered_result_bytes"] == 40
    assert receipt["metadata"]["preceding_tool_receipt_ids"] == ["rcpt_tool"]
    assert receipt["metadata"]["route_attribution_ambiguous"] is False
    await router.close()


@pytest.mark.asyncio
async def test_bridge_route_and_receipt_match_direct_router_semantics() -> None:
    direct_router = _host_router()
    bridge_router = _host_router()
    bridge = HostBridge(bridge_router, integration_id="test-host-v1")
    action = ActionRequest(
        capability="web.page.read@1", input={"url": "https://example.com"}
    )
    direct_decision = await direct_router.route_with_discovery(action)
    bridged, _ = await bridge.handle(
        {
            "id": "route",
            "op": "route",
            "capability": action.capability,
            "input": action.input,
        }
    )
    assert bridged["result"]["selected"] == direct_decision.selected_executor_id
    assert bridged["result"]["selected"] is not None

    footprint = ToolFootprint(
        schema_bytes=40,
        schema_approx_tokens=10,
        raw_result_bytes=20,
        raw_result_approx_tokens=5,
        filtered_result_bytes=16,
        filtered_result_approx_tokens=4,
        exposed_to_model=True,
    )
    direct_receipt = direct_router.record_external_outcome(
        ExternalOutcomeReport(
            decision_id=direct_decision.decision_id,
            executor_id="dsh.web",
            status=ExecutionStatus.SUCCESS,
            actual_resources=ResourceVector(latency_ms=20),
        ),
        _trusted_accounting=ResourceAccounting(tool_footprint=footprint),
        _trusted_metadata={"host_integration": "test-host-v1"},
    )
    bridged_receipt, _ = await bridge.handle(
        {
            "id": "record",
            "op": "record",
            "decision_id": bridged["result"]["decision_id"],
            "executor_id": "dsh.web",
            "status": "success",
            "resources": {"latency_ms": 20},
            "tool_footprint": footprint.model_dump(mode="json"),
        }
    )
    observed = bridged_receipt["result"]
    assert observed["status"] == direct_receipt.status.value
    assert observed["actual_resources"] == direct_receipt.actual_resources.model_dump(
        mode="json"
    )
    assert observed["accounting"] == direct_receipt.accounting.model_dump(mode="json")
    assert observed["metadata"] == direct_receipt.metadata
    await direct_router.close()
    await bridge_router.close()


@pytest.mark.asyncio
async def test_bridge_rejects_arbitrary_metadata_and_duplicate_correlations() -> None:
    router = _host_router()
    bridge = HostBridge(router)
    with pytest.raises(ValueError, match="unknown bridge fields"):
        await bridge.handle({"id": "1", "op": "ping", "metadata": {"trusted": True}})
    with pytest.raises(ValueError, match="unique"):
        await bridge.handle(
            {
                "id": "2",
                "op": "record",
                "decision_id": "decision",
                "executor_id": "dsh.web",
                "status": "success",
                "preceding_tool_receipt_ids": ["rcpt_x", "rcpt_x"],
            }
        )
    await router.close()


def test_jsonl_bridge_keeps_one_router_and_bounds_input(tmp_path) -> None:
    manifest = write_default_manifest(tmp_path / "aeep.yaml")
    source = io.BytesIO(
        b'{"id":"1","op":"record","decision_id":"missing","executor_id":"missing","status":"success","resources":{}}\n'
        b'{"id":"2","op":"ping"}\n{"id":"3","op":"close"}\n'
    )
    destination = io.BytesIO()
    assert run_host_bridge(
        manifest,
        source,
        destination,
        max_input_bytes=1024,
        max_output_bytes=4096,
    ) == 0
    responses = [json.loads(line) for line in destination.getvalue().splitlines()]
    assert [item["id"] for item in responses] == ["1", "2", "3"]
    assert responses[0]["ok"] is False
    assert all(item["ok"] for item in responses[1:])

    oversized = io.BytesIO(b"{" + b"x" * 1024 + b"}\n")
    bounded = io.BytesIO()
    assert run_host_bridge(
        manifest,
        oversized,
        bounded,
        max_input_bytes=1024,
        max_output_bytes=4096,
    ) == 2
    assert json.loads(bounded.getvalue())["ok"] is False
