"""Dependency-light MCP server exposing the AEEP router.

The server supports:
- stateless MCP 2026-07-28 discovery and per-request metadata, and
- the legacy 2025-11-25 initialize handshake,

over newline-delimited stdio or Streamable HTTP-style JSON POSTs.

Only JSON-RPC messages are written to stdout in stdio mode. Diagnostics belong
on stderr so agent harnesses can safely parse the protocol stream.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import Request as _FastAPIRequest

from ..errors import AEEPError, ApprovalRequired, ProtocolError
from ..integrations import export_tools
from ..models import ActionRequest, ExternalOutcomeReport, QuoteRequest, ResourceVector, SideEffect
from ..router import Router
from ..version import __version__
from .client import LEGACY_VERSION, MODERN_VERSION, UNSUPPORTED_PROTOCOL_VERSION
from .headers import decode_header_value, validate_tool_parameter_headers

JSONRPC_VERSION = "2.0"
HEADER_MISMATCH = -32020
_SERVER_INFO_KEY = "io.modelcontextprotocol/serverInfo"
_INSTRUCTIONS = (
    "Use aeep_route_action to inspect alternatives and aeep_execute_action to execute. "
    "Report a selected host-delegated route exactly once with aeep_record_outcome."
)


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"cannot JSON encode {type(value).__name__}")


def _server_meta() -> dict[str, Any]:
    return {_SERVER_INFO_KEY: {"name": "aeep-agent-router", "version": __version__}}


def _tool_result(
    payload: Any,
    *,
    is_error: bool = False,
    usage: ResourceVector | None = None,
) -> dict[str, Any]:
    encoded = json.dumps(payload, ensure_ascii=False, default=_json_default)
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": encoded}],
        "isError": is_error,
    }
    if isinstance(payload, dict):
        result["structuredContent"] = payload
    if usage is not None:
        result["_meta"] = {"org.aeep/usage": usage.model_dump(mode="json")}
    return result


def _action_from_arguments(arguments: dict[str, Any]) -> ActionRequest:
    value: dict[str, Any] = {
        "capability": arguments["capability"],
        "input": arguments.get("input", {}),
        "policy": arguments.get("policy", "balanced"),
    }
    if "constraints" in arguments:
        value["constraints"] = arguments["constraints"]
    if "context" in arguments:
        value["context"] = arguments["context"]
    if "idempotency_key" in arguments:
        value["idempotency_key"] = arguments["idempotency_key"]
    return ActionRequest.model_validate(value)


def _sum_receipt_usage(receipts: list[Any]) -> ResourceVector:
    total = ResourceVector()
    for receipt in receipts:
        resources = getattr(receipt, "actual_resources", None)
        if isinstance(resources, ResourceVector):
            total = total.plus(resources)
    return total


def _request_version(params: Mapping[str, Any]) -> str | None:
    meta = params.get("_meta")
    if not isinstance(meta, Mapping):
        return None
    value = meta.get("io.modelcontextprotocol/protocolVersion")
    return str(value) if isinstance(value, str) else None


def _tool_by_name(tools: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((tool for tool in tools if tool.get("name") == name), None)


class AEEPToolService:
    """Provider-neutral implementations behind MCP and generated tool schemas."""

    def __init__(
        self,
        router: Router,
        *,
        approved_side_effect: SideEffect = SideEffect.READ,
        allow_unsafe_executor: bool = False,
    ) -> None:
        self.router = router
        # These are operator-controlled ceilings. Tool-call arguments are
        # untrusted model output and therefore cannot elevate approvals.
        self.approved_side_effect = approved_side_effect
        self.allow_unsafe_executor = allow_unsafe_executor

    def list_tools(self) -> list[dict[str, Any]]:
        return export_tools("mcp")

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "aeep_list_capabilities":
                payload = self.router.search_capabilities(
                    str(arguments.get("query", "")),
                    prefix=arguments.get("prefix"),
                    limit=int(arguments.get("limit", 20)),
                    cursor=int(arguments.get("cursor", 0)),
                    include_executors=bool(arguments.get("include_executors", False)),
                )
                return _tool_result(payload)
            if name == "aeep_route_action":
                decision = await self.router.route_with_discovery(_action_from_arguments(arguments))
                route_payload = (
                    decision
                    if arguments.get("detail") == "full"
                    else self.router.compact_decision(decision)
                )
                return _tool_result(route_payload.model_dump(mode="json"))
            if name == "aeep_execute_action":
                request = _action_from_arguments(arguments)
                outcome = await self.router.execute(
                    request,
                    approved_side_effect=self.approved_side_effect,
                    allow_unsafe_executor=self.allow_unsafe_executor,
                    dry_run=bool(arguments.get("dry_run", False)),
                )
                execution_payload = (
                    outcome
                    if arguments.get("detail") == "full"
                    else self.router.compact_outcome(outcome)
                )
                return _tool_result(
                    execution_payload.model_dump(mode="json"),
                    is_error=not outcome.ok,
                    usage=_sum_receipt_usage(outcome.receipts),
                )
            if name == "aeep_record_outcome":
                report = ExternalOutcomeReport.model_validate(arguments)
                receipt = self.router.record_external_outcome(report)
                return _tool_result(
                    receipt.model_dump(mode="json"),
                    usage=receipt.actual_resources,
                )
            if name == "aeep_request_quotes":
                quote_request = QuoteRequest(
                    action=_action_from_arguments(arguments),
                    executor_ids=arguments.get("executor_ids"),
                )
                quotes = self.router.quotes(quote_request)
                return _tool_result({"quotes": [quote.model_dump(mode="json") for quote in quotes]})
            if name == "aeep_get_metrics":
                metrics = self.router.metrics(limit=int(arguments.get("limit", 10_000)))
                return _tool_result(metrics.model_dump(mode="json"))
            return _tool_result({"error": f"unknown tool {name!r}"}, is_error=True)
        except ApprovalRequired as exc:
            return _tool_result(
                {
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "executor_id": exc.executor_id,
                    "required_level": exc.required_level,
                },
                is_error=True,
            )
        except (AEEPError, ValueError, KeyError) as exc:
            return _tool_result(
                {"error": str(exc), "error_type": type(exc).__name__},
                is_error=True,
            )


class MCPProtocolApp:
    def __init__(self, service: AEEPToolService) -> None:
        self.service = service

    @staticmethod
    def _result(
        request_id: Any,
        result: dict[str, Any],
        *,
        modern: bool = False,
    ) -> dict[str, Any]:
        payload = dict(result)
        if modern:
            payload.setdefault("resultType", "complete")
            meta = payload.get("_meta")
            merged_meta = dict(meta) if isinstance(meta, dict) else {}
            merged_meta.setdefault(_SERVER_INFO_KEY, _server_meta()[_SERVER_INFO_KEY])
            payload["_meta"] = merged_meta
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": payload}

    @staticmethod
    def _error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}

    async def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get("id")
        if message.get("jsonrpc") != JSONRPC_VERSION:
            return self._error(request_id, -32600, "Invalid Request")
        method = message.get("method")
        params = message.get("params", {})
        if not isinstance(method, str) or not isinstance(params, dict):
            return self._error(request_id, -32600, "Invalid Request")

        # Notifications intentionally produce no JSON-RPC response.
        if request_id is None:
            return None

        version = _request_version(params)
        modern = method == "server/discover" or version == MODERN_VERSION

        if method == "server/discover":
            return self._result(
                request_id,
                {
                    "supportedVersions": [MODERN_VERSION, LEGACY_VERSION],
                    "capabilities": {"tools": {"listChanged": False}},
                    "instructions": _INSTRUCTIONS,
                    "ttlMs": 300_000,
                    "cacheScope": "private",
                },
                modern=True,
            )
        if method == "initialize":
            # initialize is a legacy-era handshake. A modern client uses
            # server/discover and per-request metadata instead.
            return self._result(
                request_id,
                {
                    "protocolVersion": LEGACY_VERSION,
                    "serverInfo": {"name": "aeep-agent-router", "version": __version__},
                    "capabilities": {"tools": {"listChanged": False}},
                    "instructions": _INSTRUCTIONS,
                },
            )
        if method == "ping":
            if modern:
                return self._error(request_id, -32601, "Method not found: ping")
            return self._result(request_id, {})
        if method == "tools/list":
            result: dict[str, Any] = {"tools": self.service.list_tools()}
            if modern:
                result.update({"ttlMs": 60_000, "cacheScope": "private"})
            return self._result(request_id, result, modern=modern)
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return self._error(request_id, -32602, "Invalid tools/call parameters")
            if _tool_by_name(self.service.list_tools(), name) is None:
                return self._error(request_id, -32602, f"Unknown tool: {name}")
            result = await self.service.call(name, arguments)
            return self._result(request_id, result, modern=modern)
        return self._error(request_id, -32601, f"Method not found: {method}")


def _http_error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    return MCPProtocolApp._error(request_id, code, message, data)


def _validate_modern_http_headers(
    message: dict[str, Any],
    headers: Mapping[str, str],
    tools: list[dict[str, Any]],
) -> None:
    method = message.get("method")
    params = message.get("params", {})
    if not isinstance(method, str) or not isinstance(params, dict):
        raise ProtocolError("invalid JSON-RPC request body")
    body_version = _request_version(params)
    header_version = headers.get("mcp-protocol-version")
    if header_version != body_version:
        raise ProtocolError("MCP-Protocol-Version does not match request _meta")
    if header_version != MODERN_VERSION:
        raise ProtocolError("modern MCP request must use the modern protocol version")
    if headers.get("mcp-method") != method:
        raise ProtocolError("Mcp-Method does not match request method")

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise ProtocolError("invalid tools/call parameters")
        encoded_name = headers.get("mcp-name")
        if encoded_name is None or decode_header_value(encoded_name) != name:
            raise ProtocolError("Mcp-Name does not match request body")
        tool = _tool_by_name(tools, name)
        if tool is not None:
            validate_tool_parameter_headers(tool, arguments, headers)


async def serve_stdio(
    manifest: str | None = None,
    *,
    approved_side_effect: SideEffect = SideEffect.READ,
    allow_unsafe_executor: bool = False,
    max_message_bytes: int = 2_000_000,
) -> None:
    """Run until stdin closes."""

    router = Router.from_manifest(manifest)
    app = MCPProtocolApp(
        AEEPToolService(
            router,
            approved_side_effect=approved_side_effect,
            allow_unsafe_executor=allow_unsafe_executor,
        )
    )
    max_bytes = max(1024, int(max_message_bytes))
    try:
        while True:
            line = await asyncio.to_thread(sys.stdin.buffer.readline)
            if not line:
                break
            try:
                if len(line) > max_bytes:
                    raise ValueError("message exceeds configured size limit")
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError("message must be a JSON object")
                response = await app.handle(message)
            except Exception as exc:  # protocol boundary: return a parse/internal error
                response = MCPProtocolApp._error(None, -32700, "Parse error", str(exc))
            if response is not None:
                payload = json.dumps(
                    response,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=_json_default,
                )
                sys.stdout.write(payload + "\n")
                sys.stdout.flush()
    finally:
        await router.close()


def create_http_app(
    manifest: str | None = None,
    *,
    bearer_token: str | None = None,
    approved_side_effect: SideEffect = SideEffect.READ,
    allow_unsafe_executor: bool = False,
) -> Any:
    """Create an optional FastAPI app without making FastAPI a base dependency."""

    try:
        from fastapi import FastAPI, Header, HTTPException, Request, Response
        from fastapi.responses import JSONResponse
    except ImportError as exc:  # pragma: no cover - optional extra
        raise RuntimeError(
            "HTTP serving requires `pip install 'aeep-agent-router[http-server]'`"
        ) from exc

    # FastAPI resolves postponed annotations from module globals. Request is an
    # optional dependency imported locally, so expose only this runtime alias.
    globals()["_FastAPIRequest"] = Request

    router = Router.from_manifest(manifest)
    service = AEEPToolService(
        router,
        approved_side_effect=approved_side_effect,
        allow_unsafe_executor=allow_unsafe_executor,
    )
    protocol = MCPProtocolApp(service)

    @asynccontextmanager
    async def lifespan(_app: Any) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await router.close()

    app = FastAPI(title="AEEP MCP Server", version=__version__, lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    @app.post("/mcp")
    async def mcp_endpoint(
        message: dict[str, Any],
        request: _FastAPIRequest,
        authorization: str | None = Header(default=None),
    ) -> Any:
        if bearer_token:
            expected = f"Bearer {bearer_token}"
            if authorization != expected:
                raise HTTPException(status_code=401, detail="invalid bearer token")

        method = message.get("method")
        params = message.get("params", {})
        body_version = _request_version(params) if isinstance(params, dict) else None
        header_version = request.headers.get("mcp-protocol-version")
        modern_request = (
            method == "server/discover"
            or body_version == MODERN_VERSION
            or header_version == MODERN_VERSION
        )

        if header_version is not None and header_version not in {MODERN_VERSION, LEGACY_VERSION}:
            return JSONResponse(
                status_code=400,
                content=_http_error(
                    message.get("id"),
                    UNSUPPORTED_PROTOCOL_VERSION,
                    f"Unsupported protocol version: {header_version}",
                    {"supported": [MODERN_VERSION, LEGACY_VERSION]},
                ),
            )

        if modern_request:
            try:
                _validate_modern_http_headers(message, request.headers, service.list_tools())
            except ProtocolError as exc:
                return JSONResponse(
                    status_code=400,
                    content=_http_error(message.get("id"), HEADER_MISMATCH, str(exc)),
                )

        result = await protocol.handle(message)
        if result is None:
            # 202 is the MCP-recommended response for accepted notifications.
            return Response(status_code=202)
        status_code = 200
        if modern_request and result.get("error", {}).get("code") == -32601:
            status_code = 404
        return JSONResponse(result, status_code=status_code)

    return app
