"""Bounded stdio client and managed-host adapter for Codex App Server."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any, TypeAlias

from ..capacity import CapacityObservation, principal_digest
from ..errors import ConfigurationError
from ..models import ExecutionStatus, RawExecution, SideEffect
from .base import HostModel, HostProbe, HostProbeStatus, ManagedHostExecutionContext
from .codex_accounting import rate_limit_observation, turn_accounting
from .codex_models import (
    CodexAccountObservation,
    CodexTurnResult,
    sanitize_account,
    usage_telemetry,
)

JsonObject: TypeAlias = dict[str, Any]
NotificationHandler: TypeAlias = Callable[[str, JsonObject], None]
ApprovalHandler: TypeAlias = Callable[[str, JsonObject, str, SideEffect], bool]

_APPROVAL_METHODS = {
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
}
_TERMINAL_METHOD = "turn/completed"


class CodexProtocolError(RuntimeError):
    pass


class CodexRequestError(RuntimeError):
    def __init__(self, method: str, error: object) -> None:
        super().__init__(f"Codex App Server request {method!r} failed")
        self.method = method
        self.error = error


class CodexAppServerTransport:
    """One persistent JSONL subprocess with strict bounds and request matching."""

    def __init__(
        self,
        argv: tuple[str, ...],
        *,
        environment_allowlist: tuple[str, ...] = (),
        cwd: str | None = None,
        max_message_bytes: int = 1_048_576,
        max_stderr_bytes: int = 65_536,
        request_timeout: float = 30,
    ) -> None:
        if not argv or not Path(argv[0]).is_absolute():
            raise ConfigurationError("Codex App Server executable must be an absolute argv path")
        if any(not part or "\x00" in part for part in argv):
            raise ConfigurationError("Codex App Server argv entries must be non-empty and NUL-free")
        self.argv = argv
        self.environment_allowlist = environment_allowlist
        self.cwd = cwd
        self.max_message_bytes = max_message_bytes
        self.max_stderr_bytes = max_stderr_bytes
        self.request_timeout = request_timeout
        self._process: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future[JsonObject]] = {}
        self._response_ids: set[int] = set()
        self._expired_ids: set[int] = set()
        self._server_request_ids: set[str | int] = set()
        self._subscribers: set[NotificationHandler] = set()
        self._next_id = 1
        self._write_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task[None]] = []
        self._fatal: BaseException | None = None
        self._closing = False
        self._started = False
        self.stderr = bytearray()
        self.stderr_truncated = False
        self.protocol_version: str | None = None
        self.approval_handler: ApprovalHandler | None = None
        self.approval_ceiling = SideEffect.NONE
        self.approval_digests: list[str] = []

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None and self._fatal is None

    async def start(self) -> None:
        self._raise_if_failed()
        if self.running and self._started:
            return
        async with self._start_lock:
            if self.running and self._started:
                return
            if self._process is not None:
                await self.close()
            environment = {
                key: os.environ[key]
                for key in self.environment_allowlist
                if key in os.environ
            }
            self._fatal = None
            self._closing = False
            self._process = await asyncio.create_subprocess_exec(
                *self.argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
                env=environment,
                limit=self.max_message_bytes + 1,
            )
            self._tasks = [
                asyncio.create_task(self._read_stdout()),
                asyncio.create_task(self._read_stderr()),
                asyncio.create_task(self._watch_process()),
            ]
            self._started = True
            response = await self._request_started(
                "initialize",
                {
                    "clientInfo": {
                        "name": "aeep-agent-router",
                        "title": "AEEP",
                        "version": "0.7",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            )
            user_agent = response.get("userAgent")
            self.protocol_version = (
                user_agent[:100] if isinstance(user_agent, str) else "app-server-v2"
            )
            await self.notify("initialized", {})

    async def request(
        self, method: str, params: JsonObject | None = None, *, timeout: float | None = None
    ) -> JsonObject:
        await self.start()
        return await self._request_started(method, params or {}, timeout=timeout)

    async def _request_started(
        self, method: str, params: JsonObject, *, timeout: float | None = None
    ) -> JsonObject:
        self._raise_if_failed()
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[JsonObject] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._write({"method": method, "id": request_id, "params": params})
            return await asyncio.wait_for(
                asyncio.shield(future), timeout=timeout or self.request_timeout
            )
        except TimeoutError:
            self._pending.pop(request_id, None)
            self._expired_ids.add(request_id)
            raise
        except BaseException:
            self._pending.pop(request_id, None)
            raise

    async def notify(self, method: str, params: JsonObject) -> None:
        self._raise_if_failed()
        await self._write({"method": method, "params": params})

    def subscribe(self, handler: NotificationHandler) -> Callable[[], None]:
        self._subscribers.add(handler)
        return lambda: self._subscribers.discard(handler)

    async def _write(self, message: JsonObject) -> None:
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
        if len(encoded) > self.max_message_bytes:
            raise CodexProtocolError("outbound App Server frame exceeds configured limit")
        process = self._process
        if process is None or process.stdin is None or process.returncode is not None:
            raise CodexProtocolError("Codex App Server is not running")
        async with self._write_lock:
            process.stdin.write(encoded)
            await process.stdin.drain()

    async def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            while True:
                try:
                    line = await process.stdout.readline()
                except (ValueError, asyncio.LimitOverrunError) as exc:
                    raise CodexProtocolError("oversized App Server frame") from exc
                if not line:
                    return
                if len(line) > self.max_message_bytes:
                    raise CodexProtocolError("oversized App Server frame")
                try:
                    message = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise CodexProtocolError("malformed App Server frame") from exc
                if not isinstance(message, dict):
                    raise CodexProtocolError("App Server frame must be an object")
                await self._dispatch(message)
        except BaseException as exc:
            if not self._closing:
                self._fail(exc)

    async def _dispatch(self, message: JsonObject) -> None:
        method = message.get("method")
        if isinstance(method, str):
            params = message.get("params")
            payload = params if isinstance(params, dict) else {}
            if "id" in message:
                await self._handle_server_request(message["id"], method, payload)
            else:
                for subscriber in tuple(self._subscribers):
                    subscriber(method, payload)
            return
        request_id = message.get("id")
        if not isinstance(request_id, int) or isinstance(request_id, bool):
            raise CodexProtocolError("App Server response has an invalid request ID")
        if request_id in self._response_ids:
            raise CodexProtocolError("duplicate App Server response ID")
        if request_id in self._expired_ids:
            self._expired_ids.remove(request_id)
            return
        future = self._pending.pop(request_id, None)
        if future is None:
            raise CodexProtocolError("App Server response has no pending request")
        self._response_ids.add(request_id)
        error = message.get("error")
        if error is not None:
            future.set_exception(CodexRequestError("request", error))
            return
        result = message.get("result", {})
        if not isinstance(result, dict):
            future.set_exception(CodexProtocolError("App Server result must be an object"))
            return
        future.set_result(result)

    async def _handle_server_request(
        self, request_id: object, method: str, params: JsonObject
    ) -> None:
        if not isinstance(request_id, str | int) or isinstance(request_id, bool):
            raise CodexProtocolError("App Server request has an invalid ID")
        if request_id in self._server_request_ids:
            raise CodexProtocolError("duplicate App Server server-request ID")
        self._server_request_ids.add(request_id)
        if method not in _APPROVAL_METHODS:
            await self._write(
                {
                    "id": request_id,
                    "error": {"code": -32601, "message": "method not supported by AEEP"},
                }
            )
            return
        required = _approval_side_effect(method, params)
        request_digest = _message_digest({"method": method, "params": params})
        approved = False
        if required.rank <= self.approval_ceiling.rank and self.approval_handler is not None:
            decision = self.approval_handler(method, params, request_digest, required)
            if inspect.isawaitable(decision):
                raise CodexProtocolError("approval handler must be synchronous")
            approved = decision is True
        response = {"decision": "accept" if approved else "decline"}
        response_digest = _message_digest(response)
        self.approval_digests.extend((request_digest, response_digest))
        await self._write({"id": request_id, "result": response})

    async def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        while chunk := await process.stderr.read(4096):
            remaining = self.max_stderr_bytes - len(self.stderr)
            if remaining > 0:
                self.stderr.extend(chunk[:remaining])
            if len(chunk) > remaining:
                self.stderr_truncated = True

    async def _watch_process(self) -> None:
        process = self._process
        if process is None:
            return
        return_code = await process.wait()
        if not self._closing:
            self._fail(CodexProtocolError(f"Codex App Server exited with status {return_code}"))

    def _fail(self, error: BaseException) -> None:
        if self._fatal is None:
            self._fatal = error
        for future in self._pending.values():
            if not future.done():
                future.set_exception(self._fatal)
        self._pending.clear()
        process = self._process
        if process is not None and process.returncode is None:
            process.terminate()

    def _raise_if_failed(self) -> None:
        if self._fatal is not None:
            raise CodexProtocolError("Codex App Server transport failed") from self._fatal

    async def close(self) -> None:
        self._closing = True
        process = self._process
        if process is not None and process.stdin is not None and not process.stdin.is_closing():
            process.stdin.close()
            with suppress(BrokenPipeError):
                await process.stdin.wait_closed()
        if process is not None and process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=1)
            except TimeoutError:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=1)
                except TimeoutError:
                    process.kill()
                    await process.wait()
        current = asyncio.current_task()
        for task in self._tasks:
            if task is not current and not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(
                *(task for task in self._tasks if task is not current), return_exceptions=True
            )
        self._tasks.clear()
        self._process = None
        self._started = False
        self._pending.clear()


class CodexAppServerAdapter:
    """Official App Server adapter; Codex retains ownership of authentication."""

    adapter_id = "codex-app-server"

    def __init__(
        self,
        *,
        argv: tuple[str, ...],
        resource_id: str,
        principal_salt: bytes,
        environment_allowlist: tuple[str, ...] = (),
        cwd: str | None = None,
        max_message_bytes: int = 1_048_576,
        request_timeout: float = 30,
        approval_handler: ApprovalHandler | None = None,
    ) -> None:
        if not principal_salt:
            raise ConfigurationError("a principal HMAC salt is required")
        self.resource_id = resource_id
        self.principal_salt = principal_salt
        self.approval_handler = approval_handler
        self.transport = CodexAppServerTransport(
            argv,
            environment_allowlist=environment_allowlist,
            cwd=cwd,
            max_message_bytes=max_message_bytes,
            request_timeout=request_timeout,
        )
        self._account: CodexAccountObservation | None = None
        self._probe: HostProbe | None = None
        self._attempts: dict[str, tuple[str, str]] = {}
        self._execute_lock = asyncio.Lock()

    async def account(self) -> CodexAccountObservation:
        payload = await self.transport.request("account/read", {"refreshToken": False})
        account = payload.get("account")
        account_data = account if isinstance(account, dict) else {}
        principal = next(
            (
                value
                for key in ("id", "accountId", "email")
                if isinstance((value := account_data.get(key)), str) and value
            ),
            None,
        )
        digest = principal_digest(principal, salt=self.principal_salt) if principal else None
        observation = sanitize_account(payload, principal_digest=digest)
        if (
            self._account is not None
            and self._account.principal_digest is not None
            and observation.principal_digest != self._account.principal_digest
        ):
            self._probe = None
        self._account = observation
        return observation

    async def probe(self) -> HostProbe:
        try:
            await self.transport.start()
            account = await self.account()
            if not account.authenticated:
                self._probe = HostProbe(
                    adapter_id=self.adapter_id,
                    status=HostProbeStatus.AUTH_REQUIRED,
                    protocol_version=self.transport.protocol_version,
                    supported_features=("account/read",),
                    reason="Codex login is required",
                )
                return self._probe
            await self.list_models()
            await self.transport.request("account/rateLimits/read", {})
            features = [
                "account/read",
                "account/rateLimits/read",
                "model/list",
                "thread/start",
                "thread/resume",
                "turn/start",
                "turn/steer",
                "turn/interrupt",
            ]
            try:
                telemetry = await self.transport.request("account/usage/read", {})
                usage_telemetry(telemetry)
                features.append("account/usage/read")
            except CodexRequestError:
                pass
            self._probe = HostProbe(
                adapter_id=self.adapter_id,
                status=HostProbeStatus.READY,
                protocol_version=self.transport.protocol_version,
                supported_features=tuple(features),
            )
        except (OSError, TimeoutError, CodexProtocolError, CodexRequestError) as exc:
            self._probe = HostProbe(
                adapter_id=self.adapter_id,
                status=HostProbeStatus.UNSUPPORTED,
                protocol_version=self.transport.protocol_version,
                reason=type(exc).__name__,
            )
        return self._probe

    async def snapshot_capacity(self) -> CapacityObservation:
        payload = await self.transport.request("account/rateLimits/read", {})
        return rate_limit_observation(payload, resource_id=self.resource_id)

    async def list_models(self) -> list[HostModel]:
        models: list[HostModel] = []
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            params: JsonObject = {"includeHidden": False}
            if cursor is not None:
                params["cursor"] = cursor
            payload = await self.transport.request("model/list", params)
            page = payload.get("data")
            if not isinstance(page, list):
                raise CodexProtocolError("model/list omitted its data page")
            for raw in page:
                if not isinstance(raw, dict):
                    continue
                model_id = raw.get("model") or raw.get("id")
                if not isinstance(model_id, str) or not model_id or model_id in seen:
                    continue
                efforts = raw.get("supportedReasoningEfforts")
                reasoning = tuple(
                    str(item.get("reasoningEffort"))
                    for item in efforts
                    if isinstance(item, dict) and isinstance(item.get("reasoningEffort"), str)
                ) if isinstance(efforts, list) else ()
                modalities = raw.get("inputModalities")
                capabilities = tuple(
                    str(item) for item in modalities if isinstance(item, str)
                ) if isinstance(modalities, list) else ()
                models.append(
                    HostModel(
                        id=model_id,
                        capabilities=capabilities,
                        reasoning_efforts=reasoning,
                    )
                )
                seen.add(model_id)
            next_cursor = payload.get("nextCursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                break
            if next_cursor in seen:
                raise CodexProtocolError("model/list pagination cursor repeated")
            cursor = next_cursor
        return models

    async def execute(self, context: ManagedHostExecutionContext) -> RawExecution:
        async with self._execute_lock:
            started = time.monotonic()
            probe = await self.probe()
            if probe.status is not HostProbeStatus.READY:
                return RawExecution(
                    status=ExecutionStatus.REJECTED,
                    error_type=probe.status.value.upper(),
                    error_message=probe.reason,
                )
            models = await self.list_models()
            selected = _select_model(models, context)
            if selected is None:
                return RawExecution(
                    status=ExecutionStatus.REJECTED,
                    error_type="NO_COMPATIBLE_MODEL",
                    error_message="runtime model catalog has no compatible model",
                )
            effort = next(
                (
                    item
                    for item in context.config.reasoning_efforts
                    if item in selected.reasoning_efforts
                ),
                None,
            )
            cwd = _execution_cwd(context)
            ceiling = min(
                context.config.approval_ceiling,
                SideEffect(context.approved_side_effect),
                key=lambda value: value.rank,
            )
            self.transport.approval_handler = self.approval_handler
            self.transport.approval_ceiling = ceiling
            self.transport.approval_digests.clear()
            collector = _TurnCollector(max_output_bytes=context.config.max_message_bytes)
            unsubscribe = self.transport.subscribe(collector.handle)
            try:
                thread_params: JsonObject = {
                    "ephemeral": True,
                    "model": selected.id,
                    "approvalPolicy": "on-request",
                    "sandbox": _sandbox_mode(context.config.sandbox_policy),
                }
                if cwd is not None:
                    thread_params["cwd"] = cwd
                thread_response = await self.transport.request("thread/start", thread_params)
                thread = thread_response.get("thread")
                thread_id = thread.get("id") if isinstance(thread, dict) else None
                if not isinstance(thread_id, str) or not thread_id:
                    raise CodexProtocolError("thread/start omitted thread identity")
                collector.thread_id = thread_id
                actual_model = thread_response.get("model")
                collector.actual_model = (
                    actual_model if isinstance(actual_model, str) else selected.id
                )
                turn_params: JsonObject = {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": context.instruction}],
                    "model": selected.id,
                }
                if effort is not None:
                    turn_params["effort"] = effort
                if context.output_schema is not None:
                    turn_params["outputSchema"] = context.output_schema
                turn_response = await self.transport.request("turn/start", turn_params)
                turn = turn_response.get("turn")
                turn_id = turn.get("id") if isinstance(turn, dict) else None
                if not isinstance(turn_id, str) or not turn_id:
                    raise CodexProtocolError("turn/start omitted turn identity")
                collector.turn_id = turn_id
                self._attempts[context.attempt_id] = (thread_id, turn_id)
                result = await asyncio.wait_for(
                    asyncio.shield(collector.future), timeout=context.config.timeout_seconds
                )
                await asyncio.sleep(0)
                if collector.error is not None:
                    raise collector.error
                result = result.model_copy(
                    update={
                        "approval_digests": tuple(self.transport.approval_digests),
                    }
                )
            except TimeoutError:
                await self._interrupt_known(context.attempt_id)
                return RawExecution(
                    status=ExecutionStatus.TIMEOUT,
                    error_type="TIMEOUT",
                    error_message="Codex turn exceeded its configured deadline",
                )
            except (CodexProtocolError, CodexRequestError) as exc:
                return RawExecution(
                    status=ExecutionStatus.FAILED,
                    error_type="ProtocolError",
                    error_message=str(exc),
                )
            finally:
                unsubscribe()
                self.transport.approval_handler = None
                self.transport.approval_ceiling = SideEffect.NONE
            resources, accounting = turn_accounting(
                result.token_usage,
                model=result.actual_model,
                resource_pool=self.resource_id,
            )
            resources.latency_ms = (time.monotonic() - started) * 1000
            status = (
                ExecutionStatus.SUCCESS
                if result.status == "completed"
                else ExecutionStatus.TIMEOUT
                if result.status == "interrupted"
                else ExecutionStatus.FAILED
            )
            return RawExecution(
                status=status,
                output=result.output,
                resources=resources,
                accounting=accounting,
                error_type=None if status is ExecutionStatus.SUCCESS else "CODEX_TURN_FAILED",
                error_message=result.error,
                metadata={
                    "actual_model": result.actual_model,
                    "model_turn_count": 1,
                    "tool_call_count": result.tool_count,
                    "approval_evidence_digest": _message_digest(
                        {"digests": list(result.approval_digests)}
                    ) if result.approval_digests else None,
                    "thread_identity_digest": _message_digest({"thread_id": result.thread_id}),
                    "turn_identity_digest": _message_digest({"turn_id": result.turn_id}),
                },
            )

    async def interrupt(self, attempt_id: str) -> None:
        await self._interrupt_known(attempt_id)

    async def _interrupt_known(self, attempt_id: str) -> None:
        identity = self._attempts.get(attempt_id)
        if identity is None:
            return
        thread_id, turn_id = identity
        with suppress(CodexProtocolError, CodexRequestError, TimeoutError):
            await self.transport.request(
                "turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, timeout=2
            )

    async def login(self) -> JsonObject:
        """Start the official interactive flow; callers must keep this operator-only."""

        return await self.transport.request(
            "account/login/start",
            {"type": "chatgpt", "codexStreamlinedLogin": True},
        )

    async def close(self) -> None:
        await self.transport.close()


class _TurnCollector:
    def __init__(self, *, max_output_bytes: int) -> None:
        self.max_output_bytes = max_output_bytes
        self.thread_id: str | None = None
        self.turn_id: str | None = None
        self.actual_model: str | None = None
        self.token_usage: dict[str, int] | None = None
        self.output_parts: list[str] = []
        self.tool_count = 0
        self.terminal: tuple[str, dict[str, int] | None] | None = None
        self.error: CodexProtocolError | None = None
        self.future: asyncio.Future[CodexTurnResult] = asyncio.get_running_loop().create_future()

    def handle(self, method: str, params: JsonObject) -> None:
        if self.thread_id is not None and params.get("threadId") not in {None, self.thread_id}:
            return
        event_turn = params.get("turnId")
        if self.turn_id is not None and event_turn not in {None, self.turn_id}:
            return
        if method == "model/rerouted" and isinstance(params.get("toModel"), str):
            self.actual_model = params["toModel"]
        elif method == "thread/tokenUsage/updated":
            token_usage = params.get("tokenUsage")
            total = token_usage.get("total") if isinstance(token_usage, dict) else None
            parsed = _token_usage(total)
            if parsed is not None:
                if self.terminal is not None and self.terminal[1] != parsed:
                    self._reject("conflicting terminal token usage")
                    return
                self.token_usage = parsed
        elif method == "item/completed":
            item = params.get("item")
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "agentMessage" and isinstance(item.get("text"), str):
                    self.output_parts.append(item["text"])
                elif item_type in {"commandExecution", "fileChange", "mcpToolCall", "dynamicToolCall"}:
                    self.tool_count += 1
        elif method == _TERMINAL_METHOD:
            turn = params.get("turn")
            if not isinstance(turn, dict) or not isinstance(turn.get("status"), str):
                self._reject("turn/completed omitted terminal state")
                return
            status = turn["status"]
            marker = (status, self.token_usage)
            if self.terminal is not None:
                if self.terminal != marker:
                    self._reject("conflicting terminal events")
                else:
                    self._reject("duplicate terminal event")
                return
            self.terminal = marker
            output_text = "".join(self.output_parts)
            if len(output_text.encode()) > self.max_output_bytes:
                self._reject("Codex output exceeds configured message limit")
                return
            output: Any = output_text
            if output_text:
                with suppress(json.JSONDecodeError):
                    output = json.loads(output_text)
            error = turn.get("error")
            error_text = error.get("message") if isinstance(error, dict) else None
            if not self.future.done():
                self.future.set_result(
                    CodexTurnResult(
                        thread_id=str(params.get("threadId") or self.thread_id or "unknown"),
                        turn_id=str(turn.get("id") or self.turn_id or "unknown"),
                        status=status,
                        output=output,
                        actual_model=self.actual_model,
                        token_usage=self.token_usage,
                        tool_count=self.tool_count,
                        error=error_text if isinstance(error_text, str) else None,
                    )
                )

    def _reject(self, message: str) -> None:
        self.error = CodexProtocolError(message)
        if not self.future.done():
            self.future.set_exception(self.error)


def _select_model(
    models: list[HostModel], context: ManagedHostExecutionContext
) -> HostModel | None:
    constraints = context.config.model_constraints
    required = set(constraints.required_capabilities)
    candidates = [
        model
        for model in models
        if required.issubset(model.capabilities)
        and (
            constraints.minimum_context_tokens is None
            or (
                model.context_tokens is not None
                and model.context_tokens >= constraints.minimum_context_tokens
            )
        )
        and (
            not context.config.reasoning_efforts
            or any(item in model.reasoning_efforts for item in context.config.reasoning_efforts)
        )
    ]
    return sorted(candidates, key=lambda item: item.id)[0] if candidates else None


def _execution_cwd(context: ManagedHostExecutionContext) -> str | None:
    policy = context.config.working_directory_policy
    if policy == "fixed":
        return context.config.working_directory
    if policy == "manifest":
        return None
    return os.getcwd()


def _sandbox_mode(policy: str) -> str:
    return {
        "host_default": "read-only",
        "read_only": "read-only",
        "workspace_write": "workspace-write",
    }[policy]


def _approval_side_effect(method: str, params: Mapping[str, Any]) -> SideEffect:
    if method == "item/fileChange/requestApproval":
        return SideEffect.WRITE
    actions = params.get("commandActions")
    if isinstance(actions, list) and actions and all(
        isinstance(action, dict) and action.get("type") in {"read", "listFiles", "search"}
        for action in actions
    ):
        return SideEffect.READ
    return SideEffect.DESTRUCTIVE


def _token_usage(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    keys = (
        "inputTokens",
        "cachedInputTokens",
        "cacheWriteInputTokens",
        "outputTokens",
        "reasoningOutputTokens",
        "totalTokens",
    )
    result = {
        key: raw
        for key in keys
        if isinstance((raw := value.get(key, 0)), int) and not isinstance(raw, bool) and raw >= 0
    }
    return result if len(result) == len(keys) else None


def _message_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
