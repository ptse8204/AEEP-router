"""Safe argv-based local command executor."""

from __future__ import annotations

import asyncio
import json
import math
import os
import signal
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from ..codex_capture import parse_codex_jsonl
from ..errors import ConfigurationError
from ..execution import ExecutorCapabilities
from ..models import (
    ExecutionStatus,
    ExecutorSpec,
    ModelAccessChannel,
    RawExecution,
    ResourceAccounting,
    ResourceVector,
    TaskScope,
)
from ..profiler import approximate_tokens
from ..templates import render
from .base import BaseExecutor, ExecutionContext
from .parsing import parse_output


@dataclass(slots=True)
class _ProcessMetrics:
    cpu_ms: float = 0.0
    peak_memory_mb: float = 0.0
    memory_mb_seconds: float = 0.0


async def _monitor_process(
    pid: int, stop: asyncio.Event, interval: float = 0.01,
    observed: set[psutil.Process] | None = None,
) -> _ProcessMetrics:
    metrics = _ProcessMetrics()
    last = time.perf_counter()
    try:
        process = psutil.Process(pid)
    except psutil.Error:
        return metrics
    while not stop.is_set():
        now = time.perf_counter()
        try:
            processes = [process, *process.children(recursive=True)]
            if observed is not None:
                observed.update(processes)
            rss = 0.0
            cpu = 0.0
            for item in processes:
                try:
                    rss += item.memory_info().rss / (1024 * 1024)
                    times = item.cpu_times()
                    cpu += times.user + times.system
                except psutil.Error:
                    continue
            metrics.peak_memory_mb = max(metrics.peak_memory_mb, rss)
            metrics.memory_mb_seconds += rss * max(0.0, now - last)
            metrics.cpu_ms = max(metrics.cpu_ms, cpu * 1000.0)
        except psutil.Error:
            pass
        last = now
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)
    return metrics


async def _read_limited(stream: asyncio.StreamReader | None, limit: int,
                        observer: Callable[[bytes], None] | None = None) -> tuple[bytes, int]:
    if stream is None:
        return b"", 0
    captured = bytearray()
    total = 0
    while True:
        chunk = await stream.read(65_536)
        if not chunk:
            break
        total += len(chunk)
        if len(captured) < limit:
            bounded = chunk[: max(0, limit - len(captured))]
            captured.extend(bounded)
            if observer is not None:
                observer(bounded)
    return bytes(captured), total


