"""First-party workflow cost boundaries; no upstream SDK, model or container."""

import hashlib
import json
import time
from datetime import timedelta
from pathlib import Path

import pytest
from test_toolkit_workflow_v2 import definition as workflow_definition

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.reporting import resource_measurements
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.errors import ConfigurationError
from aeep.models import Manifest, StrictModel, utc_now
from aeep.router import Router
from aeep_toolkit.cli import main
from aeep_toolkit.workflow_accounting import (
    WorkflowAccountingDefinition,
    account_workflow,
    active_accounting,
    exclude_canonical_execution,
)


class OwnedScope(StrictModel):
    role: str


def accounting(tmp_path, workflow=None, configuration="document-data"):
    tmp_path = tmp_path.resolve()
    workflow = workflow or tmp_path / "selected-workflow.json"
    if not workflow.exists():
        workflow.write_text('{"purpose":"owned accounting boundary fixture"}')
    manifest_path = tmp_path / "accounting-manifest.json"
    manifest = Manifest(database=str(tmp_path / "canonical.sqlite3"), executors=[])
    manifest_path.write_text(manifest.model_dump_json())
    router = Router.from_manifest(manifest_path)
    repo = AssessmentRepository(router.store)
    refs = [repo.put("toolkit_engineering_scope", role, OwnedScope(role=role))
            for role in ("subject", "recipe", "mapping", "environment")]
    for ref in refs:
        repo.review(ref)
    request = RecipeMaterializationRequest(
        plan_id="owned-workflow-costs", subject_digest=refs[0], recipe_digest=refs[1],
        mapping_digest=refs[2], environment_digest=refs[3], definition_digests=refs,
        authorization_id="owned-accounting", seed=0,
    )
    repo.grant(AssessmentAuthorization(
        authorization_id=request.authorization_id, subject_digests=[refs[0]],
        recipe_digests=[refs[1]], environment_digests=[refs[3]],
        limits=AssessmentLimits(max_operations=20, max_model_turns=0, max_elapsed_seconds=600),
        allowed_destinations=["local"], expires_at=utc_now() + timedelta(minutes=10),
    ))
    scope = WorkflowAccountingDefinition(
        workflow_sha256=hashlib.sha256(workflow.read_bytes()).hexdigest(),
        configurations=(configuration,), operations=("plan", "prepare", "run", "report"),
        source_digest=verification_source_digest(Path(__file__).resolve().parents[1]),
        manifest_path=str(manifest_path), manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        request=request, maximum_overhead_seconds=30,
    )
    ref = repo.put("toolkit_workflow_accounting", content_digest(scope), scope)
    repo.review(ref)
    scope_path = tmp_path / "accounting.json"
    scope_path.write_text(scope.model_dump_json())
    return router, repo, scope, scope_path, workflow


@pytest.fixture
def configured(tmp_path):
    result = accounting(tmp_path)
    yield result
    result[0].store.close()


def invoke(configured, key="one", stage="plan", **kwargs):
    _router, _repo, _scope, scope_path, workflow = configured
    return account_workflow(scope_path, workflow_file=workflow,
                            configuration="document-data", stage=stage,
                            operation_key=key, **kwargs)


def test_no_scope_stays_inert_and_does_not_initialize_router(tmp_path, monkeypatch):
    monkeypatch.setattr(Router, "from_manifest", lambda *_: pytest.fail("unmetered preview opened Router"))
    with account_workflow(None, workflow_file=tmp_path / "absent", configuration="doc",
                          stage="plan", operation_key=None) as meter:
        assert meter is None and active_accounting() is None
        with exclude_canonical_execution():
            pass


def test_canonical_ledger_excludes_nested_execution_but_keeps_raw_interval(configured):
    _router, repo, scope, *_ = configured
    with invoke(configured) as meter:
        assert meter and active_accounting()["operation_id"] == meter.operation_id
        with exclude_canonical_execution():
            time.sleep(0.02)
        time.sleep(0.005)
    ledger = repo.operation_ledger(scope.request.plan_id)
    assert len(ledger.operations) == 1
    operation = ledger.operations[0]
    assert operation.stage == "workflow_plan_overhead" and operation.elapsed_seconds > 0
    receipt = repo.get("toolkit_workflow_receipt", meter.operation_id)
    meta = receipt["metadata"]
    nested = sum(item["wall_seconds"] for item in meta["excluded_nested_intervals"])
    assert nested >= 0.02
    assert receipt["actual_resources"]["latency_ms"] == pytest.approx(
        (meta["whole_wrapper_wall_seconds"] - nested) * 1000
    )
    assert operation.elapsed_seconds * 1000 == receipt["actual_resources"]["latency_ms"]
    assert meta["observed_resource_dimensions"] == ["latency_ms", "cpu_ms"]
    assert operation.accounting is None
    # Required legacy vector zeros are not observations of unmeasured dimensions.
    from aeep.models import ResourceAccounting
    measured = resource_measurements(ResourceAccounting(), operation.resources)
    assert measured["local.memory_mb_seconds"] is None
    assert not any(key.startswith("model.") or key.startswith("cash.") for key in measured)
    assert active_accounting() is None
    with pytest.raises(ConfigurationError, match="already reserved"), invoke(configured):
        pytest.fail("terminal operation replayed")
    assert len(repo.operation_ledger(scope.request.plan_id).operations) == 1


