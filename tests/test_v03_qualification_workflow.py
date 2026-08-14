from __future__ import annotations

import sys
from decimal import Decimal

import pytest
from conftest import manifest_with

from aeep.errors import ConfigurationError, NoRouteError
from aeep.models import (
    ActionRequest,
    CandidateScore,
    EvidenceSource,
    EvidenceStatus,
    ExecutorKind,
    ExecutorSpec,
    Locality,
    Manifest,
    MeasurementEvidence,
    ResourceVector,
    RouteDecision,
    RouteEstimate,
    SideEffect,
    SubscriptionQuota,
    SubscriptionResource,
    SubscriptionUsage,
    TrustLevel,
)
from aeep.qualification import (
    QualificationCase,
    QualificationCondition,
    RouteLifecycle,
    behavior_fingerprint,
    static_qualification_checks,
)
from aeep.router import Router
from aeep.workflow import (
    WorkflowInputBinding,
    WorkflowOutputProjection,
    WorkflowRequest,
    WorkflowStatus,
    WorkflowStep,
)

CALLS = 0


def echo(value: str = "ok") -> dict[str, str]:
    global CALLS
    CALLS += 1
    return {"value": value}


def other(value: str = "ok") -> dict[str, str]:
    return {"value": value.upper()}


def spec(
    identifier: str,
    *,
    capability: str = "demo.echo",
    callable_path: str = "test_v03_qualification_workflow:echo",
    resource_pool: str | None = None,
    subscription_units: float = 0,
    kind: ExecutorKind = ExecutorKind.PYTHON,
) -> ExecutorSpec:
    config = (
        {"instructions": "Return {input.value}"}
        if kind == ExecutorKind.HOST
        else {"callable": callable_path}
    )
    return ExecutorSpec(
        id=identifier,
        capability=capability,
        kind=kind,
        description=identifier,
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        estimate=RouteEstimate(
            resources=ResourceVector(monetary_usd=0, subscription_units=subscription_units)
        ),
        side_effect=SideEffect.NONE,
        locality=Locality.LOCAL,
        resource_pool=resource_pool,
        config=config,
    )


def test_static_qualification_covers_every_external_adapter_boundary():
    command = spec("command").model_copy(
        update={
            "kind": ExecutorKind.COMMAND,
            "side_effect": SideEffect.READ,
            "config": {
                "argv": ["/usr/bin/tool", "{input.value}"],
                "env": {"API_TOKEN": "${ENV:LAB_TOKEN}"},
            },
        }
    )
    assert all(static_qualification_checks(command).values())

    unsafe_command = command.model_copy(
        update={
            "input_schema": {"type": "not-a-json-schema-type"},
            "config": {
                "argv": ["{input.executable}"],
                "env": {"API_TOKEN": "literal-secret"},
                "shell": True,
            },
        }
    )
    failed = static_qualification_checks(unsafe_command)
    assert not failed["schemas"]
    assert not failed["adapter_config"]
    assert not failed["secret_references"]

    http = command.model_copy(
        update={
            "kind": ExecutorKind.HTTP,
            "config": {
                "url": "https://api.example.test/v1",
                "allowed_hosts": ["api.example.test"],
                "headers": {"Authorization": "${ENV:LAB_TOKEN}"},
            },
        }
    )
    assert static_qualification_checks(http)["adapter_config"]
    assert behavior_fingerprint(http) != behavior_fingerprint(
        http.model_copy(update={"config": {**http.config, "allowed_hosts": ["other.example.test"]}})
    )
    assert not static_qualification_checks(
        http.model_copy(update={"config": {**http.config, "max_response_bytes": 0}})
    )["bounded_io"]
    assert (
        static_qualification_checks(http.model_copy(update={"config": {"url": "http://x"}}))[
            "adapter_config"
        ]
        is False
    )

    mcp = command.model_copy(
        update={
            "kind": ExecutorKind.MCP,
            "config": {
                "transport": "stdio",
                "command": "/usr/bin/docker",
                "args": ["mcp", "gateway", "run"],
                "env": {"TOKEN": "env:LAB_TOKEN"},
            },
        }
    )
    assert static_qualification_checks(mcp)["adapter_config"]
    templated = mcp.model_copy(update={"config": {**mcp.config, "args": ["{input.profile}"]}})
    assert not static_qualification_checks(templated)["adapter_config"]


