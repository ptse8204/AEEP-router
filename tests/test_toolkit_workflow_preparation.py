"""Canonical setup and source guards; synthetic fixtures, no upstream execution."""

import asyncio
import base64
import hashlib
import io
import json
import random
import zipfile
from datetime import timedelta
from pathlib import Path

import pytest
from test_toolkit_runtime_install import installer_fixture_capacity as installer_fixture_capacity
from test_toolkit_workflow_v2 import definition
from test_v08_executable_recipes import definition as recipe_definition
from test_v08_incremental import environment as differential_environment
from test_v08_managed_workers import binding

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    AssessmentPlan,
    AssessmentSetupRequest,
    IncrementalExperiment,
    IntegrationCaseSet,
    RecipeCaseSet,
    RecipeDefinition,
    UtilityPolicy,
    content_digest,
)
from aeep.assessment.onboarding import incremental_host_routes
from aeep.assessment.service import AssessmentService
from aeep.benchmarking import BenchmarkCase
from aeep.errors import ConfigurationError, InputValidationError
from aeep.hosts.base import HostModel
from aeep.models import (
    ActionRequest,
    ManagedHostInvocation,
    Manifest,
    SubscriptionResource,
    ValidationSpec,
    utc_now,
)
from aeep.router import Router
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.cli import main
from aeep_toolkit.models import SourcePin
from aeep_toolkit.workflow import prepare_stack
from aeep_toolkit.workflow_preparation import TaskRightsReview, prepare_canonical


