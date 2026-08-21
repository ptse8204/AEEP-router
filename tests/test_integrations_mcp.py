from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from aeep.config import write_default_manifest
from aeep.integrations import export_tools
from aeep.mcp.client import LEGACY_VERSION, MODERN_VERSION, MCPStdioClient
from aeep.mcp.server import AEEPToolService, MCPProtocolApp
from aeep.models import ExternalOutcomeReport
from aeep.router import Router


@pytest.mark.parametrize(
    "format,key",
    [
        ("mcp", "inputSchema"),
        ("openai-responses", "parameters"),
        ("openai-chat", "function"),
        ("anthropic", "input_schema"),
        ("deepseek", "function"),
        ("zai", "function"),
    ],
)
def test_tool_schema_exports(format, key):
    tools = export_tools(format)
    assert len(tools) == 9
    assert key in tools[0]


def test_record_outcome_schema_matches_runtime_report() -> None:
    schema = next(
        item["inputSchema"]
        for item in export_tools("mcp")
        if item["name"] == "aeep_record_outcome"
    )
    report = ExternalOutcomeReport.model_validate(
        {
            "decision_id": "decision-1",
            "executor_id": "executor-1",
            "status": "success",
            "actual_resources": {"cached_input_tokens": 7},
            "validation_results": [{"kind": "schema", "valid": True}],
            "quota_observation": {
                "state": "tight",
                "unit": "request",
                "allowance_units": "100",
                "remaining_units": "10",
            },
            "started_at": "2026-08-14T12:00:00Z",
            "ended_at": "2026-08-14T12:00:01Z",
        }
    ).model_dump(mode="json")
    validator = Draft202012Validator(schema)

    assert set(schema["properties"]) == set(ExternalOutcomeReport.model_fields)
    assert not list(validator.iter_errors(report))
    assert list(validator.iter_errors({**report, "validation_results": [{}]}))
    assert list(validator.iter_errors({**report, "status": "host_selected"}))


def test_protocol_modern_discover_and_list(tmp_path):
    manifest = write_default_manifest(tmp_path / "aeep.yaml")
    router = Router.from_manifest(manifest)
    app = MCPProtocolApp(AEEPToolService(router))

    async def exercise():
        meta = {
            "io.modelcontextprotocol/protocolVersion": MODERN_VERSION,
            "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "1"},
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        discover = await app.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "server/discover",
                "params": {"_meta": meta},
            }
        )
        assert MODERN_VERSION in discover["result"]["supportedVersions"]
        assert discover["result"]["resultType"] == "complete"
        assert discover["result"]["cacheScope"] == "private"
        assert "io.modelcontextprotocol/serverInfo" in discover["result"]["_meta"]
        listed = await app.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {"_meta": meta},
            }
        )
        assert len(listed["result"]["tools"]) == 9
        assert listed["result"]["resultType"] == "complete"
        assert listed["result"]["ttlMs"] > 0
        assert listed["result"]["cacheScope"] == "private"
        ping = await app.handle(
            {"jsonrpc": "2.0", "id": 3, "method": "ping", "params": {"_meta": meta}}
        )
        assert ping["error"]["code"] == -32601
        await router.close()

    asyncio.run(exercise())


def test_protocol_legacy_initialize(tmp_path):
    manifest = write_default_manifest(tmp_path / "aeep.yaml")
    router = Router.from_manifest(manifest)
    app = MCPProtocolApp(AEEPToolService(router))

    async def exercise():
        response = await app.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": LEGACY_VERSION},
            }
        )
        assert response["result"]["protocolVersion"] == LEGACY_VERSION
        assert (
            await app.handle(
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
            )
            is None
        )
        await router.close()

    asyncio.run(exercise())


@pytest.mark.asyncio
async def test_real_stdio_mcp_round_trip(tmp_path):
    manifest = write_default_manifest(tmp_path / "aeep.yaml")
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    client = MCPStdioClient(
        command=sys.executable,
        args=["-m", "aeep", "serve", "--transport", "stdio", "-m", str(manifest)],
        env=env,
    )
    try:
        listed = await client.list_tools()
        assert listed.protocol_version == MODERN_VERSION
        response = await client.call_tool(
            "aeep_execute_action",
            {"capability": "text.stats", "input": {"text": "one two"}},
        )
        assert response.result["isError"] is False
        assert response.result["structuredContent"]["output"]["words"] == 2
    finally:
        await client.close()


