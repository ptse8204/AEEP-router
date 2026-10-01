"""Original three-way authority; no live workers or model calls."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from test_v08_incremental import environment

from aeep.assessment.boundary import BoundaryConformance, BoundaryProbe, require_three_way_access
from aeep.assessment.models import (
    IncrementalExperiment,
    ThreeWayAccessDefinition,
    UtilityPolicy,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.errors import ConfigurationError
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
    mapping = SimpleNamespace(subjects=[SimpleNamespace(id=r) for r in boundaries])
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
    yield repo, plan, env, access, boundaries, bind, calls
    store.close()


def test_three_actual_role_bindings_reach_existing_boundary_gate(access_fixture):
    repo, plan, env, _access, _records, _bind, calls = access_fixture
    require_three_way_access(repo, env, plan)
    assert calls[0][0] == ["normal", "baseline", "candidate"]
    assert set(calls[0][1]) == set(calls[0][0])


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
    repo, plan, env, access, records, bind, calls = access_fixture
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
