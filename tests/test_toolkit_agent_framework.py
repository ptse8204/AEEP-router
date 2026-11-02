"""First-party adapter fixtures only; this file never imports the real SDK."""

import asyncio
from types import SimpleNamespace
from typing import Generic, TypeVar, get_args, get_origin

import pytest

from aeep.assessment.models import content_digest
from aeep.models import ExecutionReceipt, RouteEstimate
from aeep_toolkit import agent_framework_workflow as bridge
from aeep_toolkit.agent_framework_workflow import (
    PipelineDefinition,
    PipelineState,
    compile_pipeline,
)

TASK = "a" * 64


def pipeline(*executors):
    return PipelineDefinition(
        steps=tuple(
            dict(
                executor_id=name,
                fingerprint="sha256:" + content_digest({"synthetic_executor": name}),
            )
            for name in executors
        )
    )


def receipt(executor, fingerprint, success, key):
    return ExecutionReceipt(
        decision_id="synthetic-decision",
        action_id=key,
        capability="fixture@1",
        executor_id=executor,
        executor_kind="command",
        executor_fingerprint=fingerprint,
        status="success" if success else "failed",
        execution_success=success,
        estimated=RouteEstimate(),
        metadata={"evidence_kind": "synthetic"},
    )


@pytest.fixture
def sdk_fixture(monkeypatch):
    constructed = []
    Out, Final = TypeVar("Out"), TypeVar("Final")

    class Context(Generic[Out, Final]):
        pass

    class Node:
        def __init__(self, function, **kwargs):
            # Mirror the pinned SDK's required context contract. This substitute
            # is first-party development evidence, never upstream execution proof.
            context = function.__annotations__["context"]
            assert get_origin(context) is Context and get_args(context) == (dict, dict)
            self.function = function
            self.id = kwargs["id"]
            assert kwargs["input"] is kwargs["output"] is kwargs["workflow_output"] is dict

    class Builder:
        def __init__(self, **kwargs):
            self.settings = kwargs
            self.nodes = [kwargs["start_executor"]]
            constructed.append(self)

        def add_edge(self, left, right):
            assert left is self.nodes[-1]
            self.nodes.append(right)

        def build(self):
            async def run(state):
                output = []
                for node in self.nodes:
                    sent = []

                    async def send(value, target=sent):
                        target.append(value)

                    async def emit(value):
                        output.append(value)

                    await node.function(
                        state, SimpleNamespace(send_message=send, yield_output=emit)
                    )
                    if output:
                        break
                    assert len(sent) == 1
                    state = sent[0]
                return SimpleNamespace(get_outputs=lambda: output)

            return SimpleNamespace(run=run)

    monkeypatch.setattr(bridge, "version", lambda _: "1.21.0")
    monkeypatch.setattr(
        bridge,
        "importlib",
        SimpleNamespace(
            import_module=lambda _: SimpleNamespace(FunctionExecutor=Node, WorkflowBuilder=Builder, WorkflowContext=Context)
        ),
    )
    return constructed


async def test_sdk_glue_transmits_only_references_and_binds_successor_consumption(sdk_fixture):
    calls = []
    receipts = []

    async def dispatch(executor, key, task, predecessors, fingerprint):
        calls.append((executor, key, task, predecessors))
        result = receipt(executor, fingerprint, True, key)
        receipts.append(content_digest(result))
        return result

    compiled = compile_pipeline(
        pipeline("approved.extract", "approved.verify"),
        run_id="fixture-owned",
        dispatch=dispatch,
    )
    result = await compiled.run(task_ref=TASK)
    assert result["completed"] and result["state"]["next_step"] == 2
    assert calls[0][0] == "approved.extract" and calls[0][3] == ()
    assert calls[1][0] == "approved.verify" and calls[1][3] == (receipts[0],)
    assert len({c[1] for c in calls}) == 2 and all(c[2] == TASK for c in calls)
    assert set(result["state"]) == {
        "definition_ref",
        "run_id",
        "task_ref",
        "next_step",
        "receipt_refs",
        "succeeded",
    }
    assert sdk_fixture[0].settings["max_iterations"] == 3
    with pytest.raises(ValueError, match="already started"):
        await compiled.run(task_ref=TASK)
    assert len(calls) == 2


