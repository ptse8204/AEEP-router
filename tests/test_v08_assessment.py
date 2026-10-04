from __future__ import annotations

import asyncio
import json
import re
from datetime import timedelta

import pytest
from conftest import manifest_with, python_spec

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    AssessmentSetupCost,
    PilotPolicy,
    content_digest,
)
from aeep.assessment.recipes import (
    VARIATIONS,
    features,
    generate_case,
    generate_reviewed_case,
    reference_csv,
    reference_search,
    reference_text,
    shipped_recipe,
)
from aeep.assessment.service import AssessmentService
from aeep.benchmarking import BenchmarkSplit
from aeep.errors import ConfigurationError, NoRouteError
from aeep.mcp.server import AEEPToolService
from aeep.models import ActionRequest, utc_now
from aeep.router import Router
from aeep.validators import ValidationContext, run_validators

pytestmark = pytest.mark.assessment_lifecycle


async def slow_csv(text, delimiter):
    await asyncio.sleep(0.004)
    return reference_csv(text, delimiter)


def custom_record(text):
    return {"record": dict(re.findall(r"(id|name) = (value-[a-f0-9]{24})", text))}


async def slow_record(text):
    await asyncio.sleep(0.004)
    return custom_record(text)


async def test_generated_definition_requires_review_and_uses_same_pipeline(tmp_path):
    recipe = shipped_recipe("text").model_copy(
        update={
            "recipe_id": "generated-record.v1",
            "capability": "example.record@1",
            "output_schema": {"type": "object", "properties": {"record": {"type": "object", "additionalProperties": {"type": "string"}}}, "required": ["record"], "additionalProperties": False},
            "generator": "record_template:1",
            "extractor": "record_template:1",
            "generator_config": {
                "fields": ["id", "name"],
                "independent_fixtures": [
                    {"input": {"text": "id = value-000000000000000000000000\nname = value-111111111111111111111111"}, "output": {"record": {"id": "value-000000000000000000000000", "name": "value-111111111111111111111111"}}},
                    {"input": {"text": "name = value-111111111111111111111111\nid = value-000000000000000000000000"}, "output": {"record": {"id": "value-000000000000000000000000", "name": "value-111111111111111111111111"}}},
                ],
                "templates": {
                    "forward": "id = {id}\nname = {name}",
                    "reverse": "name = {name}\nid = {id}",
                },
            },
            "variations": ["forward", "reverse"],
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string", "maxLength": 4096}},
                "required": ["text"],
                "additionalProperties": False,
            },
        }
    )
    routes = [
        python_spec(
            name,
            f"test_v08_assessment:{function}",
            capability=recipe.capability,
            input_schema=recipe.input_schema,
            output_schema=recipe.output_schema,
        )
        for name, function in [("candidate", "custom_record"), ("baseline", "slow_record")]
    ]
    router = Router(manifest_with(*routes))
    service = AssessmentService(router, tmp_path / "assessment")
    file = tmp_path / "plugin.txt"
    file.write_text("selected generated-recipe fixture")
    try:
        subject = service.inspect_local(file)
        digest = service.repository.put("recipe", recipe.recipe_id, recipe)
        options = dict(
            subject_id=subject.subject_id,
            family=recipe.recipe_id,
            candidate_id="candidate",
            baseline_id="baseline",
            authorization_id="grant",
            environment=AssessmentEnvironment(
                environment_id="test", kind="trusted_local", identity={"fixture": "1"}
            ),
        )
        with pytest.raises(ConfigurationError, match="first execution"):
            service.propose(**options)
        service.repository.review(digest)
        plan = service.propose(**options)
        for definition in plan.definition_digests:
            service.repository.review(definition)
        service.repository.grant(
            AssessmentAuthorization(
                authorization_id="grant",
                subject_digests=[plan.subject_digest],
                recipe_digests=[plan.recipe_digest],
                environment_digests=[plan.environment_digest],
                limits=AssessmentLimits(max_operations=1000, max_elapsed_seconds=20000),
                automatic_admission=True,
                expires_at=utc_now() + timedelta(hours=1),
            )
        )
        report = await service.run(service.enqueue(plan.plan_id))
        assert report.qualification_passed
        assert report.outcome == "useful_within_scope"
        tools = AEEPToolService(router, profile="assessment")
        name = next(
            tool["name"] for tool in tools.list_tools() if tool["name"].startswith("aeep_recipe_")
        )
        response = await tools.call(name, plan.suite.cases[0].action.input)
        assert not response.get("isError")
        service.repository.review(digest, revoke=True)
        assert name not in {tool["name"] for tool in tools.list_tools()}
        assert (
            router.route(
                ActionRequest(
                    capability=recipe.capability,
                    input=plan.suite.cases[0].action.input,
                    constraints={"allowed_executor_ids": ["candidate"]},
                )
            ).selected_executor_id
            is None
        )
        malicious = recipe.model_copy(deep=True)
        malicious.generator_config["templates"]["forward"] = "{id.__class__}"
        with pytest.raises(ConfigurationError, match="literal field"):
            generate_reviewed_case(malicious, 0, 0, BenchmarkSplit.HOLDOUT)
    finally:
        await router.close()


