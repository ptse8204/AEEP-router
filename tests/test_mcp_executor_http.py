from __future__ import annotations

import json
import os
import sys
import textwrap
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from conftest import manifest_with
from fastapi.testclient import TestClient

from aeep.config import write_default_manifest
from aeep.errors import ProtocolError
from aeep.executors.mcp import _extract_result, _usage_from_meta
from aeep.mcp.client import (
    LEGACY_VERSION,
    MODERN_VERSION,
    MCPHTTPClient,
    MCPStdioClient,
    _validate_complete_result,
    _validate_response_envelope,
)
from aeep.mcp.headers import encode_header_value, tool_header_bindings
from aeep.mcp.server import create_http_app
from aeep.models import (
    ActionRequest,
    ExecutorKind,
    ExecutorSpec,
    Locality,
    ResourceVector,
    RouteEstimate,
    SideEffect,
)
from aeep.router import Router

INPUT = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}
OUTPUT = {
    "type": "object",
    "properties": {
        "characters": {"type": "integer"},
        "words": {"type": "integer"},
        "lines": {"type": "integer"},
    },
    "required": ["characters", "words", "lines"],
    "additionalProperties": False,
}


def test_mcp_result_and_usage_helpers():
    assert _extract_result({"structuredContent": {"x": 1}}, parse_json_text=True) == {"x": 1}
    assert _extract_result(
        {"content": [{"type": "text", "text": '{"x":2}'}]}, parse_json_text=True
    ) == {"x": 2}
    assert (
        _extract_result({"content": [{"type": "text", "text": "plain"}]}, parse_json_text=False)
        == "plain"
    )
    assert _extract_result({"content": [{"type": "image"}]}, parse_json_text=True) == [
        {"type": "image"}
    ]
    usage = _usage_from_meta(
        {"_meta": {"org.aeep/usage": {"monetary_usd": 0.3, "cpu_ms": 4, "unknown": 9}}},
        0.1,
    )
    assert usage.monetary_usd == 0.3
    assert usage.cpu_ms == 4
    assert _usage_from_meta({"_meta": {"org.aeep/usage": "bad"}}, 0.2).monetary_usd == 0.2
    assert (
        _usage_from_meta({"_meta": {"org.aeep/usage": {"cpu_ms": "bad"}}}, 0.4).monetary_usd == 0.4
    )


@pytest.mark.asyncio
async def test_mcp_executor_real_stdio_example():
    repo = Path(__file__).parents[1]
    script = repo / "examples" / "mcp" / "text_stats_server.py"
    spec = ExecutorSpec(
        id="mcp",
        capability="text.stats",
        kind=ExecutorKind.MCP,
        description="mcp",
        input_schema=INPUT,
        output_schema=OUTPUT,
        estimate=RouteEstimate(resources=ResourceVector(monetary_usd=0.01, latency_ms=100)),
        side_effect=SideEffect.NONE,
        locality=Locality.LOCAL,
        config={
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(script)],
            "tool": "text_stats",
            "arguments": {"text": "{input.text}"},
        },
    )
    router = Router(manifest_with(spec))
    try:
        first = await router.execute(ActionRequest(capability="text.stats", input={"text": "a b"}))
        second = await router.execute(
            ActionRequest(capability="text.stats", input={"text": "c d e"})
        )
        assert first.ok and second.ok
        assert first.output["words"] == 2
        assert second.output["words"] == 3
        assert first.receipts[0].actual_resources.monetary_usd == 0
        assert first.receipts[0].accounting.cash.status.value == "partial"
        assert first.receipts[0].metadata["transport"] == "stdio"
        assert first.receipts[0].metadata["tool_schema_tokens_estimate"] > 0
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_mcp_executor_missing_tool_is_failed():
    repo = Path(__file__).parents[1]
    script = repo / "examples" / "mcp" / "text_stats_server.py"
    spec = ExecutorSpec(
        id="mcp",
        capability="x",
        kind=ExecutorKind.MCP,
        description="mcp",
        input_schema={"type": "object"},
        estimate=RouteEstimate(),
        side_effect=SideEffect.NONE,
        config={
            "command": sys.executable,
            "args": [str(script)],
            "tool": "does_not_exist",
        },
    )
    router = Router(manifest_with(spec))
    try:
        outcome = await router.execute(ActionRequest(capability="x", input={}))
        assert not outcome.ok
        assert "does not expose" in (outcome.receipts[0].error_message or "")
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_http_schema_mismatch_error_never_retries_tool_call(monkeypatch):
    client = MCPHTTPClient(url="https://example.test/mcp", protocol_mode="modern")
    client.protocol_version = MODERN_VERSION
    calls = 0

    async def fail_once(message, **_kwargs):
        nonlocal calls
        calls += 1
        return (
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {"code": -32020, "message": "schema mismatch"},
            },
            1,
            1,
            {},
            200,
        )

    monkeypatch.setattr(client, "_post", fail_once)
    with pytest.raises(ProtocolError):
        await client.call_tool("dangerous", {"value": 1})
    assert calls == 1
    await client.close()


