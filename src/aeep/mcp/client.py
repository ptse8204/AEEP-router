"""Dependency-light dual-era MCP clients used by the built-in executor.

The clients prefer stateless MCP 2026-07-28 and can fall back to the legacy
2025-11-25 initialize handshake. The HTTP client implements required request
header mirroring, bounded responses, optional SSE envelopes, and x-mcp-header
parameter mirroring. The stdio client bounds individual protocol messages and
keeps diagnostics off the protocol stream.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import warnings
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..errors import ProtocolError
from ..version import __version__
from .headers import encode_header_value, tool_header_bindings, tool_parameter_headers

MODERN_VERSION = "2026-07-28"
LEGACY_VERSION = "2025-11-25"
UNSUPPORTED_PROTOCOL_VERSION = -32022


@dataclass(slots=True)
class MCPResponse:
    result: dict[str, Any]
    request_bytes: int
    response_bytes: int
    protocol_version: str
    raw: dict[str, Any] = field(default_factory=dict)


def _modern_meta(version: str = MODERN_VERSION) -> dict[str, Any]:
    return {
        "io.modelcontextprotocol/protocolVersion": version,
        "io.modelcontextprotocol/clientInfo": {"name": "aeep", "version": __version__},
        "io.modelcontextprotocol/clientCapabilities": {},
    }


def _decode_sse(text: str, request_id: int | str | None) -> dict[str, Any]:
    for block in text.replace("\r\n", "\n").split("\n\n"):
        data_lines = [line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")]
        if not data_lines:
            continue
        try:
            message = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict) and message.get("id") == request_id:
            return message
    raise ProtocolError("MCP SSE response did not contain the matching JSON-RPC response")


def _error_from_response(
    response: dict[str, Any],
    method: str,
    *,
    status_code: int | None = None,
) -> ProtocolError | None:
    error = response.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    code_value = int(code) if isinstance(code, int) else None
    return ProtocolError(
        f"MCP {method} failed: {error}",
        code=code_value,
        status_code=status_code,
        data=error.get("data"),
    )


def _validate_response_envelope(response: dict[str, Any], request_id: int | str) -> None:
    if response.get("jsonrpc") != "2.0":
        raise ProtocolError("MCP response must declare jsonrpc=2.0")
    if response.get("id") != request_id:
        raise ProtocolError("MCP response id does not match request")
    has_result = "result" in response
    has_error = "error" in response
    if has_result == has_error:
        raise ProtocolError("MCP response must contain exactly one of result or error")
    if has_result and not isinstance(response["result"], dict):
        raise ProtocolError("MCP response result must be an object")
    if has_error and not isinstance(response["error"], dict):
        raise ProtocolError("MCP response error must be an object")


def _validate_complete_result(result: dict[str, Any], method: str, version: str) -> None:
    if version == MODERN_VERSION and "resultType" not in result:
        raise ProtocolError(f"MCP {method} omitted required resultType")
    result_type = result.get("resultType", "complete")
    if result_type == "input_required":
        raise ProtocolError(
            f"MCP {method} requires multi-round-trip input, which this executor does not yet support"
        )
    if version == MODERN_VERSION and result_type != "complete":
        raise ProtocolError(f"MCP {method} returned unsupported resultType {result_type!r}")


class MCPStdioClient:
    def __init__(
        self,
        *,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: float = 30.0,
        discovery_timeout: float = 5.0,
        max_message_bytes: int = 2_000_000,
        protocol_mode: str = "auto",
    ) -> None:
        self.command = command
        self.args = list(args or [])
        self.env = env
        self.cwd = cwd
        self.timeout = timeout
        # Starting an MCP child can take more than two seconds on instrumented,
        # cold, or dependency-heavy runtimes. A too-aggressive discovery probe
        # silently downgrades a modern server to the legacy handshake. Keep the
        # probe bounded, but give a local process a realistic startup window.
        self.discovery_timeout = max(0.1, min(float(discovery_timeout), float(timeout)))
        self.max_message_bytes = max(1024, int(max_message_bytes))
        if protocol_mode not in {"auto", "modern", "legacy"}:
            raise ValueError("protocol_mode must be auto, modern, or legacy")
        self.protocol_mode = protocol_mode
        self.process: asyncio.subprocess.Process | None = None
        self.protocol_version: str | None = None
        self._next_id = 1
        self._lock = asyncio.Lock()
        self._stderr_task: asyncio.Task[None] | None = None
        self.stderr_tail: deque[str] = deque(maxlen=50)

    async def _start(self) -> None:
        if self.process is not None and self.process.returncode is None:
            return
        self.process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=self.env,
            start_new_session=os.name == "posix",
            limit=self.max_message_bytes + 1,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _drain_stderr(self) -> None:
        assert self.process is not None
        if self.process.stderr is None:
            return
        while line := await self.process.stderr.readline():
            # Bound diagnostic retention independently of child behavior.
            self.stderr_tail.append(line[-4096:].decode("utf-8", errors="replace").rstrip())

    async def connect(self) -> None:
        if (
            self.protocol_version is not None
            and self.process is not None
            and self.process.returncode is None
        ):
            return
        await self._start()
        if self.protocol_mode == "legacy":
            await self._legacy_initialize()
            return
        discover_id = self._allocate_id()
        discover = {
            "jsonrpc": "2.0",
            "id": discover_id,
            "method": "server/discover",
            "params": {"_meta": _modern_meta()},
        }
        response, _, _ = await self._exchange(discover, timeout=self.discovery_timeout)
        _validate_response_envelope(response, discover_id)

        result = response.get("result")
        if isinstance(result, dict) and isinstance(result.get("supportedVersions"), list):
            _validate_complete_result(result, "server/discover", MODERN_VERSION)
            versions = [str(item) for item in result["supportedVersions"]]
            if MODERN_VERSION not in versions:
                raise ProtocolError(
                    f"MCP server does not support {MODERN_VERSION}; supports {versions}",
                    code=UNSUPPORTED_PROTOCOL_VERSION,
                    data={"supported": versions},
                )
            self.protocol_version = MODERN_VERSION
            return

        error = response.get("error")
        if isinstance(error, dict) and error.get("code") == UNSUPPORTED_PROTOCOL_VERSION:
            data = error.get("data")
            supported = data.get("supported", []) if isinstance(data, dict) else []
            if MODERN_VERSION in supported:
                self.protocol_version = MODERN_VERSION
                return
            raise ProtocolError(
                f"MCP server rejected protocol version; supports {supported}",
                code=UNSUPPORTED_PROTOCOL_VERSION,
                data=data,
            )

        if self.protocol_mode == "auto" and isinstance(error, dict) and error.get("code") == -32601:
            await self._legacy_initialize()
            return
        raise ProtocolError("MCP modern discovery did not return a supported protocol")

    async def _legacy_initialize(self) -> None:
        request_id = self._allocate_id()
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": LEGACY_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "aeep", "version": __version__},
            },
        }
        response, _, _ = await self._exchange(request)
        _validate_response_envelope(response, request_id)
        error = _error_from_response(response, "initialize")
        if error:
            raise error
        result = response.get("result", {})
        if not isinstance(result, dict):
            raise ProtocolError("MCP initialize returned a non-object result")
        self.protocol_version = str(result.get("protocolVersion", LEGACY_VERSION))
        await self._notify("notifications/initialized", {})

    def _allocate_id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    async def _exchange(
        self, message: dict[str, Any], *, timeout: float | None = None
    ) -> tuple[dict[str, Any], int, int]:
        assert self.process is not None
        if self.process.stdin is None or self.process.stdout is None:
            raise ProtocolError("MCP stdio process is missing pipes")
        payload = (
            json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
        )
        if len(payload) > self.max_message_bytes:
            raise ProtocolError("MCP stdio request exceeds configured message limit")
        self.process.stdin.write(payload)
        await self.process.stdin.drain()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (timeout or self.timeout)
        ignored = 0
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("MCP stdio response deadline exceeded")
            try:
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=remaining)
            except (ValueError, asyncio.LimitOverrunError) as exc:
                raise ProtocolError("MCP stdio response exceeds configured message limit") from exc
            if not line:
                detail = "; ".join(self.stderr_tail)
                raise ProtocolError(
                    f"MCP server closed stdout unexpectedly{': ' + detail if detail else ''}"
                )
            if len(line) > self.max_message_bytes:
                raise ProtocolError("MCP stdio response exceeds configured message limit")
            try:
                response = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProtocolError("MCP server wrote non-JSON data to stdout") from exc
            if not isinstance(response, dict):
                raise ProtocolError("MCP server returned a non-object JSON-RPC message")
            if response.get("id") == message.get("id"):
                return response, len(payload), len(line)
            # Ignore notifications and responses to cancelled/previous requests.
            ignored += 1
            if ignored > 100:
                raise ProtocolError("MCP stdio response exceeded ignored-message limit")

    async def _request(self, method: str, params: dict[str, Any]) -> MCPResponse:
        async with self._lock:
            await self.connect()
            request_id = self._allocate_id()
            request_params = dict(params)
            if self.protocol_version == MODERN_VERSION:
                request_params["_meta"] = {
                    **(
                        request_params.get("_meta", {})
                        if isinstance(request_params.get("_meta"), dict)
                        else {}
                    ),
                    **_modern_meta(),
                }
            message = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": request_params,
            }
            response, request_bytes, response_bytes = await self._exchange(message)
            _validate_response_envelope(response, request_id)
            error = _error_from_response(response, method)
            if error:
                raise error
            result = response.get("result")
            if not isinstance(result, dict):
                raise ProtocolError(f"MCP {method} returned a non-object result")
            version = self.protocol_version or LEGACY_VERSION
            _validate_complete_result(result, method, version)
            return MCPResponse(
                result=result,
                request_bytes=request_bytes,
                response_bytes=response_bytes,
                protocol_version=version,
                raw=response,
            )

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        assert self.process is not None and self.process.stdin is not None
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(payload) > self.max_message_bytes:
            raise ProtocolError("MCP stdio notification exceeds configured message limit")
        self.process.stdin.write(payload)
        await self.process.stdin.drain()

    async def list_tools(self) -> MCPResponse:
        return await self._request("tools/list", {})

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        tool_schema: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MCPResponse:
        del tool_schema  # x-mcp-header only applies to Streamable HTTP.
        params: dict[str, Any] = {"name": name, "arguments": arguments}
        if metadata:
            params["_meta"] = metadata
        return await self._request("tools/call", params)

    async def _restart(self) -> None:
        await self.close()
        self.protocol_version = None
        await self._start()

    async def close(self) -> None:
        process = self.process
        self.process = None
        self.protocol_version = None
        if process is not None and process.returncode is None:
            if process.stdin is not None:
                process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except TimeoutError:
                if os.name == "posix":
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGTERM)
                else:  # pragma: no cover - Windows CI covers this branch
                    process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=1.0)
                except TimeoutError:
                    if os.name == "posix":
                        with suppress(ProcessLookupError):
                            os.killpg(process.pid, signal.SIGKILL)
                    else:  # pragma: no cover
                        process.kill()
                    await process.wait()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            await asyncio.gather(self._stderr_task, return_exceptions=True)
            self._stderr_task = None


class MCPHTTPClient:
    def __init__(
        self,
        *,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        max_response_bytes: int = 2_000_000,
        max_request_bytes: int = 2_000_000,
        trust_env: bool = False,
        protocol_mode: str = "auto",
    ) -> None:
        self.url = url
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.max_response_bytes = max(1024, int(max_response_bytes))
        self.max_request_bytes = max(1024, int(max_request_bytes))
        if protocol_mode not in {"auto", "modern", "legacy"}:
            raise ValueError("protocol_mode must be auto, modern, or legacy")
        self.protocol_mode = protocol_mode
        self.protocol_version: str | None = None
        self.session_id: str | None = None
        self._next_id = 1
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=trust_env,
        )
        self._lock = asyncio.Lock()
        self._tool_schemas: dict[str, dict[str, Any]] = {}

    def _allocate_id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    async def _post(
        self,
        message: dict[str, Any],
        *,
        method: str,
        name: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], int, int, httpx.Headers, int]:
        payload = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(payload) > self.max_request_bytes:
            raise ProtocolError("MCP HTTP request exceeds configured size limit")
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            **self.headers,
        }
        version = self.protocol_version or MODERN_VERSION
        headers["MCP-Protocol-Version"] = version
        headers["Mcp-Method"] = method
        if name:
            headers["Mcp-Name"] = encode_header_value(name)
        if self.session_id and version != MODERN_VERSION:
            headers["Mcp-Session-Id"] = self.session_id
        if extra_headers:
            headers.update(extra_headers)

        async with self._client.stream(
            "POST", self.url, content=payload, headers=headers
        ) as response:
            response_headers = httpx.Headers(response.headers)
            status_code = response.status_code
            content_type = response.headers.get("content-type", "")
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > self.max_response_bytes:
                    raise ProtocolError(
                        "MCP HTTP response exceeds configured size limit",
                        status_code=status_code,
                    )
                chunks.append(chunk)
            body = b"".join(chunks)

        if status_code in {202, 204} and not body and "id" not in message:
            return {}, len(payload), 0, response_headers, status_code
        if status_code in {202, 204} and not body:
            raise ProtocolError("MCP request returned an empty response", status_code=status_code)
        if status_code >= 400 and not body:
            raise ProtocolError(f"MCP HTTP returned {status_code}", status_code=status_code)

        if "application/json" not in content_type and "text/event-stream" not in content_type:
            raise ProtocolError("MCP HTTP response has an unsupported content type")
        text = body.decode("utf-8", errors="strict")
        try:
            if "text/event-stream" in content_type:
                decoded = _decode_sse(text, message.get("id"))
            else:
                decoded = json.loads(text)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise ProtocolError(
                f"MCP HTTP returned invalid JSON with status {status_code}",
                status_code=status_code,
            ) from exc
        if not isinstance(decoded, dict):
            raise ProtocolError("MCP HTTP returned a non-object JSON-RPC message")
        return decoded, len(payload), len(body), response_headers, status_code

    async def connect(self) -> None:
        if self.protocol_version is not None:
            return
        if self.protocol_mode == "legacy":
            await self._legacy_initialize()
            return
        request_id = self._allocate_id()
        discover = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "server/discover",
            "params": {"_meta": _modern_meta()},
        }
        response, _, _, _, status = await self._post(discover, method="server/discover")
        _validate_response_envelope(response, request_id)
        result = response.get("result")
        if isinstance(result, dict) and isinstance(result.get("supportedVersions"), list):
            _validate_complete_result(result, "server/discover", MODERN_VERSION)
            versions = [str(item) for item in result["supportedVersions"]]
            if MODERN_VERSION not in versions:
                raise ProtocolError(
                    f"MCP server does not support {MODERN_VERSION}; supports {versions}",
                    code=UNSUPPORTED_PROTOCOL_VERSION,
                    status_code=status,
                    data={"supported": versions},
                )
            self.protocol_version = MODERN_VERSION
            return

        error = response.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            if code == UNSUPPORTED_PROTOCOL_VERSION:
                data = error.get("data")
                supported = data.get("supported", []) if isinstance(data, dict) else []
                if MODERN_VERSION in supported:
                    self.protocol_version = MODERN_VERSION
                    return
                raise ProtocolError(
                    f"MCP server rejected protocol version; supports {supported}",
                    code=UNSUPPORTED_PROTOCOL_VERSION,
                    status_code=status,
                    data=data,
                )
            # A 404 with a JSON-RPC method-not-found body is a recognized modern
            # response. A legacy fallback is only safe for era-ambiguous responses.
            if status == 404 and code == -32601:
                raise ProtocolError(
                    "MCP endpoint speaks modern HTTP but does not implement server/discover",
                    code=-32601,
                    status_code=status,
                    data=error.get("data"),
                )
            if status not in {200, 400, 404, 405}:
                raise _error_from_response(response, "server/discover", status_code=status)  # type: ignore[misc]

        if self.protocol_mode == "auto" and isinstance(error, dict) and error.get("code") == -32601:
            await self._legacy_initialize()
            return
        raise ProtocolError("MCP modern discovery did not return a supported protocol")

    async def _legacy_initialize(self) -> None:
        self.protocol_version = LEGACY_VERSION
        init_id = self._allocate_id()
        initialize = {
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {
                "protocolVersion": LEGACY_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "aeep", "version": __version__},
            },
        }
        response, _, _, headers, status = await self._post(initialize, method="initialize")
        _validate_response_envelope(response, init_id)
        error = _error_from_response(response, "initialize", status_code=status)
        if error:
            raise error
        self.session_id = headers.get("Mcp-Session-Id")
        notification = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        await self._post(notification, method="notifications/initialized")

    async def _request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        name: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> MCPResponse:
        async with self._lock:
            await self.connect()
            request_params = dict(params)
            if self.protocol_version == MODERN_VERSION:
                request_params["_meta"] = {
                    **(
                        request_params.get("_meta", {})
                        if isinstance(request_params.get("_meta"), dict)
                        else {}
                    ),
                    **_modern_meta(),
                }
            request_id = self._allocate_id()
            message = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": request_params,
            }
            response, request_bytes, response_bytes, _, status = await self._post(
                message,
                method=method,
                name=name,
                extra_headers=extra_headers,
            )
            _validate_response_envelope(response, request_id)
            error = _error_from_response(response, method, status_code=status)
            if error:
                raise error
            result = response.get("result")
            if not isinstance(result, dict):
                raise ProtocolError(f"MCP {method} returned a non-object result")
            version = self.protocol_version or MODERN_VERSION
            _validate_complete_result(result, method, version)
            return MCPResponse(
                result=result,
                request_bytes=request_bytes,
                response_bytes=response_bytes,
                protocol_version=version,
                raw=response,
            )

    def _filter_and_cache_tools(self, response: MCPResponse) -> MCPResponse:
        tools = response.result.get("tools", [])
        if not isinstance(tools, list):
            raise ProtocolError("MCP tools/list returned a non-list tools field")
        valid: list[dict[str, Any]] = []
        self._tool_schemas.clear()
        for tool in tools:
            if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                continue
            try:
                tool_header_bindings(tool)
            except ProtocolError as exc:
                warnings.warn(
                    f"excluding invalid MCP tool {tool.get('name')!r}: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue
            valid.append(tool)
            self._tool_schemas[str(tool["name"])] = tool
        response.result["tools"] = valid
        return response

    async def list_tools(self) -> MCPResponse:
        return self._filter_and_cache_tools(await self._request("tools/list", {}))

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        tool_schema: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MCPResponse:
        schema = tool_schema or self._tool_schemas.get(name)
        headers = tool_parameter_headers(schema, arguments) if schema is not None else {}
        params: dict[str, Any] = {"name": name, "arguments": arguments}
        if metadata:
            params["_meta"] = metadata
        return await self._request(
            "tools/call",
            params,
            name=name,
            extra_headers=headers,
        )

    async def close(self) -> None:
        await self._client.aclose()
