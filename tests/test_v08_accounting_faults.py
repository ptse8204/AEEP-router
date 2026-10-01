from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from test_codex_subscription_adapter import managed_config
from test_v08_assessment import setup_assessment

from aeep.assessment.models import AssessmentLimits
from aeep.errors import ConfigurationError
from aeep.executors.base import ExecutionContext
from aeep.executors.managed_host import ManagedHostExecutor
from aeep.hosts import HostProbe, ManagedHostRegistry
from aeep.models import (
    ActionRequest,
    CashAccounting,
    CashEvidence,
    ExecutorSpec,
    RawExecution,
    ResourceAccounting,
    ResourceVector,
)

pytestmark = pytest.mark.assessment_lifecycle


@pytest.mark.parametrize("output", ["x" * 2048, {"unserializable"}], ids=["oversized", "unserializable"])
async def test_host_output_rejection_retains_incurred_usage(output):
    async def probe():
        return HostProbe(adapter_id="codex-app-server", status="ready")

    async def execute(_context):
        return RawExecution(status="success", output=output, resources=ResourceVector(cpu_ms=3, latency_ms=25))

    registry = ManagedHostRegistry()
    registry.register("codex-app-server", SimpleNamespace(probe=probe, execute=execute))
    spec = ExecutorSpec(id="host", capability="test@1", kind="host_managed", resource_pool="self", description="Fixture", config=managed_config())
    context = ExecutionContext(spec=spec, request=ActionRequest(capability="test@1", input={"text": "hello"}), estimate=spec.estimate, attempt=1)
    result = await ManagedHostExecutor(registry).execute(context)
    assert result.status.value == "failed" and result.output is None
    assert result.resources.cpu_ms == 3 and result.resources.latency_ms == 25


@pytest.mark.parametrize("failure", ["probe", "execute", "specific_code"])
async def test_managed_rejection_stops_campaign_after_first_charged_trial(tmp_path, monkeypatch, failure):
    from aeep.executors.python import PythonExecutor

    async def probe():
        return HostProbe(adapter_id="codex-app-server", status="unavailable" if failure == "probe" else "ready")

    async def execute(_context):
        assert failure != "probe"
        return RawExecution(status="rejected", error_type="NO_COMPATIBLE_MODEL",
                            resources=ResourceVector(cpu_ms=3),
                            metadata={"host_failure_code": "environment_verification_unavailable"} if failure == "specific_code" else {})

    registry = ManagedHostRegistry()
    registry.register("codex-app-server", SimpleNamespace(probe=probe, execute=execute))
    spec = ExecutorSpec(id="host", capability="test@1", kind="host_managed", resource_pool="self", description="Rejected host fixture", config=managed_config())
    context = ExecutionContext(spec=spec, request=ActionRequest(capability="test@1", input={"text": "hello"}), estimate=spec.estimate, attempt=1)
    raw = await ManagedHostExecutor(registry).execute(context)
    code = "environment_verification_unavailable" if failure == "specific_code" else "host_request_rejected"
    assert raw.metadata["host_failure_code"] == code
    assert raw.resources.cpu_ms == (0 if failure == "probe" else 3)

    router, service, plan, _ = setup_assessment(tmp_path)
    calls = 0

    async def rejected(self, _context):
        nonlocal calls
        calls += 1
        return raw.model_copy(deep=True)

    monkeypatch.setattr(PythonExecutor, "execute", rejected)
    try:
        job = service.enqueue(plan.plan_id)
        report = await service.run(job)
        assert calls == 1 and report.execution_failures == 1
        assert report.outcome == "insufficient_evidence" and report.correctness_failures == 0
        trials = [item for item in service.repository.operation_ledger(plan.plan_id).operations if item.stage == "trial"]
        assert len(trials) == 1 and trials[0].elapsed_seconds is not None
        assert service.status(job)["error_code"] == "assessment_blocked_or_budget_exhausted"
    finally:
        await router.close()


