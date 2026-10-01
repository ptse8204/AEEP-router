"""Bounded stdio client and managed-host adapter for Codex App Server."""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import inspect
import json
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, TypeAlias

from pydantic import Field

from ..capacity import CapacityObservation, principal_digest
from ..errors import ConfigurationError, InputValidationError
from ..execution import (
    EventJournal,
    EventKind,
    ExecutionEvent,
    ExecutionHandle,
    ExecutorCapabilities,
    cancel_execution,
    execution_events,
    start_execution,
)
from ..models import (
    EvidenceStatus,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    ManagedHostExecutorConfig,
    RawExecution,
    SideEffect,
    StrictModel,
    new_id,
)
from .base import HostModel, HostProbe, HostProbeStatus, ManagedHostExecutionContext
from .codex_accounting import rate_limit_observation, turn_accounting
from .codex_invocation import (
    inventory,
    isolated_config,
    resolve_skill_name,
    verify_thread_inventory,
    worker_permissions,
)
from .codex_metrics import NOTIFICATION as METRICS_NOTIFICATION
from .codex_metrics import WORKER_PATH as METRICS_WORKER_PATH
from .codex_metrics import snapshot as metrics_snapshot
from .codex_metrics import validate_snapshot
from .codex_models import (
    CodexAccountObservation,
    CodexTurnResult,
    sanitize_account,
    usage_telemetry,
)
from .workers import ManagedWorkerBinding, binding_from_config

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


