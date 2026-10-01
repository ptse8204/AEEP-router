"""Execute one bounded action through a locally registered managed host."""

from __future__ import annotations

import asyncio
import json

from ..hosts import HostProbeStatus, ManagedHostExecutionContext, ManagedHostRegistry
from ..models import ExecutionStatus, RawExecution
from ..store import ReceiptStore
from ..templates import render
from .base import BaseExecutor, ExecutionContext


class ManagedHostExecutor(BaseExecutor):
    def __init__(self, registry: ManagedHostRegistry, store: ReceiptStore | None = None) -> None:
        self.registry = registry
        self.store = store

    async def execute(self, context: ExecutionContext) -> RawExecution:
        config = context.spec.managed_host_config()
        adapter = self.registry.get(config.adapter_id)
        if config.input_tree is not None:
            self.registry.capabilities(config.adapter_id).require(["input_tree"])
        probe = await asyncio.wait_for(adapter.probe(), timeout=config.timeout_seconds)
        if probe.status is not HostProbeStatus.READY:
            return RawExecution(
                status=ExecutionStatus.REJECTED,
                error_type=probe.status.value.upper(),
                error_message=probe.reason or probe.status.value,
                metadata={"adapter_id": config.adapter_id, "protocol_version": probe.protocol_version,
                          "host_failure_code": "host_request_rejected"},
            )
        prompt_input = dict(context.request.input)
        if config.input_tree is not None:
            prompt_input.pop("files", None)
            prompt_input["root"] = "/workspace/case-tree"
        if config.artifact is not None:
            prompt_input.pop(config.artifact.input_field, None)
            prompt_input["input_path"] = "/workspace/" + config.artifact.input_name
            prompt_input["output_path"] = "/workspace/" + config.artifact.output_name
        prompt_action = context.request.model_dump(mode="json")
        prompt_action["input"] = prompt_input
        instruction = str(
            render(
                config.instructions,
                {"input": prompt_input, "action": prompt_action},
            )
        )
        attempt_id = context.attempt_id or f"{context.request.action_id}:{context.attempt}"
        expected = self.store.expected_host_runtime_digests.get(context.spec.id) if self.store else None
        boundary = context.invocation_check() if context.invocation_check is not None else None
        host_context = ManagedHostExecutionContext(
            request=context.request, instruction=instruction, config=config,
            attempt=context.attempt, attempt_id=attempt_id,
            output_schema=context.spec.output_schema,
            approved_side_effect=context.approved_side_effect.value,
            expected_runtime_digest=expected,
            invocation_check=context.invocation_check,
        )
        start = getattr(adapter, "start", None)
        if start is None:
            raw = await asyncio.wait_for(adapter.execute(host_context), timeout=config.timeout_seconds)
        else:
            handle = await start(host_context)
            try:
                raw = await asyncio.wait_for(handle.task, timeout=config.timeout_seconds)
            finally:
                if not handle.task.done():
                    await adapter.interrupt(attempt_id)
        if raw.status is ExecutionStatus.REJECTED:
            raw.metadata.setdefault("host_failure_code", "host_request_rejected")
        try:
            encoded = (
                json.dumps(raw.output, ensure_ascii=False).encode()
                if config.output_mode == "json"
                else str(raw.output).encode()
            )
        except (TypeError, ValueError):
            raw.status = ExecutionStatus.FAILED
            raw.output = None
            raw.error_type = "HOST_OUTPUT_INVALID"
            raw.error_message = "managed-host output is not serializable"
            return raw
        if len(encoded) > config.max_message_bytes:
            raw.status = ExecutionStatus.FAILED
            raw.output = None
            raw.error_type = "HOST_OUTPUT_TOO_LARGE"
            raw.error_message = "managed-host output exceeds configured message limit"
        raw.metadata.update(
            {
                "adapter_id": config.adapter_id,
                "protocol_version": probe.protocol_version,
                "response_bytes": len(encoded),
            }
        )
        if boundary is not None:
            raw.metadata["boundary_digest"] = boundary
        return raw

    async def close(self) -> None:
        await self.registry.close()