@pytest.mark.parametrize("exception", [RuntimeError, KeyboardInterrupt, SystemExit])
def test_failure_and_interruptions_keep_terminal_costs_without_payloads(configured, exception):
    _router, repo, scope, *_ = configured
    with pytest.raises(exception), invoke(configured) as meter:
        raise exception("private task content must not enter receipt")
    item = repo.operation_ledger(scope.request.plan_id).operations[0]
    assert item.elapsed_seconds is not None
    receipt = repo.get("toolkit_workflow_receipt", meter.operation_id)
    assert receipt["execution_success"] is False and receipt["error_type"] == exception.__name__
    assert "private task content" not in json.dumps(receipt)
    assert active_accounting() is None


@pytest.mark.parametrize("change", ["workflow", "manifest", "source", "review", "grant", "scope", "selection", "operation", "manifest-argument"])
def test_authority_and_input_drift_fail_before_body_or_reservation(configured, change):
    router, repo, scope, scope_path, workflow = configured
    configuration, key, manifest = "document-data", "new", None
    if change == "workflow":
        workflow.write_text(workflow.read_text() + " ")
    elif change == "manifest":
        Path(scope.manifest_path).write_text(Path(scope.manifest_path).read_text() + " ")
    elif change == "source":
        scope.source_digest = "a" * 64
        scope_path.write_text(scope.model_dump_json())
    elif change == "review":
        repo.review(content_digest(scope), revoke=True)
    elif change == "grant":
        with router.store._immediate_transaction() as connection:
            connection.execute("UPDATE assessment_grants SET revoked=1")
    elif change == "scope":
        scope.maximum_overhead_seconds = 31
        scope_path.write_text(scope.model_dump_json())
    elif change == "selection":
        configuration = "other"
    elif change == "operation":
        key = "../unsafe"
    else:
        manifest = workflow
    with pytest.raises((ConfigurationError, ValueError)), account_workflow(
        scope_path, workflow_file=workflow, configuration=configuration,
        stage="plan", operation_key=key, manifest=manifest
    ):
        pytest.fail("unreviewed operation entered body")
    assert not repo.operation_ledger(scope.request.plan_id).operations


def test_unreconciled_reservation_stops_new_identity_without_reset(configured):
    _router, repo, scope, *_ = configured
    repo.reserve(scope.request, "interrupted", AssessmentLimits(max_operations=1, max_elapsed_seconds=30),
                 stage="workflow_prepare_overhead")
    with pytest.raises(ConfigurationError, match="unresolved accounting"), invoke(configured, key="different-name"):
        pytest.fail("unresolved allowance was bypassed")
    ledger = repo.operation_ledger(scope.request.plan_id)
    assert len(ledger.operations) == 1 and ledger.operations[0].elapsed_seconds is None


def test_drift_during_body_is_terminal_failure_and_retains_charge(configured):
    _router, repo, scope, _scope_path, workflow = configured
    with pytest.raises(ConfigurationError, match="source changed"), invoke(configured) as meter:
        workflow.write_text(workflow.read_text() + " ")
    assert repo.operation_ledger(scope.request.plan_id).operations[0].elapsed_seconds is not None
    assert repo.get("toolkit_workflow_receipt", meter.operation_id)["error_type"] == "WorkflowSourceDrift"


def test_overlap_and_recursive_wrapper_are_rejected(configured):
    with invoke(configured) as meter:
        with meter.exclude("canonical"), pytest.raises(ConfigurationError, match="overlapping"), meter.exclude("another"):
            pytest.fail("overlapping intervals admitted")
        with pytest.raises(ConfigurationError, match="one scope"), invoke(configured, key="recursive"):
            pytest.fail("recursive wrapper admitted")


