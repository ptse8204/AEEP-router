"""Original three-way authority; no live workers or model calls."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from test_v08_incremental import environment
from test_v08_managed_workers import binding as worker_binding

from aeep.assessment.boundary import BoundaryConformance, BoundaryProbe, require_three_way_access
from aeep.assessment.comparison import validate_incremental_hosts
from aeep.assessment.models import (
    IncrementalExperiment,
    ThreeWayAccessDefinition,
    UtilityPolicy,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.errors import ConfigurationError
from aeep.models import ExecutorSpec, ReviewedHostSkill
from aeep.store import ReceiptStore

pytestmark = pytest.mark.assessment_contract


def value(**changes):
    args = dict(
        schema_version="assessment.experiment.v2",
        stage="aeep_value",
        exposure="optional",
        environment=environment(),
        utility=UtilityPolicy(
            benefit_dimensions=["wall_time_ms"], guardrail_dimensions=["wall_time_ms"]
        ),
        normal_host={"executor_id": "normal", "fingerprint": "1" * 64, "dependencies": {}},
        three_way_access_digest="2" * 64,
        qualification_report_digest="3" * 64,
        feasible_challengers=["normal"],
    )
    args.update(changes)
    return IncrementalExperiment(**args)


def test_historical_exact_json_and_three_role_version():
    old = IncrementalExperiment(
        stage="qualification",
        exposure="required",
        environment=environment(),
        utility=value().utility,
    )
    encoded = old.model_dump_json()
    assert encoded == Path(__file__).with_name("legacy-experiment-v1-f55.json").read_text()
    assert "normal_host" not in encoded and "three_way_access_digest" not in encoded
    assert IncrementalExperiment.model_validate_json(encoded).model_dump_json() == encoded
    assert [a.executor_id for a in value().challengers] == ["normal"]
    for change in (
        {"schema_version": "assessment.experiment.v1"},
        {"normal_host": None},
        {"three_way_access_digest": None},
        {"higher_compute": {"executor_id": "high", "fingerprint": "a" * 64, "dependencies": {}}},
        {"feasible_challengers": []},
        {"exposure": "required"},
    ):
        with pytest.raises(ValidationError):
            value(**change)
    with pytest.raises(ValidationError):
        IncrementalExperiment.model_validate(
            {**old.model_dump(), "normal_host": value().normal_host.model_dump()}
        )


def _three_way_host(role, *, mode="turn", worker_id=None, credential_volume=None, skills=()):
    worker = worker_binding(credential_volume=credential_volume or "aeep-auth-" + role).model_copy(
        update={"worker_id": worker_id or "worker-" + role}
    )
    invocation = {"mode": mode, "supporting_skills": [skill.model_dump(mode="json") for skill in skills]}
    if mode == "skill":
        invocation.update(skill_name="Candidate", skill_path="/opt/candidate/SKILL.md",
                          skill_sha256="e" * 64, exposure="optional")
    spec = ExecutorSpec(
        id=role,
        capability="assessment.workbook@1",
        kind="host_managed",
        resource_pool="three-way",
        description="Static three-way comparison fixture",
        config={
            "adapter_id": "codex-app-server:three-way",
            "argv": ["/opt/codex", "app-server"],
            "instructions": "Same frozen task instructions.",
            "timeout_seconds": 60,
            "managed_worker": worker.model_dump(mode="json"),
            "invocation": invocation,
        },
    )
    return spec


def _validate_three_way_hosts(*, normal_skills=(), normal_worker_id=None,
                              normal_volume=None, baseline_skills=None, candidate_skills=None):
    discovery_skill = ReviewedHostSkill(name="Spreadsheets", path="/opt/discovery/SKILL.md", sha256="a" * 64)
    baseline_skills = (discovery_skill,) if baseline_skills is None else baseline_skills
    candidate_skills = baseline_skills if candidate_skills is None else candidate_skills
    candidate = _three_way_host("candidate", mode="skill", skills=candidate_skills)
    baseline = _three_way_host("baseline", skills=baseline_skills)
    normal = _three_way_host("normal", skills=normal_skills, worker_id=normal_worker_id,
                             credential_volume=normal_volume)
    validate_incremental_hosts(candidate, baseline, {"normal": normal}, value())


def test_aeep_value_all_three_workers_are_pairwise_independent():
    _validate_three_way_hosts()
    with pytest.raises(ConfigurationError, match="independent"):
        _validate_three_way_hosts(normal_worker_id="worker-candidate")
    with pytest.raises(ConfigurationError, match="independent"):
        _validate_three_way_hosts(normal_volume="aeep-auth-candidate")


def test_aeep_value_normal_may_omit_discovery_support_only():
    _validate_three_way_hosts(normal_skills=())
    extra = ReviewedHostSkill(name="Unreviewed", path="/opt/unreviewed/SKILL.md", sha256="b" * 64)
    with pytest.raises(ConfigurationError, match="exact subset"):
        _validate_three_way_hosts(normal_skills=(extra,))
    drifted = ReviewedHostSkill(name="Spreadsheets", path="/opt/discovery/SKILL.md", sha256="c" * 64)
    with pytest.raises(ConfigurationError, match="exact subset"):
        _validate_three_way_hosts(normal_skills=(drifted,))


def test_historical_four_arm_value_still_requires_equal_supporting_skills():
    skill = ReviewedHostSkill(name="Spreadsheets", path="/opt/discovery/SKILL.md", sha256="a" * 64)
    candidate = _three_way_host("candidate", mode="skill", skills=(skill,))
    baseline = _three_way_host("baseline", skills=(skill,))
    high = _three_way_host("high", skills=(skill,))
    high.config["timeout_seconds"] = 120
    high.config["reasoning_efforts"] = ["high"]
    for spec in (candidate, baseline):
        spec.config["reasoning_efforts"] = ["low"]
    reusable = _three_way_host("reusable", skills=(skill,))
    reusable.config["reasoning_efforts"] = ["low"]
    experiment = IncrementalExperiment(
        stage="marginal_value",
        exposure="optional",
        environment=environment(),
        utility=value().utility,
        higher_compute={"executor_id": "high", "fingerprint": "4" * 64, "dependencies": {}},
        reusable_tool={"executor_id": "reusable", "fingerprint": "5" * 64, "dependencies": {}},
        reusable_artifact_digest="6" * 64,
        reusable_build_operation_ids=["build-op"],
        qualification_report_digest="7" * 64,
        feasible_challengers=["high", "reusable"],
    )
    dependencies = {"high": high, "reusable": reusable}
    validate_incremental_hosts(candidate, baseline, dependencies, experiment)
    reusable.config["invocation"]["supporting_skills"] = []
    with pytest.raises(ConfigurationError, match="reviewed background skills"):
        validate_incremental_hosts(candidate, baseline, dependencies, experiment)



@pytest.fixture
def access_fixture(tmp_path, monkeypatch):
    store = ReceiptStore(tmp_path / "fixture.db")
    repo = AssessmentRepository(store)
    experiment = value()
    access = ThreeWayAccessDefinition(
        normal_inventory={},
        discovery_inventory=experiment.environment.control_inventory,
        external_candidate_inventory=experiment.environment.control_inventory,
        worker_digests={r: "4" * 64 for r in ("normal", "baseline", "candidate")},
        configuration_digests={r: "5" * 64 for r in ("normal", "baseline", "candidate")},
    )
    plan = SimpleNamespace(
        comparison=SimpleNamespace(experiment=experiment),
        candidate_id="candidate",
        baseline_id="baseline",
        mapping_digest="6" * 64,
        definition_digests=[],
    )
    env = SimpleNamespace(conformance_digests={})
    boundaries = {}
    for role, available, inventory in [
        ("normal", False, {}),
        ("baseline", False, experiment.environment.control_inventory),
        ("candidate", True, experiment.environment.treatment_inventory),
    ]:
        probe = BoundaryProbe(
            probe_id=role,
            name="candidate_access",
            implementation_digest="a" * 64,
            worker_digest="4" * 64,
            execution_evidence_digest="b" * 64,
            observed={
                "definition_digest": content_digest(experiment.environment),
                "candidate_available": available,
            },
        )
        ref = repo.put("boundary_probe", role, probe)
        boundaries[role] = BoundaryConformance(
            schema_version="assessment.boundary-conformance.v2",
            conformance_id=role,
            source_digest="c" * 64,
            worker_digest="4" * 64,
            image_digest="sha256:" + "d" * 64,
            binary_digest="e" * 64,
            adapter="fixture",
            adapter_version="1",
            effective_policy_digest="f" * 64,
            reviewed_inventory_digest=content_digest(inventory),
            identity_digest="1" * 64,
            enforcement_definition_digest="2" * 64,
            advertised_tools=list(inventory),
            permitted_tools=list(inventory),
            used_tools=[],
            probe_digests=[ref],
            configuration_digest="5" * 64,
            effective_inventory=inventory,
        )

    def bind(access_record=access, records=boundaries, review=True):
        digest = repo.put("three_way_access", content_digest(access_record), access_record)
        if review:
            repo.review(digest)
        experiment.three_way_access_digest = digest
        plan.definition_digests = [digest]
        env.conformance_digests = {
            role: repo.put("boundary_conformance", content_digest(record), record)
            for role, record in records.items()
        }
        return digest

    bind()
    # This unit tests semantic bindings; actual execution-backed conformance remains
    # covered independently by test_v08_conformance and require_managed_boundaries.
    original_get = repo.get
    mapping = SimpleNamespace(subjects=[SimpleNamespace(id=r, managed_host_config=lambda: SimpleNamespace(
        invocation=SimpleNamespace(supporting_skills=()))) for r in boundaries])
    monkeypatch.setattr("aeep.assessment.models.ReviewedMapping.model_validate", lambda _v: mapping)
    monkeypatch.setattr(
        repo,
        "get",
        lambda kind, identity: {} if kind == "mapping" else original_get(kind, identity),
    )
    calls = []
    monkeypatch.setattr(
        "aeep.assessment.boundary.require_managed_boundaries",
        lambda _repo, _env, specs, ids: calls.append(([s.id for s in specs], ids)),
    )
    yield repo, plan, env, access, boundaries, bind, calls, mapping
    store.close()


def _bind_support_inventory(repo, plan, env, access, records, bind, mapping, *,
                            baseline_names=("Spreadsheets",), normal_names=(),
                            external_names=("Spreadsheets",)):
    skill_digests = {"Spreadsheets": "a" * 64, "Background": "d" * 64}
    skills = {
        name: ReviewedHostSkill(name=name, path=f"/opt/{name.lower()}/SKILL.md", sha256=digest)
        for name, digest in skill_digests.items()
    }
    normal_inventory = {"python": "b" * 64}
    discovery_inventory = {"skill:" + name: skill_digests[name] for name in baseline_names}
    external_inventory = {"skill:" + name: skill_digests[name] for name in external_names}
    control_inventory = {**normal_inventory, **discovery_inventory}
    candidate_inventory = plan.comparison.experiment.environment.candidate_inventory
    treatment_inventory = {**control_inventory, **candidate_inventory}
    experiment = plan.comparison.experiment
    experiment.environment = experiment.environment.model_copy(update={
        "control_inventory": control_inventory,
        "treatment_inventory": treatment_inventory,
    })
    access = ThreeWayAccessDefinition(
        normal_inventory=normal_inventory,
        discovery_inventory=discovery_inventory,
        external_candidate_inventory=external_inventory,
        worker_digests=access.worker_digests,
        configuration_digests=access.configuration_digests,
    )
    access_records = {
        "normal": normal_names,
        "baseline": baseline_names,
        "candidate": baseline_names,
    }
    mapping.subjects = [
        SimpleNamespace(
            id=role,
            managed_host_config=lambda names=names: SimpleNamespace(
                invocation=SimpleNamespace(supporting_skills=tuple(skills[name] for name in names))
            ),
        )
        for role, names in access_records.items()
    ]
    inventories = {
        "normal": normal_inventory,
        "baseline": control_inventory,
        "candidate": treatment_inventory,
    }
    updated_records = {}
    for role, inventory in inventories.items():
        old = records[role]
        probe = BoundaryProbe(
            probe_id="support-" + role,
            name="candidate_access",
            implementation_digest="a" * 64,
            worker_digest=old.worker_digest,
            execution_evidence_digest="b" * 64,
            observed={
                "definition_digest": content_digest(experiment.environment),
                "candidate_available": role == "candidate",
            },
        )
        probe_ref = repo.put("boundary_probe", "support-" + role, probe)
        updated_records[role] = old.model_copy(update={
            "reviewed_inventory_digest": content_digest(inventory),
            "advertised_tools": list(inventory),
            "permitted_tools": list(inventory),
            "effective_inventory": inventory,
            "probe_digests": [probe_ref],
        })
    bind(access, records=updated_records)
    return access


def test_three_actual_role_bindings_reach_existing_boundary_gate(access_fixture):
    repo, plan, env, _access, _records, _bind, calls, _mapping = access_fixture
    require_three_way_access(repo, env, plan)
    assert calls[0][0] == ["normal", "baseline", "candidate"]
    assert set(calls[0][1]) == set(calls[0][0])


def test_three_way_boundary_joins_only_omitted_external_discovery_skill(access_fixture):
    repo, plan, env, access, records, bind, calls, mapping = access_fixture
    _bind_support_inventory(repo, plan, env, access, records, bind, mapping)
    require_three_way_access(repo, env, plan)
    assert calls


def test_three_way_boundary_rejects_omitted_non_candidate_support(access_fixture):
    repo, plan, env, access, records, bind, calls, mapping = access_fixture
    _bind_support_inventory(
        repo, plan, env, access, records, bind, mapping,
        baseline_names=("Spreadsheets", "Background"),
        external_names=("Spreadsheets",),
    )
    with pytest.raises(ConfigurationError, match="omitted supports"):
        require_three_way_access(repo, env, plan)
    assert not calls


@pytest.mark.parametrize("fault", ["wrong_skill_hash", "external_already_normal"])
def test_three_way_external_support_must_match_discovery_only(access_fixture, fault):
    repo, plan, env, access, records, bind, calls, mapping = access_fixture
    access = _bind_support_inventory(repo, plan, env, access, records, bind, mapping)
    external = dict(access.external_candidate_inventory)
    if fault == "wrong_skill_hash":
        external["skill:Spreadsheets"] = "9" * 64
    else:
        # Matching a control inventory entry is insufficient when normal already has it.
        external["python"] = access.normal_inventory["python"]
    changed = access.model_copy(update={"external_candidate_inventory": external})
    digest = repo.put("three_way_access", content_digest(changed), changed)
    repo.review(digest)
    plan.comparison.experiment.three_way_access_digest = digest
    plan.definition_digests = [digest]
    with pytest.raises(ConfigurationError, match="discovery or external candidate"):
        require_three_way_access(repo, env, plan)
    assert not calls


@pytest.mark.parametrize(
    "fault",
    [
        "fake_equal",
        "unreviewed",
        "revoked",
        "worker",
        "config",
        "inventory",
        "missing_role",
        "normal_absence",
        "external_access",
    ],
)
def test_false_or_unbound_three_way_access_fails_closed(access_fixture, fault):
    repo, plan, env, access, records, bind, calls, _mapping = access_fixture
    if fault == "fake_equal":
        plan.comparison.experiment.three_way_access_digest = "9" * 64
        plan.definition_digests = ["9" * 64]
    elif fault == "unreviewed":
        access = access.model_copy(update={"configuration_digests": {r: "6" * 64 for r in records}})
        bind(access, review=False)
    elif fault == "revoked":
        repo.review(plan.comparison.experiment.three_way_access_digest, revoke=True)
    elif fault in {"worker", "config", "inventory"}:
        field = {
            "worker": "worker_digest",
            "config": "configuration_digest",
            "inventory": "effective_inventory",
        }[fault]
        records = {
            **records,
            "normal": records["normal"].model_copy(
                update={field: {"fake": "8" * 64} if fault == "inventory" else "8" * 64}
            ),
        }
        bind(records=records)
    elif fault == "missing_role":
        env.conformance_digests.pop("normal")
    elif fault == "normal_absence":
        record = records["normal"]
        bad = BoundaryProbe(
            probe_id="bad",
            name="candidate_access",
            implementation_digest="a" * 64,
            worker_digest="4" * 64,
            execution_evidence_digest="b" * 64,
            observed={"definition_digest": "9" * 64, "candidate_available": False},
        )
        ref = repo.put("boundary_probe", "bad", bad)
        bind(records={**records, "normal": record.model_copy(update={"probe_digests": [ref]})})
    elif fault == "external_access":
        bind(access.model_copy(update={"external_candidate_inventory": {"python": "8" * 64}}))
    with pytest.raises(ConfigurationError):
        require_three_way_access(repo, env, plan)
    assert not calls


@pytest.mark.parametrize(
    "fault", [None, "candidate", "revoked", "grader_recipe", "grader_job", "backend", "exposure"]
)
def test_qualification_transfer_uses_canonical_records_and_exact_backend(
    tmp_path, monkeypatch, fault
):
    from aeep.assessment.models import GraderValidationEvidence
    from aeep.assessment.service import AssessmentService
    from aeep.models import StrictModel

    class Qualified(StrictModel):
        candidate_id: str = "candidate"
        plan_id: str = "qualified"
        mapping_digest: str = "qmap"

    qualified = Qualified()
    plan = SimpleNamespace(candidate_id="candidate", recipe_digest="a" * 64, mapping_digest="vmap")
    validation = GraderValidationEvidence(
        recipe_digest=plan.recipe_digest,
        independent_fixture_digests=["b" * 64],
        generator_fixture_digests=[],
        rejected_fault_count=1,
    )
    store = ReceiptStore(tmp_path / "qualification.db")
    repo = AssessmentRepository(store)
    digest = repo.put("grader_validation", "validation", validation)
    report = SimpleNamespace(
        plan_digest=content_digest(qualified),
        grader_validation_digest=digest,
        report_id="qualified-report",
    )
    store._connection.execute(
        "INSERT INTO assessment_jobs(id,plan_id,state,report_id) VALUES(?,?,?,?)",
        ("job", qualified.plan_id, "complete", report.report_id),
    )
    store._connection.execute(
        "UPDATE assessment_records SET id=? WHERE kind='grader_validation' AND digest=?",
        ("job:grader-validation", digest),
    )
    configs = {
        "qmap": {"invocation": {"exposure": "required"}, "model": "same"},
        "vmap": {"invocation": {"exposure": "optional"}, "model": "same"},
    }
    original_get = repo.get

    def get(kind, key):
        if kind == "mapping":
            return key
        return original_get(kind, key)

    monkeypatch.setattr(repo, "get", get)
    monkeypatch.setattr(
        "aeep.assessment.service.ReviewedMapping.model_validate",
        lambda key: SimpleNamespace(
            candidate=SimpleNamespace(
                managed_host_config=lambda: SimpleNamespace(
                    model_dump=lambda **kw: {
                        **configs[key],
                        "invocation": dict(configs[key]["invocation"]),
                    }
                )
            )
        ),
    )
    calls = []

    def authorize(value):
        calls.append("authorize")
        if fault == "revoked":
            raise ConfigurationError("qualification review revoked")

    monkeypatch.setattr(repo, "authorize", authorize)
    service = object.__new__(AssessmentService)
    service.repository = repo
    service.router = SimpleNamespace(store=store)
    service._verify_dependencies = lambda value: calls.append("dependencies")
    if fault == "candidate":
        plan.candidate_id = "other"
    if fault == "grader_recipe":
        plan.recipe_digest = "c" * 64
    if fault == "grader_job":
        store._connection.execute("UPDATE assessment_jobs SET state='running'")
    if fault == "backend":
        configs["vmap"]["model"] = "other"
    if fault == "exposure":
        configs["qmap"]["invocation"]["exposure"] = "optional"
    if fault:
        with pytest.raises(ConfigurationError):
            service._verify_three_way_qualification(plan, qualified, report)
    else:
        service._verify_three_way_qualification(plan, qualified, report)
        assert calls == ["authorize", "dependencies"]
    store.close()


@pytest.mark.parametrize("fault", ["grant", "subject", "recipe", "source", "holdout"])
def test_three_way_keeps_shared_qualification_lineage_and_holdout_gate(monkeypatch, fault):
    import aeep.assessment.service as module
    from aeep.assessment.service import AssessmentService

    current = value()
    prior = current.model_copy(update={"stage": "qualification", "exposure": "required"})
    case = SimpleNamespace(
        split=SimpleNamespace(value="holdout"), action=SimpleNamespace(input={"seed": 1})
    )
    from aeep.benchmarking import BenchmarkSplit

    case.split = BenchmarkSplit.HOLDOUT
    qualified = SimpleNamespace(
        plan_id="qualified",
        candidate_id="candidate",
        authorization_id="grant",
        subject_digest="subject",
        recipe_digest="recipe",
        comparison=SimpleNamespace(experiment=prior),
        suite=SimpleNamespace(routes=["candidate"], cases=[case]),
    )
    plan = SimpleNamespace(
        candidate_id="candidate",
        authorization_id="grant",
        subject_digest="subject",
        recipe_digest="recipe",
        environment_digest="environment",
        suite=SimpleNamespace(cases=[case]),
    )
    report = SimpleNamespace(
        plan_digest="qualified-digest",
        campaign_digest="campaign-digest",
        grader_validation_digest="grader",
    )
    campaign = SimpleNamespace()
    binding = SimpleNamespace(source_digest="current-source")
    records = {
        "environment": SimpleNamespace(),
        "report": report,
        "plan": qualified,
        "campaign": campaign,
        "run_binding": binding,
        "recipe": SimpleNamespace(),
    }
    for name in (
        "AssessmentEnvironment",
        "AssessmentReport",
        "AssessmentPlan",
        "BenchmarkCampaignReport",
        "AssessmentRunBinding",
        "RecipeDefinition",
    ):
        monkeypatch.setattr(getattr(module, name), "model_validate", lambda record: record)
    monkeypatch.setattr("aeep.assessment.boundary.require_differential", lambda *args: None)
    monkeypatch.setattr(
        "aeep.assessment.verification.verification_source_digest", lambda *args: "current-source"
    )
    monkeypatch.setattr(
        module, "fit_report", lambda *args: SimpleNamespace(qualification_passed=True)
    )

    def digest(record):
        if record is report:
            return current.qualification_report_digest
        if record is qualified:
            return report.plan_digest
        if record is campaign:
            return report.campaign_digest
        return "same-input"

    monkeypatch.setattr(module, "content_digest", digest)
    service = object.__new__(AssessmentService)
    service.repository = SimpleNamespace(
        get=lambda kind, key: records[kind], authorize=lambda _: None
    )
    if fault in ("grant", "subject", "recipe"):
        setattr(
            qualified,
            {"grant": "authorization_id", "subject": "subject_digest", "recipe": "recipe_digest"}[
                fault
            ],
            "unrelated",
        )
    if fault == "source":
        binding.source_digest = "old-source"
    with pytest.raises(
        ConfigurationError,
        match="disjoint holdout" if fault == "holdout" else "current independent qualification",
    ):
        service._verify_incremental_evidence(plan, current)
