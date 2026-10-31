"""Microsoft Agent Framework core over existing approved AEEP dispatch.

Only task and receipt references cross the SDK workflow. The supplied dispatcher
owns permissions, reservations, attempts, predecessor output handles and cleanup.
This adapter adds no provider, model, scheduler service or persistence backend.
Interrupted runs cannot be restarted through this object; canonical recovery is
required before an operator prepares another workflow. SDK checkpoint restoration
is deliberately unsupported until its identity and replay rules are verified.
"""

from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from importlib.metadata import version
from itertools import pairwise
from typing import Any, Literal

from pydantic import Field, model_validator

from aeep.assessment.models import content_digest
from aeep.models import ExecutionReceipt

from .install_runtime import digest
from .models import ContractModel, Digest, Identifier


class PipelineStep(ContractModel):
    executor_id: Identifier
    fingerprint: str = Field(pattern=r'^sha256:[a-f0-9]{64}$')


class PipelineDefinition(ContractModel):
    schema_version: Literal["aeep.toolkit.agent-framework.v1"] = "aeep.toolkit.agent-framework.v1"
    steps: tuple[PipelineStep, ...] = Field(min_length=1, max_length=64)


class PipelineState(ContractModel):
    definition_ref: Digest
    run_id: Identifier
    task_ref: Digest
    next_step: int = Field(strict=True, ge=0, le=64)
    receipt_refs: tuple[Digest, ...]
    succeeded: bool = Field(strict=True)

    @model_validator(mode="after")
    def complete_lineage(self) -> PipelineState:
        if len(self.receipt_refs) != self.next_step:
            raise ValueError("workflow state lost its receipt lineage")
        return self


FrameworkDispatcher = Callable[[str, str, str, tuple[str, ...], str], Awaitable[ExecutionReceipt]]


@dataclass
class PreparedPipeline:
    upstream: Any
    definition_ref: str
    run_id: str
    steps: int
    started: bool = False

    async def run(self, *, task_ref: str) -> dict[str, Any]:
        state = PipelineState(
            definition_ref=self.definition_ref,
            run_id=self.run_id,
            task_ref=task_ref,
            next_step=0,
            receipt_refs=(),
            succeeded=True,
        )
        if self.started:
            raise ValueError(
                "workflow already started; reconcile its canonical attempts before new dispatch"
            )
        # Charge/reconcile at the dispatcher. Even a cancelled or failed SDK
        # invocation must never silently restart this run with empty state.
        self.started = True
        result = await self.upstream.run(state.model_dump(mode="json"))
        outputs = result.get_outputs()
        if len(outputs) != 1:
            raise ValueError("SDK workflow has no single terminal receipt state")
        final = PipelineState.model_validate(outputs[0])
        if (
            final.definition_ref != self.definition_ref
            or final.run_id != self.run_id
            or final.task_ref != task_ref
            or final.next_step > self.steps
            or (final.succeeded and final.next_step != self.steps)
        ):
            raise ValueError("SDK workflow terminal identity or step count differs")
        return {
            "completed": final.succeeded,
            "state": final.model_dump(mode="json"),
            "candidate_usefulness": "NOT_ASSESSED",
            "selection_usefulness": "NOT_ASSESSED",
            "recovery": "existing-dispatcher-reconciliation; SDK checkpoint restoration unsupported",
        }


def compile_pipeline(
    definition: PipelineDefinition,
    *,
    run_id: str,
    dispatch: FrameworkDispatcher,
) -> PreparedPipeline:
    """Load the real optional core SDK only in a reviewed component runtime."""
    from pydantic import TypeAdapter

    TypeAdapter(Identifier).validate_python(run_id)
    if version("agent-framework-core") != "1.21.0":
        raise ValueError("Agent Framework runtime differs from the reviewed version")
    module = importlib.import_module("agent_framework")
    definition_ref = digest(definition)
    steps = tuple(step.model_copy(deep=True) for step in definition.steps)

    def callback(index: int) -> Callable[..., Awaitable[None]]:
        async def run(message: dict[str, Any], context: Any) -> None:
            state = PipelineState.model_validate(message)
            if (
                state.definition_ref != definition_ref
                or state.run_id != run_id
                or state.next_step != index
                or not state.succeeded
            ):
                raise ValueError("SDK workflow step differs from the approved lineage")
            key = digest(
                {
                    "definition": definition_ref,
                    "run_id": run_id,
                    "task": state.task_ref,
                    "step": index,
                    "predecessors": state.receipt_refs,
                }
            )
            step = steps[index]
            receipt = ExecutionReceipt.model_validate(
                await dispatch(
                    step.executor_id, key, state.task_ref, state.receipt_refs, step.fingerprint
                )
            )
            if (
                receipt.executor_id != step.executor_id
                or receipt.executor_fingerprint != step.fingerprint
                or receipt.action_id != key
                or type(receipt.execution_success) is not bool
                or (receipt.execution_success and receipt.status.value != "success")
            ):
                raise ValueError(
                    "dispatch receipt lacks the exact approved executor or terminal evidence"
                )
            successor = PipelineState(
                definition_ref=definition_ref,
                run_id=run_id,
                task_ref=state.task_ref,
                next_step=index + 1,
                receipt_refs=(*state.receipt_refs, content_digest(receipt)),
                succeeded=receipt.execution_success,
            )
            if index + 1 == len(steps) or not receipt.execution_success:
                await context.yield_output(successor.model_dump(mode="json"))
            else:
                await context.send_message(successor.model_dump(mode="json"))

        return run

    nodes = [
        module.FunctionExecutor(
            callback(index),
            id=f"approved-step-{index}",
            input=dict,
            output=dict,
            workflow_output=dict,
        )
        for index in range(len(steps))
    ]
    builder = module.WorkflowBuilder(
        start_executor=nodes[0],
        max_iterations=len(nodes) + 1,
        name="aeep-" + definition_ref,
        output_from="all",
    )
    for left, right in pairwise(nodes):
        builder.add_edge(left, right)
    return PreparedPipeline(builder.build(), definition_ref, run_id, len(nodes))
