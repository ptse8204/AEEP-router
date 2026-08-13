"""Select work performed by the current subscribed host without calling its API."""

from __future__ import annotations

from ..errors import ConfigurationError
from ..models import ExecutionStatus, RawExecution, ResourceVector
from ..templates import render
from .base import BaseExecutor, ExecutionContext


class HostExecutor(BaseExecutor):
    async def execute(self, context: ExecutionContext) -> RawExecution:
        template = context.spec.config.get("instructions")
        if not isinstance(template, str) or not template.strip():
            raise ConfigurationError(
                f"host executor {context.spec.id} requires config.instructions"
            )
        values = {"input": context.request.input, "action": context.request.model_dump(mode="json")}
        instructions = str(render(template, values))
        return RawExecution(
            status=ExecutionStatus.HOST_SELECTED,
            output={
                "status": "HOST_SELECTED",
                "executor_id": context.spec.id,
                "resource_pool": context.spec.resource_pool,
                "capability": context.spec.capability,
                "instructions": instructions,
                "input": context.request.input,
                "report_outcome": {
                    "decision_id": "provided-by-route-decision",
                    "executor_id": context.spec.id,
                },
            },
            resources=ResourceVector(),
            metadata={
                "instructions": instructions,
                "resource_pool": context.spec.resource_pool,
            },
        )