def test_mcp_response_envelopes_and_modern_result_type_fail_closed():
    with pytest.raises(ProtocolError, match="jsonrpc"):
        _validate_response_envelope({"id": 1, "result": {}}, 1)
    with pytest.raises(ProtocolError, match="id"):
        _validate_response_envelope({"jsonrpc": "2.0", "id": 2, "result": {}}, 1)
    with pytest.raises(ProtocolError, match="exactly one"):
        _validate_response_envelope({"jsonrpc": "2.0", "id": 1, "result": {}, "error": {}}, 1)
    with pytest.raises(ProtocolError, match="required resultType"):
        _validate_complete_result({}, "tools/list", MODERN_VERSION)
    _validate_complete_result({}, "tools/list", LEGACY_VERSION)


@pytest.mark.asyncio
async def test_http_client_rejects_wrong_response_id(monkeypatch):
    client = MCPHTTPClient(url="https://example.test/mcp", protocol_mode="modern")
    client.protocol_version = MODERN_VERSION

    async def wrong_id(message, **_kwargs):
        return (
            {
                "jsonrpc": "2.0",
                "id": message["id"] + 1,
                "result": {"resultType": "complete", "tools": []},
            },
            1,
            1,
            {},
            200,
        )

    monkeypatch.setattr(client, "_post", wrong_id)
    with pytest.raises(ProtocolError, match="id does not match"):
        await client.list_tools()
    await client.close()


class _MCPHandler(BaseHTTPRequestHandler):
    sse = False
    include_header_tool = False
    invalid_header_tool = False
    oversized = False
    wrong_content_type = False
    last_headers: dict[str, str] = {}

    def do_POST(self):
        length = int(self.headers.get("content-length", "0"))
        message = json.loads(self.rfile.read(length) or b"{}")
        method = message.get("method")
        request_id = message.get("id")
        type(self).last_headers = {key.lower(): value for key, value in self.headers.items()}
        if method == "server/discover":
            result = {"resultType": "complete", "supportedVersions": [MODERN_VERSION]}
        elif method == "tools/list":
            schema = INPUT
            if type(self).include_header_tool:
                schema = {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "region": {
                            "type": "string",
                            "x-mcp-header": "Region",
                        },
                    },
                    "required": ["text", "region"],
                    "additionalProperties": False,
                }
            if type(self).invalid_header_tool:
                schema = {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "x-mcp-header": "Invalid",
                            },
                        }
                    },
                }
            result = {
                "resultType": "complete",
                "tools": [{"name": "text_stats", "inputSchema": schema}],
                "ttlMs": 1000,
                "cacheScope": "private",
            }
        elif method == "tools/call":
            text = message["params"]["arguments"]["text"]
            output = {"characters": len(text), "words": len(text.split()), "lines": 1}
            result = {
                "resultType": "complete",
                "structuredContent": output,
                "content": [],
                "isError": False,
            }
        else:
            result = {"resultType": "complete"}
        payload = {"jsonrpc": "2.0", "id": request_id, "result": result}
        if type(self).oversized:
            payload["result"]["padding"] = "x" * 4096
        if self.sse:
            body = f"event: message\ndata: {json.dumps(payload)}\n\n".encode()
            content_type = "text/event-stream"
        else:
            body = json.dumps(payload).encode()
            content_type = "text/plain" if type(self).wrong_content_type else "application/json"
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        return