def setup_assessment(tmp_path, family="csv", operations=2000):
    recipe = shipped_recipe(family)
    candidate = python_spec(
        "candidate",
        f"aeep.assessment.recipes:reference_{family}",
        capability=recipe.capability,
        input_schema=recipe.input_schema,
        output_schema=recipe.output_schema,
    )
    baseline = python_spec(
        "baseline",
        "test_v08_assessment:slow_csv"
        if family == "csv"
        else f"aeep.assessment.recipes:reference_{family}",
        capability=recipe.capability,
        input_schema=recipe.input_schema,
        output_schema=recipe.output_schema,
    )
    router = Router(manifest_with(candidate, baseline))
    service = AssessmentService(router, tmp_path / "assessment")
    plugin = tmp_path / "plugin.txt"
    plugin.write_text("a reviewed local fixture")
    subject = service.inspect_local(plugin)
    environment = AssessmentEnvironment(
        environment_id="local", kind="trusted_local", identity={"runtime": "test"}
    )
    plan = service.propose(
        subject_id=subject.subject_id,
        family=family,
        candidate_id="candidate",
        baseline_id="baseline",
        authorization_id="grant",
        environment=environment,
    )
    for digest in plan.definition_digests:
        service.repository.review(digest)
    grant = AssessmentAuthorization(
        authorization_id="grant",
        subject_digests=[plan.subject_digest],
        recipe_digests=[plan.recipe_digest],
        environment_digests=[plan.environment_digest],
        automatic_admission=True,
        limits=AssessmentLimits(max_operations=operations, max_elapsed_seconds=20000),
        expires_at=utc_now() + timedelta(hours=1),
    )
    service.repository.grant(grant)
    return router, service, plan, grant


