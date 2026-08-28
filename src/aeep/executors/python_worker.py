"""Bounded JSON worker for isolated Python callables."""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import sys
from contextlib import redirect_stdout
from typing import Any

from .python import load_callable


def _apply_limits(cpu_seconds: int | None, memory_mb: int | None) -> None:
    if sys.platform == "win32":
        return
    import resource

    if cpu_seconds is not None:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    if memory_mb is not None:
        limit = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


async def _invoke(payload: dict[str, Any]) -> Any:
    function = load_callable(str(payload["callable"]))
    mode = str(payload.get("argument_mode", "kwargs"))
    input_value = payload.get("input", {})
    if mode == "kwargs":
        result = function(**input_value)
    elif mode == "dict":
        result = function(input_value)
    elif mode == "request":
        from ..models import ActionRequest

        result = function(ActionRequest.model_validate(payload["request"]))
    else:
        raise ValueError(f"unsupported Python argument_mode {mode!r}")
    return await result if inspect.isawaitable(result) else result


def main() -> int:
    try:
        encoded = sys.stdin.buffer.read(1_333_337)
        if len(encoded) > 1_333_336:
            raise ValueError("isolated Python input exceeds limit")
        payload = json.loads(base64.b64decode(encoded, validate=True))
        if not isinstance(payload, dict):
            raise ValueError("isolated Python input must be an object")
        _apply_limits(payload.get("cpu_limit_seconds"), payload.get("memory_limit_mb"))
        with redirect_stdout(sys.stderr):
            output = asyncio.run(_invoke(payload))
        response = {"ok": True, "output": output}
    except Exception as exc:
        response = {
            "ok": False,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    try:
        sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    except (TypeError, ValueError):
        sys.stdout.write(
            '{"ok":false,"error_type":"TypeError",'
            '"error_message":"isolated Python output is not JSON serializable"}'
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