def configured(tmp_path, *, large=False, grader_container=False):
    path, data, skill = definition(tmp_path)
    selected = data["configurations"]["document-data"]
    benchmark_path = path.parent / "benchmark.json"
    pack = BenchmarkPack.model_validate_json(benchmark_path.read_bytes())
    task = pack.tasks[0]
    if large:
        raw = random.Random(183).randbytes(1_200_000)
        (path.parent/'task-pack/data.csv').write_bytes(raw)
        asset = next(item for item in task.assets if item.path == 'data.csv')
        asset.bytes = len(raw)
        asset.sha256 = hashlib.sha256(raw).hexdigest()
    rights = TaskRightsReview(
        source_revision=pack.source.revision,
        task_id=task.task_id,
        assets={a.path: a.sha256 for a in task.assets},
        basis=["Synthetic owned test bytes"],
        local_execution_allowed=True,
        provider_disclosure_allowed=True,
    )
    task.rights_review_ref = content_digest(rights)
    benchmark_path.write_text(pack.model_dump_json())
    selected["benchmark"]["sha256"] = hashlib.sha256(benchmark_path.read_bytes()).hexdigest()
    recipe = recipe_definition()
    recipe.input_schema = {"type": "object"}
    recipe.dependencies["benchmark_pack"] = content_digest(pack.model_dump(mode="json"))
    control = binding().model_copy(update={"worker_id": "control"})
    routes = incremental_host_routes(
        recipe=recipe,
        control_worker=control,
        treatment_worker=control.model_copy(update={"worker_id": "treatment"}),
        higher_worker=control.model_copy(update={"worker_id": "higher"}),
        reusable_worker=control.model_copy(update={"worker_id": "reusable"}),
        candidate_invocation=ManagedHostInvocation(
            mode="skill",
            skill_name="fixture",
            skill_path="/opt/plugin/SKILL.md",
            skill_sha256=hashlib.sha256((skill / "SKILL.md").read_bytes()).hexdigest(),
        ),
        model=HostModel(id="synthetic-model", reasoning_efforts=("low", "medium")),
        normal_effort="low",
        effort_order=("low", "medium"),
        timeout_seconds=30,
        protocol_user_agent="fixture",
    )
    routes[1].config["invocation"]["exposure"] = "required"
    for route in routes:
        route.config["artifact"] = dict(
            input_field="task_archive_b64",
            output_field="deliverable_archive_b64",
            input_name="task.zip",
            output_name="deliverables.zip",
            max_bytes=4_000_000,
        )
    manifest = Manifest(
        database=str(path.parent / "canonical.sqlite3"),
        executors=routes,
        resources=[SubscriptionResource(id="codex.self", provider="openai", product="codex")],
    )
    manifest_path = path.parent / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json())
    router = Router.from_manifest(manifest_path)
    service = AssessmentService(router, path.parent / "assessments")
    repo = service.repository
    subject = service.inspect_local(skill, kind="skill")
    environment = AssessmentEnvironment(
        environment_id="synthetic-container", identity={},
        kind="container" if grader_container else "codex_sandbox",
        container_image="sha256:" + "a" * 64 if grader_container else None,
        container_runtime=str(tmp_path / "fixture-container") if grader_container else None,
        container_socket=str(tmp_path / "fixture-container.sock") if grader_container else None,
    )
    recipe_ref = repo.put("recipe", recipe.recipe_id, recipe)
    env_ref = repo.put("environment", environment.environment_id, environment)
    experiment = IncrementalExperiment(
        stage="qualification",
        exposure="required",
        environment=differential_environment(),
        utility=UtilityPolicy(
            benefit_dimensions=["wall_time_ms"], guardrail_dimensions=["wall_time_ms"]
        ),
    )
    exp_ref = repo.put("experiment", content_digest(experiment), experiment)
    repo.review(exp_ref)
    repo.review(recipe_ref)
    repo.put("toolkit_task_rights", content_digest(rights), rights)
    repo.review(content_digest(rights))
    case = BenchmarkCase(
        case_id="upstream-fixture",
        split="qualification",
        variation="1",
        template_family="list-count",
        action=ActionRequest(
            capability=recipe.capability,
            input=task_input(pack, path.parent / "task-pack", task.task_id),
        ),
        validators=[ValidationSpec(kind="exact_match", config={"expected": {"count": 1}})],
    )
    cases = IntegrationCaseSet(
        request_id="integration-preparation",
        recipe_digest=recipe_ref,
        environment_digest=env_ref,
        benchmark_pack_digest=content_digest(pack.model_dump(mode="json")),
        seed=0,
        cases=[case],
    )
    cases_ref = repo.put("integration_case_set", content_digest(cases), cases)
    repo.review(cases_ref)
    repo.grant(
        AssessmentAuthorization(
            authorization_id="synthetic-grant",
            subject_digests=[content_digest(subject)],
            recipe_digests=[recipe_ref],
            environment_digests=[env_ref],
            limits=AssessmentLimits(
                max_model_turns=6, max_operations=100, max_elapsed_seconds=1000
            ),
            expires_at=utc_now() + timedelta(hours=1),
        )
    )
    request = AssessmentSetupRequest(
        schema_version="assessment.setup.v2",
        authorization_id="synthetic-grant",
        subject_id=subject.subject_id,
        recipe_id=recipe.recipe_id,
        environment_id=environment.environment_id,
        candidate_id=routes[1].id,
        baseline_id=routes[0].id,
        structure="controlled_agent",
        experiment_id=exp_ref,
        integration_case_set_id=cases_ref,
    )
    source = SourcePin(
        repository="https://example.test/owned-fixture",
        revision="d" * 40,
        artifact_sha256=selected["candidate"]["sha256"],
        license_expression="MIT",
        data_rights="Owned synthetic bytes",
    )

    def bind_file(name, value):
        target = path.parent / (name + ".json")
        target.write_text(value.model_dump_json())
        return {"path": target.name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}

    selected["benchmark_recipe"] = bind_file("recipe", recipe)
    selected["preparation"] = {
        "request": bind_file("request", request),
        "source": bind_file("source", source),
        "manifest": {
            "path": manifest_path.name,
            "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        },
    }
    path.write_text(json.dumps(data))
    return path, service, cases, rights


def test_public_asset_transport_is_exact_and_excludes_answers_installers_and_skills(tmp_path):
    path, *_ = definition(tmp_path)
    pack = BenchmarkPack.model_validate_json((path.parent / "benchmark.json").read_bytes())
    value = task_input(pack, path.parent / "task-pack", "fixture")
    assert value == task_input(pack, path.parent / "task-pack", "fixture")
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(value["task_archive_b64"]))) as archive:
        assert set(archive.namelist()) == {"task.md", "data.csv"}
        assert archive.read("task.md").decode() == value["task"]
        assert archive.read("data.csv") == (path.parent / "task-pack/data.csv").read_bytes()