async def test_shared_preparation_is_frozen_and_charged_once_across_plans(tmp_path):
    router, service, original, grant = setup_assessment(tmp_path)
    original_digest = content_digest(original)
    try:
        setup = [AssessmentSetupCost(subject_digest=original.subject_digest, stage=stage,
                    elapsed_seconds=seconds, cpu_ms=seconds * 10)
                 for stage, seconds in [('worker_image', 2), ('inventory', 3)]]
        unrelated = AssessmentSetupCost(subject_digest='f' * 64, stage='worker_image', elapsed_seconds=7, cpu_ms=1)
        for cost in [*setup, unrelated]:
            service.repository.put('setup_cost', cost.cost_id, cost)
        options = dict(subject_id=original.subject_digest, family='csv', candidate_id='candidate',
            baseline_id='baseline', authorization_id=grant.authorization_id,
            environment=AssessmentEnvironment.model_validate(service.repository.get('environment', original.environment_digest)))
        plans = [service.propose(**options, seed=seed, pilot=PilotPolicy()) for seed in (101, 102)]
        expected = {original.setup_cost_ids[0], *(cost.cost_id for cost in setup)}
        for plan in plans:
            assert set(plan.setup_cost_ids[:-1]) == expected
            assert unrelated.cost_id not in plan.setup_cost_ids
            assert original.setup_cost_ids[-1] not in plan.setup_cost_ids
        later = AssessmentSetupCost(subject_digest=original.subject_digest, stage='later_setup', elapsed_seconds=11, cpu_ms=1)
        service.repository.put('setup_cost', later.cost_id, later)
        for plan in plans:
            for digest in plan.definition_digests:
                service.repository.review(digest)
            report = await service.run(service.enqueue(plan.plan_id))
            ledger = service.repository.get('operation_ledger', report.operation_ledger_digest)
            measured = [operation for operation in ledger['operations'] if operation['operation_id'] in expected]
            assert len(measured) == len(expected)
            assert all(operation['elapsed_seconds'] is not None for operation in measured)
            assert later.cost_id not in {operation['operation_id'] for operation in ledger['operations']}
        rows = router.store._connection.execute(
            "SELECT id,state FROM assessment_operations WHERE id IN (?,?)",
            tuple(cost.cost_id for cost in setup),
        ).fetchall()
        assert {row[0]: row[1] for row in rows} == {cost.cost_id: 'complete' for cost in setup}
        for cost in setup:
            measurement = service.repository.get('operation_measurement', cost.cost_id)
            assert measurement['elapsed_seconds'] == cost.elapsed_seconds
        assert content_digest(service.repository.get('plan', original.plan_id)) == original_digest
    finally:
        await router.close()


@pytest.mark.parametrize("family", VARIATIONS)
async def test_synthetic_recipes_validate_good_and_reject_faulty_outputs(tmp_path, family):
    reference = {"csv": reference_csv, "text": reference_text, "search": reference_search}[family]
    seen = set()
    for index in range(105):
        case, variation = generate_case(
            family, index, 1234, BenchmarkSplit.HOLDOUT, fixture_root=tmp_path
        )
        again, _ = generate_case(family, index, 1234, BenchmarkSplit.HOLDOUT, fixture_root=tmp_path)
        assert case.action.input == again.action.input
        seen.add(variation)
        good = await run_validators(
            case.validators,
            ValidationContext(case.action.input, reference(**case.action.input)),
            {},
        )
        bad = await run_validators(
            case.validators, ValidationContext(case.action.input, {"wrong": True}), {}
        )
        assert all(result.valid for result in good)
        assert all(result.valid is False for result in bad)
    assert seen == set(VARIATIONS[family])