def test_ordinary_cli_records_inspection_and_reports_unmetered_coverage(tmp_path, capsys):
    workflow, *_ = workflow_definition(tmp_path)
    configured = accounting(tmp_path, workflow)
    router, repo, scope, scope_path, _ = configured
    try:
        args = ["workflow", "plan", "--workflow", str(workflow), "--configuration", "document-data"]
        main(args)
        assert json.loads(capsys.readouterr().out)["workflow_accounting"]["coverage"] == "NOT_RECORDED"
        assert not repo.operation_ledger(scope.request.plan_id).operations
        main([*args, "--accounting", str(scope_path), "--operation-id", "inspection-one"])
        value = json.loads(capsys.readouterr().out)
        assert value["workflow_accounting"]["definition_ref"] == content_digest(scope)
        assert value["candidate"]["executed"] is False
        assert len(repo.operation_ledger(scope.request.plan_id).operations) == 1
        with pytest.raises(SystemExit):
            main([*args, "--accounting", str(scope_path), "--operation-id", "inspection-one"])
        assert len(repo.operation_ledger(scope.request.plan_id).operations) == 1
    finally:
        router.store.close()


def test_concurrent_wrappers_cannot_bypass_uncertain_cost_guard(configured):
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
    from threading import Barrier, Event

    _router, repo, scope, *_ = configured
    barrier, release = Barrier(2), Event()

    def attempt(key):
        barrier.wait(timeout=5)
        try:
            with invoke(configured, key=key):
                assert release.wait(timeout=5)
            return "completed"
        except ConfigurationError as error:
            assert "unresolved accounting" in str(error)
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(attempt, key) for key in ("parallel-one", "parallel-two")]
        try:
            completed, _ = wait(tasks, timeout=4, return_when=FIRST_COMPLETED)
            assert len(completed) == 1 and next(iter(completed)).result() == "blocked"
        finally:
            release.set()
        assert sorted(task.result() for task in tasks) == ["blocked", "completed"]
    assert len(repo.operation_ledger(scope.request.plan_id).operations) == 1


def test_review_revocation_between_preview_and_atomic_debit_is_respected(configured, monkeypatch):
    _router, repo, scope, *_ = configured
    original = AssessmentRepository.reserve

    def revoke_then_reserve(self, *args, **kwargs):
        self.review(content_digest(scope), revoke=True)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(AssessmentRepository, "reserve", revoke_then_reserve)
    with pytest.raises(ConfigurationError, match="operator review"), invoke(configured):
        pytest.fail("revoked wrapper entered its body")
    assert not repo.operation_ledger(scope.request.plan_id).operations


@pytest.mark.parametrize("change", [None, "authorization_id", "subject_digest", "recipe_digest", "mapping_digest", "environment_digest", "manifest"])
def test_plan_link_cannot_charge_an_unrelated_grant_or_definition(configured, tmp_path, change):
    from test_v08_assessment import setup_assessment

    from aeep.assessment.models import AssessmentPlan
    from aeep_toolkit.workflow_accounting import bind_workflow_plan

    _router, repo, scope, *_ = configured
    other = tmp_path / "owned-plan-fixture"
    other.mkdir()
    original_router, _service, original, _grant = setup_assessment(other)
    try:
        values = original.model_dump(mode="json")
        for name in ("authorization_id", "subject_digest", "recipe_digest", "mapping_digest", "environment_digest"):
            values[name] = getattr(scope.request, name)
        if change and change != "manifest":
            values[change] = "unrelated" if change == "authorization_id" else "f" * 64
        plan = AssessmentPlan.model_validate(values)
        manifest = tmp_path / "another.json" if change == "manifest" else Path(scope.manifest_path)
        if change:
            with pytest.raises(ConfigurationError, match="different authority"), invoke(configured):
                bind_workflow_plan(plan, manifest)
        else:
            with invoke(configured) as meter:
                bind_workflow_plan(plan, manifest)
                bind_workflow_plan(plan, manifest)  # Idempotent link; never another reservation.
                assert active_accounting()["assessment_plan_ids"] == [plan.plan_id]
            record = repo.get("toolkit_workflow_plan_link", meter.operation_id)
            assert record["assessment_plan_digest"] == content_digest(plan)
        assert len(repo.operation_ledger(scope.request.plan_id).operations) == 1
    finally:
        original_router.store.close()


def test_store_scope_command_is_inert_and_does_not_review_or_reset_allowances(configured, capsys):
    _router, repo, scope, scope_path, _workflow = configured
    repo.review(content_digest(scope), revoke=True)
    main(["workflow", "define-accounting", "--file", str(scope_path),
          "--manifest", scope.manifest_path])
    result = json.loads(capsys.readouterr().out)
    assert result["accounting_ref"] == content_digest(scope)
    assert result["reviewed"] is False and result["execution_authorized"] is False
    assert not repo.operation_ledger(scope.request.plan_id).operations
    with pytest.raises(ConfigurationError, match="operator review"), invoke(configured):
        pytest.fail("inert definition storage reapproved a scope")
