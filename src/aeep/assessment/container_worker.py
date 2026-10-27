"""Inside-container adapter entrypoint. The parent router owns policy and receipts."""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from typing import Any

from ..errors import ConfigurationError
from ..executors.base import BaseExecutor, ExecutionContext
from ..executors.command import CommandExecutor
from ..executors.mcp import MCPExecutor
from ..executors.python import PythonExecutor
from ..models import ActionRequest, ExecutorKind, ExecutorSpec, SideEffect


async def run(payload: dict[str, Any]) -> dict[str, Any]:
    spec = ExecutorSpec.model_validate(payload["spec"])
    adapters: dict[ExecutorKind, type[BaseExecutor]] = {
        ExecutorKind.COMMAND: CommandExecutor,
        ExecutorKind.PYTHON: PythonExecutor,
        ExecutorKind.MCP: MCPExecutor,
    }
    if spec.kind not in adapters:
        raise ConfigurationError("unsupported contained adapter")
    adapter = adapters[spec.kind]()
    try:
        raw = await adapter.execute(
            ExecutionContext(
                request=ActionRequest.model_validate(payload["request"]),
                spec=spec,
                estimate=spec.estimate,
                attempt=payload["attempt"],
                attempt_id=payload.get("attempt_id"),
                approved_side_effect=SideEffect(payload["approved_side_effect"]),
            )
        )
        raw.stdout = raw.stderr = None
        # Candidate-controlled usage is a claim. The parent never adopts it as an observation.
        return raw.model_dump(mode="json")
    finally:
        await adapter.close()


def _input_limit(argv: list[str]) -> int:
    if not argv:
        return 2_000_000
    if (len(argv) != 2 or argv[0] != '--input-limit'
            or not argv[1].isascii() or not argv[1].isdecimal()):
        raise ConfigurationError('invalid container input limit argument')
    limit = int(argv[1])
    if not 2_000_000 <= limit <= 17_000_000:
        raise ConfigurationError('container input exceeds the reviewed transport ceiling')
    return limit


def main() -> None:
    limit = _input_limit(sys.argv[1:])
    data = sys.stdin.buffer.read(limit + 1)
    if len(data) > limit:
        raise ConfigurationError("container input exceeds its limit")
    with contextlib.redirect_stdout(sys.stderr):
        result = asyncio.run(run(json.loads(data)))
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