async def test_complete_assessment_admission_scope_and_revocation(tmp_path, monkeypatch):
    router, service, plan, grant = setup_assessment(tmp_path)
    try:
        job = service.enqueue(plan.plan_id)
        assert service.enqueue(plan.plan_id) == job
        report = await service.run(job)
        assert report.qualification_passed, report.explanations
        assert report.distinct_holdout_cases == 105
        assert report.distinct_paired_cases == 105
        assert report.outcome == "useful_within_scope"
        assert not router.store.list_receipts()
        assert await service.run(job) == report
        without_grader = report.model_copy(update={"report_id": "missing-grader", "grader_validation_digest": None})
        service.repository.put("report", without_grader.report_id, without_grader)
        with pytest.raises(ConfigurationError, match="grader-validation"):
            service.admit(without_grader.report_id)
        admission = service.admit(report.report_id)
        assert admission.executor_id == "candidate"
        bound = {content_digest(plan), plan.subject_digest, plan.recipe_digest,
            plan.mapping_digest, plan.environment_digest, *plan.definition_digests}
        trial = router._campaign_router([router.registry.get('baseline')],
            plan_digest=content_digest(plan), snapshot_bound_digests=bound)
        try:
            assert trial.store._connection.execute(
                "SELECT COUNT(*) FROM assessment_records WHERE kind='admission'").fetchone()[0] >= 1
            assert trial.store._connection.execute(
                "SELECT COUNT(*) FROM assessment_admissions WHERE executor_id='candidate'").fetchone()[0] == 1
            assert trial.store._connection.execute(
                "SELECT COUNT(*) FROM assessment_records WHERE kind='plan'").fetchone()[0] == 1
            candidate = trial.registry.get('candidate')  # Active admitted, but not a trial subject.
            request = ActionRequest(capability='assessment.csv@1',
                input={'text': 'id,name,note\nx,y,z\n', 'delimiter': ','})
            trial._require_active_spec(candidate, request)
            with trial.store._immediate_transaction() as connection:
                connection.execute("UPDATE assessment_admissions SET revoked=1 WHERE executor_id='candidate'")
            with pytest.raises(NoRouteError):
                trial._require_active_spec(candidate, request)
            assert router.store._connection.execute(
                "SELECT revoked FROM assessment_admissions WHERE executor_id='candidate'").fetchone()[0] == 0
        finally:
            await trial.close()
        earlier_report = report
        from aeep.assessment.models import AssessmentEnvironment

        reassessment = service.propose(
            subject_id=plan.subject_digest,
            family="csv",
            candidate_id="candidate",
            baseline_id="baseline",
            authorization_id=grant.authorization_id,
            environment=AssessmentEnvironment.model_validate(
                service.repository.get("environment", plan.environment_digest)
            ),
            seed=1,
        )
        report = await service.run(service.enqueue(reassessment.plan_id))
        assert report.outcome == "useful_within_scope"
        with monkeypatch.context() as patch:
            original_get = router.store.get_route_candidate
            current_candidate = original_get("candidate")
            assert current_candidate is not None
            bad_candidate = current_candidate.model_copy(update={"behavior_fingerprint": "0" * 64})
            patch.setattr(
                router.store,
                "get_route_candidate",
                lambda identity: (
                    bad_candidate if identity == "candidate" else original_get(identity)
                ),
            )
            before = router.store._connection.execute(
                "SELECT count(*) FROM qualification_reports"
            ).fetchone()[0]
            with pytest.raises(ConfigurationError, match="atomic admission"):
                service.admit(earlier_report.report_id)
            assert (
                router.store._connection.execute(
                    "SELECT count(*) FROM qualification_reports"
                ).fetchone()[0]
                == before
            )
        with monkeypatch.context() as patch:
            import sys

            from aeep.assessment.service import ReviewedMapping
            from aeep.models import ExecutorKind, ExecutorSpec

            managed = ExecutorSpec(
                id="candidate",
                capability=plan.suite.domain,
                kind=ExecutorKind.MANAGED_HOST,
                description="fixture",
                resource_pool="fixture",
                config={"adapter_id": "codex", "argv": [sys.executable], "instructions": "fixture"},
            )
            patch.setattr(
                service,
                "_verify_dependencies",
                lambda _plan: ReviewedMapping(
                    candidate=managed, baseline=router.registry.get("baseline")
                ),
            )
            with pytest.raises(ConfigurationError, match="resolved runtime identity"):
                service.admit(report.report_id)
        clone = Router(router.manifest, store=router.store.campaign_snapshot())
        assert clone.registry.get("candidate").enabled
        await clone.close()
        request = ActionRequest(
            capability="assessment.csv@1", input={"text": "id,name,note\nx,y,z\n", "delimiter": ","}
        )
        from aeep.assessment import applicability

        spec = router.registry.get("candidate")
        baseline = router.registry.get("baseline")
        scoped = router.store.campaign_snapshot(bound_digests={content_digest(plan)})
        try:
            applicability.require_applicable(scoped, spec, request, baseline)
            for table in ("assessment_grants", "assessment_reviews", "assessment_admissions"):
                assert list(scoped._connection.execute(f"SELECT * FROM {table} ORDER BY 1")) == list(router.store._connection.execute(f"SELECT * FROM {table} ORDER BY 1"))
            with scoped._immediate_transaction() as connection:
                connection.execute("UPDATE assessment_admissions SET revoked=1")
            with pytest.raises(NoRouteError, match="revoked"):
                applicability.require_applicable(scoped, spec, request, baseline)
            assert router.store._connection.execute("SELECT revoked FROM assessment_admissions").fetchone()[0] == 0
        finally:
            scoped.close()
        for changed_spec, changed_baseline in (
            (spec.model_copy(update={"config": {"callable": "builtins:len"}}), baseline),
            (spec, baseline.model_copy(update={"config": {"callable": "builtins:len"}})),
        ):
            with pytest.raises(NoRouteError):
                applicability.require_applicable(router.store, changed_spec, request, changed_baseline)
            assert router.store._connection.execute("SELECT revoked FROM assessment_admissions").fetchone()[0] == 1
            with router.store._immediate_transaction() as connection:
                connection.execute("UPDATE assessment_admissions SET revoked=0, revoked_at=NULL")
        with monkeypatch.context() as patch:
            def drift(_dependencies):
                raise ConfigurationError("fixture executable drift")
            patch.setattr(applicability, "verify_dependencies", drift)
            with pytest.raises(NoRouteError):
                applicability.require_applicable(router.store, spec, request, baseline)
        assert router.store._connection.execute("SELECT revoked FROM assessment_admissions").fetchone()[0] == 1
        with router.store._immediate_transaction() as connection:
            connection.execute("UPDATE assessment_admissions SET revoked=0, revoked_at=NULL")
        applicability.require_applicable(router.store, baseline, request)
        with monkeypatch.context() as patch:
            original_features = applicability.recipe_features
            def untested_combination(recipe, value):
                observed = original_features(recipe, value)
                observed["unicode"] = True
                return observed
            patch.setattr(applicability, "recipe_features", untested_combination)
            with pytest.raises(NoRouteError):
                applicability.require_applicable(router.store, spec, request, baseline)
        with pytest.raises(NoRouteError):
            applicability.require_applicable(router.store, spec, None, baseline)
        with monkeypatch.context() as patch:
            patch.setattr(applicability, "utc_now", lambda: grant.expires_at + timedelta(days=1))
            with pytest.raises(NoRouteError):
                applicability.require_applicable(router.store, spec, request, baseline)
        with pytest.raises(NoRouteError):
            applicability.require_applicable(router.store, spec, request)
        with monkeypatch.context() as patch:
            patch.setattr(applicability, "recipe_implementation_digest", lambda: "0" * 64)
            with pytest.raises(NoRouteError):
                applicability.require_applicable(router.store, spec, request, baseline)
        assert router.store._connection.execute("SELECT revoked FROM assessment_admissions").fetchone()[0] == 1
        # Restore the fixture to exercise the next independent failure boundary.
        with router.store._immediate_transaction() as connection:
            connection.execute("UPDATE assessment_admissions SET revoked=0, revoked_at=NULL")
        path = tmp_path / "plugin.txt"
        original = path.read_text()
        path.write_text("changed plugin")
        with pytest.raises(NoRouteError):
            applicability.require_applicable(router.store, spec, request, baseline)
        path.write_text(original)
        with pytest.raises(NoRouteError):
            applicability.require_applicable(router.store, spec, request, baseline)
        with router.store._immediate_transaction() as connection:
            connection.execute("UPDATE assessment_admissions SET revoked=0, revoked_at=NULL")
        with monkeypatch.context() as patch:
            patch.setattr(
                service.repository,
                "authorize",
                lambda _plan: grant.model_copy(update={"automatic_admission": False}),
            )
            with pytest.raises(ConfigurationError, match="automatic admission"):
                service.admit(report.report_id)
        assert (await router.execute(request)).ok
        request.constraints.allowed_executor_ids = ["candidate"]
        decision = router.route(request)
        assert decision.selected_executor_id == "candidate"
        outside = request.model_copy(deep=True)
        outside.input["delimiter"] = "\t"
        assert router.route(outside).selected_executor_id is None
        from aeep.models import ValidationKind, ValidationResult, new_id

        successful = (await router.execute(decision)).receipts[-1]
        with monkeypatch.context() as patch:
            from aeep.models import RawExecution, ResourceVector
            async def invalid_result(_context):
                return RawExecution(status="success", output={"unexpected": True}, resources=ResourceVector(cpu_ms=7))
            patch.setattr(router._executors[ExecutorKind.PYTHON], "execute", invalid_result)
            invalid = await router.execute(decision)
            assert not invalid.ok and invalid.receipts[-1].actual_resources.cpu_ms == 7
        assert router.store._connection.execute("SELECT revoked FROM assessment_admissions").fetchone()[0] == 1
        with router.store._immediate_transaction() as connection:
            connection.execute("UPDATE assessment_admissions SET revoked=0, revoked_at=NULL")
        failed = successful.model_copy(
            update={
                "receipt_id": new_id("rcpt"),
                "validation_results": [
                    ValidationResult(kind=ValidationKind.EXACT_MATCH, valid=False)
                ],
            }
        )
        router._save_receipt(failed)
        with pytest.raises(ConfigurationError, match="fresh assessment"):
            service.admit(report.report_id)
        with pytest.raises(ConfigurationError, match="fresh assessment"):
            service.admit(earlier_report.report_id)
        service.repository.revoke(grant.authorization_id)
        assert router.route(request).selected_executor_id is None
        with pytest.raises(NoRouteError):
            await router.execute(decision)
        assert (
            router.store._connection.execute(
                "SELECT revoked FROM assessment_admissions"
            ).fetchone()[0]
            == 1
        )
    finally:
        await router.close()


