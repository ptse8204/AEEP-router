"""Safe argv-based local command executor."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import psutil

from ..errors import ConfigurationError
from ..models import ExecutionStatus, RawExecution, ResourceVector
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
    pid: int, stop: asyncio.Event, interval: float = 0.01
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


async def _read_limited(stream: asyncio.StreamReader | None, limit: int) -> tuple[bytes, int]:
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
            captured.extend(chunk[: max(0, limit - len(captured))])
    return bytes(captured), total


def _minimal_environment() -> dict[str, str]:
    names = ["PATH", "HOME", "USERPROFILE", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT"]
    return {name: os.environ[name] for name in names if name in os.environ}


class CommandExecutor(BaseExecutor):
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
        argv = render(argv_template, values)
        if not all(isinstance(item, (str, int, float)) for item in argv):
            raise ConfigurationError("rendered command arguments must be scalar values")
        argv = [str(item) for item in argv]
        timeout = float(config.get("timeout_seconds", 60.0))
        max_output = int(config.get("max_output_bytes", 1_000_000))
        cwd = config.get("cwd")
        environment = (
            dict(os.environ) if config.get("inherit_env", False) else _minimal_environment()
        )
        configured_env = config.get("env", {})
        if not isinstance(configured_env, dict):
            raise ConfigurationError("command config.env must be a mapping")
        environment.update(
            {
                str(key): str(value)
                for key, value in render(configured_env, values, allow_env=True).items()
            }
        )
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

        kwargs: dict[str, Any] = {}
        if os.name == "posix":
            kwargs["start_new_session"] = True
        elif os.name == "nt":  # pragma: no cover - Windows CI is not available here
            kwargs["creationflags"] = 0x00000200  # CREATE_NEW_PROCESS_GROUP

        started = time.perf_counter()
        try:
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
                resources=ResourceVector(monetary_usd=context.estimate.resources.monetary_usd),
                metadata={"argv": argv[:1]},
            )

        stop = asyncio.Event()
        monitor_task = asyncio.create_task(_monitor_process(process.pid, stop))
        stdout_task = asyncio.create_task(_read_limited(process.stdout, max_output))
        stderr_task = asyncio.create_task(_read_limited(process.stderr, max_output))
        if stdin_bytes is not None and process.stdin is not None:
            process.stdin.write(stdin_bytes)
            await process.stdin.drain()
            process.stdin.close()

        timed_out = False
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except TimeoutError:
            timed_out = True
            if os.name == "posix":
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGTERM)
            else:  # pragma: no cover
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except TimeoutError:
                if os.name == "posix":
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
                else:  # pragma: no cover
                    process.kill()
                await process.wait()
        finally:
            stop.set()

        stdout_data, stdout_total = await stdout_task
        stderr_data, stderr_total = await stderr_task
        metrics = await monitor_task
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        stdout = stdout_data.decode("utf-8", errors="replace")
        stderr = stderr_data.decode("utf-8", errors="replace")
        actual = ResourceVector(
            monetary_usd=context.estimate.resources.monetary_usd,
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
        if timed_out:
            return RawExecution(
                status=ExecutionStatus.TIMEOUT,
                stdout=stdout,
                stderr=stderr,
                exit_code=process.returncode,
                resources=actual,
                error_type="TimeoutError",
                error_message=f"command exceeded {timeout:g} seconds",
                metadata=metadata,
            )
        if process.returncode != 0:
            return RawExecution(
                status=ExecutionStatus.FAILED,
                stdout=stdout,
                stderr=stderr,
                exit_code=process.returncode,
                resources=actual,
                error_type="CommandExitError",
                error_message=f"command exited with status {process.returncode}",
                metadata=metadata,
            )
        try:
            output = parse_output(stdout, config.get("output"))
        except Exception as exc:
            return RawExecution(
                status=ExecutionStatus.FAILED,
                stdout=stdout,
                stderr=stderr,
                exit_code=process.returncode,
                resources=actual,
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata=metadata,
            )
        actual.context_tokens = approximate_tokens(output)
        return RawExecution(
            status=ExecutionStatus.SUCCESS,
            output=output,
            stdout=stdout,
            stderr=stderr,
            exit_code=process.returncode,
            resources=actual,
            metadata=metadata,
        )