@pytest.mark.asyncio
async def test_candidate_requires_qualification_activation_and_suspends_on_drift():
    router = Router(Manifest(database=":memory:"))
    imported = spec("imported").model_copy(
        update={
            "kind": ExecutorKind.COMMAND,
            "config": {
                "argv": [
                    sys.executable,
                    "-m",
                    "aeep.examples.text_stats_cli",
                    "{input.value}",
                ],
                "output": {"type": "json"},
                "inherit_env": False,
            },
        }
    )
    imported.output_schema = {
        "type": "object",
        "properties": {
            "characters": {"type": "integer"},
            "words": {"type": "integer"},
            "lines": {"type": "integer"},
        },
        "required": ["characters", "words", "lines"],
        "additionalProperties": False,
    }
    imported.enabled = True
    imported.safe_to_auto_execute = True
    candidate = router.ingest_candidate(imported, source_id="catalog:test")
    assert candidate.status == RouteLifecycle.CANDIDATE
    assert router.registry.find("demo.echo") == []

    report = await router.qualify_candidate(
        "imported",
        side_effect=SideEffect.NONE,
        idempotent=True,
        safe_to_auto_execute=True,
        cases=[
            QualificationCase(
                input={"value": "x"},
                expected_output={"characters": 1, "words": 1, "lines": 1},
            )
        ],
        repetitions=2,
        conditions=[
            QualificationCondition.PROCESS_COLD,
            QualificationCondition.ROUTER_WARM,
        ],
    )
    assert report.passed
    assert report.dynamic_runs == report.passed_runs == 4
    assert router.registry.find("demo.echo") == []
    router.activate_candidate("imported")
    assert (await router.execute(ActionRequest(capability="demo.echo", input={"value": "x"}))).ok

    estimate_only = imported.model_copy(deep=True)
    estimate_only.estimate.resources.latency_ms = 999
    assert (
        router.ingest_candidate(estimate_only, source_id="catalog:test").status
        == RouteLifecycle.ACTIVE
    )

    drifted = imported.model_copy(deep=True)
    drifted.config["argv"] = [*drifted.config["argv"], "--drift"]
    suspended = router.ingest_candidate(drifted, source_id="catalog:test")
    assert suspended.status == RouteLifecycle.SUSPENDED
    assert router.registry.find("demo.echo") == []
    await router.close()


@pytest.mark.asyncio
async def test_external_python_candidate_never_imports_or_executes_in_process():
    global CALLS
    CALLS = 0
    router = Router(Manifest(database=":memory:"))
    router.ingest_candidate(spec("python-candidate"), source_id="catalog:test")
    with pytest.raises(ConfigurationError, match="cannot be qualified in-process"):
        await router.qualify_candidate(
            "python-candidate",
            side_effect=SideEffect.NONE,
            idempotent=True,
            safe_to_auto_execute=True,
            cases=[QualificationCase(input={"value": "x"}, expected_output={"value": "x"})],
        )
    assert CALLS == 0
    await router.close()


@pytest.mark.asyncio
async def test_forged_decision_cannot_execute_disabled_route():
    global CALLS
    CALLS = 0
    disabled = spec("disabled")
    disabled.enabled = False
    router = Router(manifest_with(disabled))
    request = ActionRequest(capability="demo.echo", input={"value": "x"})
    forged = RouteDecision(
        action=request,
        policy=router.manifest.policies["balanced"],
        selected_executor_id="disabled",
        candidates=[
            CandidateScore(
                executor_id="disabled",
                feasible=True,
                estimate=disabled.estimate,
                rank=1,
            )
        ],
    )
    with pytest.raises(NoRouteError):
        await router.execute(forged)
    assert CALLS == 0
    await router.close()


@pytest.mark.asyncio
async def test_post_invocation_store_failure_leaves_idempotency_indeterminate(monkeypatch):
    global CALLS
    CALLS = 0
    router = Router(manifest_with(spec("once")))
    request = ActionRequest(
        capability="demo.echo",
        input={"value": "x"},
        idempotency_key="one-attempt",
    )
    original = router.store.save_receipt

    def fail_store(_receipt):
        raise OSError("simulated store failure")

    monkeypatch.setattr(router.store, "save_receipt", fail_store)
    with pytest.raises(OSError):
        await router.execute(request)
    monkeypatch.setattr(router.store, "save_receipt", original)
    with pytest.raises(ConfigurationError, match="in progress"):
        await router.execute(request)
    assert CALLS == 1
    await router.close()