@pytest.mark.parametrize("family", ["text", "search"])
async def test_other_families_run_through_same_campaign(tmp_path, family):
    router, service, plan, _grant = setup_assessment(tmp_path, family)
    try:
        report = await service.run(service.enqueue(plan.plan_id))
        assert report.qualification_passed, report.explanations
        assert report.distinct_holdout_cases == 105
    finally:
        await router.close()


async def test_budget_review_drift_and_cancellation_fail_closed(tmp_path):
    router, service, plan, grant = setup_assessment(tmp_path, operations=1)
    try:
        service.repository.review(plan.mapping_digest, revoke=True)
        with pytest.raises(ConfigurationError, match="review"):
            service.enqueue(plan.plan_id)
        service.repository.review(plan.mapping_digest)
        job = service.enqueue(plan.plan_id)
        service.cancel(job)
        with pytest.raises(ConfigurationError, match="stopped"):
            service.repository.reserve(
                plan, "cancelled-op", AssessmentLimits(max_operations=1, max_elapsed_seconds=1)
            )
        with pytest.raises(ConfigurationError, match="cancelled"):
            await service.run(job)
        assert service.enqueue(plan.plan_id) == job
        plan = plan.model_copy(
            update={
                "plan_id": plan.plan_id + "_retry",
                "suite": plan.suite.model_copy(update={"suite_id": plan.suite.suite_id + "_retry"}),
            }
        )
        service.repository.put("plan", plan.plan_id, plan)
        other = service.enqueue(plan.plan_id)
        report = await service.run(other)
        assert report.outcome == "insufficient_evidence"
        assert not report.qualification_passed
        assert not router.store.list_receipts()
        with pytest.raises(ConfigurationError, match="measured benefit"):
            service.admit(report.report_id)
        (tmp_path / "plugin.txt").write_text("changed")
        with pytest.raises(ConfigurationError, match="changed"):
            service._verify_dependencies(plan)
        service.repository.revoke(grant.authorization_id)
        with pytest.raises(ConfigurationError, match="revoked"):
            service.enqueue(plan.plan_id)
    finally:
        await router.close()


