"""Execute one bounded action through a locally registered managed host."""

from __future__ import annotations

import asyncio
import json

from ..errors import ConfigurationError
from ..hosts import HostProbeStatus, ManagedHostExecutionContext, ManagedHostRegistry
from ..models import ExecutionStatus, RawExecution
from ..templates import render
from .base import BaseExecutor, ExecutionContext


class ManagedHostExecutor(BaseExecutor):
    def __init__(self, registry: ManagedHostRegistry) -> None:
        self.registry = registry

    async def execute(self, context: ExecutionContext) -> RawExecution:
        config = context.spec.managed_host_config()
        adapter = self.registry.get(config.adapter_id)
        probe = await asyncio.wait_for(adapter.probe(), timeout=config.timeout_seconds)
        if probe.status is not HostProbeStatus.READY:
            return RawExecution(
                status=ExecutionStatus.REJECTED,
                error_type=probe.status.value.upper(),
                error_message=probe.reason or probe.status.value,
                metadata={"adapter_id": config.adapter_id, "protocol_version": probe.protocol_version},
            )
        instruction = str(
            render(
                config.instructions,
                {"input": context.request.input, "action": context.request.model_dump(mode="json")},
            )
        )
        attempt_id = context.attempt_id or f"{context.request.action_id}:{context.attempt}"
        raw = await asyncio.wait_for(
            adapter.execute(
                ManagedHostExecutionContext(
                    request=context.request,
                    instruction=instruction,
                    config=config,
                    attempt=context.attempt,
                    attempt_id=attempt_id,
                )
            ),
            timeout=config.timeout_seconds,
        )
        try:
            encoded = (
                json.dumps(raw.output, ensure_ascii=False).encode()
                if config.output_mode == "json"
                else str(raw.output).encode()
            )
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("managed-host output is not serializable") from exc
        if len(encoded) > config.max_message_bytes:
            raise ConfigurationError("managed-host output exceeds configured message limit")
        raw.metadata.update(
            {
                "adapter_id": config.adapter_id,
                "protocol_version": probe.protocol_version,
                "response_bytes": len(encoded),
            }
        )
        return raw

    async def close(self) -> None:
        await self.registry.close()