@pytest.mark.asyncio
async def test_workflow_binding_projection_and_parallel_quota_reservation():
    resource = SubscriptionResource(
        id="plan",
        provider="demo",
        product="plan",
        unit="credit",
        quota=SubscriptionQuota(
            unit="credit",
            allowance_units=10,
            remaining_units=3,
            confidence=1,
        ),
    )
    first = spec("first", capability="demo.first", resource_pool="plan", subscription_units=2)
    second = spec(
        "second",
        capability="demo.second",
        callable_path="test_v03_qualification_workflow:other",
        resource_pool="plan",
        subscription_units=2,
    )
    for route in (first, second):
        route.estimate.resources.subscription_units = 0
        route.estimate.subscription_usage = [
            SubscriptionUsage(
                provider="demo",
                resource_pool="plan",
                unit="credit",
                consumed=Decimal(2),
                source=MeasurementEvidence(
                    status=EvidenceStatus.COMPLETE,
                    source=EvidenceSource.STATIC_ESTIMATE,
                    trust=TrustLevel.SELF_ASSERTED,
                ),
            )
        ]
    router = Router(Manifest(database=":memory:", resources=[resource], executors=[first, second]))
    overcommitted = WorkflowRequest(
        workflow_id="overcommitted",
        steps=[
            WorkflowStep(
                step_id="a",
                action=ActionRequest(capability="demo.first", input={"value": "a"}),
            ),
            WorkflowStep(
                step_id="b",
                action=ActionRequest(capability="demo.second", input={"value": "b"}),
            ),
        ],
    )
    failed = await router.execute_workflow(overcommitted)
    assert failed.status == WorkflowStatus.FAILED
    assert failed.receipts == []
    assert "reservation" in (failed.error or "")
    router.observe_quota(
        "plan",
        SubscriptionQuota(
            unit="credit",
            allowance_units=10,
            remaining_units=10,
            confidence=1,
        ),
    )

    sequential = WorkflowRequest(
        workflow_id="sequential",
        steps=[
            WorkflowStep(
                step_id="a",
                action=ActionRequest(capability="demo.first", input={"value": "hello"}),
            ),
            WorkflowStep(
                step_id="b",
                action=ActionRequest(capability="demo.second", input={"value": "placeholder"}),
                depends_on=["a"],
                bindings=[
                    WorkflowInputBinding(
                        target_path="/value",
                        source_step_id="a",
                        source_path="/value",
                    )
                ],
            ),
        ],
        outputs=[WorkflowOutputProjection(name="result", step_id="b", path="/value")],
    )
    completed = await router.execute_workflow(sequential)
    assert completed.status == WorkflowStatus.SUCCESS
    assert completed.outputs == {"result": "HELLO"}
    await router.close()


@pytest.mark.asyncio
async def test_workflow_waiting_resume_keeps_payloads_out_of_checkpoint():
    resource = SubscriptionResource(id="host-plan", provider="demo", product="host")
    host = spec(
        "host",
        capability="demo.host",
        resource_pool="host-plan",
        subscription_units=1,
        kind=ExecutorKind.HOST,
    )
    local = spec(
        "local",
        capability="demo.local",
        callable_path="test_v03_qualification_workflow:other",
    )
    router = Router(Manifest(database=":memory:", resources=[resource], executors=[host, local]))
    workflow = WorkflowRequest(
        workflow_id="resume",
        steps=[
            WorkflowStep(
                step_id="host",
                action=ActionRequest(capability="demo.host", input={"value": "secret"}),
            ),
            WorkflowStep(
                step_id="local",
                action=ActionRequest(capability="demo.local", input={"value": "placeholder"}),
                depends_on=["host"],
                bindings=[
                    WorkflowInputBinding(
                        target_path="/value",
                        source_step_id="host",
                        source_path="/value",
                    )
                ],
            ),
        ],
        outputs=[WorkflowOutputProjection(name="result", step_id="local", path="/value")],
    )
    waiting = await router.execute_workflow(workflow)
    assert waiting.status == WorkflowStatus.WAITING
    checkpoint = router.store.get_workflow_checkpoint("resume")
    assert checkpoint is not None and "secret" not in str(checkpoint)
    resumed = await router.resume_workflow(
        workflow,
        waiting,
        step_id="host",
        output={"value": "done"},
    )
    assert resumed.status == WorkflowStatus.SUCCESS
    assert resumed.outputs == {"result": "DONE"}
    await router.close()