async def test_durable_reservations_cannot_replay_or_expand(tmp_path):
    router, service, plan, _grant = setup_assessment(tmp_path)
    try:
        limits = AssessmentLimits(max_operations=1, max_elapsed_seconds=1)
        service.repository.reserve(plan, "op", limits)
        with pytest.raises(ConfigurationError, match="already reserved"):
            service.repository.reserve(plan, "op", limits)
        with pytest.raises(ConfigurationError, match="budget"):
            service.repository.reserve(
                plan, "model", limits.model_copy(update={"max_model_turns": 1})
            )
        service.repository.finish_operation("op", elapsed_seconds=0.5)
        with pytest.raises(ConfigurationError, match="terminal"):
            service.repository.finish_operation("op", elapsed_seconds=0.5)
        for elapsed in [float("inf"), float("nan"), -1]:
            with pytest.raises(ConfigurationError, match="measurement"):
                service.repository.finish_operation("op", elapsed_seconds=elapsed)
        changed = plan.model_copy(update={"baseline_id": "other"})
        with pytest.raises(ConfigurationError, match="immutable"):
            service.repository.put("plan", plan.plan_id, changed)
        assert service.repository.get("plan", content_digest(plan))["plan_id"] == plan.plan_id
        with pytest.raises(ConfigurationError, match="scope"):
            service.repository.authorize(plan.model_copy(update={"subject_digest": "0" * 64}))
        with pytest.raises(ConfigurationError, match="unknown"):
            service.repository.get("plan", "absent")
        with pytest.raises(ConfigurationError, match="stored exact"):
            service.repository.review("0" * 64)
        service.repository.reserve(plan, "overrun", limits)
        service.repository.finish_operation("overrun", elapsed_seconds=2)
        with pytest.raises(ConfigurationError, match="revoked"):
            service.repository.authorize(plan)
    finally:
        await router.close()


