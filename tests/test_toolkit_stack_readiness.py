"""Synthetic canonical fixtures for the delivery barrier, never upstream proof."""

import asyncio
import hashlib
import json

import pytest
from test_toolkit_managed import prepared

from aeep.assessment.boundary import BoundaryProbe, BoundaryProbeDefinition
from aeep.assessment.models import content_digest
from aeep.errors import ConfigurationError
from aeep.execution import EventJournal, ExecutionEvidence
from aeep.models import ExecutorSpec
from aeep_toolkit.cli import main
from aeep_toolkit.stack_readiness import (
    REQUIRED_CHECKS,
    IntegrationDefinition,
    IntegrationEvidence,
    StackCompletion,
    require_integration,
    require_stack_complete,
    source_revisions,
)

D = "a" * 64


def synthetic_component(repo, component, binary, *, fault=None):
    definitions, observations = {}, {}
    spec = ExecutorSpec(
        id="synthetic-check",
        capability="fixture@1",
        kind="command",
        description="Test fixture only",
        config={"argv": ["/never-executed"]},
    )
    for name in REQUIRED_CHECKS[component]:
        value = dict(
            component=component,
            check=name,
            source_revision=source_revisions(D)[component],
            implementation_source=D,
            mode="upstream_functional",
            exercised_fixture=True,
        )
        if fault == "mock":
            value["mode"] = "mock"
        definition = BoundaryProbeDefinition(
            name=component + "." + name, executor=spec, expected=value
        )
        definition_ref = repo.put(
            "boundary_probe_definition", content_digest(definition), definition
        )
        repo.review(definition_ref)
        definitions[name] = definition_ref
        attempt = "synthetic-" + component + "-" + name
        stream = EventJournal(attempt)
        stream.append("execution.started", "start")
        stream.append("artifact.created", "probe-result", evidence_ref=content_digest(value))
        stream.append(
            "execution.failed" if fault == "failed" else "execution.completed", "terminal"
        )
        journal = ExecutionEvidence(
            attempt_id=attempt,
            adapter="synthetic-only",
            events=stream.items,
            journal_id=stream.journal_id,
            complete=True,
            boundary_digest=D,
        )
        journal_ref = repo.put("execution_evidence", content_digest(journal), journal)
        probe = BoundaryProbe(
            probe_id=attempt,
            name=definition.name,
            implementation_digest=definition_ref,
            worker_digest=D,
            execution_evidence_digest=journal_ref,
            observed=value,
        )
        observations[name] = repo.put("boundary_probe", probe.probe_id, probe)
        if fault != "unaccounted":
            with repo.store._immediate_transaction() as connection:
                connection.execute(
                    "INSERT INTO assessment_operations VALUES (?,?,?,?)",
                    (attempt, "grant", "reserved" if fault == "unresolved" else "complete", "{}"),
                )
    definition = IntegrationDefinition(
        component=component,
        source_revision=source_revisions(D)[component],
        implementation_source=D,
        runtime_digest=D,
        executable_dependencies={str(binary): hashlib.sha256(binary.read_bytes()).hexdigest()},
        probe_definitions=definitions,
    )
    definition_ref = repo.put(
        "toolkit_integration_definition", content_digest(definition), definition
    )
    repo.review(definition_ref)
    if fault == "revoked":
        repo.review(definition_ref, revoke=True)
    record = IntegrationEvidence(definition_ref=definition_ref, probe_refs=observations)
    return repo.put("toolkit_integration_evidence", content_digest(record), record)


