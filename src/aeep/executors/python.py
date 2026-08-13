"""In-process Python callable executor."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import time
from collections.abc import Callable
from typing import Any, cast

import psutil

from ..errors import ConfigurationError
from ..models import ExecutionStatus, RawExecution, ResourceVector
from ..profiler import approximate_tokens
from .base import BaseExecutor, ExecutionContext


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
            monetary_usd=context.estimate.resources.monetary_usd,
            latency_ms=elapsed * 1000.0,
            cpu_ms=max(
                0.0,
                (
                    cpu_after.user
                    + cpu_after.system
                    - cpu_before.user
                    - cpu_before.system
                )
                * 1000.0,
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