async def test_focused_tools_do_not_expose_operator_arguments(tmp_path):
    router, _service, _plan, _grant = setup_assessment(tmp_path)
    try:
        service = AEEPToolService(router, profile="assessment")
        names = {tool["name"] for tool in service.list_tools()}
        assert names == {
            "aeep_csv",
            "aeep_text",
            "aeep_search",
            "aeep_assessment_start",
            "aeep_assessment_status",
            "aeep_assessment_report",
            "aeep_assessment_cancel",
            "aeep_assessment_generate_definition",
            "aeep_assessment_structures",
            "aeep_assessment_select_structure",
            "aeep_assessment_budget",
            "aeep_assessment_options",
            "aeep_assessment_setup",
            "aeep_assessment_generate_cases",
            "aeep_lookup_capability",
        }
        assert len(AEEPToolService(router).list_tools()) == 11
        response = await service.call("aeep_csv", {"text": "a,b\nx,y\n", "delimiter": ","})
        assert not response.get("isError")
        response = await service.call(
            "aeep_csv", {"text": "a,b", "delimiter": ",", "approved_side_effect": "financial"}
        )
        assert response["isError"]
        response = await service.call("aeep_execute_action", {})
        assert response["isError"]
        response = await service.call("aeep_assessment_start", {"plan_id": "unknown"})
        assert response["isError"]
        with pytest.raises(ConfigurationError):
            AEEPToolService(router, profile="unknown")
    finally:
        await router.close()


def test_feature_and_file_boundaries(tmp_path):
    assert features("unknown", {}) is None
    assert features("csv", {}) is None
    assert features("csv", {"text": "x" * 100001, "delimiter": ","}) is None
    assert features("csv", {"text": 123, "delimiter": ","}) is None
    assert features("text", {"text": "x", "fields": [1]}) is None
    assert features("search", {"root": str(tmp_path), "path": "../", "query": "x"}) is None
    assert reference_csv("a,a\nx,y") == {"error": "invalid_input"}
    assert reference_csv("a,b\nx") == {"error": "invalid_input"}
    assert reference_csv("") == {"error": "invalid_input"}
    assert reference_search(str(tmp_path), "x", "../") == {"error": "invalid_input"}
    assert reference_search(str(tmp_path), "x") == {"matches": []}
    (tmp_path / "oversized").write_text("x" * 1000001)
    assert reference_search(str(tmp_path), "x") == {"error": "invalid_input"}
    with pytest.raises(ConfigurationError):
        shipped_recipe("unknown")
    with pytest.raises(ConfigurationError):
        generate_case("search", 0, 0, BenchmarkSplit.HOLDOUT)
    with pytest.raises(ValueError):
        AssessmentEnvironment(
            environment_id="x", kind="container", identity={}, container_image="latest"
        )
    with pytest.raises(ValueError):
        AssessmentLimits(max_operations=1, max_elapsed_seconds=float("inf"))
    assert "NaN" not in json.dumps(shipped_recipe("csv").model_dump())