@pytest.mark.asyncio
async def test_mcp_executor_http_and_sse():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MCPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/mcp"
        spec = ExecutorSpec(
            id="mcp-http",
            capability="text.stats",
            kind=ExecutorKind.MCP,
            description="mcp http",
            input_schema=INPUT,
            output_schema=OUTPUT,
            estimate=RouteEstimate(resources=ResourceVector(latency_ms=100)),
            side_effect=SideEffect.NONE,
            locality=Locality.LAN,
            requires_network=True,
            config={
                "transport": "http",
                "url": url,
                "allowed_hosts": ["127.0.0.1"],
                "allow_private_networks": True,
                "tool": "text_stats",
                "arguments": {"text": "{input.text}"},
            },
        )
        router = Router(manifest_with(spec))
        try:
            outcome = await router.execute(
                ActionRequest(capability="text.stats", input={"text": "a b"})
            )
            assert outcome.ok
            assert outcome.receipts[0].actual_resources.network_bytes > 0
            assert outcome.receipts[0].metadata["transport"] == "http"
        finally:
            await router.close()

        _MCPHandler.sse = True
        client = MCPHTTPClient(url=url)
        try:
            listed = await client.list_tools()
            assert listed.result["tools"][0]["name"] == "text_stats"
        finally:
            await client.close()
    finally:
        _MCPHandler.sse = False
        _MCPHandler.include_header_tool = False
        _MCPHandler.invalid_header_tool = False
        _MCPHandler.oversized = False
        _MCPHandler.wrong_content_type = False
        server.shutdown()
        server.server_close()


@pytest.mark.asyncio
async def test_legacy_stdio_client(tmp_path):
    script = tmp_path / "legacy.py"
    script.write_text(
        textwrap.dedent(
            """
            import json, sys
            for line in sys.stdin:
                m=json.loads(line); i=m.get("id"); method=m.get("method")
                if i is None: continue
                if method=="server/discover": out={"jsonrpc":"2.0","id":i,"error":{"code":-32601,"message":"no"}}
                elif method=="initialize": out={"jsonrpc":"2.0","id":i,"result":{"protocolVersion":"2025-11-25","capabilities":{"tools":{}},"serverInfo":{"name":"legacy","version":"1"}}}
                elif method=="tools/list": out={"jsonrpc":"2.0","id":i,"result":{"tools":[]}}
                else: out={"jsonrpc":"2.0","id":i,"result":{}}
                print(json.dumps(out), flush=True)
            """
        )
    )
    client = MCPStdioClient(command=sys.executable, args=[str(script)])
    try:
        listed = await client.list_tools()
        assert listed.protocol_version == LEGACY_VERSION
        assert listed.result == {"tools": []}
    finally:
        await client.close()


