"""In-process Python callable executor."""

from __future__ import annotations

import asyncio
import base64
import importlib
import inspect
import json
import sys
import time
from collections.abc import Callable
from typing import Any, cast

import psutil

from ..errors import ConfigurationError
from ..models import ExecutionStatus, ExecutorKind, RawExecution, ResourceVector
from ..profiler import approximate_tokens
from .base import BaseExecutor, ExecutionContext
from .command import CommandExecutor


def load_callable(path: str) -> Callable[..., Any]:
    if ":" not in path:
        raise ConfigurationError("Python callable must use module.path:function syntax")
    module_name, attribute_path = path.split(":", 1)
    try:
        value: Any = importlib.import_module(module_name)
        for part in attribute_path.split("."):
            value = getattr(value, part)
    except (ImportError, AttributeError) as exc:
        raise ConfigurationError(f"cannot import Python callable {path!r}: {exc}") from exc
    if not callable(value):
        raise ConfigurationError(f"configured object {path!r} is not callable")
    return cast(Callable[..., Any], value)


class PythonExecutor(BaseExecutor):
    async def execute(self, context: ExecutionContext) -> RawExecution:
        isolation = str(context.spec.config.get("isolation", "in_process"))
        if isolation == "subprocess":
            return await self._execute_subprocess(context)
        if isolation != "in_process":
            raise ConfigurationError(f"unsupported Python isolation {isolation!r}")
        callable_path = context.spec.config.get("callable")
        if not isinstance(callable_path, str):
            raise ConfigurationError(f"Python executor {context.spec.id} requires config.callable")
        function = load_callable(callable_path)
        mode = str(context.spec.config.get("argument_mode", "kwargs"))
        timeout = float(context.spec.config.get("timeout_seconds", 60.0))
        if not inspect.iscoroutinefunction(function):
            # Thread-pool creation is harness cold-start overhead shared by all
            # synchronous Python routes. Warm it before profiling so the first
            # benchmark candidate is not penalized merely for running first.
            await asyncio.to_thread(lambda: None)
        process = psutil.Process()
        cpu_before = process.cpu_times()
        rss_before = process.memory_info().rss / (1024 * 1024)
        started = time.perf_counter()

        async def invoke() -> Any:
            if mode == "kwargs":
                arguments = context.request.input
                if inspect.iscoroutinefunction(function):
                    return await function(**arguments)
                return await asyncio.to_thread(function, **arguments)
            if mode == "dict":
                if inspect.iscoroutinefunction(function):
                    return await function(context.request.input)
                return await asyncio.to_thread(function, context.request.input)
            if mode == "request":
                if inspect.iscoroutinefunction(function):
                    return await function(context.request)
                return await asyncio.to_thread(function, context.request)
            raise ConfigurationError(f"unsupported Python argument_mode {mode!r}")

        try:
            output = await asyncio.wait_for(invoke(), timeout=timeout)
            status = ExecutionStatus.SUCCESS
            error_type = None
            error_message = None
        except TimeoutError:
            output = None
            status = ExecutionStatus.TIMEOUT
            error_type = "TimeoutError"
            error_message = f"Python callable exceeded {timeout:g} seconds"
        except Exception as exc:  # The callable is an integration boundary.
            output = None
            status = ExecutionStatus.FAILED
            error_type = type(exc).__name__
            error_message = str(exc)

        elapsed = max(0.0, time.perf_counter() - started)
        cpu_after = process.cpu_times()
        rss_after = process.memory_info().rss / (1024 * 1024)
        incremental_memory = max(0.0, rss_after - rss_before)
        resources = ResourceVector(
            latency_ms=elapsed * 1000.0,
            cpu_ms=max(
                0.0,
                (cpu_after.user + cpu_after.system - cpu_before.user - cpu_before.system) * 1000.0,
            ),
            memory_mb_seconds=incremental_memory * elapsed,
            peak_memory_mb=incremental_memory,
            context_tokens=approximate_tokens(output) if output is not None else 0,
        )
        return RawExecution(
            status=status,
            output=output,
            resources=resources,
            error_type=error_type,
            error_message=error_message,
            metadata={"callable": callable_path, "argument_mode": mode},
        )

    async def _execute_subprocess(self, context: ExecutionContext) -> RawExecution:
        config = context.spec.config
        callable_path = config.get("callable")
        if not isinstance(callable_path, str):
            raise ConfigurationError(f"Python executor {context.spec.id} requires config.callable")
        envelope = {
            "callable": callable_path,
            "argument_mode": str(config.get("argument_mode", "kwargs")),
            "input": context.request.input,
            "request": context.request.model_dump(mode="json"),
            "cpu_limit_seconds": config.get("cpu_limit_seconds"),
            "memory_limit_mb": config.get("memory_limit_mb"),
        }
        stdin = base64.b64encode(
            json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode()
        ).decode("ascii")
        if len(stdin) > int(config.get("max_stdin_bytes", 1_000_000)):
            return RawExecution(
                status=ExecutionStatus.REJECTED,
                error_type="ConfigurationError",
                error_message="isolated Python input exceeds configured limit",
            )
        command_spec = context.spec.model_copy(deep=True)
        command_spec.kind = ExecutorKind.COMMAND
        command_spec.config = {
            "argv": [sys.executable, "-m", "aeep.executors.python_worker"],
            "stdin": stdin,
            "timeout_seconds": config.get("timeout_seconds", 60.0),
            "max_stdin_bytes": config.get("max_stdin_bytes", 1_000_000),
            "max_output_bytes": config.get("max_output_bytes", 1_000_000),
            "inherit_env": bool(config.get("inherit_env", False)),
            "env": config.get("env", {}),
            "cwd": config.get("cwd"),
            "output": {"type": "json"},
        }
        raw = await CommandExecutor().execute(
            ExecutionContext(
                request=context.request,
                spec=command_spec,
                estimate=context.estimate,
                attempt=context.attempt,
                prepared_id=context.prepared_id,
                quote_id=context.quote_id,
                attempt_id=context.attempt_id,
            )
        )
        raw.metadata.update({"callable": callable_path, "isolation": "subprocess"})
        if raw.status is not ExecutionStatus.SUCCESS:
            return raw
        response = raw.output
        if not isinstance(response, dict) or not isinstance(response.get("ok"), bool):
            raw.status = ExecutionStatus.FAILED
            raw.output = None
            raw.error_type = "ProtocolError"
            raw.error_message = "isolated Python worker returned an invalid envelope"
            return raw
        if not response["ok"]:
            raw.status = ExecutionStatus.FAILED
            raw.output = None
            raw.error_type = str(response.get("error_type", "ExecutionError"))
            raw.error_message = str(response.get("error_message", "isolated Python failed"))
            return raw
        raw.output = response.get("output")
        raw.resources.context_tokens = approximate_tokens(raw.output)
        return raw
