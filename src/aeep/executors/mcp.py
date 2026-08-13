"""MCP tool executor with stdio and Streamable HTTP transports."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from ..errors import ConfigurationError, ProtocolError
from ..mcp.client import MCPHTTPClient, MCPResponse, MCPStdioClient
from ..models import ExecutionStatus, RawExecution, ResourceVector
from ..profiler import approximate_tokens
from ..templates import render
from .base import BaseExecutor, ExecutionContext
from .network import validate_http_url


def _minimal_environment() -> dict[str, str]:
    names = ["PATH", "HOME", "USERPROFILE", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT"]
    return {name: os.environ[name] for name in names if name in os.environ}


def _extract_result(result: dict[str, Any], *, parse_json_text: bool) -> Any:
    if "structuredContent" in result:
        return result["structuredContent"]
    content = result.get("content", [])
    if not isinstance(content, list):
        return content
    texts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
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
    meta = result.get("_meta", {})
    usage = meta.get("org.aeep/usage", {}) if isinstance(meta, dict) else {}
    if not isinstance(usage, dict):
        usage = {}
    allowed = ResourceVector.model_fields
    values = {key: value for key, value in usage.items() if key in allowed}
    values.setdefault("monetary_usd", fallback_cost)
    try:
        return ResourceVector.model_validate(values)
    except Exception:
        return ResourceVector(monetary_usd=fallback_cost)


class MCPExecutor(BaseExecutor):
    def __init__(self) -> None:
        self._clients: dict[str, MCPStdioClient | MCPHTTPClient] = {}
        self._tool_schemas: dict[str, dict[str, Any]] = {}

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
                trust_env=bool(config.get("trust_proxy_env", False)),
            )
        raise ConfigurationError(f"unsupported MCP transport {transport!r}")

    async def _client(self, context: ExecutionContext) -> MCPStdioClient | MCPHTTPClient:
        client = self._clients.get(context.spec.id)
        if client is None:
            client = await self._create_client(context)
            self._clients[context.spec.id] = client
        return client

    async def _ensure_tool(
        self,
        context: ExecutionContext,
        client: MCPStdioClient | MCPHTTPClient,
        tool_name: str,
    ) -> tuple[dict[str, Any], MCPResponse | None]:
        cached = self._tool_schemas.get(context.spec.id)
        if cached is not None:
            return cached, None
        response = await client.list_tools()
        tools = response.result.get("tools", [])
        for tool in tools:
            if isinstance(tool, dict) and tool.get("name") == tool_name:
                self._tool_schemas[context.spec.id] = tool
                return tool, response
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
            tool_schema, list_response = await self._ensure_tool(context, client, tool_name)
            if list_response is not None:
                request_bytes += list_response.request_bytes
                response_bytes += list_response.response_bytes
            call = await client.call_tool(tool_name, arguments, tool_schema=tool_schema)
            request_bytes += call.request_bytes
            response_bytes += call.response_bytes
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            usage = _usage_from_meta(
                call.result, context.estimate.resources.monetary_usd
            )
            usage.latency_ms = elapsed_ms
            is_http = isinstance(client, MCPHTTPClient)
            if is_http:
                usage.network_bytes += request_bytes + response_bytes
            output = _extract_result(
                call.result,
                parse_json_text=bool(config.get("parse_json_text", True)),
            )
            schema_context = approximate_tokens(tool_schema)
            usage.context_tokens += schema_context + approximate_tokens(output)
            metadata = {
                "transport": "http" if is_http else "stdio",
                "tool": tool_name,
                "protocol_version": call.protocol_version,
                "ipc_bytes": request_bytes + response_bytes,
                "tool_schema_tokens_estimate": schema_context,
            }
            if bool(call.result.get("isError", False)):
                return RawExecution(
                    status=ExecutionStatus.FAILED,
                    output=output,
                    resources=usage,
                    error_type="MCPToolError",
                    error_message=str(output),
                    metadata=metadata,
                )
            return RawExecution(
                status=ExecutionStatus.SUCCESS,
                output=output,
                resources=usage,
                metadata=metadata,
            )
        except TimeoutError as exc:
            return RawExecution(
                status=ExecutionStatus.TIMEOUT,
                resources=ResourceVector(
                    monetary_usd=context.estimate.resources.monetary_usd,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                ),
                error_type=type(exc).__name__,
                error_message=str(exc) or "MCP call timed out",
            )
        except Exception as exc:
            return RawExecution(
                status=ExecutionStatus.FAILED,
                resources=ResourceVector(
                    monetary_usd=context.estimate.resources.monetary_usd,
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
