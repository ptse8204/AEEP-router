"""Codex exec adapter; JSONL is transient and authentication remains owned by Codex."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ..capacity import CapacityObservation, CapacityWindow
from ..codex_capture import parse_codex_jsonl
from ..errors import ConfigurationError
from ..execution import (
    EventJournal,
    ExecutionEvent,
    ExecutionHandle,
    ExecutorCapabilities,
    cancel_execution,
    execution_events,
    opaque_digest,
    start_execution,
)
from ..models import (
    EvidenceSource,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    ManagedHostExecutorConfig,
    RawExecution,
    ResourceAccounting,
    ResourceVector,
    RouteEstimate,
    TrustLevel,
)
from .base import HostModel, HostProbe, HostProbeStatus, ManagedHostExecutionContext
from .codex_accounting import turn_accounting
from .workers import binding_from_config


class CodexExecAdapter:
    adapter_id = "codex-exec"

    def __init__(self, spec: ExecutorSpec, *, manifest_directory: Path | None = None) -> None:
        self.spec = spec
        self.config = spec.managed_host_config()
        self.adapter_id = self.config.adapter_id
        self.worker = binding_from_config(self.config.managed_worker)
        if self.worker is not None and (self.config.argv != (self.worker.binary,) or self.config.environment_allowlist):
            raise ConfigurationError("worker binding requires its exact binary and no inherited host environment")
        self.manifest_directory = manifest_directory
        self._handles: dict[str, ExecutionHandle] = {}

    @classmethod
    def from_executor(cls, spec: ExecutorSpec, *, principal_salt: bytes,
                      manifest_directory: Path | None = None) -> CodexExecAdapter:
        return cls(spec, manifest_directory=manifest_directory)

    def capabilities(self) -> ExecutorCapabilities:
        return ExecutorCapabilities(
            adapter=self.adapter_id, version="1", support_status="supported",
            features={"execution": "supported", "structured_output": "supported",
                      "usage": "supported", "process_termination": "supported",
                      "streaming": "supported", "identity": "unknown",
                      "fresh_worker": "supported", "reused_worker": "unsupported",
                      "isolation": "unknown", "cancellation": "unknown"},
        )

    async def probe(self) -> HostProbe:
        return await asyncio.to_thread(self._probe)

    def _probe(self) -> HostProbe:
        path = Path(self.worker.runtime if self.worker is not None else self.config.argv[0])
        if not path.is_file() or not os.access(path, os.X_OK):
            return HostProbe(adapter_id=self.adapter_id, status=HostProbeStatus.UNAVAILABLE,
                             reason="configured executable is unavailable")
        if self.config.executable_sha256 is not None and self.worker is None:
            with path.open("rb") as stream:
                actual = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != self.config.executable_sha256:
                return HostProbe(adapter_id=self.adapter_id, status=HostProbeStatus.UNAVAILABLE,
                                 reason="configured executable digest changed")
        if not self.config.exec_model:
            return HostProbe(adapter_id=self.adapter_id, status=HostProbeStatus.UNSUPPORTED,
                             reason="Codex Exec requires an explicit configured model")
        return HostProbe(adapter_id=self.adapter_id, status=HostProbeStatus.READY,
                         protocol_version="codex-exec-jsonl", supported_features=("turns",))

    async def list_models(self) -> list[HostModel]:
        # A configured model name is not a discovered host capability.
        return []

    async def resolve_identity(self, config: ManagedHostExecutorConfig) -> str | None:
        return None

    async def snapshot_capacity(self) -> CapacityObservation:
        return CapacityObservation(resource_id=self.spec.resource_pool or "unknown",
                                   source="codex_exec_unknown",
                                   windows=(CapacityWindow(window_id="unknown", confidence=0),))

    async def start(self, context: ManagedHostExecutionContext) -> ExecutionHandle:
        if context.attempt_id in self._handles:
            raise ConfigurationError("execution attempt already started")
        handle = start_execution(context.attempt_id, self.adapter_id,
                                 lambda journal: self._run(context, journal))
        self._handles[context.attempt_id] = handle
        return handle

    def events(self, handle: ExecutionHandle) -> AsyncIterator[ExecutionEvent]:
        return execution_events(handle)

    async def cancel(self, handle: ExecutionHandle) -> None:
        await cancel_execution(handle)

    async def execute(self, context: ManagedHostExecutionContext) -> RawExecution:
        handle = await self.start(context)
        return await handle.task

    async def interrupt(self, attempt_id: str) -> None:
        handle = self._handles.get(attempt_id)
        if handle is not None:
            await self.cancel(handle)

    async def close(self) -> None:
        for handle in self._handles.values():
            await self.cancel(handle)
        if self._handles:
            await asyncio.gather(*(handle.task for handle in self._handles.values()), return_exceptions=True)
        self._handles.clear()

    async def _run(self, context: ManagedHostExecutionContext, journal: EventJournal) -> RawExecution:
        # Reuse argv, bounded pipe capture and process-group termination.
        from ..executors.base import ExecutionContext
        from ..executors.command import CommandExecutor

        if context.config.artifact is not None or context.config.input_tree is not None:
            return RawExecution(status=ExecutionStatus.REJECTED, error_type="ARTIFACT_TRANSPORT_UNSUPPORTED")
        probe = await self.probe()
        if probe.status is not HostProbeStatus.READY:
            return RawExecution(status=ExecutionStatus.REJECTED, error_type=probe.status.value.upper(),
                                error_message=probe.reason)
        if context.expected_runtime_digest is not None:
            return RawExecution(status=ExecutionStatus.REJECTED, error_type="ENVIRONMENT_VERIFICATION_UNAVAILABLE",
                                error_message="Codex Exec identity and enforcement boundary are unverified")
        config = context.config
        if config != self.config:
            return RawExecution(status=ExecutionStatus.REJECTED, error_type="CONFIGURATION_REJECTED",
                                error_message="execution configuration differs from registered adapter")
        if config.invocation is not None and (config.invocation.mode != "turn" or config.invocation.dynamic_tools_digest is not None):
            return RawExecution(status=ExecutionStatus.REJECTED, error_type="MISSING_CAPABILITY",
                                error_message="this Exec adapter supports explicit turn execution only")
        observed = RawExecution(status=ExecutionStatus.SUCCESS)
        _, observed.accounting = turn_accounting(None, model=None, resource_pool=self.spec.resource_pool or "unknown")
        decoder = ExecEventDecoder(journal, observed, model=config.exec_model or "unknown",
                                   max_bytes=config.max_message_bytes, output_mode=config.output_mode)
        with TemporaryDirectory(prefix="aeep-exec-") as temporary:
            root = Path(temporary)
            schema = root / "output.schema.json"
            schema.write_text(json.dumps(context.output_schema or {}))
            workspace = root / "workspace"
            workspace.mkdir()
            cwd = (str(workspace) if config.worker_workspace == "temporary" else
                   config.working_directory if config.working_directory_policy == "fixed" else
                   str(self.manifest_directory) if self.manifest_directory is not None else None)
            argv = [*config.argv, "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                    "--skip-git-repo-check",
                    "-c", 'approval_policy="never"', "--model", config.exec_model or ""]
            if self.worker is not None and self.worker.permissions_profile is not None:
                argv += ["-c", "default_permissions=" + json.dumps(self.worker.permissions_profile, ensure_ascii=False)]
            else:
                argv += ["--sandbox", "workspace-write" if config.sandbox_policy == "workspace_write" else "read-only"]
            if config.reasoning_efforts:
                argv += ["-c", "model_reasoning_effort=" + json.dumps(config.reasoning_efforts[0])]
            if config.output_mode == "json":
                argv += ["--output-schema", "/tmp/aeep-output.schema.json" if self.worker else str(schema)]
            argv += ["-"]
            if self.worker is not None:
                argv = list(self.worker.argv(tuple(argv[1:]), execution_id=context.attempt_id,
                                             output_schema=context.output_schema if config.output_mode == "json" else None,
                                             security_path=self.worker.prepare_security(root)))
                cwd = None
            command = ExecutorSpec(id=self.spec.id, capability=context.request.capability,
                                   kind=ExecutorKind.COMMAND, description="Reviewed Codex Exec invocation",
                                   config={"argv": argv, "stdin": "{input.instruction}", "cwd": cwd,
                                           "env": {name: os.environ[name] for name in config.environment_allowlist if name in os.environ},
                                           "timeout_seconds": config.timeout_seconds,
                                           "max_output_bytes": config.max_message_bytes,
                                           "output": {"type": "text"}})
            request = context.request.model_copy(update={"input": {"instruction": context.instruction}})
            try:
                if context.invocation_check is not None:
                    context.invocation_check()
                raw = await CommandExecutor(stdout_observer=decoder.feed).execute(ExecutionContext(
                    request=request, spec=command, estimate=RouteEstimate(), attempt=context.attempt,
                    attempt_id=context.attempt_id))
            finally:
                if self.worker is not None:
                    await self.worker.cleanup(context.attempt_id)
        if self.worker is not None:
            raw.metadata["worker_digest"] = self.worker.digest()
            raw.metadata["container_client_cpu_ms"] = raw.resources.cpu_ms
            raw.metadata["container_client_peak_memory_mb"] = raw.resources.peak_memory_mb
            raw.metadata["container_resource_usage"] = "unavailable"
            raw.resources = ResourceVector(latency_ms=raw.resources.latency_ms)
        raw.output = None
        raw.stdout = raw.stderr = ""
        raw.metadata.update(adapter_id=self.adapter_id, protocol_version="codex-exec-jsonl",
                            host_available_tools="unknown", model_identity="configured_only")
        raw.accounting = observed.accounting
        raw.metadata.update(observed.metadata)
        try:
            decoder.finish(raw)
            if raw.metadata.get("stdout_truncated"):
                raise ConfigurationError("execution event stream exceeded its bound")
        except (ConfigurationError, ValueError, TypeError, KeyError):
            raw.status = ExecutionStatus.FAILED if raw.status != ExecutionStatus.TIMEOUT else raw.status
            raw.output = None
            raw.metadata["execution_stream_complete"] = False
            raw.error_type = "INCOMPLETE_EXECUTION_EVIDENCE"
            raw.error_message = "Codex Exec returned incomplete, conflicting or malformed events"
        return raw


class ExecEventDecoder:
    """Incremental bounded JSONL decoding; content stays transient."""

    def __init__(self, journal: EventJournal, raw: RawExecution, *, model: str,
                 max_bytes: int, output_mode: str) -> None:
        self.journal, self.raw = journal, raw
        self.model, self.max_bytes, self.output_mode = model, max_bytes, output_mode
        self.terminal: str | None = None
        self.output: str | None = None
        self.total = 0
        self.seen: set[str] = set()
        self.pending = bytearray()
        self.invalid = False

    def feed(self, chunk: bytes) -> None:
        self.pending.extend(chunk)
        while b"\n" in self.pending:
            line, _, rest = self.pending.partition(b"\n")
            self.pending = bytearray(rest)
            self._bounded_line(bytes(line))

    def _bounded_line(self, line: bytes) -> None:
        try:
            self.line(line.decode("utf-8"))
        except (ConfigurationError, ValueError, TypeError, KeyError):
            self.invalid = True

    def line(self, line: str) -> None:
        self.total += len(line.encode())
        if self.total > self.max_bytes:
            raise ConfigurationError("execution event stream exceeded its bound")
        event: Any = json.loads(line)
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ConfigurationError("malformed execution event")
        digest = opaque_digest(event)
        if digest in self.seen:
            return
        self.seen.add(digest)
        kind = event["type"]
        if self.terminal is not None:
            raise ConfigurationError("event follows a terminal event")
        if kind == "turn.started":
            self.journal.append("action.started", "turn")
            self.raw.metadata["model_turn_count"] = 1
        elif kind in {"item.started", "item.completed"}:
            item = event.get("item")
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise ConfigurationError("malformed execution item")
            source = opaque_digest([kind, item["id"]])
            self.journal.append("action.started" if kind == "item.started" else "action.completed",
                                source, action_digest=opaque_digest(item))
            if kind == "item.completed" and item.get("type") == "agent_message":
                if not isinstance(item.get("text"), str):
                    raise ConfigurationError("missing structured result")
                self.output = item["text"]
        elif kind in {"turn.completed", "turn.failed"}:
            self.terminal = kind
            if kind == "turn.completed" and isinstance(event.get("usage"), dict):
                usage = parse_codex_jsonl([line], model=self.model, max_bytes=self.max_bytes)
                usage.evidence.source = EvidenceSource.PROVIDER_REPORT
                usage.evidence.trust = TrustLevel.SELF_ASSERTED
                self.raw.accounting.model_usage.append(usage)
                self.journal.append("usage.reported", "turn-usage", accounting=ResourceAccounting(model_usage=[usage]))
        elif kind not in {"thread.started", "item.updated", "error"}:
            raise ConfigurationError("unknown execution event")
        elif kind == "error":
            raise ConfigurationError("execution error event")

    def finish(self, raw: RawExecution) -> None:
        if self.pending:
            self._bounded_line(bytes(self.pending))
            self.pending.clear()
        if self.invalid or self.terminal is None:
            raise ConfigurationError("incomplete execution event stream")
        if self.terminal == "turn.failed":
            raw.status = ExecutionStatus.FAILED
            raw.error_type = "HOST_EXECUTION_FAILED"
            raw.error_message = "Codex reported a failed turn"
        elif raw.status == ExecutionStatus.SUCCESS:
            if self.output is None:
                raise ConfigurationError("missing execution output")
            raw.output = json.loads(self.output) if self.output_mode == "json" else self.output


def normalize_exec_events(lines: list[str], journal: EventJournal, raw: RawExecution, *,
                          model: str, max_bytes: int, output_mode: str) -> None:
    decoder = ExecEventDecoder(journal, raw, model=model, max_bytes=max_bytes, output_mode=output_mode)
    for line in lines:
        decoder.line(line)
    decoder.finish(raw)