def test_canonical_prepare_uses_existing_service_without_execution_and_is_recoverable(
    tmp_path, monkeypatch, capsys
):
    path, service, cases, _ = configured(tmp_path)
    repo = service.repository
    preview = prepare_stack(path, "document-data")
    before = repo.store._connection.execute("SELECT count(*) FROM assessment_grants").fetchone()[0]
    monkeypatch.setattr(service, "enqueue", lambda *_: pytest.fail("started execution"))
    # Return this actual fixture service's Router, so the ordinary setup path and
    # canonical proposals run without loading any upstream worker.
    monkeypatch.setattr(Router, "from_manifest", lambda *_: service.router)
    monkeypatch.setattr(service.router, "close", _no_close)
    try:
        args = [
            "workflow",
            "prepare",
            "--workflow",
            str(path),
            "--configuration",
            "document-data",
            "--reviewed-digest",
            preview["review_sha256"],
            "--write-plan",
            str(tmp_path / "prepared"),
        ]
        assert main(args) == 0
        result = json.loads(capsys.readouterr().out)
        plan = AssessmentPlan.model_validate(repo.get("plan", result["plan_id"]))
        assert plan.schema_version == "assessment.plan.v7"
        assert plan.suite.cases == cases.cases and len(plan.suite.routes) == 1
        assert plan.integration_case_set_digest == content_digest(cases)
        assert not result["execution_authorized"] and result["models_started"] == 0
        assert (
            repo.store._connection.execute("SELECT count(*) FROM assessment_grants").fetchone()[0]
            == before
        )
        assert (
            repo.store._connection.execute("SELECT count(*) FROM assessment_jobs").fetchone()[0]
            == 0
        )
        assert (
            repo.store._connection.execute("SELECT count(*) FROM assessment_operations").fetchone()[
                0
            ]
            == 0
        )
        bound = prepare_stack(tmp_path / "prepared/workflow.json", "document-data")
        assert bound["assessment"]["backend_review"]["plan_id"] == plan.plan_id
        # Recover the existing immutable draft rather than generating another.
        again = prepare_canonical(
            path,
            "document-data",
            reviewed_digest=preview["review_sha256"],
            destination=tmp_path / "recovered",
        )
        assert again["plan_id"] == plan.plan_id
        assert service.budget_preview(plan.plan_id)["purpose"] == "stack_integration_only"
        assert service.budget_preview(plan.plan_id)["minimum_trial_model_turns"] == 1
        from aeep.assessment.reporting import fit_report
        from aeep.benchmarking import BenchmarkCampaignReport

        campaign = BenchmarkCampaignReport(
            run_id="fixture-empty",
            suite_id=plan.plan_id,
            domain=plan.suite.domain,
            trials=[],
            deterministic_tools_available=True,
            pricing_snapshot_ids=[],
            frozen_holdout_decisions={},
            summaries=[],
            baseline_deltas=[],
            oracles=[],
            subscription_conservation=[],
        )
        recipe = RecipeDefinition.model_validate(repo.get("recipe", plan.recipe_digest))
        report = fit_report(plan, recipe, campaign)
        assert not report.qualification_passed and report.outcome == "insufficient_evidence"
        assert any("Stack integration only" in text for text in report.explanations)
        for change in ("version", "holdout", "repetitions", "extra_route"):
            raw = plan.model_dump(mode="json")
            if change == "version":
                raw["schema_version"] = "assessment.plan.v4"
            elif change == "holdout":
                raw["suite"]["cases"][0]["split"] = "holdout"
            elif change == "repetitions":
                raw["suite"]["repetitions"] = 2
            else:
                raw["suite"]["routes"].append(
                    {"route_id": plan.baseline_id, "executor_id": plan.baseline_id}
                )
            with pytest.raises(ValueError):
                AssessmentPlan.model_validate(raw)
    finally:
        asyncio.run(Router.close(service.router))


async def _no_close():
    pass


