"""MCP tool executor with stdio and Streamable HTTP transports."""

from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import suppress
from decimal import Decimal
from typing import Any

from ..errors import ConfigurationError, ProtocolError
from ..mcp.client import MCPHTTPClient, MCPResponse, MCPStdioClient
from ..models import (
    CashAccounting,
    CashClassification,
    CashEvidence,
    EvidenceSource,
    EvidenceStatus,
    ExecutionStatus,
    MeasurementEvidence,
    RawExecution,
    ResourceAccounting,
    ResourceVector,
    SubscriptionCharge,
    SubscriptionUsage,
    ToolFootprint,
    TrustLevel,
)
from ..profiler import approximate_tokens
from ..templates import extract_path, render
from .base import BaseExecutor, ExecutionContext
from .network import validate_http_url


def _minimal_environment() -> dict[str, str]:
    names = ["PATH", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT"]
    return {name: os.environ[name] for name in names if name in os.environ}


def _extract_result(result: dict[str, Any], *, parse_json_text: bool) -> Any:
    if "structuredContent" in result:
        return result["structuredContent"]
    content = result.get("content", [])
    if not isinstance(content, list):
        return content
    texts = [
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    if not texts:
        return content
    joined = "\n".join(texts)
    if parse_json_text:
        try:
            return json.loads(joined)
        except json.JSONDecodeError:
            pass
    return joined


def _usage_from_meta(result: dict[str, Any], fallback_cost: float) -> ResourceVector:
    """Legacy parser retained for callers; the executor no longer treats it as observed usage."""

    meta = result.get("_meta", {})
    usage = meta.get("org.aeep/usage", {}) if isinstance(meta, dict) else {}
    values = (
        {key: value for key, value in usage.items() if key in ResourceVector.model_fields}
        if isinstance(usage, dict)
        else {}
    )
    values.setdefault("monetary_usd", fallback_cost)
    try:
        return ResourceVector.model_validate(values)
    except Exception:
        return ResourceVector(monetary_usd=fallback_cost)


def _accounting_from_meta(result: dict[str, Any], context: ExecutionContext) -> ResourceAccounting:
    meta = result.get("_meta", {})
    usage = meta.get("org.aeep/usage", {}) if isinstance(meta, dict) else {}
    if not isinstance(usage, dict):
        usage = {}
    evidence = MeasurementEvidence(
        status=EvidenceStatus.PARTIAL,
        source=EvidenceSource.PROVIDER_REPORT,
        trust=TrustLevel.SELF_ASSERTED,
    )
    cash = CashAccounting()
    if "monetary_usd" in usage:
        with suppress(Exception):
            cash = CashAccounting(
                status=EvidenceStatus.PARTIAL,
                components=[
                    CashEvidence(
                        charge_id=f"mcp-provider:{context.spec.id}",
                        amount=Decimal(str(usage["monetary_usd"])),
                        classification=CashClassification.ESTIMATED,
                        evidence=evidence,
                    )
                ],
            )
    subscription: list[SubscriptionUsage] = []
    if context.spec.resource_pool and "subscription_units" in usage:
        with suppress(Exception):
            subscription.append(
                SubscriptionUsage(
                    provider=context.spec.provider_id or "unknown",
                    resource_pool=context.spec.resource_pool,
                    unit=str(context.spec.config.get("subscription_unit", "provider_unit")),
                    consumed=Decimal(str(usage["subscription_units"])),
                    source=evidence,
                    included_or_paid=SubscriptionCharge.UNKNOWN,
                )
            )
    return ResourceAccounting(cash=cash, subscription_usage=subscription)


class MCPExecutor(BaseExecutor):
    def __init__(self) -> None:
        self._clients: dict[str, MCPStdioClient | MCPHTTPClient] = {}
        self._tool_schemas: dict[str, tuple[dict[str, Any], float]] = {}

    @staticmethod
    def _connection_key(context: ExecutionContext) -> str:
        config = context.spec.config
        connection = {
            key: config.get(key)
            for key in (
                "transport",
                "command",
                "args",
                "url",
                "cwd",
                "env",
                "headers",
                "credential_scope_id",
                "protocol_mode",
            )
        }
        rendered_identity = json.dumps(connection, sort_keys=True, separators=(",", ":"))
        if "{input" in rendered_identity or "{action" in rendered_identity:
            raise ConfigurationError("MCP connection identity cannot depend on action input")
        if config.get("headers") and not config.get("credential_scope_id"):
            raise ConfigurationError("MCP HTTP credentials require credential_scope_id")
        canonical = json.dumps(connection, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(canonical).hexdigest()

    async def _create_client(self, context: ExecutionContext) -> MCPStdioClient | MCPHTTPClient:
        config = context.spec.config
        transport = str(config.get("transport", "stdio"))
        timeout = float(config.get("timeout_seconds", 30.0))
        values = {"input": context.request.input, "action": context.request.model_dump(mode="json")}
        if transport == "stdio":
            command = config.get("command")
            if not isinstance(command, str) or not command:
                raise ConfigurationError("MCP stdio executor requires config.command")
            args = render(config.get("args", []), values)
            if not isinstance(args, list):
                raise ConfigurationError("MCP stdio config.args must be a list")
            environment = (
                dict(os.environ) if config.get("inherit_env", False) else _minimal_environment()
            )
            configured_env = config.get("env", {})
            if not isinstance(configured_env, dict):
                raise ConfigurationError("MCP stdio config.env must be a mapping")
            environment.update(
                {
                    str(key): str(value)
                    for key, value in render(configured_env, values, allow_env=True).items()
                }
            )
            return MCPStdioClient(
                command=command,
                args=[str(item) for item in args],
                env=environment,
                cwd=config.get("cwd"),
                timeout=timeout,
                max_message_bytes=int(config.get("max_message_bytes", 2_000_000)),
                protocol_mode=str(config.get("protocol_mode", "auto")),
            )
        if transport in {"http", "streamable_http", "streamable-http"}:
            url = config.get("url")
            if not isinstance(url, str) or not url:
                raise ConfigurationError("MCP HTTP executor requires config.url")
            headers_template = config.get("headers", {})
            if not isinstance(headers_template, dict):
                raise ConfigurationError("MCP HTTP config.headers must be a mapping")
            headers = {
                str(key): str(value)
                for key, value in render(headers_template, values, allow_env=True).items()
            }
            rendered_url = str(render(url, values))
            await validate_http_url(rendered_url, config, label="MCP HTTP")
            return MCPHTTPClient(
                url=rendered_url,
                headers=headers,
                timeout=timeout,
                max_response_bytes=int(config.get("max_response_bytes", 2_000_000)),
                max_request_bytes=int(config.get("max_request_bytes", 2_000_000)),
                trust_env=bool(config.get("trust_proxy_env", False)),
                protocol_mode=str(config.get("protocol_mode", "auto")),
            )
        raise ConfigurationError(f"unsupported MCP transport {transport!r}")

    async def _client(self, context: ExecutionContext) -> MCPStdioClient | MCPHTTPClient:
        key = self._connection_key(context)
        client = self._clients.get(key)
        if client is None:
            client = await self._create_client(context)
            self._clients[key] = client
        return client

    async def _ensure_tool(
        self,
        context: ExecutionContext,
        client: MCPStdioClient | MCPHTTPClient,
        tool_name: str,
    ) -> tuple[dict[str, Any], MCPResponse | None, bool]:
        cache_key = f"{self._connection_key(context)}:{tool_name}"
        cached = self._tool_schemas.get(cache_key)
        if cached is not None and cached[1] > time.monotonic():
            return cached[0], None, True
        response = await client.list_tools()
        tools = response.result.get("tools", [])
        for tool in tools:
            if isinstance(tool, dict) and tool.get("name") == tool_name:
                advertised = tool.get("inputSchema")
                if not isinstance(advertised, dict) or advertised != context.spec.input_schema:
                    raise ProtocolError("MCP tool schema drift detected before invocation")
                meta = response.result.get("_meta", {})
                ttl_ms = response.result.get(
                    "ttlMs", meta.get("ttlMs", 60_000) if isinstance(meta, dict) else 60_000
                )
                cache_scope = response.result.get(
                    "cacheScope",
                    meta.get("cacheScope", "private") if isinstance(meta, dict) else "private",
                )
                if cache_scope not in {"private", "public", "no-store"}:
                    raise ProtocolError("MCP tools/list returned an invalid cacheScope")
                if not isinstance(ttl_ms, (int, float, str)):
                    raise ProtocolError("MCP tools/list returned an invalid ttlMs")
                try:
                    ttl = max(0.0, min(float(ttl_ms), 3_600_000.0)) / 1000.0
                except ValueError as exc:
                    raise ProtocolError("MCP tools/list returned an invalid ttlMs") from exc
                if cache_scope != "no-store" and ttl > 0:
                    self._tool_schemas[cache_key] = (tool, time.monotonic() + ttl)
                return tool, response, False
        raise ProtocolError(f"MCP server does not expose configured tool {tool_name!r}")

    async def execute(self, context: ExecutionContext) -> RawExecution:
        config = context.spec.config
        tool_name = config.get("tool")
        if not isinstance(tool_name, str) or not tool_name:
            raise ConfigurationError(f"MCP executor {context.spec.id} requires config.tool")
        values = {"input": context.request.input, "action": context.request.model_dump(mode="json")}
        arguments_template = config.get("arguments", "{input}")
        arguments = render(arguments_template, values)
        if not isinstance(arguments, dict):
            raise ConfigurationError("rendered MCP tool arguments must be an object")
        started = time.perf_counter()
        request_bytes = 0
        response_bytes = 0
        try:
            client = await self._client(context)
            tool_schema, list_response, schema_cache_hit = await self._ensure_tool(
                context, client, tool_name
            )
            if list_response is not None:
                request_bytes += list_response.request_bytes
                response_bytes += list_response.response_bytes
            call = await client.call_tool(
                tool_name,
                arguments,
                tool_schema=tool_schema,
                metadata=(
                    {"org.aeep/idempotencyKey": context.request.idempotency_key}
                    if context.request.idempotency_key
                    and config.get("propagate_idempotency_key", True)
                    else None
                ),
            )
            request_bytes += call.request_bytes
            response_bytes += call.response_bytes
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            usage = ResourceVector(latency_ms=elapsed_ms)
            accounting = _accounting_from_meta(call.result, context)
            is_http = isinstance(client, MCPHTTPClient)
            if is_http:
                usage.network_bytes += request_bytes + response_bytes
            output = _extract_result(
                call.result,
                parse_json_text=bool(config.get("parse_json_text", True)),
            )
            output = extract_path(output, config.get("output", {}).get("path"))
            schema_context = approximate_tokens(tool_schema)
            result_tokens = approximate_tokens(output)
            accounting.tool_footprint = ToolFootprint(
                schema_approx_tokens=schema_context,
                raw_result_bytes=response_bytes,
                raw_result_approx_tokens=result_tokens,
                filtered_result_approx_tokens=result_tokens,
                exposed_to_model=False,
            )
            metadata = {
                "transport": "http" if is_http else "stdio",
                "tool": tool_name,
                "protocol_version": call.protocol_version,
                "ipc_bytes": request_bytes + response_bytes,
                "tool_schema_tokens_estimate": schema_context,
                "schema_cache_hit": schema_cache_hit,
            }
            if bool(call.result.get("isError", False)):
                return RawExecution(
                    status=ExecutionStatus.FAILED,
                    output=output,
                    resources=usage,
                    accounting=accounting,
                    error_type="MCPToolError",
                    error_message="MCP server reported a tool error",
                    metadata=metadata,
                )
            return RawExecution(
                status=ExecutionStatus.SUCCESS,
                output=output,
                resources=usage,
                accounting=accounting,
                metadata=metadata,
            )
        except TimeoutError as exc:
            return RawExecution(
                status=ExecutionStatus.TIMEOUT,
                resources=ResourceVector(
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                ),
                error_type=type(exc).__name__,
                error_message=str(exc) or "MCP call timed out",
            )
        except Exception as exc:
            return RawExecution(
                status=ExecutionStatus.FAILED,
                resources=ResourceVector(
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                ),
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

    async def close(self) -> None:
        clients = list(self._clients.values())
        self._clients.clear()
        self._tool_schemas.clear()
        for client in clients:
            await client.close()
