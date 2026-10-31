"""Thin LangGraph composition over an operator-supplied approved dispatcher.

No provider, shell command, generated code or artifact content is accepted in a
graph. The dispatcher owns authority, durable attempts, receipts and recovery.
LangGraph checkpoints contain only task/evidence references and counters. A
caller must supply a reviewed checkpointer for recovery across process restarts.
"""

from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from pydantic import Field, model_validator

from .models import ContractModel, Digest, Identifier


class Step(ContractModel):
    executor_id: Identifier
    on_success: Identifier
    on_failure: Identifier


class GraphDefinition(ContractModel):
    schema_version: Literal["aeep.toolkit.langgraph.v1"] = "aeep.toolkit.langgraph.v1"
    entry: Identifier
    nodes: dict[Identifier, Step] = Field(min_length=1, max_length=64)
    maximum_steps: int = Field(ge=1, le=256, strict=True)
    interrupt_before: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def explicit_edges(self) -> GraphDefinition:
        if "end" in self.nodes or self.entry not in self.nodes:
            raise ValueError("graph entry must be a reviewed node; end is reserved")
        targets = {
            value for step in self.nodes.values() for value in (step.on_success, step.on_failure)
        }
        if not targets <= set(self.nodes) | {"end"}:
            raise ValueError("graph edge has an unknown destination")
        if len(set(self.interrupt_before)) != len(self.interrupt_before) or not set(
            self.interrupt_before
        ) <= set(self.nodes):
            raise ValueError("graph interruptions require distinct known nodes")
        return self


class DispatchResult(ContractModel):
    succeeded: bool = Field(strict=True)
    evidence_ref: Digest


class ReferenceState(TypedDict):
    task_ref: str
    steps: int
    evidence_refs: list[str]
    succeeded: bool


Dispatcher = Callable[[str, str, str], Awaitable[DispatchResult]]


@dataclass(frozen=True)
class CompiledWorkflow:
    graph: Any
    definition_digest: str
    thread_id: str


async def execute_step(
    definition: GraphDefinition,
    name: str,
    state: ReferenceState,
    *,
    thread_id: str,
    dispatch: Dispatcher,
) -> ReferenceState:
    """Use a stable invocation key; unresolved/repeated attempts stay dispatcher-owned."""
    from .install_runtime import digest as content_digest

    if type(state["steps"]) is not int or not 0 <= state["steps"] < definition.maximum_steps:
        raise ValueError("reviewed graph step ceiling reached")
    if len(state["evidence_refs"]) != state["steps"]:
        raise ValueError("graph state lost its execution evidence")
    invocation = content_digest(
        {
            "graph": content_digest(definition),
            "thread": thread_id,
            "task": state["task_ref"],
            "step": state["steps"],
            "node": name,
        }
    )
    result = await dispatch(definition.nodes[name].executor_id, invocation, state["task_ref"])
    result = DispatchResult.model_validate(result)
    return {
        "task_ref": state["task_ref"],
        "steps": state["steps"] + 1,
        "evidence_refs": [*state["evidence_refs"], result.evidence_ref],
        "succeeded": result.succeeded,
    }


def compile_graph(
    definition: GraphDefinition,
    *,
    thread_id: str,
    dispatch: Dispatcher,
    checkpointer: Any,
) -> CompiledWorkflow:
    """Import the real optional SDK only inside its reviewed reusable runtime."""
    if not thread_id or len(thread_id) > 128 or checkpointer is None:
        raise ValueError("graph requires a bounded thread identity and explicit checkpointer")
    module = importlib.import_module("langgraph.graph")
    builder = module.StateGraph(ReferenceState)

    def node_callback(name: str) -> Callable[[ReferenceState], Awaitable[ReferenceState]]:
        async def run(state: ReferenceState) -> ReferenceState:
            return await execute_step(
                definition, name, state, thread_id=thread_id, dispatch=dispatch
            )

        return run

    def destination(name: str) -> Callable[[ReferenceState], str]:
        step = definition.nodes[name]

        def choose(state: ReferenceState) -> str:
            return step.on_success if state["succeeded"] else step.on_failure

        return choose

    for name in definition.nodes:
        builder.add_node(name, node_callback(name))
        destinations = set((definition.nodes[name].on_success, definition.nodes[name].on_failure))
        builder.add_conditional_edges(
            name,
            destination(name),
            {target: module.END if target == "end" else target for target in destinations},
        )
    builder.set_entry_point(definition.entry)
    from .install_runtime import digest

    return CompiledWorkflow(
        builder.compile(
            checkpointer=checkpointer, interrupt_before=list(definition.interrupt_before)
        ),
        digest(definition),
        thread_id,
    )


async def invoke(
    graph: CompiledWorkflow,
    definition: GraphDefinition,
    *,
    thread_id: str,
    task_ref: str | None,
) -> dict[str, Any]:
    """None resumes an interrupted checkpoint; it never resets attempts or counters."""
    from .install_runtime import digest

    if graph.thread_id != thread_id or graph.definition_digest != digest(definition):
        raise ValueError("graph definition or thread identity differs from its compiled binding")
    upstream = graph.graph
    if task_ref is not None:
        # Reuse the canonical digest validator without accepting arbitrary task contents.
        from pydantic import TypeAdapter

        TypeAdapter(Digest).validate_python(task_ref)
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": definition.maximum_steps + 2,
    }
    initial = (
        ReferenceState(task_ref=task_ref, steps=0, evidence_refs=[], succeeded=False)
        if task_ref is not None
        else None
    )
    if initial is not None:
        prior = await upstream.aget_state(config)
        if prior.values:
            raise ValueError("graph thread already started; resume its existing checkpoint")
    elif not (await upstream.aget_state(config)).next:
        raise ValueError("graph has no interrupted checkpoint to resume")
    result = await upstream.ainvoke(initial, config)
    snapshot = await upstream.aget_state(config)
    return {
        "state": result,
        "interrupted": bool(snapshot.next),
        "recovery": "caller-supplied-checkpointer; dispatcher reconciles durable attempts",
    }
