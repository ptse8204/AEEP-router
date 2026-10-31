"""Owned adapter fixtures. SDK execution needs the separate exact runtime review."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aeep_toolkit.langgraph_workflow import (
    CompiledWorkflow,
    DispatchResult,
    GraphDefinition,
    compile_graph,
    execute_step,
    invoke,
)


def definition():
    return GraphDefinition(
        entry="validate",
        maximum_steps=3,
        nodes={
            "validate": {
                "executor_id": "approved.validator",
                "on_success": "end",
                "on_failure": "validate",
            }
        },
        interrupt_before=("validate",),
    )


@pytest.mark.asyncio
async def test_dispatch_is_reference_only_bounded_and_recovery_keys_do_not_reset():
    graph = definition()
    calls = []

    async def dispatch(executor, key, task):
        calls.append((executor, key, task))
        return DispatchResult(succeeded=len(calls) == 2, evidence_ref=str(len(calls)) * 64)

    state = dict(task_ref="a" * 64, steps=0, evidence_refs=[], succeeded=False)
    first = await execute_step(graph, "validate", state, thread_id="frozen", dispatch=dispatch)
    second = await execute_step(graph, "validate", first, thread_id="frozen", dispatch=dispatch)
    assert first["succeeded"] is False and second["succeeded"] is True
    assert calls[0][1] != calls[1][1] and all(c[0] == "approved.validator" for c in calls)
    assert second["evidence_refs"] == ["1" * 64, "2" * 64]
    with pytest.raises(ValueError, match="ceiling"):
        await execute_step(
            graph, "validate", dict(second, steps=3), thread_id="frozen", dispatch=dispatch
        )
    with pytest.raises(ValueError, match="lost"):
        await execute_step(
            graph, "validate", dict(first, evidence_refs=[]), thread_id="frozen", dispatch=dispatch
        )


@pytest.mark.parametrize(
    "change", ["entry", "edge", "reserved", "interrupt", "duplicate", "ceiling"]
)
def test_graph_rejects_unknown_execution_paths(change):
    data = definition().model_dump()
    if change == "entry":
        data["entry"] = "missing"
    elif change == "edge":
        data["nodes"]["validate"]["on_failure"] = "missing"
    elif change == "reserved":
        data["nodes"]["end"] = data["nodes"]["validate"]
    elif change == "interrupt":
        data["interrupt_before"] = ("missing",)
    elif change == "duplicate":
        data["interrupt_before"] = ("validate", "validate")
    else:
        data["maximum_steps"] = 0
    with pytest.raises(ValueError):
        GraphDefinition.model_validate(data)


@pytest.mark.asyncio
async def test_sdk_api_wiring_is_not_an_upstream_execution_claim(monkeypatch):
    methods = {}

    class Builder:
        def __init__(self, state):
            methods["state"] = state

        def add_node(self, name, callback):
            methods["node"] = callback

        def add_conditional_edges(self, name, choose, paths):
            methods.update(choose=choose, paths=paths)

        def set_entry_point(self, name):
            methods["entry"] = name

        def compile(self, **kwargs):
            return kwargs

    monkeypatch.setattr(
        "aeep_toolkit.langgraph_workflow.importlib.import_module",
        lambda name: SimpleNamespace(StateGraph=Builder, END="__end__"),
    )
    marker = object()
    callback = AsyncMock(return_value=DispatchResult(succeeded=True, evidence_ref="f" * 64))
    result = compile_graph(definition(), thread_id="frozen", dispatch=callback, checkpointer=marker)
    assert result.graph == {"checkpointer": marker, "interrupt_before": ["validate"]}
    assert methods["paths"] == {"end": "__end__", "validate": "validate"}
    for success in (False, True):
        assert methods["choose"]({"succeeded": success}) == ("end" if success else "validate")
    await methods["node"](dict(task_ref="a" * 64, steps=0, evidence_refs=[], succeeded=False))
    assert callback.await_count == 1
    with pytest.raises(ValueError):
        compile_graph(definition(), thread_id="", dispatch=callback, checkpointer=marker)
    with pytest.raises(ValueError):
        compile_graph(definition(), thread_id="frozen", dispatch=callback, checkpointer=None)


@pytest.mark.asyncio
async def test_interruption_resumes_existing_state_and_never_restarts_thread():
    backend = SimpleNamespace(aget_state=AsyncMock(), ainvoke=AsyncMock(return_value={"steps": 1}))
    backend.aget_state.side_effect = [
        SimpleNamespace(values={}, next=()),
        SimpleNamespace(next=("validate",)),
    ]
    from aeep_toolkit.install_runtime import digest

    compiled = CompiledWorkflow(backend, digest(definition()), "frozen")
    first = await invoke(compiled, definition(), thread_id="frozen", task_ref="a" * 64)
    assert first["interrupted"] is True
    backend.aget_state.side_effect = [SimpleNamespace(next=("validate",)), SimpleNamespace(next=())]
    second = await invoke(compiled, definition(), thread_id="frozen", task_ref=None)
    assert second["interrupted"] is False and backend.ainvoke.call_args.args[0] is None
    backend.aget_state.side_effect = [SimpleNamespace(values={"steps": 1})]
    with pytest.raises(ValueError, match="already started"):
        await invoke(compiled, definition(), thread_id="frozen", task_ref="a" * 64)
    backend.aget_state.side_effect = [SimpleNamespace(next=())]
    with pytest.raises(ValueError, match="no interrupted"):
        await invoke(compiled, definition(), thread_id="frozen", task_ref=None)
    with pytest.raises(ValueError):
        await invoke(compiled, definition(), thread_id="frozen", task_ref="contents")


@pytest.mark.asyncio
async def test_changed_compiled_identity_is_rejected_before_sdk_invocation():
    from aeep_toolkit.install_runtime import digest

    backend = SimpleNamespace(aget_state=AsyncMock())
    compiled = CompiledWorkflow(backend, digest(definition()), "frozen")
    with pytest.raises(ValueError, match="compiled binding"):
        await invoke(compiled, definition(), thread_id="other", task_ref="a" * 64)
    backend.aget_state.assert_not_awaited()
