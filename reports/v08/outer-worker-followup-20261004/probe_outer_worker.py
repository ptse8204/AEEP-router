#!/usr/bin/env python3
"""Bounded synthetic probe of Codex worker wrapper and outer timeout behavior."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
EXPECTED_SOURCE = "e6b71acba487280dfe50057d17379e5994c9113bc651a262935474f656a5dba6"
MAX_CASE_SECONDS = 1.0
MAX_TOTAL_SECONDS = 18.0
MAX_REPORT_BYTES = 1_048_576
PROGRESS = '{"stage":"turn_completed","turn_completion_received":true}'

sys.path.insert(0, str(ROOT / "src"))

from aeep.assessment.verification import verification_source_digest  # noqa: E402
from aeep.errors import ConfigurationError  # noqa: E402
from aeep.executors.base import ExecutionContext  # noqa: E402
from aeep.executors.managed_host import ManagedHostExecutor  # noqa: E402
from aeep.hosts.base import HostProbe, HostProbeStatus, ManagedHostExecutionContext  # noqa: E402
from aeep.hosts.codex_app_server import AppServerOptions, CodexAppServerAdapter  # noqa: E402
from aeep.models import (  # noqa: E402
    ActionRequest,
    ExecutorKind,
    ExecutorSpec,
    ExecutionStatus,
    ManagedHostArtifact,
    ManagedHostExecutorConfig,
    RawExecution,
    RouteEstimate,
)


class FakeTransport:
    metrics_scope = None
    catalog_metrics = None
    metrics_observer = None

    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def close(self) -> None:
        self.log.append("transport.close")


class FakeWorker:
    def __init__(self, log: list[str], *, artifact_mode: str = "success",
                 cleanup_mode: str = "success") -> None:
        self.log = log
        self.artifact_mode = artifact_mode
        self.cleanup_mode = cleanup_mode
        self.artifact_started = asyncio.Event()
        self.cleanup_started = asyncio.Event()
        self.artifact_calls: list[str] = []

    def digest(self) -> str:
        return "d" * 64

    async def artifact(self, execution_id: str, *, name: str, limit: int,
                       timeout: float, data: str | None = None,
                       files: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        self.artifact_calls.append(name)
        self.log.append("worker.artifact.start")
        self.artifact_started.set()
        if self.artifact_mode == "pending":
            try:
                await asyncio.Event().wait()
            finally:
                self.log.append("worker.artifact.cancelled")
        if self.artifact_mode == "configuration_error":
            self.log.append("worker.artifact.configuration_error")
            raise ConfigurationError("synthetic artifact transfer failure")
        self.log.append("worker.artifact.done")
        return {
            "data": "synthetic-output",
            "sha256": "a" * 64,
            "size": 16,
        }

    async def cleanup(self, execution_id: str) -> bool:
        self.log.append("worker.cleanup.start")
        self.cleanup_started.set()
        if self.cleanup_mode == "pending":
            try:
                await asyncio.Event().wait()
            finally:
                self.log.append("worker.cleanup.cancelled")
        if self.cleanup_mode == "delayed":
            await asyncio.sleep(0.05)
        self.log.append("worker.cleanup.done")
        return True


class FakeRegistry:
    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter

    def get(self, adapter_id: str) -> Any:
        assert adapter_id == "codex-app-server"
        return self.adapter


def config(*, timeout: float = 2.0) -> ManagedHostExecutorConfig:
    return ManagedHostExecutorConfig(
        adapter_id="codex-app-server",
        argv=(sys.executable, "-u", "synthetic-app-server"),
        instructions="Synthetic offline probe.",
        timeout_seconds=timeout,
        max_message_bytes=1024,
        managed_worker={"synthetic": True},
        artifact=ManagedHostArtifact(
            input_field="source",
            output_field="result",
            input_name="synthetic-input.txt",
            output_name="synthetic-output.txt",
            max_bytes=128,
        ),
    )


def host_context(cfg: ManagedHostExecutorConfig, attempt_id: str) -> ManagedHostExecutionContext:
    return ManagedHostExecutionContext(
        request=ActionRequest(capability="synthetic@1", input={"source": "synthetic-input"}),
        instruction="Synthetic offline probe.", config=cfg, attempt=1, attempt_id=attempt_id,
    )


def make_adapter(*, timeout: float = 2.0, artifact_mode: str = "success",
                 cleanup_mode: str = "success") -> tuple[CodexAppServerAdapter, FakeWorker, list[str], ManagedHostExecutorConfig]:
    log: list[str] = []
    worker = FakeWorker(log, artifact_mode=artifact_mode, cleanup_mode=cleanup_mode)
    cfg = config(timeout=timeout)
    adapter = CodexAppServerAdapter(
        argv=cfg.argv, resource_id="synthetic", principal_salt=b"synthetic-only",
        options=AppServerOptions(experimental_api=True),
    )
    adapter._worker = worker
    adapter._worker_process_id = "synthetic-worker"
    adapter.transport = FakeTransport(log)  # type: ignore[assignment]

    async def ready_probe() -> HostProbe:
        return HostProbe(adapter_id="codex-app-server", status=HostProbeStatus.READY)

    adapter.probe = ready_probe  # type: ignore[method-assign]
    return adapter, worker, log, cfg


def raw(status: ExecutionStatus) -> RawExecution:
    timeout = status is ExecutionStatus.TIMEOUT
    return RawExecution(
        status=status,
        output=None if timeout else {"result": "inner-synthetic"},
        error_type="TIMEOUT" if timeout else None,
        error_message="synthetic timeout" if timeout else None,
        metadata={"host_progress": PROGRESS, "synthetic_marker": "kept-through-wrapper"},
    )


def as_record(case_id: str, log: list[str], worker: FakeWorker,
              *, result: RawExecution | None = None,
              exception: BaseException | None = None, started: float) -> dict[str, Any]:
    metadata = result.metadata if result is not None else {}
    return {
        "case_id": case_id,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "call_order": list(log),
        "artifact_calls": list(worker.artifact_calls),
        "returned_status": result.status.value if result is not None else None,
        "returned_error_type": result.error_type if result is not None else None,
        "exception_type": type(exception).__name__ if exception is not None else None,
        "progress_preserved": metadata.get("host_progress") == PROGRESS if result is not None else None,
        "progress_value": metadata.get("host_progress") if result is not None else None,
        "cleanup_confirmed": metadata.get("worker_cleanup_confirmed") if result is not None else None,
        "artifact_sha256_recorded": metadata.get("artifact_sha256") == "a" * 64 if result is not None else None,
        "artifact_bytes_recorded": metadata.get("artifact_bytes") if result is not None else None,
    }


async def case_inner_timeout() -> dict[str, Any]:
    started = time.monotonic()
    adapter, worker, log, cfg = make_adapter()

    async def inner(ctx: ManagedHostExecutionContext) -> RawExecution:
        log.append("inner.return_timeout")
        return raw(ExecutionStatus.TIMEOUT)

    adapter._execute = inner  # type: ignore[method-assign]
    result = await asyncio.wait_for(adapter.execute(host_context(cfg, "inner-timeout")), MAX_CASE_SECONDS)
    assert result.status is ExecutionStatus.TIMEOUT and result.error_type == "TIMEOUT"
    assert worker.artifact_calls == []
    assert log == ["inner.return_timeout", "transport.close", "worker.cleanup.start", "worker.cleanup.done"]
    assert result.metadata["host_progress"] == PROGRESS
    assert result.metadata["worker_cleanup_confirmed"] is True
    return as_record("inner_timeout_skips_artifact", log, worker, result=result, started=started)


async def case_success_artifact() -> dict[str, Any]:
    started = time.monotonic()
    adapter, worker, log, cfg = make_adapter()

    async def inner(ctx: ManagedHostExecutionContext) -> RawExecution:
        log.append("inner.return_success")
        return raw(ExecutionStatus.SUCCESS)

    adapter._execute = inner  # type: ignore[method-assign]
    result = await asyncio.wait_for(adapter.execute(host_context(cfg, "artifact-success")), MAX_CASE_SECONDS)
    assert result.status is ExecutionStatus.SUCCESS
    assert result.output == {"result": "synthetic-output"}
    assert result.metadata["artifact_sha256"] == "a" * 64 and result.metadata["artifact_bytes"] == 16
    assert result.metadata["host_progress"] == PROGRESS
    assert log == ["inner.return_success", "worker.artifact.start", "worker.artifact.done",
                   "transport.close", "worker.cleanup.start", "worker.cleanup.done"]
    return as_record("success_artifact_succeeds", log, worker, result=result, started=started)


async def case_artifact_error() -> dict[str, Any]:
    started = time.monotonic()
    adapter, worker, log, cfg = make_adapter(artifact_mode="configuration_error")

    async def inner(ctx: ManagedHostExecutionContext) -> RawExecution:
        log.append("inner.return_success")
        return raw(ExecutionStatus.SUCCESS)

    adapter._execute = inner  # type: ignore[method-assign]
    result = await asyncio.wait_for(adapter.execute(host_context(cfg, "artifact-error")), MAX_CASE_SECONDS)
    assert result.status is ExecutionStatus.FAILED
    assert result.error_type == "WORKER_ARTIFACT_FAILED" and result.output is None
    assert result.metadata["host_progress"] == PROGRESS
    assert log == ["inner.return_success", "worker.artifact.start", "worker.artifact.configuration_error",
                   "transport.close", "worker.cleanup.start", "worker.cleanup.done"]
    return as_record("success_artifact_configuration_error", log, worker, result=result, started=started)


async def case_cancel_artifact() -> dict[str, Any]:
    started = time.monotonic()
    adapter, worker, log, cfg = make_adapter(artifact_mode="pending")

    async def inner(ctx: ManagedHostExecutionContext) -> RawExecution:
        log.append("inner.return_success")
        return raw(ExecutionStatus.SUCCESS)

    adapter._execute = inner  # type: ignore[method-assign]
    task = asyncio.create_task(adapter.execute(host_context(cfg, "artifact-cancel")))
    await asyncio.wait_for(worker.artifact_started.wait(), MAX_CASE_SECONDS)
    task.cancel()
    exception: BaseException | None = None
    try:
        await asyncio.wait_for(task, MAX_CASE_SECONDS)
    except asyncio.CancelledError as exc:
        exception = exc
    assert isinstance(exception, asyncio.CancelledError)
    assert log == ["inner.return_success", "worker.artifact.start", "worker.artifact.cancelled",
                   "transport.close", "worker.cleanup.start", "worker.cleanup.done"]
    return as_record("cancel_while_artifact_pending", log, worker, exception=exception, started=started)


async def case_cancel_cleanup() -> dict[str, Any]:
    started = time.monotonic()
    adapter, worker, log, cfg = make_adapter(cleanup_mode="pending")

    async def inner(ctx: ManagedHostExecutionContext) -> RawExecution:
        log.append("inner.return_timeout")
        return raw(ExecutionStatus.TIMEOUT)

    adapter._execute = inner  # type: ignore[method-assign]
    task = asyncio.create_task(adapter.execute(host_context(cfg, "cleanup-cancel")))
    await asyncio.wait_for(worker.cleanup_started.wait(), MAX_CASE_SECONDS)
    task.cancel()
    exception: BaseException | None = None
    try:
        await asyncio.wait_for(task, MAX_CASE_SECONDS)
    except asyncio.CancelledError as exc:
        exception = exc
    assert isinstance(exception, asyncio.CancelledError)
    assert log == ["inner.return_timeout", "transport.close", "worker.cleanup.start", "worker.cleanup.cancelled"]
    return as_record("cancel_while_cleanup_pending", log, worker, exception=exception, started=started)


async def case_delayed_cleanup() -> dict[str, Any]:
    started = time.monotonic()
    adapter, worker, log, cfg = make_adapter(cleanup_mode="delayed")

    async def inner(ctx: ManagedHostExecutionContext) -> RawExecution:
        log.append("inner.return_timeout")
        return raw(ExecutionStatus.TIMEOUT)

    adapter._execute = inner  # type: ignore[method-assign]
    result = await asyncio.wait_for(adapter.execute(host_context(cfg, "cleanup-delay")), MAX_CASE_SECONDS)
    assert result.status is ExecutionStatus.TIMEOUT and result.error_type == "TIMEOUT"
    assert result.metadata["host_progress"] == PROGRESS
    assert time.monotonic() - started >= 0.05
    assert log == ["inner.return_timeout", "transport.close", "worker.cleanup.start", "worker.cleanup.done"]
    return as_record("delayed_cleanup_after_timeout", log, worker, result=result, started=started)


async def case_outer_timeout_inner_catches() -> dict[str, Any]:
    started = time.monotonic()
    adapter, worker, log, cfg = make_adapter(timeout=0.1)

    async def inner(ctx: ManagedHostExecutionContext) -> RawExecution:
        log.append("inner.pending")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            log.append("inner.caught_outer_cancellation_as_timeout")
            return raw(ExecutionStatus.TIMEOUT)

    adapter._execute = inner  # type: ignore[method-assign]
    spec = ExecutorSpec(id="synthetic-host", capability="synthetic@1", kind=ExecutorKind.MANAGED_HOST,
        resource_pool="synthetic", description="Offline synthetic managed host", config=cfg.model_dump(mode="json"))
    context = ExecutionContext(request=ActionRequest(capability="synthetic@1", input={"source": "synthetic-input"}),
        spec=spec, estimate=RouteEstimate(), attempt=1, attempt_id="outer-inner-timeout")
    executor = ManagedHostExecutor(FakeRegistry(adapter))  # type: ignore[arg-type]
    result = await asyncio.wait_for(executor.execute(context), 2.0)
    assert result.status is ExecutionStatus.TIMEOUT and result.error_type == "TIMEOUT"
    assert result.metadata["host_progress"] == PROGRESS
    assert result.metadata["worker_cleanup_confirmed"] is True
    assert "inner.caught_outer_cancellation_as_timeout" in log
    assert "worker.artifact.start" not in log
    assert log[-3:] == ["transport.close", "worker.cleanup.start", "worker.cleanup.done"]
    return as_record("outer_deadline_inner_converts_cancellation_to_timeout", log, worker,
                     result=result, started=started)


async def case_outer_timeout_in_artifact() -> dict[str, Any]:
    started = time.monotonic()
    adapter, worker, log, cfg = make_adapter(timeout=0.1, artifact_mode="pending")

    async def inner(ctx: ManagedHostExecutionContext) -> RawExecution:
        log.append("inner.return_success")
        return raw(ExecutionStatus.SUCCESS)

    adapter._execute = inner  # type: ignore[method-assign]
    spec = ExecutorSpec(id="synthetic-host", capability="synthetic@1", kind=ExecutorKind.MANAGED_HOST,
        resource_pool="synthetic", description="Offline synthetic managed host", config=cfg.model_dump(mode="json"))
    context = ExecutionContext(request=ActionRequest(capability="synthetic@1", input={"source": "synthetic-input"}),
        spec=spec, estimate=RouteEstimate(), attempt=1, attempt_id="outer-artifact-timeout")
    executor = ManagedHostExecutor(FakeRegistry(adapter))  # type: ignore[arg-type]
    exception: BaseException | None = None
    try:
        await asyncio.wait_for(executor.execute(context), 2.0)
    except TimeoutError as exc:
        exception = exc
    assert isinstance(exception, TimeoutError)
    assert worker.artifact_started.is_set()
    assert log == ["inner.return_success", "worker.artifact.start", "worker.artifact.cancelled",
                   "transport.close", "worker.cleanup.start", "worker.cleanup.done"]
    return as_record("outer_deadline_during_artifact_propagates_timeout_error", log, worker,
                     exception=exception, started=started)


async def run_all() -> list[dict[str, Any]]:
    functions: tuple[Callable[[], Awaitable[dict[str, Any]]], ...] = (
        case_inner_timeout,
        case_success_artifact,
        case_artifact_error,
        case_cancel_artifact,
        case_cancel_cleanup,
        case_delayed_cleanup,
        case_outer_timeout_inner_catches,
        case_outer_timeout_in_artifact,
    )
    outcomes: list[dict[str, Any]] = []
    for function in functions:
        case_id = function.__name__.removeprefix("case_")
        try:
            result = await asyncio.wait_for(function(), timeout=MAX_CASE_SECONDS)
            result["check"] = "passed"
        except BaseException as exc:
            result = {
                "case_id": case_id,
                "check": "failed",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)[:300],
            }
        outcomes.append(result)
    return outcomes


async def main() -> None:
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    source_before = verification_source_digest(ROOT)
    if source_before != EXPECTED_SOURCE:
        raise RuntimeError(f"frozen source digest mismatch: {source_before}")
    started = time.monotonic()
    outcomes = await asyncio.wait_for(run_all(), timeout=MAX_TOTAL_SECONDS)
    source_after = verification_source_digest(ROOT)
    report = {
        "schema_version": "aeep.outer-worker-followup.outcomes.v1",
        "source_digest": source_before,
        "source_digest_after": source_after,
        "git_head": "c0609f0e1839ea17bbd4871c028e84e75e26970e",
        "started_at": started_at,
        "definition_sha256": hashlib.sha256((OUT / "test-definition-review.json").read_bytes()).hexdigest(),
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "probe_kind": "offline synthetic adapter/worker behavior; no model, Codex process, Docker or network",
        "status": "passed" if source_after == source_before and all(item.get("check") == "passed" for item in outcomes) else "failed",
        "cases": outcomes,
        "interpretation_limit": "These are synthetic current-code wrapper outcomes. They do not reconstruct, explain, or alter any historical timeout trial.",
    }
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    existing = sum(path.stat().st_size for path in OUT.iterdir() if path.is_file())
    if existing + len(encoded.encode("utf-8")) > MAX_REPORT_BYTES:
        raise RuntimeError("probe artifacts exceed the 1 MiB report bound")
    (OUT / "outcomes.json").write_text(encoded, encoding="utf-8")
    if report["status"] != "passed":
        raise RuntimeError("one or more diagnostic cases failed; see outcomes.json")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except TimeoutError as exc:
        print(f"bounded diagnostic failed: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(2)
