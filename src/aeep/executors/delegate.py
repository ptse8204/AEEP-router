"""Return a structured execution plan for routes controlled by the host agent."""

from __future__ import annotations

from ..errors import ConfigurationError
from ..models import ExecutionStatus, RawExecution, ResourceVector
from ..templates import render
from .base import BaseExecutor, ExecutionContext


class DelegateExecutor(BaseExecutor):
    async def execute(self, context: ExecutionContext) -> RawExecution:
        template = context.spec.config.get("instructions")
        if not isinstance(template, str) or not template.strip():
            raise ConfigurationError(
                f"delegate executor {context.spec.id} requires config.instructions"
            )
        values = {"input": context.request.input, "action": context.request.model_dump(mode="json")}
        instructions = str(render(template, values))
        return RawExecution(
            status=ExecutionStatus.DELEGATED,
            output={
                "executor_id": context.spec.id,
                "capability": context.spec.capability,
                "instructions": instructions,
                "input": context.request.input,
                "report_outcome": {
                    "decision_id": "provided-by-route-decision",
                    "executor_id": context.spec.id,
                },
            },
            resources=ResourceVector(),
            metadata={"instructions": instructions},
        )