@pytest.mark.parametrize(
    "fault",
    ["pack", "environment", "seed", "template", "validators", "input_schema", "not_qualification"],
)
def test_integration_task_sets_keep_their_reviewed_contract(tmp_path, fault):
    from aeep.assessment.integration_cases import require_integration_cases

    path, service, cases, _ = configured(tmp_path)
    repo = service.repository
    request = AssessmentSetupRequest.model_validate_json(
        (path.parent / "request.json").read_bytes()
    )
    recipe = RecipeDefinition.model_validate(repo.get("recipe", request.recipe_id))
    environment = AssessmentEnvironment.model_validate(
        repo.get("environment", request.environment_id)
    )
    experiment = IncrementalExperiment.model_validate(repo.get("experiment", request.experiment_id))
    raw = cases.model_dump(mode="json")
    if fault == "pack":
        raw["benchmark_pack_digest"] = "f" * 64
    elif fault == "environment":
        raw["environment_digest"] = "f" * 64
    elif fault == "seed":
        raw["seed"] = 10
    elif fault == "template":
        raw["cases"][0]["template_family"] = "unreviewed"
    elif fault == "validators":
        raw["cases"][0]["validators"] = []
    elif fault == "input_schema":
        recipe.input_schema = {"type": "object", "required": ["missing"]}
        raw["recipe_digest"] = content_digest(recipe)
    else:
        object.__setattr__(experiment, "stage", "marginal_value")
    record = IntegrationCaseSet.model_validate(raw)
    ref = repo.put("integration_case_set", content_digest(record), record)
    repo.review(ref)
    try:
        with pytest.raises((ConfigurationError, InputValidationError)):
            require_integration_cases(
                repo, ref, recipe=recipe, environment=environment, seed=0, experiment=experiment
            )
    finally:
        asyncio.run(service.router.close())


@pytest.mark.parametrize(
    "fault",
    ["rights_revoked", "wrong_input", "case_revoked", "wrong_tasks", "stale_review", "interrupted"],
)
def test_bad_inputs_or_uncertain_preparation_cannot_create_another_plan(
    tmp_path, monkeypatch, fault
):
    from aeep_toolkit.workflow_preparation import PreparationIntent

    path, service, cases, rights = configured(tmp_path)
    repo = service.repository
    preview = prepare_stack(path, "document-data")
    monkeypatch.setattr(Router, "from_manifest", lambda *_: service.router)
    monkeypatch.setattr(service.router, "close", _no_close)
    if fault == "rights_revoked":
        repo.review(content_digest(rights), revoke=True)
    if fault == "case_revoked":
        repo.review(content_digest(cases), revoke=True)
    if fault in {"wrong_input", "wrong_tasks"}:
        raw = cases.model_dump(mode="json")
        raw["cases"][0]["action"]["input"]["task" if fault == "wrong_input" else "task_id"] = (
            "wrong"
        )
        changed = IntegrationCaseSet.model_validate(raw)
        changed_ref = repo.put("integration_case_set", content_digest(changed), changed)
        repo.review(changed_ref)
        data = json.loads(path.read_text())
        request_path = path.parent / "request.json"
        request = json.loads(request_path.read_text())
        request["integration_case_set_id"] = changed_ref
        request_path.write_text(json.dumps(request))
        data["configurations"]["document-data"]["preparation"]["request"]["sha256"] = (
            hashlib.sha256(request_path.read_bytes()).hexdigest()
        )
        path.write_text(json.dumps(data))
        preview = prepare_stack(path, "document-data")
    if fault == "interrupted":
        request = AssessmentSetupRequest.model_validate(preview["preparation"]["request"])
        intent = PreparationIntent(
            workflow_review=preview["review_sha256"],
            configuration="document-data",
            request_digest=content_digest(request),
        )
        repo.put("toolkit_workflow_preparation", content_digest(intent), intent)
    try:
        with pytest.raises(ConfigurationError):
            prepare_canonical(
                path,
                "document-data",
                reviewed_digest="f" * 64 if fault == "stale_review" else preview["review_sha256"],
                destination=tmp_path / "out",
            )
        assert not (tmp_path / "out").exists()
        assert (
            repo.store._connection.execute(
                "SELECT count(*) FROM assessment_records WHERE kind='plan'"
            ).fetchone()[0]
            == 0
        )
    finally:
        asyncio.run(Router.close(service.router))