async def test_failed_step_ends_pipeline_without_dispatching_another_executor(sdk_fixture):
    calls = []

    async def dispatch(executor, *_):
        calls.append(executor)
        return receipt(executor, _[-1], False, _[0])

    compiled = compile_pipeline(pipeline("first", "second"), run_id="failure", dispatch=dispatch)
    result = await compiled.run(task_ref=TASK)
    assert not result["completed"] and result["state"]["next_step"] == 1
    assert calls == ["first"] and result["candidate_usefulness"] == "NOT_ASSESSED"


async def test_cancelled_dispatch_keeps_run_claimed_and_never_restarts_it(sdk_fixture):
    started = asyncio.Event()
    calls = []

    async def dispatch(*args):
        calls.append(args)
        started.set()
        await asyncio.Event().wait()

    compiled = compile_pipeline(pipeline("approved"), run_id="cancelled", dispatch=dispatch)
    running = asyncio.create_task(compiled.run(task_ref=TASK))
    await started.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    with pytest.raises(ValueError, match="reconcile"):
        await compiled.run(task_ref=TASK)
    assert len(calls) == 1


async def test_denied_dispatch_and_forged_terminal_state_fail_closed(sdk_fixture):
    async def denied(*_):
        raise PermissionError("operator revoked scope")

    compiled = compile_pipeline(pipeline("approved"), run_id="denied", dispatch=denied)
    with pytest.raises(PermissionError):
        await compiled.run(task_ref=TASK)

    async def forged(_):
        return SimpleNamespace(
            get_outputs=lambda: [
                dict(
                    definition_ref="b" * 64,
                    run_id="other",
                    task_ref=TASK,
                    next_step=0,
                    receipt_refs=[],
                    succeeded=True,
                )
            ]
        )

    compiled = compile_pipeline(pipeline("approved"), run_id="forged", dispatch=denied)
    compiled.upstream = SimpleNamespace(run=forged)
    with pytest.raises(ValueError, match="terminal identity"):
        await compiled.run(task_ref=TASK)


@pytest.mark.parametrize("fault", ["executor", "fingerprint", "other_task", "unknown_outcome"])
async def test_receipt_must_bind_this_step_and_its_reviewed_executor(sdk_fixture, fault):
    calls = []

    async def dispatch(executor, key, task, predecessors, fingerprint):
        calls.append(key)
        result = receipt(executor, fingerprint, True, key)
        if fault == "executor":
            result.executor_id = "other"
        elif fault == "fingerprint":
            result.executor_fingerprint = "sha256:" + "c" * 64
        elif fault == "other_task":
            result.action_id = "unrelated-action"
        else:
            result.execution_success = None
        return result

    compiled = compile_pipeline(
        pipeline("approved", "never-called"), run_id="bad-receipt", dispatch=dispatch
    )
    with pytest.raises(ValueError, match="dispatch receipt"):
        await compiled.run(task_ref=TASK)
    assert len(calls) == 1


def test_unreviewed_sdk_version_and_malformed_lineage_are_rejected(sdk_fixture, monkeypatch):
    monkeypatch.setattr(bridge, "version", lambda _: "unreviewed")
    with pytest.raises(ValueError, match="reviewed version"):
        compile_pipeline(pipeline("approved"), run_id="bounded", dispatch=None)
    with pytest.raises(ValueError, match="lineage"):
        PipelineState(
            definition_ref=TASK,
            run_id="invalid",
            task_ref=TASK,
            next_step=1,
            receipt_refs=(),
            succeeded=True,
        )