@pytest.mark.parametrize("unknown", [False, True])
async def test_cash_overrun_or_unknown_paid_usage_revokes_further_spend(tmp_path, unknown):
    router, service, plan, grant = setup_assessment(tmp_path)
    grant = grant.model_copy(update={"authorization_id": "paid", "limits": grant.limits.model_copy(update={"max_cash_usd": Decimal(2)})})
    plan = plan.model_copy(update={"authorization_id": grant.authorization_id})
    service.repository.grant(grant)
    try:
        service.repository.reserve(plan, "paid-call", AssessmentLimits(max_operations=1, max_elapsed_seconds=1, max_cash_usd=Decimal(1)))
        accounting = ResourceAccounting() if unknown else ResourceAccounting(cash=CashAccounting(status="complete", components=[CashEvidence(charge_id="observed", amount=Decimal(2), classification="verified", evidence={"status": "complete", "source": "local_meter", "trust": "verified"})]))
        service.repository.finish_operation("paid-call", elapsed_seconds=0.1, accounting=accounting)
        with pytest.raises(ConfigurationError, match="revoked"):
            service.repository.authorize(plan)
        assert service.repository.operation_ledger(plan.plan_id).operations[-1].accounting == accounting
        if not unknown:
            assert router.store._connection.execute("SELECT cash_usd FROM assessment_grants WHERE id='paid'").fetchone()[0] == "2"
    finally:
        await router.close()


async def test_faulty_grader_keeps_measured_overhead_without_running_candidates(tmp_path, monkeypatch):
    from aeep.assessment import service as module
    from aeep.models import ValidationResult

    router, service, plan, _ = setup_assessment(tmp_path)

    async def broken(*_args):
        return [ValidationResult(kind="exact_match", valid=True)]

    monkeypatch.setattr(module, "run_validators", broken)
    try:
        report = await service.run(service.enqueue(plan.plan_id))
        assert report.outcome == "insufficient_evidence"
        ledger = service.repository.operation_ledger(plan.plan_id)
        grader = next(item for item in ledger.operations if item.stage == "grader_validation")
        assert grader.elapsed_seconds is not None and grader.resources is not None
        assert report.measured_usage["known_overhead_wall_time_ms"] > 0
        assert not router.store.list_receipts()
    finally:
        await router.close()


async def test_trial_deadline_and_revocation_are_checked_before_each_invocation(tmp_path):
    import asyncio

    from aeep.errors import NoRouteError

    router, _service, plan, _grant = setup_assessment(tmp_path)
    action = plan.suite.cases[0].action
    action.constraints.allowed_executor_ids = ["baseline"]
    try:
        router._trial_deadline = asyncio.get_running_loop().time() - 1
        with pytest.raises(NoRouteError, match="deadline"):
            await router.execute(action)
        assert not router.store.list_receipts()
        router._trial_deadline = None
        checks = 0

        def revoked():
            nonlocal checks
            checks += 1
            if checks == 2:
                raise ConfigurationError("grant revoked between checks")

        router._trial_check = revoked
        with pytest.raises(ConfigurationError, match="revoked"):
            await router.execute(action)
        assert checks == 2 and not router.store.list_receipts()
        checks = 0

        def begin_deadline():
            nonlocal checks
            checks += 1
            if checks == 2:
                router._trial_deadline = asyncio.get_running_loop().time() + 0.0001

        router._trial_check = begin_deadline
        with pytest.raises(TimeoutError):
            await router.execute(action)
        assert not router.store.list_receipts()
    finally:
        await router.close()


@pytest.mark.parametrize("failure", ["quota", "configuration", "cancelled"])
async def test_unavailable_environment_stops_after_first_charged_trial(tmp_path, monkeypatch, failure):
    from aeep.errors import NoRouteError
    from aeep.router import Router

    router, service, plan, _ = setup_assessment(tmp_path)
    job = service.enqueue(plan.plan_id)
    calls = 0

    async def unavailable(self, *_args, **_kwargs):
        nonlocal calls
        calls += 1
        if failure == "quota":
            raise NoRouteError("subscription resource is exhausted")
        if failure == "cancelled":
            service.cancel(job)
        raise ConfigurationError("execution unavailable")

    monkeypatch.setattr(Router, "execute", unavailable)
    try:
        report = await service.run(job)
        assert calls == 1
        assert report.outcome == "insufficient_evidence" and not report.qualification_passed
        trials = [item for item in service.repository.operation_ledger(plan.plan_id).operations if item.stage == "trial"]
        assert len(trials) == 1 and trials[0].elapsed_seconds is not None
        assert not router.store.list_receipts()
        assert service.status(job)["error_code"] == "assessment_blocked_or_budget_exhausted"
    finally:
        await router.close()