def _minimal_environment() -> dict[str, str]:
    names = ["PATH", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT"]
    return {name: os.environ[name] for name in names if name in os.environ}


class CommandExecutor(BaseExecutor):
    def require_task_scope(self, scope: TaskScope, spec: ExecutorSpec, control_paths: list[Path], *, activating: bool = False) -> None:
        from ..hosts.codex_sandbox import NativeSandboxConfig
        if 'native_sandbox' not in spec.config or 'assessment_workflow' in spec.config:
            raise ConfigurationError('task scope v1 requires a native sandbox command')
        boundary = NativeSandboxConfig.model_validate(spec.config['native_sandbox'])
        if spec.config.get('inherit_env'):
            raise ConfigurationError('native sandbox commands require the minimal environment')
        boundary.validate_environment(spec.config.get('env', {}))
        timeout = float(spec.config.get('timeout_seconds', 60))
        if boundary.project_root != scope.project_root or not math.isfinite(timeout) or not 0 < timeout <= scope.max_attempt_seconds:
            raise ConfigurationError('task scope permission or resource bound exceeded')
        for control in control_paths:
            if (any(control.resolve().is_relative_to(Path(root)) for root in [*boundary.read_roots, *boundary.write_roots])
                    and not any(control.resolve().is_relative_to(Path(root)) for root in boundary.deny_roots)):
                raise ConfigurationError('task scope exposes coordinator control files')
        boundary.permission_overrides()
        if activating:
            boundary.validate_single_process()
            boundary.argv([])

    def capabilities(self) -> ExecutorCapabilities:
        return ExecutorCapabilities(adapter=type(self).__name__, features={"fresh_worker":"supported", "reused_worker":"unsupported"})

    def __init__(self, *, stdout_observer: Callable[[bytes], None] | None = None) -> None:
        # Adapter-owned callback, deliberately absent from candidate configuration.
        self.stdout_observer = stdout_observer

    async def execute(self, context: ExecutionContext) -> RawExecution:
        config = context.spec.config
        if config.get("shell"):
            raise ConfigurationError(
                "shell execution is intentionally unsupported; use an argv list or a reviewed wrapper script"
            )
        argv_template = config.get("argv")
        if not isinstance(argv_template, list) or not argv_template:
            raise ConfigurationError(
                f"command executor {context.spec.id} requires non-empty config.argv"
            )
        values = {"input": context.request.input, "action": context.request.model_dump(mode="json")}
        if 'argv_literal' in config and type(config['argv_literal']) is not bool:
            raise ConfigurationError('argv_literal must be an operator-configured boolean')
        argv = argv_template if config.get('argv_literal') is True else render(argv_template, values)
        if not all(isinstance(item, (str, int, float)) for item in argv):
            raise ConfigurationError("rendered command arguments must be scalar values")
        argv = [str(item) for item in argv]
        timeout = float(config.get("timeout_seconds", 60.0))
        max_output = int(config.get("max_output_bytes", 1_000_000))
        cwd = config.get("cwd")
        configured_env = config.get("env", {})
        if not isinstance(configured_env, dict):
            raise ConfigurationError("command config.env must be a mapping")
        if 'native_sandbox' in config:
            from ..hosts.codex_sandbox import NativeSandboxConfig
            boundary = NativeSandboxConfig.model_validate(config['native_sandbox'])
            if config.get('inherit_env'):
                raise ConfigurationError('native sandbox commands require the minimal environment')
            environment = _minimal_environment()
            for key in ('TMPDIR', 'TMP', 'TEMP'):
                environment.pop(key, None)
            environment.update(boundary.validate_environment(configured_env))
        else:
            environment = dict(os.environ) if config.get("inherit_env", False) else _minimal_environment()
            environment.update({str(key): str(value) for key, value in
                                render(configured_env, values, allow_env=True).items()})
        if context.request.idempotency_key and config.get("propagate_idempotency_key", True):
            environment["AEEP_IDEMPOTENCY_KEY"] = context.request.idempotency_key
        stdin_template = config.get("stdin")
        stdin_bytes = None
        if config.get("stdin_json", False):
            stdin_bytes = json.dumps(
                context.request.input,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        elif stdin_template is not None:
            stdin_value = render(stdin_template, values)
            stdin_bytes = str(stdin_value).encode("utf-8")
        max_stdin = int(config.get("max_stdin_bytes", 1_000_000))
        if 'native_sandbox' in config and boundary.single_process:
            if stdin_bytes is not None and len(stdin_bytes) > 1_048_576:
                raise ConfigurationError("single-process command input exceeds 1 MiB")
            boundary.validate_single_process()
        if stdin_bytes is not None and len(stdin_bytes) > max_stdin:
            return RawExecution(
                status=ExecutionStatus.REJECTED,
                resources=ResourceVector(),
                error_type="ConfigurationError",
                error_message="command input exceeds configured max_stdin_bytes",
            )

        kwargs: dict[str, Any] = {}
        if 'native_sandbox' in config:
            if cwd is not None and str(cwd) != boundary.project_root:
                raise ConfigurationError('command working directory differs from native sandbox project')
            cwd = boundary.project_root
        if os.name == "posix":
            kwargs["start_new_session"] = True
        elif os.name == "nt":  # pragma: no cover - Windows CI is not available here
            kwargs["creationflags"] = 0x00000200  # CREATE_NEW_PROCESS_GROUP

        started = time.perf_counter()
        observed: set[psutil.Process] = set()
        stream_error_type = "STREAM_OBSERVER_FAILED"
        if 'native_sandbox' in config and boundary.single_process:
            from ..hosts.codex_native_process import execute_single_process
            if context.invocation_check is not None:
                context.invocation_check()
            result = await execute_single_process(boundary, argv, environment, stdin_bytes,
                                                  timeout, max_output, self.stdout_observer)
            stdout_data, stdout_total = result.stdout, result.stdout_total
            stderr_data, stderr_total = result.stderr, result.stderr_total
            metrics, exit_code = result.metrics, result.exit_code
            timed_out, stream_error = result.timed_out, result.stream_error
            stream_error_type = result.error_type or stream_error_type
            background_processes = False
            cleanup_incomplete = result.cleanup_incomplete
            observed = set()
        else:
            try:
                if context.invocation_check is not None:
                    context.invocation_check()
                if 'native_sandbox' in config:
                    # Hash once per actual launch, after the last authority check.
                    # Eligibility checks compile policy without repeatedly reading the binary.
                    argv = boundary.argv(argv)
                process = await asyncio.create_subprocess_exec(
                    *argv,
                    stdin=asyncio.subprocess.PIPE
                    if stdin_bytes is not None
                    else asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=environment,
                    **kwargs,
                )
            except (OSError, ValueError) as exc:
                return RawExecution(
                    status=ExecutionStatus.FAILED,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    resources=ResourceVector(),
                    metadata={"argv": argv[:1]},
                )

            stop = asyncio.Event()
            observed = set()
            monitor_task = asyncio.create_task(_monitor_process(process.pid, stop, observed=observed))
            stdout_task = asyncio.create_task(_read_limited(process.stdout, max_output, self.stdout_observer))
            stderr_task = asyncio.create_task(_read_limited(process.stderr, max_output))
            completion = asyncio.gather(process.wait(), stdout_task, stderr_task)
            timed_out = False
            stream_error = False
            background_processes = False
            cleanup_incomplete = False
            try:
                async with asyncio.timeout(timeout):
                    if stdin_bytes is not None and process.stdin is not None:
                        process.stdin.write(stdin_bytes)
                        with suppress(BrokenPipeError, ConnectionResetError):
                            await process.stdin.drain()
                        process.stdin.close()
                    await asyncio.shield(completion)
            except (Exception, asyncio.CancelledError) as exc:
                timed_out = isinstance(exc, (TimeoutError, asyncio.CancelledError))
                stream_error = not timed_out
                # Process handles retain creation-time identity; PID reuse must never
                # let cleanup signal an unrelated process. Sessions may change while
                # the command runs, so process-group cancellation alone is insufficient.
                if sys.platform != "win32":
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGTERM)
                else:  # pragma: no cover
                    process.terminate()
                for owned in observed:
                    if owned.pid != process.pid:
                        with suppress(psutil.Error):
                            owned.terminate()
                try:
                    draining = asyncio.gather(process.wait(), stdout_task, stderr_task, return_exceptions=True)
                    await asyncio.wait_for(asyncio.shield(draining), timeout=2.0)
                except TimeoutError:
                    if sys.platform != "win32":
                        with suppress(ProcessLookupError):
                            os.killpg(process.pid, signal.SIGKILL)
                    else:  # pragma: no cover
                        process.kill()
                    await process.wait()
            finally:
                if timed_out or stream_error or 'native_sandbox' in config:
                    for owned in observed:
                        if owned.pid == process.pid:
                            continue
                        try:
                            if owned.is_running() and owned.status() != psutil.STATUS_ZOMBIE:
                                background_processes = True
                                owned.kill()
                        except psutil.NoSuchProcess:
                            pass
                        except psutil.Error:
                            cleanup_incomplete = True
                stop.set()

            captured = await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            stdout_data, stdout_total = captured[0] if isinstance(captured[0], tuple) else (b"", 0)
            stderr_data, stderr_total = captured[1] if isinstance(captured[1], tuple) else (b"", 0)
            metrics = await monitor_task
            exit_code = process.returncode
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        stdout = stdout_data.decode("utf-8", errors="replace")
        stderr = stderr_data.decode("utf-8", errors="replace")
        actual = ResourceVector(
            latency_ms=elapsed_ms,
            cpu_ms=metrics.cpu_ms,
            memory_mb_seconds=metrics.memory_mb_seconds,
            peak_memory_mb=metrics.peak_memory_mb,
            context_tokens=approximate_tokens(stdout),
        )
        metadata = {
            "executable": argv[0],
            "stdout_bytes": stdout_total,
            "stderr_bytes": stderr_total,
            "stdout_truncated": stdout_total > len(stdout_data),
            "stderr_truncated": stderr_total > len(stderr_data),
        }
        if 'native_sandbox' in config:
            from ..hosts.codex_sandbox import native_backend_digest
            metadata['enforcement_backend_digest'] = native_backend_digest(boundary)
            if boundary.single_process:
                metadata['native_output_truncated'] = result.output_truncated
                if result.output_truncated:
                    metadata['output_byte_measurement'] = 'observed native stream bytes; cap leaves remainder unknown'
                metadata['guard_stdout_bytes'] = result.guard_stdout_bytes
                metadata['process_sampling'] = 'native host and descendants after initialization; startup sampling unavailable'
            metadata['process_cleanup'] = {
                'boundary': ('native App Server EOF ownership and hard no-fork session leader' if boundary.single_process
                             else 'process group and observed descendants; not complete containment'),
                'observed_processes': len(observed), 'cleanup_incomplete': cleanup_incomplete,
            }
        accounting = ResourceAccounting()
        if stream_error:
            return RawExecution(status=ExecutionStatus.FAILED, resources=actual,
                exit_code=exit_code, error_type=stream_error_type,
                error_message=("native command failed; inspect recorded cleanup state" if boundary.single_process
                               else "command stream processing failed") if 'native_sandbox' in config
                               else "command stream processing failed", metadata=metadata)
        capture = config.get("usage_capture")
        if capture is not None:
            if not isinstance(capture, dict) or capture.get("type") != "codex_jsonl":
                raise ConfigurationError("command usage_capture must declare type=codex_jsonl")
            model = capture.get("model")
            if not isinstance(model, str) or not model:
                raise ConfigurationError("Codex JSONL capture requires a model")
            try:
                lines = stdout.splitlines()
                accounting.model_usage.append(
                    parse_codex_jsonl(
                        lines,
                        provider=str(capture.get("provider", "openai")),
                        model=model,
                        access_channel=ModelAccessChannel(
                            str(capture.get("access_channel", "subscription"))
                        ),
                        max_bytes=max_output,
                    )
                )
                required_command = capture.get("required_command_substring")
                if required_command is not None:
                    if not isinstance(required_command, str) or not required_command:
                        raise ConfigurationError(
                            "required_command_substring must be a non-empty string"
                        )
                    commands = [
                        event["item"]
                        for line in lines
                        if isinstance((event := json.loads(line)), dict)
                        and event.get("type") == "item.completed"
                        and isinstance(event.get("item"), dict)
                        and event["item"].get("type") == "command_execution"
                    ]
                    if (
                        len(commands) != 1
                        or commands[0].get("status") != "completed"
                        or commands[0].get("exit_code") != 0
                        or required_command not in commands[0].get("command", "")
                    ):
                        raise ConfigurationError(
                            "Codex did not complete exactly one required command execution"
                        )
                    metadata["codex_command_executions"] = 1
            except Exception as exc:
                return RawExecution(
                    status=ExecutionStatus.FAILED,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=exit_code,
                    resources=actual,
                    error_type=type(exc).__name__,
                    error_message="command usage capture failed",
                    accounting=accounting,
                    metadata=metadata,
                )
        if not timed_out and (background_processes or cleanup_incomplete):
            return RawExecution(status=ExecutionStatus.FAILED, resources=actual,
                exit_code=exit_code, error_type='BACKGROUND_PROCESS_REJECTED',
                error_message='native command left observed background processes; inspect effects before retrying',
                accounting=accounting, metadata=metadata)
        if timed_out:
            return RawExecution(
                status=ExecutionStatus.TIMEOUT,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                resources=actual,
                error_type="TimeoutError",
                error_message=f"command exceeded {timeout:g} seconds",
                accounting=accounting,
                metadata=metadata,
            )
        if exit_code != 0:
            return RawExecution(
                status=ExecutionStatus.FAILED,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                resources=actual,
                error_type="CommandExitError",
                error_message=f"command exited with status {exit_code}",
                accounting=accounting,
                metadata=metadata,
            )
        try:
            output = parse_output(stdout, config.get("output"))
        except Exception as exc:
            return RawExecution(
                status=ExecutionStatus.FAILED,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                resources=actual,
                error_type=type(exc).__name__,
                error_message=str(exc),
                accounting=accounting,
                metadata=metadata,
            )
        actual.context_tokens = approximate_tokens(output)
        return RawExecution(
            status=ExecutionStatus.SUCCESS,
            output=output,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            resources=actual,
            accounting=accounting,
            metadata=metadata,
        )