def test_small_task_set_cannot_relax_formal_counts_or_acquire_value_semantics(tmp_path):
    path, service, cases, _ = configured(tmp_path)
    try:
        with pytest.raises(ValueError):
            RecipeCaseSet(
                request_id="x",
                recipe_digest=cases.recipe_digest,
                environment_digest=cases.environment_digest,
                seed=0,
                cases=cases.cases,
            )
        for mutation in ("holdout", "repeated_task"):
            raw = cases.model_dump(mode="json")
            if mutation == "holdout":
                raw["cases"][0]["split"] = "holdout"
            else:
                raw["cases"].append(raw["cases"][0])
            with pytest.raises(ValueError):
                IntegrationCaseSet.model_validate(raw)
        request = AssessmentSetupRequest.model_validate_json(
            (path.parent / "request.json").read_bytes()
        )
        legacy = request.model_dump(mode="json")
        legacy["schema_version"] = "assessment.setup.v1"
        with pytest.raises(ValueError):
            AssessmentSetupRequest.model_validate(legacy)
        legacy.pop("integration_case_set_id")
        legacy["experiment_id"] = None
        old = AssessmentSetupRequest.model_validate(legacy)
        assert "integration_case_set_id" not in old.model_dump(mode="json")
    finally:
        asyncio.run(service.router.close())


def test_canonical_export_retains_runtime_consumer_bindings(tmp_path, monkeypatch, installer_fixture_capacity):
    from test_toolkit_runtime_install import installation

    from aeep_toolkit.installation import manifest_digest
    from aeep_toolkit.models import ExtensionManifest
    from aeep_toolkit.workflow_runtime import lifecycle_preview

    path, service, *_ = configured(tmp_path)
    folder = tmp_path / "owned-install-plan"
    folder.mkdir()
    plan = installation(folder)
    install_file = folder / "installation.json"
    install_file.write_text(plan.model_dump_json())
    data = json.loads(path.read_bytes())
    registry_path, policy_path = tmp_path / "registry.json", tmp_path / "policy.json"
    registry, policy = json.loads(registry_path.read_bytes()), json.loads(policy_path.read_bytes())
    metadata = next(item for item in registry["extensions"] if item["extension_id"] == "aeep-evaluator")
    metadata["source"]["artifact_sha256"] = plan.wheels[0].sha256
    policy["reviewed_dependency_manifests"].extend([
        manifest_digest(ExtensionManifest.model_validate(metadata)),
        *(item.manifest_sha256 for item in plan.preview.items),
    ])
    policy["allowed_data_rights"].append("fixture-only")
    for field in ("allowed_filesystem_scopes", "allowed_authentication", "allowed_financial_exposure"):
        policy[field] = list(dict.fromkeys([*policy[field], *getattr(plan.policy, field)]))
    for name, target, value in (("registry", registry_path, registry), ("policy", policy_path, policy)):
        target.write_text(json.dumps(value))
        data[name]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    data["configurations"]["document-data"]["runtimes"] = {
        "engine": {"installation": {"path": str(install_file.relative_to(tmp_path)),
                                   "sha256": hashlib.sha256(install_file.read_bytes()).hexdigest()},
                   "components": {"aeep-evaluator": "engine"}}
    }
    data["configurations"]["software-engineering"] = data["configurations"]["document-data"]
    path.write_text(json.dumps(data))
    monkeypatch.setattr(Router, "from_manifest", lambda *_: service.router)
    monkeypatch.setattr(service.router, "close", _no_close)
    try:
        review = prepare_stack(path, "document-data")
        result = prepare_canonical(path, "document-data", reviewed_digest=review["review_sha256"],
                                   destination=tmp_path / "prepared-runtime")
        exported = json.loads(Path(result["workflow_path"]).read_bytes())
        binding = exported["configurations"]["document-data"]["runtimes"]["engine"]
        assert binding["installation"]["path"] == str(install_file)
        assert binding["references"] == [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
        removal, _ = lifecycle_preview(Path(result["workflow_path"]), "document-data", ("engine",), operation="remove")
        assert removal["blockers"] and any("software-engineering" in ref for ref in removal["shared_references"]["engine"])
        assert not Path(plan.destination).exists()
    finally:
        asyncio.run(Router.close(service.router))
