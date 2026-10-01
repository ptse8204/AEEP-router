from __future__ import annotations

import sys
from dataclasses import replace

import pytest
from conftest import python_spec

from aeep.assessment.identity import local_dependencies, verify_dependencies
from aeep.errors import ConfigurationError

pytestmark = pytest.mark.assessment_lifecycle


def test_static_python_identity_detects_drift_without_importing(tmp_path, monkeypatch):
    module = tmp_path / "candidate_fixture.py"
    module.write_text("raise AssertionError('must never import during inspection')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    dependencies = local_dependencies(python_spec("candidate", "candidate_fixture:run"))
    assert str(module) in dependencies
    assert "candidate_fixture" not in sys.modules
    verify_dependencies(dependencies)
    module.write_text("changed\n")
    with pytest.raises(ConfigurationError, match="changed"):
        verify_dependencies(dependencies)
    module.unlink()
    with pytest.raises(ConfigurationError, match="unavailable"):
        local_dependencies(python_spec("candidate", "candidate_fixture:run"))


async def test_resolved_host_identity_rejects_drift_and_separates_cohorts(monkeypatch):
    from test_codex_subscription_adapter import adapter, context

    from aeep.estimator import evidence_cohort_digest
    from aeep.models import ExecutionStatus

    host = adapter()
    ctx = context()
    try:
        digest = await host.resolve_identity(ctx.config)
        assert digest and len(digest) == 64
        assert digest == await host.resolve_identity(ctx.config)
        changed = ctx.config.model_copy(update={"sandbox_policy": "workspace_write"})
        assert digest != await host.resolve_identity(changed)
        raw = await host.execute(replace(ctx, expected_runtime_digest="0" * 64))
        assert raw.status == ExecutionStatus.REJECTED
        assert raw.error_type == "HOST_IDENTITY_DRIFT"
        # The fixture reroutes from model-a to model-b. Preserve usage but reject scoped evidence.
        raw = await host.execute(replace(ctx, expected_runtime_digest=digest))
        assert raw.status == ExecutionStatus.FAILED
        assert raw.error_type == "HOST_IDENTITY_DRIFT"
        assert raw.accounting.model_usage
        assert raw.metadata["host_runtime_digest"] != digest
        spec = python_spec("cohort", "test_v08_identity:unused")
        legacy = evidence_cohort_digest(spec, None)
        resolved = evidence_cohort_digest(spec, None, digest)
        assert legacy[0] == resolved[0] and legacy[1] != resolved[1]
        assert resolved != evidence_cohort_digest(spec, None, "0" * 64)
        original = host.transport.request

        async def request(method, params=None, **kwargs):
            if method == "model/list":
                return {"data": [], "nextCursor": "repeated"}
            return await original(method, params, **kwargs)

        monkeypatch.setattr(host.transport, "request", request)
        with pytest.raises(RuntimeError, match="pagination"):
            await host.list_models()
    finally:
        await host.close()


def test_durable_campaign_snapshot_retains_attempt_store_without_production_history(tmp_path):
    from aeep.store import ReceiptStore

    source = ReceiptStore(":memory:")
    path = tmp_path / "trial.sqlite3"
    snapshot = source.campaign_snapshot(path)
    snapshot.close()
    reopened = ReceiptStore(path)
    assert reopened.path == str(path)
    reopened.close()
    with pytest.raises(FileExistsError):
        source.campaign_snapshot(path)
    source.close()


async def test_host_assessment_admission_history_and_account_drift(tmp_path, monkeypatch):
    import asyncio
    from datetime import timedelta

    from test_codex_subscription_adapter import RESOURCE_ID, managed_config

    from aeep.assessment.models import (
        AssessmentAuthorization,
        AssessmentEnvironment,
        AssessmentLimits,
    )
    from aeep.assessment.recipes import reference_csv, shipped_recipe
    from aeep.assessment.service import AssessmentService
    from aeep.estimator import HistoricalEstimator
    from aeep.hosts import CodexAppServerAdapter
    from aeep.models import (
        ActionRequest,
        EstimateSource,
        ExecutionStatus,
        ExecutorSpec,
        Manifest,
        RawExecution,
        SideEffect,
        SubscriptionResource,
        utc_now,
    )
    from aeep.router import Router

    recipe = shipped_recipe("csv")
    candidate = python_spec("candidate", "aeep.assessment.recipes:reference_csv", capability=recipe.capability, input_schema=recipe.input_schema, output_schema=recipe.output_schema)
    # This fixture tests identity, not one-second process startup under CI load.
    baseline = ExecutorSpec(id="baseline", capability=recipe.capability, kind="host_managed", description="Offline Codex comparison", resource_pool=RESOURCE_ID, side_effect=SideEffect.READ, config={**managed_config(), "timeout_seconds": 5, "invocation": {"mode": "turn"}}, estimate=candidate.estimate.model_copy(deep=True))
    router = Router(Manifest(database=":memory:", executors=[candidate, baseline], resources=[SubscriptionResource(id=RESOURCE_ID, provider="openai", product="codex")]))
    service = AssessmentService(router, tmp_path / "assessment")
    plugin = tmp_path / "plugin.txt"
    plugin.write_text("deterministic CSV fixture")
    subject = service.inspect_local(plugin)
    environment = AssessmentEnvironment(environment_id="host", kind="codex_sandbox", identity={})
    plan = service.propose(subject_id=subject.subject_id, family="csv", candidate_id=candidate.id, baseline_id=baseline.id, authorization_id="grant", environment=environment)
    for digest in plan.definition_digests:
        service.repository.review(digest)
    service.repository.grant(AssessmentAuthorization(authorization_id="grant", subject_digests=[plan.subject_digest], recipe_digests=[plan.recipe_digest], environment_digests=[plan.environment_digest], limits=AssessmentLimits(max_operations=1000, max_model_turns=200, max_elapsed_seconds=20000), automatic_admission=True, expires_at=utc_now() + timedelta(hours=1)))

    async def execute(self, context):
        await asyncio.sleep(0.04)
        return RawExecution(status=ExecutionStatus.SUCCESS, output=reference_csv(**context.request.input), metadata={"host_runtime_digest": await self.resolve_identity(context.config)})

    monkeypatch.setattr(CodexAppServerAdapter, "execute", execute)
    try:
        # This is an offline identity fixture, not worker-conformance evidence.
        with monkeypatch.context() as campaign_patch:
            campaign_patch.setattr("aeep.assessment.boundary.require_managed_boundaries", lambda *_args: None)
            report = await service.run(service.enqueue(plan.plan_id))
        assert report.outcome == "useful_within_scope", report.explanations
        assert report.host_runtime_digests.get(baseline.id), (report.execution_failures, report.explanations)
        with pytest.raises(ConfigurationError, match="worker boundary"):
            service.admit(report.report_id)
        # Identity lifecycle fixture only; real conformance is tested separately.
        monkeypatch.setattr("aeep.assessment.boundary.require_managed_boundaries", lambda *_args: None)
        admission = service.admit(report.report_id)
        assert admission.host_runtime_digests[baseline.id]
        action = ActionRequest(capability=recipe.capability, input={"text": "id,name,note\n1,Ada,example\n", "delimiter": ","})
        action.constraints.allowed_executor_ids = [candidate.id]
        assert (await router.execute(action)).ok
        action.constraints.allowed_executor_ids = [baseline.id]
        outcome = await router.execute(action)
        receipt = outcome.receipts[0]
        estimate = HistoricalEstimator(router.store).estimate(baseline, outcome.decision.policy, receipt.action_features)
        assert estimate.source == EstimateSource.BLENDED
        router.store.host_runtime_digests.clear()
        assert HistoricalEstimator(router.store).estimate(baseline, outcome.decision.policy, receipt.action_features).source != EstimateSource.BLENDED
        from aeep.assessment.applicability import require_applicable
        from aeep.errors import NoRouteError
        with pytest.raises(NoRouteError):
            require_applicable(router.store, candidate, action, baseline)

        async def drift(_config):
            return "0" * 64

        host = router.managed_hosts.get("codex-app-server")
        monkeypatch.setattr(host, "resolve_identity", drift)
        await router._resolve_host_identity(baseline)
        assert router.store._connection.execute("SELECT revoked FROM assessment_admissions WHERE executor_id=?", (candidate.id,)).fetchone()[0] == 1
        action.constraints.allowed_executor_ids = [candidate.id]
        assert router.route(action).selected_executor_id is None
    finally:
        await router.close()


def test_identity_and_search_never_follow_paths_into_codex_state(tmp_path, monkeypatch):
    from aeep.assessment.identity import file_digest, protected_directory
    from aeep.assessment.recipes import reference_search

    codex = tmp_path / "codex"
    (codex / "plugins").mkdir(parents=True)
    state = codex / "state"
    state.mkdir()
    secret = state / "private.txt"
    secret.write_text("must not be read")
    plugin = codex / "plugins" / "script.py"
    plugin.write_text("pass\n")
    monkeypatch.setenv("CODEX_HOME", str(codex))
    assert protected_directory(tmp_path) and protected_directory(state)
    assert not protected_directory(plugin)
    assert file_digest(plugin)
    for path in (secret, codex / "plugins" / ".." / "state" / "private.txt"):
        with pytest.raises(ConfigurationError, match="Codex state"):
            file_digest(path)
    assert reference_search(str(state), "must") == {"error": "invalid_input"}
    ordinary = tmp_path / "ordinary"
    ordinary.mkdir()
    (ordinary / "auth.json").write_text("must not be read")
    assert reference_search(str(ordinary), "must") == {"error": "invalid_input"}