def _modern_meta():
    return {
        "io.modelcontextprotocol/protocolVersion": MODERN_VERSION,
        "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }


def _modern_headers(method: str, *, name: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": "Bearer secret",
        "MCP-Protocol-Version": MODERN_VERSION,
        "Mcp-Method": method,
    }
    if name is not None:
        headers["Mcp-Name"] = encode_header_value(name)
    return headers


def test_create_http_app_auth_and_modern_header_validation(tmp_path):
    manifest = write_default_manifest(tmp_path / "aeep.yaml")
    app = create_http_app(str(manifest), bearer_token="secret", max_body_bytes=1024)
    with TestClient(app) as client:
        assert client.get("/healthz").json()["ok"] is True
        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {"_meta": _modern_meta()},
        }
        assert client.post("/mcp", json=message).status_code == 401
        assert (
            client.post(
                "/mcp",
                json=message,
                headers={**_modern_headers("tools/list"), "Origin": "https://evil.test"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/mcp",
                content=b"x" * 2048,
                headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
            ).status_code
            == 413
        )
        missing = client.post("/mcp", json=message, headers={"Authorization": "Bearer secret"})
        assert missing.status_code == 400
        assert missing.json()["error"]["code"] == -32020

        response = client.post("/mcp", json=message, headers=_modern_headers("tools/list"))
        assert response.status_code == 200
        result = response.json()["result"]
        assert len(result["tools"]) == 10
        assert result["resultType"] == "complete"
        assert result["ttlMs"] > 0
        assert {
            "aeep_show_prepared_decision",
            "aeep_show_quote",
            "aeep_show_settlement",
        } <= {tool["name"] for tool in result["tools"]}

        hidden_call = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "aeep_prepare_route",
                "arguments": {},
                "_meta": _modern_meta(),
            },
        }
        hidden_response = client.post(
            "/mcp",
            json=hidden_call,
            headers=_modern_headers("tools/call", name="aeep_prepare_route"),
        )
        assert hidden_response.status_code == 200
        assert hidden_response.json()["error"]["code"] == -32602

        read_call = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "aeep_show_quote",
                "arguments": {"quote_id": "missing-quote"},
                "_meta": _modern_meta(),
            },
        }
        read_response = client.post(
            "/mcp",
            json=read_call,
            headers=_modern_headers("tools/call", name="aeep_show_quote"),
        )
        assert read_response.status_code == 200
        assert read_response.json()["result"]["isError"] is True

        mismatch = client.post("/mcp", json=message, headers=_modern_headers("tools/call"))
        assert mismatch.status_code == 400
        assert mismatch.json()["error"]["code"] == -32020

        unknown = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "unknown/method",
            "params": {"_meta": _modern_meta()},
        }
        unknown_response = client.post(
            "/mcp", json=unknown, headers=_modern_headers("unknown/method")
        )
        assert unknown_response.status_code == 404
        assert unknown_response.json()["error"]["code"] == -32601

        unsupported_headers = _modern_headers("tools/list")
        unsupported_headers["MCP-Protocol-Version"] = "2099-01-01"
        unsupported = client.post("/mcp", json=message, headers=unsupported_headers)
        assert unsupported.status_code == 400
        assert unsupported.json()["error"]["code"] == -32022

        # Legacy notifications remain accepted on the legacy compatibility path.
        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        assert (
            client.post(
                "/mcp",
                json=notification,
                headers={"Authorization": "Bearer secret"},
            ).status_code
            == 202
        )


@pytest.mark.asyncio
async def test_mcp_http_client_mirrors_x_mcp_headers_and_encodes_values():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MCPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _MCPHandler.include_header_tool = True
    try:
        client = MCPHTTPClient(url=f"http://127.0.0.1:{server.server_port}/mcp")
        try:
            listed = await client.list_tools()
            tool = listed.result["tools"][0]
            result = await client.call_tool(
                "text_stats",
                {"text": "hello", "region": "香港"},
                tool_schema=tool,
            )
            assert result.result["structuredContent"]["words"] == 1
            assert _MCPHandler.last_headers["mcp-method"] == "tools/call"
            assert _MCPHandler.last_headers["mcp-name"] == "text_stats"
            assert _MCPHandler.last_headers["mcp-param-region"].startswith("=?base64?")
        finally:
            await client.close()
    finally:
        _MCPHandler.include_header_tool = False
        server.shutdown()
        server.server_close()


@pytest.mark.asyncio
async def test_mcp_http_client_excludes_invalid_x_mcp_header_tool():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MCPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _MCPHandler.invalid_header_tool = True
    try:
        client = MCPHTTPClient(url=f"http://127.0.0.1:{server.server_port}/mcp")
        try:
            with pytest.warns(RuntimeWarning, match="excluding invalid MCP tool"):
                listed = await client.list_tools()
            assert listed.result["tools"] == []
        finally:
            await client.close()
    finally:
        _MCPHandler.invalid_header_tool = False
        server.shutdown()
        server.server_close()