def test_checklist_is_inert_and_separates_readiness_from_value(monkeypatch, capsys):
    import sqlite3

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: pytest.fail("opened database"))
    assert main(["stack-status"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result["components"]) == 19
    assert result["comparison_dispatch"].startswith("BLOCKED")
    assert result["candidate_usefulness"] == result["selection_usefulness"] == "NOT_ASSESSED"


@pytest.mark.asyncio
async def test_missing_readiness_blocks_before_enqueue_or_any_accounting(tmp_path, monkeypatch):
    router, service, adapter, *_ = prepared(tmp_path, monkeypatch)
    try:
        before = router.store._connection.total_changes
        monkeypatch.setattr(service, "enqueue", lambda *a: pytest.fail("dispatched comparison"))
        with pytest.raises(ConfigurationError, match="comparisons are paused"):
            await adapter.evaluate(adapter.review_digest)
        assert router.store._connection.total_changes == before
    finally:
        await router.close()


@pytest.mark.parametrize(
    "fault",
    [
        "mock",
        "failed",
        "unaccounted",
        "unresolved",
        "revoked",
        "runtime_changed",
        "wrong_role",
        "old_source",
    ],
)
def test_import_mock_stale_revoked_or_unaccounted_evidence_cannot_pass(
    tmp_path, monkeypatch, fault
):
    router, service, *_ = prepared(tmp_path, monkeypatch)
    binary = tmp_path.resolve() / "owned-runtime-marker"
    binary.write_text("synthetic runtime bytes; never executable")
    try:
        ref = synthetic_component(service.repository, "waza", binary, fault=fault)
        if fault == "runtime_changed":
            binary.write_text("changed")
        with pytest.raises(ConfigurationError):
            require_integration(
                service.repository,
                ref,
                component="skillrank" if fault == "wrong_role" else "waza",
                source_digest="b" * 64 if fault == "old_source" else D,
            )
    finally:
        asyncio.run(router.close())


def test_stack_requires_all_roles_both_domains_and_current_review(tmp_path, monkeypatch):
    router, service, *_ = prepared(tmp_path, monkeypatch)
    binary = tmp_path.resolve() / "owned-runtime-marker"
    binary.write_text("synthetic runtime bytes; never executable")
    try:
        components = {
            name: synthetic_component(service.repository, name, binary) for name in REQUIRED_CHECKS
        }
        record = StackCompletion(implementation_source=D, components=components)
        ref = service.repository.put("toolkit_stack_completion", content_digest(record), record)
        with pytest.raises(ConfigurationError, match="unreviewed"):
            require_stack_complete(service.repository, ref, source_digest=D)
        service.repository.review(ref)
        assert require_stack_complete(service.repository, ref, source_digest=D) == record
        with pytest.raises(ConfigurationError, match="another implementation"):
            require_stack_complete(service.repository, ref, source_digest="b" * 64)
        service.repository.review(ref, revoke=True)
        with pytest.raises(ConfigurationError, match="revoked"):
            require_stack_complete(service.repository, ref, source_digest=D)
        with pytest.raises(ValueError, match="both composed workflows"):
            StackCompletion(
                implementation_source=D,
                components={k: v for k, v in components.items() if k != "workflow-document-data"},
            )
    finally:
        asyncio.run(router.close())


def engineering_fixture(service, original, *, candidate_only=False):
    from aeep.assessment.models import (
        AssessmentComparison,
        AssessmentPlan,
        RecipeMaterializationRequest,
    )
    from aeep_toolkit.stack_readiness import EngineeringRunReview

    data = original.model_dump(mode="json")
    experiment = data["comparison"]["experiment"]
    experiment.update(
        stage="qualification",
        exposure="required",
        higher_compute=None,
        reusable_tool=None,
        reusable_artifact_digest=None,
        reusable_build_operation_ids=[],
        feasible_challengers=[],
        qualification_report_digest=None,
    )
    data["suite"].update(
        cases=[dict(data["suite"]["cases"][0], split="qualification")],
        repetitions=1,
        conditions=["router-fresh"],
        routes=[
            r for r in data["suite"]["routes"] if r["executor_id"] in {"baseline", "candidate"}
        ],
    )
    data["definition_digests"].append(
        content_digest(AssessmentComparison.model_validate(data["comparison"]))
    )
    if candidate_only:
        data['suite']['routes'] = [route for route in data['suite']['routes'] if route['executor_id'] == 'candidate']
        data['suite']['baseline_route_id'] = None
    plan = AssessmentPlan.model_validate(data)
    review = EngineeringRunReview(
        plan_digest=content_digest(plan),
        implementation_source=D,
        scope_request_id="engineering-fixture",
        case_ids=tuple(c.case_id for c in plan.suite.cases),
        maximum_model_turns=1 if candidate_only else 2,
    )
    ref = service.repository.put("toolkit_engineering_run", content_digest(review), review)
    service.repository.review(ref)
    scope = RecipeMaterializationRequest(
        plan_id=review.scope_request_id,
        subject_digest=plan.subject_digest,
        recipe_digest=plan.recipe_digest,
        mapping_digest=plan.mapping_digest,
        environment_digest=plan.environment_digest,
        authorization_id=plan.authorization_id,
        definition_digests=[*plan.definition_digests, ref],
        seed=0,
    )
    service.repository.put("recipe_materialization_request", scope.plan_id, scope)
    return plan, ref


def test_real_qualification_shape_uses_one_candidate_route_and_one_turn(tmp_path, monkeypatch):
    from aeep_toolkit.stack_readiness import require_engineering_run

    router, service, adapter, *_ = prepared(tmp_path, monkeypatch)
    try:
        plan, ref = engineering_fixture(service, adapter.plan, candidate_only=True)
        monkeypatch.setattr(service.repository, 'authorize', lambda _:None)
        assert require_engineering_run(service.repository, ref, plan=plan, source_digest=D).maximum_model_turns == 1
        # No other one-route check can borrow the candidate-only allowance.
        plan.suite.routes[0].executor_id = plan.baseline_id
        with pytest.raises(ConfigurationError):
            require_engineering_run(service.repository, ref, plan=plan, source_digest=D)
    finally:
        asyncio.run(router.close())


def test_engineering_bootstrap_requires_an_exact_separate_review_and_current_grant(
    tmp_path, monkeypatch
):
    from aeep_toolkit.stack_readiness import require_engineering_run

    router, service, adapter, *_ = prepared(tmp_path, monkeypatch)
    try:
        plan, ref = engineering_fixture(service, adapter.plan)
        calls = []
        monkeypatch.setattr(
            service.repository, "authorize", lambda request: calls.append(request.plan_id)
        )
        assert (
            require_engineering_run(
                service.repository, ref, plan=plan, source_digest=D
            ).maximum_model_turns
            == 2
        )
        assert calls == ["engineering-fixture"]
        with pytest.raises(ConfigurationError):
            require_engineering_run(service.repository, ref, plan=adapter.plan, source_digest=D)
        with pytest.raises(ConfigurationError):
            require_engineering_run(service.repository, ref, plan=plan, source_digest="f" * 64)
        service.repository.review(ref, revoke=True)
        with pytest.raises(ConfigurationError, match="revoked"):
            require_engineering_run(service.repository, ref, plan=plan, source_digest=D)
        assert calls == ["engineering-fixture"]
    finally:
        asyncio.run(router.close())


@pytest.mark.parametrize(
    "fault", ["optional", "value", "holdout", "repetitions", "cases", "routes", "turns"]
)
def test_engineering_review_cannot_be_used_to_resume_comparative_campaigns(
    tmp_path, monkeypatch, fault
):
    from aeep_toolkit.stack_readiness import EngineeringRunReview, require_engineering_run

    router, service, adapter, *_ = prepared(tmp_path, monkeypatch)
    try:
        plan, _ = engineering_fixture(service, adapter.plan)
        if fault == "optional":
            object.__setattr__(plan.comparison.experiment, "exposure", "optional")
        elif fault == "value":
            object.__setattr__(plan.comparison.experiment, "stage", "marginal_value")
        elif fault == "holdout":
            plan.suite.cases[0].split = "holdout"
        elif fault == "repetitions":
            plan.suite.repetitions = 2
        elif fault == "cases":
            object.__setattr__(plan.suite, "cases", plan.suite.cases * 7)
        elif fault == "routes":
            object.__setattr__(plan.suite, "routes", plan.suite.routes[:1])
        review = EngineeringRunReview(
            plan_digest=content_digest(plan),
            implementation_source=D,
            scope_request_id="other-scope",
            case_ids=(plan.suite.cases[0].case_id,),
            maximum_model_turns=4 if fault == "turns" else 2,
        )
        ref = service.repository.put("toolkit_engineering_run", content_digest(review), review)
        service.repository.review(ref)
        from aeep.assessment.models import RecipeMaterializationRequest

        scope = RecipeMaterializationRequest(
            plan_id="other-scope",
            subject_digest=plan.subject_digest,
            recipe_digest=plan.recipe_digest,
            mapping_digest=plan.mapping_digest,
            environment_digest=plan.environment_digest,
            authorization_id=plan.authorization_id,
            definition_digests=[*plan.definition_digests, ref],
            seed=0,
        )
        service.repository.put("recipe_materialization_request", scope.plan_id, scope)
        monkeypatch.setattr(
            service.repository,
            "authorize",
            lambda request: pytest.fail("invalid engineering plan reached grant check"),
        )
        with pytest.raises(ConfigurationError):
            require_engineering_run(service.repository, ref, plan=plan, source_digest=D)
    finally:
        asyncio.run(router.close())