class AppServerOptions(StrictModel):
    experimental_api: bool = False
    catalog_metrics: bool = False
    expected_user_agent: str | None = Field(default=None, min_length=1, max_length=1000)


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
        executable_sha256: str | None = None,
        options: AppServerOptions | None = None,
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
        if executable_sha256 is not None and (
            len(executable_sha256) != 71
            or not executable_sha256.startswith("sha256:")
            or any(
                character not in "0123456789abcdef"
                for character in executable_sha256[7:]
            )
        ):
            raise ConfigurationError("Codex executable digest must be sha256 lowercase hex")
        self.options = options or AppServerOptions()
        self.executable_sha256 = executable_sha256
        executable = Path(self.argv[0])
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ConfigurationError("Codex App Server executable is not an executable file")
        if self.executable_sha256 is not None:
            digest = hashlib.sha256()
            with executable.open("rb") as stream:
                while chunk := stream.read(1_048_576):
                    digest.update(chunk)
            if f"sha256:{digest.hexdigest()}" != self.executable_sha256:
                raise ConfigurationError("Codex App Server executable digest mismatch")
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
        self._dynamic_tasks: set[asyncio.Task[None]] = set()
        self.dynamic_tool_handler: Callable[[JsonObject], Awaitable[JsonObject]] | None = None
        self.dynamic_tool_context: contextvars.Context | None = None
        self._fatal: BaseException | None = None
        self._failure_event = asyncio.Event()
        self._closing = False
        self._started = False
        self.stderr = bytearray()
        self.stderr_truncated = False
        self.protocol_version: str | None = None
        self.approval_handler: ApprovalHandler | None = None
        self.approval_observer: Callable[[str, bool | None], None] | None = None
        self.approval_ceiling = SideEffect.NONE
        self.approval_digests: list[str] = []
        self.metrics_scope: str | None = None
        self.catalog_metrics: JsonObject | None = None
        self.metrics_observer: Callable[[JsonObject], None] | None = None

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
            self._failure_event.clear()
            self.catalog_metrics = None
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
                        "version": "0.8",
                    },
                    "capabilities": {"experimentalApi": self.options.experimental_api},
                },
            )
            user_agent = response.get("userAgent")
            if self.options.expected_user_agent is not None and user_agent != self.options.expected_user_agent:
                raise CodexProtocolError("App Server version differs from the reviewed protocol binding")
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
        if method == METRICS_NOTIFICATION:
            if self.metrics_scope is None or "id" in message:
                raise CodexProtocolError("unconfigured catalog metrics relay")
            try:
                value = validate_snapshot(message.get("params"), self.metrics_scope)
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                raise CodexProtocolError("invalid catalog metrics snapshot") from exc
            if self.catalog_metrics is not None:
                prior = self.catalog_metrics
                if (prior['collector_closed'] or value['batches'] < prior['batches']
                        or value['rejected_batches'] < prior['rejected_batches']
                        or (prior['overflow'] and not value['overflow'])
                        or any(point not in value['observations'] for point in prior['observations'])):
                    raise CodexProtocolError("conflicting catalog metrics snapshot")
            self.catalog_metrics = value
            if self.metrics_observer is not None:
                self.metrics_observer(value)
            return
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
        if method == "item/tool/call" and self.dynamic_tool_handler is not None:
            if self._dynamic_tasks:
                await self._write({"id": request_id, "error": {"code": -32602, "message": "dynamic task call already pending"}})
                return
            handler = self.dynamic_tool_handler
            task = asyncio.create_task(self._answer_dynamic_tool(request_id, params, handler),
                context=self.dynamic_tool_context.copy() if self.dynamic_tool_context is not None else None)
            self._dynamic_tasks.add(task)
            task.add_done_callback(self._dynamic_tasks.discard)
            return
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
        if self.approval_observer is not None:
            self.approval_observer(request_digest, None)
        if required.rank <= self.approval_ceiling.rank and self.approval_handler is not None:
            decision = self.approval_handler(method, params, request_digest, required)
            if inspect.isawaitable(decision):
                raise CodexProtocolError("approval handler must be synchronous")
            approved = decision is True
        if self.approval_observer is not None:
            self.approval_observer(request_digest, approved)
        response = {"decision": "accept" if approved else "decline"}
        response_digest = _message_digest(response)
        self.approval_digests.extend((request_digest, response_digest))
        await self._write({"id": request_id, "result": response})

    async def _answer_dynamic_tool(self, request_id: str | int, params: JsonObject,
                                   handler: Callable[[JsonObject], Awaitable[JsonObject]]) -> None:
        try:
            result = await handler(params)
            await self._write({"id": request_id, "result": result})
        except asyncio.CancelledError:
            raise
        except (ConfigurationError, InputValidationError, ValueError, TypeError, TimeoutError):
            with suppress(CodexProtocolError, BrokenPipeError):
                await self._write({"id": request_id, "error": {"code": -32602, "message": "dynamic task call rejected"}})
        except BaseException:
            self._fail(CodexProtocolError("dynamic task callback failed"))

    async def cancel_dynamic_tools(self) -> None:
        self.dynamic_tool_handler = None
        self.dynamic_tool_context = None
        tasks = tuple(self._dynamic_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=3)
            for task in done:
                if not task.cancelled():
                    task.exception()
            if pending:
                raise CodexProtocolError("dynamic task cleanup unconfirmed")
        self._dynamic_tasks.clear()

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
        self._failure_event.set()
        for task in tuple(self._dynamic_tasks):
            task.cancel()
        process = self._process
        if process is not None and process.returncode is None:
            process.terminate()

    def _raise_if_failed(self) -> None:
        if self._fatal is not None:
            raise CodexProtocolError("Codex App Server transport failed") from self._fatal

    async def close(self) -> None:
        cleanup_error = None
        try:
            await self.cancel_dynamic_tools()
        except CodexProtocolError as exc:
            cleanup_error = exc
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
        if self.metrics_scope is not None and self._tasks:
            # Drain the relay's final bounded snapshot before cancelling readers.
            with suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(self._tasks[0]), timeout=.5)
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
        if cleanup_error is not None:
            raise cleanup_error


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
        executable_sha256: str | None = None,
        approval_handler: ApprovalHandler | None = None,
        dynamic_tools_factory: Callable[[ManagedHostExecutionContext, Any], Any] | None = None,
        options: AppServerOptions | None = None,
    ) -> None:
        if not principal_salt:
            raise ConfigurationError("a principal HMAC salt is required")
        self.resource_id = resource_id
        self.principal_salt = principal_salt
        self.approval_handler = approval_handler
        self.dynamic_tools_factory = dynamic_tools_factory
        self.transport = CodexAppServerTransport(
            argv,
            environment_allowlist=environment_allowlist,
            cwd=cwd,
            max_message_bytes=max_message_bytes,
            request_timeout=request_timeout,
            executable_sha256=executable_sha256,
            options=options,
        )
        self._account: CodexAccountObservation | None = None
        self._probe: HostProbe | None = None
        self._attempts: dict[str, tuple[str, str]] = {}
        self._execute_lock = asyncio.Lock()
        self._worker_execute_lock = asyncio.Lock()
        self._journals: dict[str, EventJournal] = {}
        self._worker: ManagedWorkerBinding | None = None
        self._worker_process_id: str | None = None
        self._worker_security: TemporaryDirectory[str] | None = None
        self._configured_process: str | None = None

    def capabilities(self) -> ExecutorCapabilities:
        return ExecutorCapabilities(
            adapter=self.adapter_id, version="1", support_status="experimental",
            features={"execution": "supported", "structured_output": "supported",
                      "usage": "supported", "identity": "supported",
                      "fresh_worker": "supported" if self._worker is not None else "unknown",
                      "input_tree": "supported" if self._worker is not None else "unsupported",
                      "reused_worker": "unsupported",
                      "cancellation": "unknown", "isolation": "unknown"},
        )

    @classmethod
    def from_executor(
        cls,
        spec: ExecutorSpec,
        *,
        principal_salt: bytes,
        manifest_directory: Path | None = None,
    ) -> CodexAppServerAdapter:
        if spec.kind is not ExecutorKind.MANAGED_HOST or spec.resource_pool is None:
            raise ConfigurationError("Codex adapter requires a managed-host resource route")
        config = spec.managed_host_config()
        if config.adapter_id != cls.adapter_id and not config.adapter_id.startswith(cls.adapter_id + ":"):
            raise ConfigurationError("managed-host route does not select Codex App Server")
        cwd = (
            config.working_directory
            if config.working_directory_policy == "fixed"
            else str(manifest_directory)
            if config.working_directory_policy == "manifest" and manifest_directory is not None
            else None
        )
        worker = binding_from_config(config.managed_worker)
        worker_process_id = new_id("host-worker")
        options = AppServerOptions.model_validate(config.adapter_options or {})
        arguments = config.argv[1:]
        metrics_scope = None
        if options.catalog_metrics:
            expected = hashlib.sha256(Path(__file__).with_name('codex_metrics.py').read_bytes()).hexdigest()
            if (worker is None or not arguments or arguments[0] != 'app-server'
                    or (worker.reviewed_files or {}).get(METRICS_WORKER_PATH) != expected):
                raise ConfigurationError('catalog metrics require the exact reviewed collector in an immutable worker')
            metrics_scope = 'aeep-metrics-' + hashlib.sha256(worker_process_id.encode()).hexdigest()[:32]
            arguments = ('--aeep-catalog-metrics=' + metrics_scope, *arguments)
        if worker is not None and (config.argv[0] != worker.binary or config.environment_allowlist):
            raise ConfigurationError("worker binding requires its exact binary and no inherited host environment")
        security = TemporaryDirectory(prefix="aeep-worker-security-") if worker is not None and worker.seccomp_profile is not None else None
        security_path = worker.prepare_security(Path(security.name)) if worker is not None and security is not None else None
        adapter = cls(
            argv=worker.argv(arguments, execution_id=worker_process_id, security_path=security_path) if worker else config.argv,
            resource_id=spec.resource_pool,
            principal_salt=principal_salt,
            environment_allowlist=config.environment_allowlist,
            cwd=None if worker else cwd,
            max_message_bytes=config.max_message_bytes,
            request_timeout=min(30, config.timeout_seconds),
            executable_sha256=None if worker else config.executable_sha256,
            options=options,
        )
        adapter._configured_process = config.process_binding()
        adapter.adapter_id = config.adapter_id
        adapter.transport.metrics_scope = metrics_scope
        adapter._worker = worker
        adapter._worker_process_id = worker_process_id
        adapter._worker_security = security
        return adapter

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

    async def inventory(self) -> JsonObject:
        return await inventory(self.transport, self.transport.cwd)

    async def list_models(self) -> list[HostModel]:
        models: list[HostModel] = []
        cursor: str | None = None
        seen: set[str] = set()
        cursors: set[str] = set()
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
            if next_cursor in seen or next_cursor in cursors or len(cursors) >= 100:
                raise CodexProtocolError("model/list pagination cursor repeated")
            cursors.add(next_cursor)
            cursor = next_cursor
        return models

    async def resolve_identity(self, config: ManagedHostExecutorConfig) -> str | None:
        account = await self.account()
        selected = _select_model_config(await self.list_models(), config)
        if not account.authenticated or not account.principal_digest or selected is None:
            return None
        return self._runtime_digest(config, selected.id)

    def _runtime_digest(self, config: ManagedHostExecutorConfig, model: str) -> str | None:
        if self._account is None or not self._account.principal_digest:
            return None
        return _message_digest({
            "purpose": "aeep-host-runtime-v1", "adapter": self.adapter_id,
            "adapter_implementation": hashlib.sha256(Path(__file__).read_bytes() + Path(__file__).with_name("codex_invocation.py").read_bytes()).hexdigest(),
            "protocol": self.transport.protocol_version, "model": model,
            "principal": self._account.principal_digest,
            "config": config.model_dump(mode="json"),
            "cwd": "/workspace" if self._worker else config.working_directory if config.working_directory_policy == "fixed" else self.transport.cwd if config.working_directory_policy == "manifest" else os.getcwd(),
        }).removeprefix("sha256:")

    async def start(self, context: ManagedHostExecutionContext) -> ExecutionHandle:
        async def run(journal: EventJournal) -> RawExecution:
            if context.attempt_id in self._journals:
                raise ConfigurationError("execution attempt is already active")
            self._journals[context.attempt_id] = journal
            try:
                raw = await self.execute(context)
                if raw.accounting.model_usage or raw.accounting.subscription_usage:
                    journal.append("usage.reported", "turn-usage", accounting=raw.accounting, accounting_mode="cumulative")
                return raw
            finally:
                self._journals.pop(context.attempt_id, None)
        return start_execution(context.attempt_id, self.adapter_id, run,
                               lambda: self.interrupt(context.attempt_id))

    def events(self, handle: ExecutionHandle) -> AsyncIterator[ExecutionEvent]:
        return execution_events(handle)

    async def cancel(self, handle: ExecutionHandle) -> None:
        await cancel_execution(handle)

    async def execute(self, context: ManagedHostExecutionContext) -> RawExecution:
        if self._configured_process is not None and context.config.process_binding() != self._configured_process:
            return RawExecution(status=ExecutionStatus.REJECTED, error_type="CONFIGURATION_REJECTED")
        if self._worker is not None:
            # Production uses the same fresh-process condition as assessment.
            # Serialize cleanup with dispatch; closing a transport alone does
            # not confirm that its container and descendants stopped.
            async with self._worker_execute_lock:
                started = time.monotonic()
                journal = self._journals.get(context.attempt_id)
                if journal is not None and self.transport.metrics_scope is not None:
                    def observe_metrics(value: JsonObject) -> None:
                        digest = _message_digest(value).removeprefix('sha256:')
                        journal.append('message.received', 'catalog:' + digest, action_digest=digest)
                    self.transport.metrics_observer = observe_metrics
                try:
                    raw = await self._execute(replace(context, workspace="/workspace"))
                    if raw.status is ExecutionStatus.SUCCESS and context.config.artifact is not None:
                        artifact = context.config.artifact
                        try:
                            result = await self._worker.artifact(
                                self._worker_process_id or "", name=artifact.output_name, limit=artifact.max_bytes,
                                timeout=max(0.001, context.config.timeout_seconds - (time.monotonic() - started)))
                            raw.output = {artifact.output_field: result["data"]}
                            raw.metadata["artifact_sha256"] = result["sha256"]
                            raw.metadata["artifact_bytes"] = result["size"]
                        except ConfigurationError:
                            raw.status = ExecutionStatus.FAILED
                            raw.output = None
                            raw.error_type = "WORKER_ARTIFACT_FAILED"
                        raw.resources.latency_ms = (time.monotonic() - started) * 1000
                    raw.metadata["worker_digest"] = self._worker.digest()
                finally:
                    try:
                        await self.transport.close()
                    finally:
                        self.transport.metrics_observer = None
                        cleaned = await self._worker.cleanup(self._worker_process_id) if self._worker_process_id else False
                if self.transport.metrics_scope is not None:
                    raw.metadata['catalog_metrics'] = self.transport.catalog_metrics or metrics_snapshot(self.transport.metrics_scope)
                    # Injection and catalog counts are supporting observations.
                    # They cannot prove candidate-specific exposure or non-use.
                    raw.metadata['capability_discovery'] = dict.fromkeys(('exposed', 'retrieved', 'invoked'))
                    raw.resources.latency_ms = (time.monotonic() - started) * 1000
                raw.metadata['worker_cleanup_confirmed'] = cleaned
                if not cleaned:
                    raw.status = ExecutionStatus.FAILED
                    raw.error_type = 'WORKER_CLEANUP_UNCONFIRMED'
                return raw
        if context.config.worker_workspace == "temporary":
            # A fresh directory prevents cross-case state reuse. It is not a
            # filesystem sandbox: the host boundary is verified separately.
            with TemporaryDirectory(prefix="aeep-worker-") as workspace:
                resolved = await asyncio.to_thread(Path(workspace).resolve)
                return await self._execute(replace(context, workspace=str(resolved)))
        return await self._execute(context)

    async def _execute(self, context: ManagedHostExecutionContext) -> RawExecution:
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
            runtime_digest = self._runtime_digest(context.config, selected.id)
            if context.expected_runtime_digest is not None and runtime_digest != context.expected_runtime_digest:
                return RawExecution(status=ExecutionStatus.REJECTED, error_type="HOST_IDENTITY_DRIFT")
            cwd = context.workspace or _execution_cwd(context)
            ceiling = min(
                context.config.approval_ceiling,
                SideEffect(context.approved_side_effect),
                key=lambda value: value.rank,
            )
            self.transport.approval_handler = self.approval_handler
            self.transport.approval_ceiling = ceiling
            self.transport.approval_digests.clear()
            journal = self._journals.get(context.attempt_id)
            if journal is not None:
                def observe_approval(digest: str, decision: bool | None) -> None:
                    kind: EventKind = "permission.requested" if decision is None else "permission.granted" if decision else "permission.denied"
                    journal.append(kind, f"{kind}:{digest}", action_digest=digest.removeprefix("sha256:"))
                self.transport.approval_observer = observe_approval
            collector = _TurnCollector(max_output_bytes=context.config.max_message_bytes, journal=journal)
            unsubscribe = self.transport.subscribe(collector.handle)
            boundary_reference = None
            dynamic_session = None
            dynamic_cleanup_unconfirmed = False
            raw = None
            try:
                thread_params: JsonObject = {
                    "ephemeral": True,
                    "model": selected.id,
                    "approvalPolicy": "on-request",
                    "sandbox": _sandbox_mode(context.config.sandbox_policy),
                }
                if self.transport.metrics_scope is not None:
                    thread_params["serviceName"] = self.transport.metrics_scope
                if cwd is not None:
                    thread_params["cwd"] = cwd
                invocation = context.config.invocation
                if invocation is not None:
                    catalog = await inventory(self.transport, cwd)
                    collector.advertised_inventory_digest = _message_digest(catalog)
                    invocation = resolve_skill_name(catalog, invocation)
                    verified_skill = bool(self._worker and invocation.skill_path
                        and (self._worker.reviewed_files or {}).get(invocation.skill_path) == invocation.skill_sha256)
                    thread_params["config"] = isolated_config(catalog, invocation, verified_worker_skill=verified_skill,
                        reviewed_worker_files=(self._worker.reviewed_files or {}) if self._worker else None)
                if context.workspace is not None:
                    permission_profile = self._worker.permissions_profile if self._worker is not None else None
                    thread_params.pop("sandbox")
                    thread_params["permissions"] = permission_profile or "aeep_assessment"
                    thread_params["approvalPolicy"] = "never"
                    thread_params["approvalsReviewer"] = "user"
                    if permission_profile is None:
                        config_overrides = thread_params.setdefault("config", {})
                        config_overrides.update(worker_permissions(writable=context.config.sandbox_policy == "workspace_write", skill_path=invocation.skill_path if invocation is not None and invocation.mode == "skill" else None))
                dynamic_digest = invocation.dynamic_tools_digest if invocation is not None else None
                if dynamic_digest is not None:
                    assert invocation is not None
                    from .codex_dynamic_tools import CodexDynamicTools, DynamicToolSession
                    if (self._worker is None or self.dynamic_tools_factory is None
                            or not self.transport.options.experimental_api):
                        raise ConfigurationError("environment verification unavailable: dynamic task composition missing")
                    binding = self.dynamic_tools_factory(context, self)
                    if not isinstance(binding, CodexDynamicTools):
                        raise ConfigurationError("invalid operator dynamic task binding")
                    dynamic_session = DynamicToolSession(binding, worker_digest=self._worker.digest(),
                        expected_digest=dynamic_digest, approved_side_effect=ceiling,
                        max_bytes=context.config.max_message_bytes - 512,
                        deadline=asyncio.get_running_loop().time() + context.config.timeout_seconds,
                        outer_attempt_id=context.attempt_id, journal=journal)
                    if invocation.mode == "dynamic_tool" and (invocation.server != binding.namespace
                            or binding.inventory().get(f"dynamic:{invocation.server}:{invocation.tool}") != invocation.tool_sha256):
                        raise ConfigurationError("dynamic candidate target differs from reviewed declarations")
                    thread_params["dynamicTools"] = binding.declarations()
                    self.transport.dynamic_tool_handler = dynamic_session.call
                    self.transport.dynamic_tool_context = contextvars.copy_context()
                elif self.dynamic_tools_factory is not None:
                    raise ConfigurationError("environment verification unavailable: dynamic task composition is unbound")
                thread_response = await self.transport.request("thread/start", thread_params)
                if context.workspace is not None:
                    profile = thread_response.get("activePermissionProfile")
                    if (thread_response.get("cwd") != cwd or thread_response.get("approvalPolicy") != "never"
                        or thread_response.get("approvalsReviewer") != "user" or not isinstance(profile, dict)
                        or profile.get("id") != thread_params["permissions"] or profile.get("extends") is not None):
                        raise ConfigurationError("environment verification unavailable: worker permissions were not acknowledged")
                thread = thread_response.get("thread")
                thread_id = thread.get("id") if isinstance(thread, dict) else None
                if not isinstance(thread_id, str) or not thread_id:
                    raise CodexProtocolError("thread/start omitted thread identity")
                collector.thread_id = thread_id
                if dynamic_session is not None:
                    dynamic_session.bind_thread(thread_id)
                actual_model = thread_response.get("model")
                collector.actual_model = (
                    actual_model if isinstance(actual_model, str) else selected.id
                )
                if invocation is not None:
                    tool = await verify_thread_inventory(self.transport, thread_id, invocation)
                boundary_reference = context.invocation_check() if context.invocation_check is not None else None
                if context.expected_runtime_digest is not None and (invocation is not None or context.invocation_check is not None) and (
                    self._worker is None or not isinstance(boundary_reference, str)
                    or len(boundary_reference) != 64 or any(c not in "0123456789abcdef" for c in boundary_reference)
                ):
                    raise ConfigurationError("environment verification unavailable: current verified worker boundary is required")
                if invocation is not None and invocation.mode == "mcp_tool":
                    from .codex_invocation import call_mcp
                    raw = await call_mcp(self.transport, context, thread_id, tool, started)
                    raw.metadata["host_runtime_digest"] = runtime_digest
                    if boundary_reference is not None:
                        raw.metadata["boundary_digest"] = boundary_reference
                    return raw
                if context.config.input_tree is not None:
                    files = context.request.input.get("files")
                    if self._worker is None or self._worker_process_id is None or not isinstance(files, list):
                        raise ConfigurationError("worker input tree unavailable")
                    await self._worker.artifact(self._worker_process_id, name="case-tree", limit=100000,
                        files=files, timeout=max(0.001, context.config.timeout_seconds - (time.monotonic() - started)))
                if context.config.artifact is not None:
                    artifact = context.config.artifact
                    data = context.request.input.get(artifact.input_field)
                    if self._worker is None or self._worker_process_id is None or not isinstance(data, str):
                        raise ConfigurationError("worker artifact input unavailable")
                    await self._worker.artifact(self._worker_process_id, name=artifact.input_name,
                        limit=artifact.max_bytes, data=data,
                        timeout=max(0.001, context.config.timeout_seconds - (time.monotonic() - started)))
                turn_params: JsonObject = {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": context.instruction}],
                    "model": selected.id,
                }
                if invocation is not None and invocation.mode == "skill" and invocation.exposure != "optional":
                    turn_params["input"][0]["text"] = f"${invocation.skill_name} {context.instruction}"
                    turn_params["input"].append({"type": "skill", "name": invocation.skill_name, "path": invocation.skill_path})
                if invocation is not None and invocation.mode == "dynamic_tool" and invocation.exposure != "optional":
                    turn_params["input"][0]["text"] = f"Use {invocation.server}.{invocation.tool} for this task. {context.instruction}"
                if effort is not None:
                    turn_params["effort"] = effort
                if context.config.artifact is not None:
                    turn_params["outputSchema"] = {"type": "object", "properties": {"completed": {"type": "boolean"}},
                                                   "required": ["completed"], "additionalProperties": False}
                elif context.output_schema is not None:
                    turn_params["outputSchema"] = context.output_schema
                if context.invocation_check is not None and context.invocation_check() != boundary_reference:
                    raise ConfigurationError("environment verification unavailable: boundary changed before dispatch")
                turn_response = await self.transport.request("turn/start", turn_params)
                turn = turn_response.get("turn")
                turn_id = turn.get("id") if isinstance(turn, dict) else None
                if not isinstance(turn_id, str) or not turn_id:
                    raise CodexProtocolError("turn/start omitted turn identity")
                collector.turn_id = turn_id
                if dynamic_session is not None:
                    dynamic_session.bind_turn(turn_id)
                self._attempts[context.attempt_id] = (thread_id, turn_id)
                if dynamic_session is not None:
                    failed = asyncio.create_task(self.transport._failure_event.wait())
                    try:
                        done, _ = await asyncio.wait((collector.future, failed),
                            timeout=context.config.timeout_seconds, return_when=asyncio.FIRST_COMPLETED)
                        if failed in done:
                            self.transport._raise_if_failed()
                        if collector.future not in done:
                            raise TimeoutError()
                        result = collector.future.result()
                    finally:
                        failed.cancel()
                        await asyncio.gather(failed, return_exceptions=True)
                    if self.transport._dynamic_tasks:
                        raise CodexProtocolError("turn completed before dynamic task response")
                else:
                    result = await asyncio.wait_for(
                        asyncio.shield(collector.future), timeout=context.config.timeout_seconds
                    )
                await asyncio.sleep(0)
                if (dynamic_session is not None and invocation is not None and invocation.mode == "dynamic_tool"
                        and invocation.exposure != "optional"
                        and invocation.tool not in dynamic_session.tools_succeeded):
                    raise ConfigurationError("required dynamic candidate was not invoked")
                if collector.error is not None:
                    raise collector.error
                result = result.model_copy(
                    update={
                        "approval_digests": tuple(self.transport.approval_digests),
                    }
                )
            except (TimeoutError, asyncio.CancelledError):
                await self._interrupt_known(context.attempt_id)
                raw = self._partial_execution(collector, ExecutionStatus.TIMEOUT, started)
                return raw
            except (CodexProtocolError, CodexRequestError, ConfigurationError) as exc:
                raw = self._partial_execution(collector, ExecutionStatus.FAILED, started)
                raw.metadata["host_failure_code"] = (
                    "protocol_frame_limit" if isinstance(exc, CodexProtocolError) and "frame" in str(exc) and ("oversized" in str(exc) or "limit" in str(exc))
                    else "environment_verification_unavailable" if isinstance(exc, ConfigurationError) and "environment verification unavailable" in str(exc)
                    else "inventory_not_isolated" if isinstance(exc, ConfigurationError)
                    else "host_request_rejected" if isinstance(exc, CodexRequestError)
                    else "host_protocol_failure"
                )
                raw.metadata["host_advertised_inventory_digest"] = collector.advertised_inventory_digest
                raw.metadata["host_available_tools"] = "unknown"
                raw.metadata["host_tools_used"] = json.dumps(sorted(collector.tools_used))
                return raw
            finally:
                if dynamic_session is not None:
                    dynamic_session.close()
                    try:
                        await self.transport.cancel_dynamic_tools()
                    except CodexProtocolError:
                        dynamic_cleanup_unconfirmed = True
                    if raw is not None:
                        raw.metadata['dynamic_callback_evidence'] = dynamic_session.evidence
                        raw.metadata['dynamic_cleanup_confirmed'] = not dynamic_cleanup_unconfirmed
                        if dynamic_cleanup_unconfirmed:
                            raw.status = ExecutionStatus.FAILED
                            raw.error_type = 'DYNAMIC_TASK_CLEANUP_UNCONFIRMED'
                unsubscribe()
                self.transport.approval_observer = None
                self.transport.approval_handler = None
                self.transport.approval_ceiling = SideEffect.NONE
            resources, accounting = turn_accounting(
                result.token_usage,
                model=result.actual_model,
                resource_pool=self.resource_id,
            )
            resources.latency_ms = (time.monotonic() - started) * 1000
            status = (
                ExecutionStatus.FAILED if dynamic_cleanup_unconfirmed else
                ExecutionStatus.SUCCESS
                if result.status == "completed"
                else ExecutionStatus.TIMEOUT
                if result.status == "interrupted"
                else ExecutionStatus.FAILED
            )
            actual_runtime = self._runtime_digest(context.config, result.actual_model) if result.actual_model else None
            drifted = context.expected_runtime_digest is not None and actual_runtime != context.expected_runtime_digest
            if drifted:
                status = ExecutionStatus.FAILED
            output_schema_bytes = (
                len(json.dumps(turn_params["outputSchema"], separators=(",", ":")).encode())
                if "outputSchema" in turn_params
                else 0
            )
            result_bytes = len(
                json.dumps(result.output, separators=(",", ":"), ensure_ascii=False).encode()
            )
            return RawExecution(
                status=status,
                output=result.output,
                resources=resources,
                accounting=accounting,
                error_type="HOST_IDENTITY_DRIFT" if drifted else None if status is ExecutionStatus.SUCCESS else "CODEX_TURN_FAILED",
                error_message=result.error,
                metadata={
                    **({"dynamic_tools_digest": dynamic_session.expected_digest,
                        "dynamic_tool_calls": len(dynamic_session._calls),
                        "dynamic_callback_evidence": dynamic_session.evidence,
                        "dynamic_cleanup_confirmed": not dynamic_cleanup_unconfirmed,
                        "dynamic_declaration_bytes": len(json.dumps(binding.declarations(), separators=(',', ':'), allow_nan=False).encode()),
                        "dynamic_schema_bytes": sum(len(json.dumps(tool['inputSchema'], separators=(',', ':'), allow_nan=False).encode()) for tool in binding._tools),
                        "dynamic_exposure": "declaration_accepted; model visibility requires live evidence"}
                       if dynamic_session is not None else {}),
                    "actual_model": result.actual_model,
                    "host_runtime_digest": actual_runtime,
                    **({"boundary_digest": boundary_reference} if boundary_reference is not None else {}),
                    "model_turn_count": 1,
                    "tool_selection_rounds": None,
                    "implementation_schema_bytes": None,
                    "output_schema_bytes": output_schema_bytes,
                    "result_bytes": result_bytes,
                    "tool_call_count": result.tool_count,
                    "host_tools_used": json.dumps(sorted(collector.tools_used)),
                    "host_advertised_inventory_digest": collector.advertised_inventory_digest,
                    "host_available_tools": "unknown",
                    "approval_evidence_digest": _message_digest(
                        {"digests": list(result.approval_digests)}
                    ) if result.approval_digests else None,
                    "thread_identity_digest": _message_digest({"thread_id": result.thread_id}),
                    "turn_identity_digest": _message_digest({"turn_id": result.turn_id}),
                },
            )

    def _partial_execution(self, collector: _TurnCollector, status: ExecutionStatus, started: float) -> RawExecution:
        resources, accounting = turn_accounting(collector.token_usage, model=collector.actual_model, resource_pool=self.resource_id)
        for usage in accounting.model_usage:
            usage.evidence.status = EvidenceStatus.PARTIAL
        resources.latency_ms = max(0, time.monotonic() - started) * 1000
        return RawExecution(
            status=status, resources=resources, accounting=accounting,
            error_type="TIMEOUT" if status == ExecutionStatus.TIMEOUT else "ProtocolError",
            error_message="Codex execution ended before complete evidence was available",
            metadata={"execution_stream_complete": False, "actual_model": collector.actual_model, "model_turn_count": int(collector.turn_id is not None), "tool_call_count": collector.tool_count},
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
        try:
            await self.transport.close()
        finally:
            try:
                if self._worker is not None and self._worker_process_id is not None:
                    await self._worker.cleanup(self._worker_process_id)
            finally:
                if self._worker_security is not None:
                    self._worker_security.cleanup()


class _TurnCollector:
    def __init__(self, *, max_output_bytes: int, journal: EventJournal | None = None) -> None:
        self.journal = journal
        self.max_output_bytes = max_output_bytes
        self.thread_id: str | None = None
        self.turn_id: str | None = None
        self.actual_model: str | None = None
        self.token_usage: dict[str, int] | None = None
        self.output_parts: list[str] = []
        self.final_parts: list[str] = []
        self.tool_count = 0
        self.tools_used: set[str] = set()
        self.advertised_inventory_digest: str | None = None
        self.terminal: tuple[str, dict[str, int] | None] | None = None
        self.error: CodexProtocolError | None = None
        self.future: asyncio.Future[CodexTurnResult] = asyncio.get_running_loop().create_future()

    def handle(self, method: str, params: JsonObject) -> None:
        if self.thread_id is not None and params.get("threadId") not in {None, self.thread_id}:
            return
        event_turn = params.get("turnId")
        if self.turn_id is not None and event_turn not in {None, self.turn_id}:
            return
        if self.journal is not None and method in {"item/started", "item/completed"}:
            item = params.get("item")
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                try:
                    self.journal.append("action.started" if method == "item/started" else "action.completed",
                                        _message_digest({"method": method, "id": item["id"]}),
                                        action_digest=_message_digest(item).removeprefix("sha256:"))
                except ConfigurationError:
                    self._reject("conflicting canonical action events")
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
                if self.journal is not None and self.token_usage != parsed:
                    _, accounting = turn_accounting(parsed, model=self.actual_model or "unresolved", resource_pool="unknown")
                    for usage in accounting.model_usage:
                        usage.evidence.status = EvidenceStatus.PARTIAL
                    self.journal.append("usage.reported", f"usage:{self.journal.journal_id}:{len(self.journal.items)}",
                                        accounting=accounting, accounting_mode="cumulative")
                self.token_usage = parsed
        elif method == "item/completed":
            item = params.get("item")
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "agentMessage" and isinstance(item.get("text"), str):
                    phase = item.get("phase")
                    if phase == "final_answer":
                        self.final_parts.append(item["text"])
                    elif phase is None:
                        self.output_parts.append(item["text"])
                    elif phase != "commentary":
                        self._reject("unknown agent message phase")
                        return
                elif item_type in {"commandExecution", "fileChange", "mcpToolCall", "dynamicToolCall"}:
                    self.tool_count += 1
                    # Hash tool identities; never retain tool arguments or results.
                    self.tools_used.add(_message_digest({"type": item_type, "server": str(item.get("server", ""))[:200], "tool": str(item.get("tool", ""))[:200]}))
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
            output_text = "".join(self.final_parts or self.output_parts)
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
    return _select_model_config(models, context.config)


def _select_model_config(models: list[HostModel], config: ManagedHostExecutorConfig) -> HostModel | None:
    constraints = config.model_constraints
    required = set(constraints.required_capabilities)
    candidates = [
        model
        for model in models
        if (not constraints.allowed_model_ids or model.id in constraints.allowed_model_ids)
        and required.issubset(model.capabilities)
        and (
            constraints.minimum_context_tokens is None
            or (
                model.context_tokens is not None
                and model.context_tokens >= constraints.minimum_context_tokens
            )
        )
        and (
            not config.reasoning_efforts
            or any(item in model.reasoning_efforts for item in config.reasoning_efforts)
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