@pytest.mark.asyncio
async def test_mcp_http_client_rejects_oversized_response():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MCPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _MCPHandler.oversized = True
    try:
        client = MCPHTTPClient(
            url=f"http://127.0.0.1:{server.server_port}/mcp",
            max_response_bytes=1024,
        )
        try:
            with pytest.raises(ProtocolError, match="size limit"):
                await client.list_tools()
        finally:
            await client.close()
    finally:
        _MCPHandler.oversized = False
        server.shutdown()
        server.server_close()


@pytest.mark.asyncio
async def test_mcp_http_client_rejects_wrong_content_type():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MCPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _MCPHandler.wrong_content_type = True
    try:
        client = MCPHTTPClient(url=f"http://127.0.0.1:{server.server_port}/mcp")
        try:
            with pytest.raises(ProtocolError, match="content type"):
                await client.list_tools()
        finally:
            await client.close()
    finally:
        _MCPHandler.wrong_content_type = False
        server.shutdown()
        server.server_close()


@pytest.mark.asyncio
async def test_stdio_ignored_message_limit_is_absolute(tmp_path):
    script = tmp_path / "chatter.py"
    script.write_text(
        textwrap.dedent(
            """
            import json, sys
            for line in sys.stdin:
                message=json.loads(line)
                for index in range(101):
                    print(json.dumps({"jsonrpc":"2.0","method":"notice","params":{"n":index}}), flush=True)
                print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":{"resultType":"complete","supportedVersions":["2026-07-28"]}}), flush=True)
            """
        )
    )
    client = MCPStdioClient(command=sys.executable, args=[str(script)])
    try:
        with pytest.raises(ProtocolError, match="ignored-message"):
            await client.list_tools()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_stdio_server_keeps_python_prints_off_protocol_stdout(tmp_path):
    manifest = tmp_path / "printing.yaml"
    manifest.write_text(
        textwrap.dedent(
            """
            version: "0.3"
            database: ":memory:"
            executors:
              - id: printing
                capability: text.stats
                kind: python
                description: prints a diagnostic
                side_effect: none
                config: {callable: aeep.examples.tools:printing_text_stats}
            """
        )
    )
    env = {**dict(os.environ), "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    client = MCPStdioClient(
        command=sys.executable,
        args=["-m", "aeep", "serve", "--transport", "stdio", "-m", str(manifest)],
        env=env,
    )
    try:
        response = await client.call_tool(
            "aeep_execute_action",
            {"capability": "text.stats", "input": {"text": "one two"}},
        )
        assert response.result["structuredContent"]["output"]["words"] == 2
    finally:
        await client.close()


def test_x_mcp_header_schema_rejects_duplicate_names():
    tool = {
        "name": "x",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "string", "x-mcp-header": "Tenant"},
                "b": {"type": "string", "x-mcp-header": "tenant"},
            },
        },
    }
    with pytest.raises(ProtocolError, match="unique"):
        tool_header_bindings(tool)


@pytest.mark.asyncio
async def test_mcp_executor_blocks_unreviewed_private_http_target():
    spec = ExecutorSpec(
        id="private-mcp",
        capability="x",
        kind=ExecutorKind.MCP,
        description="private target",
        input_schema={"type": "object"},
        estimate=RouteEstimate(),
        side_effect=SideEffect.NONE,
        locality=Locality.LAN,
        requires_network=True,
        config={
            "transport": "http",
            "url": "https://127.0.0.2/mcp",
            "tool": "x",
        },
    )
    router = Router(manifest_with(spec))
    try:
        outcome = await router.execute(ActionRequest(capability="x", input={}))
        assert not outcome.ok
        assert "private or non-public" in (outcome.receipts[0].error_message or "")
    finally:
        await router.close()