def test_execute_tool_schema_does_not_expose_self_approval_controls():
    tool = next(item for item in export_tools("mcp") if item["name"] == "aeep_execute_action")
    properties = tool["inputSchema"]["properties"]
    assert "approved_side_effect" not in properties
    assert "allow_unsafe_executor" not in properties


@pytest.mark.asyncio
async def test_model_arguments_cannot_self_approve_write(text_schema, stats_schema):
    from conftest import manifest_with, python_spec

    from aeep.models import ActionConstraints, PolicyConfig, SideEffect

    writer = python_spec(
        "writer",
        "aeep.examples.tools:text_stats",
        input_schema=text_schema,
        output_schema=stats_schema,
        side_effect=SideEffect.WRITE,
    )
    policy = PolicyConfig(
        name="write",
        constraints=ActionConstraints(max_side_effect=SideEffect.WRITE),
    )
    router = Router(manifest_with(writer, policies={"write": policy}))
    arguments = {
        "capability": "text.stats",
        "input": {"text": "x"},
        "policy": "write",
        "constraints": {"max_side_effect": "write"},
        # Deliberately malicious/obsolete model-supplied fields. The service
        # must ignore them rather than treating model output as approval.
        "approved_side_effect": "write",
        "allow_unsafe_executor": True,
    }
    result = await AEEPToolService(router).call("aeep_execute_action", arguments)
    assert result["isError"] is True
    assert result["structuredContent"]["error_type"] == "ApprovalRequired"

    approved = await AEEPToolService(
        router,
        approved_side_effect=SideEffect.WRITE,
    ).call("aeep_execute_action", arguments)
    assert approved["isError"] is False
    await router.close()


@pytest.mark.asyncio
async def test_economic_mcp_surface_is_read_only_sanitized_and_listed():
    from types import SimpleNamespace
    from typing import Any, cast

    class Record:
        def __init__(self, payload):
            self.payload = payload

        def model_dump(self, *, mode):
            assert mode == "json"
            return self.payload

    class Store:
        def get_prepared_decision(self, prepared_id):
            return Record(
                {
                    "prepared_id": prepared_id,
                    "state": "PREPARED",
                    "disclosed_quote_features": {
                        "input_bytes": 12,
                        "access_token": "must-not-leak",
                    },
                    "input": {"resume": "must-not-leak"},
                }
            )

        def get_bounded_quote(self, quote_id):
            return Record(
                {
                    "quote_id": quote_id,
                    "maximum_amount": {"amount": "0.0050", "currency": "USD"},
                    "evidence_level": "SIGNED_QUOTE",
                    "authorization": "must-not-leak",
                }
            )

        def get_settlement_receipt(self, settlement_id):
            return Record(
                {
                    "settlement_id": settlement_id,
                    "captured_amount": {"amount": "0.0038", "currency": "USD"},
                    "released_amount": {"amount": "0.0012", "currency": "USD"},
                    "external_reference": "must-not-leak",
                }
            )

    router = cast(Any, SimpleNamespace(store=Store()))
    service = AEEPToolService(router)
    listed = {tool["name"]: tool for tool in service.list_tools()}
    safe_names = {
        "aeep_show_prepared_decision",
        "aeep_show_quote",
        "aeep_show_settlement",
    }
    assert safe_names <= listed.keys()
    assert all(listed[name]["annotations"] == {"readOnlyHint": True, "idempotentHint": True} for name in safe_names)

    prepared = await service.call(
        "aeep_show_prepared_decision", {"prepared_id": "prepared-1"}
    )
    quote = await service.call("aeep_show_quote", {"quote_id": "quote-1"})
    settlement = await service.call(
        "aeep_show_settlement", {"settlement_id": "settlement-1"}
    )
    assert prepared["structuredContent"]["disclosed_quote_features"] == {"input_bytes": 12}
    assert quote["structuredContent"]["maximum_amount"]["amount"] == "0.0050"
    assert settlement["structuredContent"]["released_amount"]["amount"] == "0.0012"
    assert "must-not-leak" not in str((prepared, quote, settlement))

    hidden = await service.call("aeep_prepare_route", {})
    assert hidden["isError"] is True
    assert "aeep_prepare_route" not in listed
