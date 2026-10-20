"""Synthetic canonical-record tests. No live host, conformance or grant is inferred."""

import asyncio
import json
import sqlite3
import sys

import pytest
from test_v08_assessment import setup_assessment
from test_v08_comparisons import trial as make_trial
from test_v08_incremental import environment

from aeep.assessment.comparison import arm
from aeep.assessment.models import (
    AssessmentComparison,
    AssessmentOperationLedger,
    AssessmentPlan,
    AssessmentRunBinding,
    AssessmentSubject,
    IncrementalExperiment,
    ReviewedMapping,
    UtilityPolicy,
    content_digest,
)
from aeep.assessment.onboarding import host_spec
from aeep.assessment.recipes import shipped_recipe
from aeep.assessment.reporting import fit_report
from aeep.benchmarking import BenchmarkCampaignReport, BenchmarkRoute
from aeep.errors import ConfigurationError
from aeep.models import ExecutionReceipt, RouteEstimate
from aeep_toolkit import managed as adapter_module
from aeep_toolkit.models import SourcePin


def prepared(tmp_path, monkeypatch):
    router, service, original, grant = setup_assessment(tmp_path)
    source = SourcePin(
        repository="https://example.test/fixture",
        revision="d" * 40,
        artifact_sha256=content_digest({"SKILL.md": "c" * 64}),
        license_expression="MIT",
        data_rights="Synthetic unit fixture only",
    )
    subject = AssessmentSubject(
        kind="skill", location=str(tmp_path / "SKILL.md"), dependency_digests={"SKILL.md": "c" * 64}
    )
    subject_ref = service.repository.put("subject", subject.subject_id, subject)
    baseline = host_spec("csv", __import__("pathlib").Path(sys.executable), tmp_path)
    baseline.id = "baseline"
    baseline.config["reasoning_efforts"] = ["low"]
    candidate = baseline.model_copy(deep=True)
    candidate.id = "candidate"
    candidate.config["invocation"] = {
        "mode": "skill",
        "skill_name": "fixture",
        "skill_path": str(tmp_path / "SKILL.md"),
        "skill_sha256": "c" * 64,
        "exposure": "optional",
    }
    high = baseline.model_copy(update={"id": "high"}, deep=True)
    reusable = baseline.model_copy(update={"id": "reusable"}, deep=True)
    mapping = ReviewedMapping(candidate=candidate, baseline=baseline, dependencies=[high, reusable])
    mapping_ref = service.repository.put("mapping", "fixture-mapping", mapping)
    experiment = IncrementalExperiment(
        stage="marginal_value",
        exposure="optional",
        environment=environment(),
        utility=UtilityPolicy(
            benefit_dimensions=["wall_time_ms"], guardrail_dimensions=["wall_time_ms"]
        ),
        higher_compute=arm(high, []),
        reusable_tool=arm(reusable, []),
        reusable_artifact_digest="d" * 64,
        reusable_build_operation_ids=["build"],
        qualification_report_digest="e" * 64,
        feasible_challengers=["high", "reusable"],
    )
    comparison = AssessmentComparison(
        schema_version="assessment.comparison.v2",
        structure="controlled_agent",
        candidate=arm(candidate, []),
        baseline=arm(baseline, []),
        experiment=experiment,
    )
    suite = original.suite.model_copy(deep=True)
    suite.routes = [
        BenchmarkRoute(route_id=spec.id, executor_id=spec.id) for spec in mapping.subjects
    ]
    value = original.model_dump()
    value.update(
        schema_version="assessment.plan.v4",
        plan_id="managed-fixture",
        subject_digest=subject_ref,
        mapping_digest=mapping_ref,
        comparison=comparison,
        suite=suite,
        feature_combinations=[],
        definition_digests=[*original.definition_digests, content_digest(comparison)],
        route_fingerprints={spec.id: arm(spec, []).fingerprint for spec in mapping.subjects},
    )
    plan = AssessmentPlan.model_validate(value)
    service.repository.put("plan", plan.plan_id, plan)
    # Stub only the source identity and conformance checker in this unit fixture.
    monkeypatch.setattr(adapter_module, "verification_source_digest", lambda root: "a" * 64)
    adapter = adapter_module.AEEPAssessmentAdapter(service, plan.plan_id, source)
    path = service.directory / plan.plan_id / "campaign.sqlite3"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE trial_receipts(receipt_id TEXT PRIMARY KEY, trial_id TEXT, payload_json TEXT)"
        )
        connection.execute('CREATE TABLE trial_stores(trial_id TEXT PRIMARY KEY, database_path TEXT)')
    service.repository.put(
        "run_binding",
        plan.plan_id,
        AssessmentRunBinding(plan_id=plan.plan_id, source_digest="a" * 64, campaign_path=str(path)),
    )
    return router, service, adapter, path, grant


def record(service, adapter, path, *, missing_prompt=False, include_journals=False):
    trials = []
    for route in ("candidate", "baseline", "high"):
        trial = make_trial(adapter.plan.suite.cases[0].case_id, route)
        trial.route_fingerprint = adapter.plan.route_fingerprints[route]
        trial.capability_discovery = {
            "exposed": route == "candidate",
            "retrieved": None,
            "invoked": None,
        }
        metadata = {
            "protocol_version": "synthetic-protocol-1",
            "actual_model": "fixture-model",
            "worker_digest": ("b" if route == "baseline" else "c") * 64,
            "host_runtime_digest": "d" * 64,
            "boundary_digest": "e" * 64,
            "task_instruction_sha256": "f" * 64,
            "model_turn_count": 1,
            "codex_token_fields": '["inputTokens", "outputTokens"]',
            "capability_discovery": trial.capability_discovery,
        }
        if missing_prompt and route == "candidate":
            del metadata["task_instruction_sha256"]
        receipt = ExecutionReceipt(
            decision_id="decision-" + route,
            action_id="action-" + route,
            capability=adapter.recipe.capability,
            executor_id=route,
            executor_kind="host_managed",
            status="success",
            estimated=RouteEstimate(),
            actual_resources={"input_tokens": 7, "output_tokens": 3},
            metadata=metadata,
        )
        journal = None
        if include_journals:
            from aeep.execution import EventJournal, ExecutionEvidence
            from aeep.hosts.codex_accounting import TOKEN_FIELDS, turn_accounting
            wire = dict.fromkeys(TOKEN_FIELDS, 0) | {"inputTokens":7, "outputTokens":3}
            receipt.actual_resources, receipt.accounting = turn_accounting(wire, model="fixture-model", resource_pool="fixture")
            receipt.metadata["codex_token_fields"] = json.dumps(sorted(wire))
            receipt.metadata["attempt_id"] = route
            stream = EventJournal(route)
            stream.append("execution.started", "start")
            stream.append("usage.reported", "turn-usage", accounting=receipt.accounting, accounting_mode="cumulative")
            stream.append("execution.completed", "terminal")
            journal = ExecutionEvidence(attempt_id=route, adapter="fixture", events=stream.items,
                journal_id=stream.journal_id, complete=True, identity_digest="d"*64, boundary_digest="e"*64)
            receipt.metadata["execution_evidence_digest"] = content_digest(journal)
        trial.receipt_ids = [receipt.receipt_id]
        from aeep.router import Router
        Router._bind_receipt_evidence(next(spec for spec in adapter.mapping.subjects if spec.id == route), receipt)
        trial.actual_resources = receipt.actual_resources.model_copy(deep=True)
        trial.status = receipt.status
        trial.host_models = {route: metadata["actual_model"]}
        trial.host_runtime_digests = {route: metadata["host_runtime_digest"]}
        original_path = path.parent / 'attempts' / (route + '.sqlite3')
        original_path.parent.mkdir(exist_ok=True)
        with sqlite3.connect(original_path) as original:
            original.execute('CREATE TABLE receipts(receipt_id TEXT PRIMARY KEY, payload_json TEXT)')
            original.execute('INSERT INTO receipts VALUES (?,?)', (receipt.receipt_id, receipt.model_dump_json()))
            if journal:
                original.execute('CREATE TABLE assessment_records(kind TEXT, digest TEXT, payload_json TEXT)')
                original.execute('INSERT INTO assessment_records VALUES (?,?,?)',
                    ('execution_evidence', content_digest(journal), journal.model_dump_json()))
        with sqlite3.connect(path) as connection:
            connection.execute('INSERT INTO trial_stores VALUES (?,?)', (trial.trial_id, str(original_path)))
            connection.execute(
                "INSERT INTO trial_receipts VALUES (?,?,?)",
                (receipt.receipt_id, trial.trial_id, receipt.model_dump_json()),
            )
        trials.append(trial)
    campaign = BenchmarkCampaignReport(
        run_id="fixture-campaign",
        suite_id=adapter.plan.suite.suite_id,
        domain=adapter.plan.suite.domain,
        trials=trials,
        deterministic_tools_available=True,
        pricing_snapshot_ids=[],
        frozen_holdout_decisions={},
        summaries=[],
        baseline_deltas=[],
        oracles=[],
        subscription_conservation=[],
    )
    ledger = AssessmentOperationLedger(plan_id=adapter.plan.plan_id, operations=[])
    report = fit_report(adapter.plan, shipped_recipe("csv"), campaign, ledger=ledger)
    service.repository.put("campaign", campaign.run_id, campaign)
    service.repository.put("operation_ledger", content_digest(ledger), ledger)
    service.repository.put("report", report.report_id, report)
    return report


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_normalization_exports_bound_capture_and_rejects_changed_journals(tmp_path, monkeypatch, changed):
    router, service, adapter, path, _grant = prepared(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr(adapter_module, "require_conformance", lambda *args, **kwargs: None)
        report = record(service, adapter, path, include_journals=True)
        if changed:
            with sqlite3.connect(path.parent / 'attempts/candidate.sqlite3') as original:
                payload = json.loads(original.execute('SELECT payload_json FROM assessment_records').fetchone()[0])
                payload['attempt_id'] = 'changed'
                original.execute('UPDATE assessment_records SET payload_json=?', (json.dumps(payload),))
        bundle = adapter.normalize(report.report_id)
        count = 1 if changed else 2
        assert len(bundle.runs) == count, adapter.details['normalization_gaps']
        assert adapter.details['telemetry_capture_summary']['verified'] == count
        assert len(adapter.details['execution_journals']) == count
        assert len(adapter.details['normalization_gaps']) == int(changed)
        from aeep_toolkit.managed import comparison_summary
        from aeep_toolkit.reporting import render
        summary = comparison_summary(adapter, bundle)
        assert summary['managed_analysis']['telemetry_capture']['verified'] == count
        assert 'not independent provider metering' in render(summary, 'html')
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_preview_never_changes_records_or_starts_service(tmp_path, monkeypatch):
    router, service, adapter, _path, _grant = prepared(tmp_path, monkeypatch)
    try:
        before = router.store._connection.total_changes
        monkeypatch.setattr(
            service, "status", lambda *args: pytest.fail("preview must not recover jobs")
        )
        preview = adapter.preview()
        assert preview["job"] is None and preview["review_sha256"] == adapter.review_digest
        assert router.store._connection.total_changes == before
        with pytest.raises(ConfigurationError, match="exact source"):
            await adapter.evaluate(adapter.plan.plan_id)
        assert router.store._connection.total_changes == before
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_normalization_keeps_unknowns_auxiliary_cost_lineage_and_boundary_check(
    tmp_path, monkeypatch
):
    router, service, adapter, path, _ = prepared(tmp_path, monkeypatch)
    try:
        report = record(service, adapter, path)
        calls = []
        monkeypatch.setattr(
            adapter_module, "require_conformance", lambda *args, **kwargs: calls.append(kwargs)
        )
        bundle = adapter.normalize(report.report_id)
        assert len(bundle.runs) == 2 and len(calls) == 2
        assert {run.arm for run in bundle.runs} == {"control", "treatment"}
        assert all(
            run.tokens.input_tokens == 7 and run.tokens.cached_input_tokens is None
            for run in bundle.runs
        )
        assert all(run.candidate_invoked is None for run in bundle.runs)
        assert (
            adapter.details["canonical_trials"] == 3
            and len(adapter.details["auxiliary_trial_ids"]) == 1
        )
        assert adapter.details["operation_ledger_sha256"] == report.operation_ledger_digest
        assert adapter.details["assessment_analysis"]["outcome"] == "insufficient_evidence"
        assert not adapter.details["normalization_gaps"]
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_missing_prompt_and_unqualified_boundary_are_explicit_gaps(tmp_path, monkeypatch):
    router, service, adapter, path, _ = prepared(tmp_path, monkeypatch)
    try:
        report = record(service, adapter, path, missing_prompt=True)

        def denied(*args, **kwargs):
            raise ConfigurationError("fixture boundary has no real conformance")

        monkeypatch.setattr(adapter_module, "require_conformance", denied)
        assert not adapter.normalize(report.report_id).runs
        assert len(adapter.details["normalization_gaps"]) == 2
        assert any(
            "task-prompt" in item["reason"] for item in adapter.details["normalization_gaps"]
        )
        assert adapter.details["canonical_trials"] == 3
        monkeypatch.setattr(adapter_module, "verification_source_digest", lambda root: "b" * 64)
        with pytest.raises(ConfigurationError, match="another source"):
            adapter.normalize(report.report_id)
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_execution_keeps_service_denial(tmp_path, monkeypatch):
    router, _service, adapter, _path, _ = prepared(tmp_path, monkeypatch)
    try:
        before = router.store._connection.total_changes
        # The unrelated original grant must not be copied or expanded for this plan.
        with pytest.raises(ConfigurationError, match="authorization scope"):
            await adapter.evaluate(adapter.review_digest)
        assert router.store._connection.total_changes == before
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_dispatch_reuses_service_and_propagates_interruption_without_retry(
    tmp_path, monkeypatch
):
    router, service, adapter, _path, _ = prepared(tmp_path, monkeypatch)
    calls = []

    def enqueue(plan_id):
        calls.append(("enqueue", plan_id))
        return "existing-job"

    async def interrupted(job_id):
        calls.append(("run", job_id))
        raise asyncio.CancelledError()

    monkeypatch.setattr(service, "enqueue", enqueue)
    monkeypatch.setattr(service, "run", interrupted)
    try:
        with pytest.raises(asyncio.CancelledError):
            await adapter.evaluate(adapter.review_digest)
        assert calls == [("enqueue", adapter.plan.plan_id), ("run", "existing-job")]
        assert not adapter.details
    finally:
        await router.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["usage", "model", "discovery", "mask", "trial", "cohort"])
async def test_tampered_receipt_cannot_supply_normalized_evidence(tmp_path, monkeypatch, change):
    router, service, adapter, path, _ = prepared(tmp_path, monkeypatch)
    try:
        report = record(service, adapter, path)
        monkeypatch.setattr(adapter_module, "require_conformance", lambda *args, **kwargs: None)
        with sqlite3.connect(path) as connection:
            identity, trial_id, raw = connection.execute(
                "SELECT * FROM trial_receipts LIMIT 1"
            ).fetchone()
            payload = json.loads(raw)
            if change == "usage":
                payload["actual_resources"]["input_tokens"] = 500
            elif change == "model":
                payload["metadata"]["actual_model"] = "other-model"
            elif change == "discovery":
                payload["metadata"]["capability_discovery"]["invoked"] = True
            elif change == "mask":
                payload["metadata"]["codex_token_fields"] = "[{}]"
            elif change == 'cohort':
                payload['cohort_digest'] = 'sha256:' + '0' * 64
            else:
                trial_id = "another-trial"
            connection.execute(
                "UPDATE trial_receipts SET trial_id=?,payload_json=? WHERE receipt_id=?",
                (trial_id, json.dumps(payload), identity),
            )
        assert len(adapter.normalize(report.report_id).runs) == 1
        assert len(adapter.details["normalization_gaps"]) == 1
        assert adapter.details["canonical_trials"] == 3
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_source_metadata_change_requires_a_new_exact_review(tmp_path, monkeypatch):
    router, _service, adapter, _path, _ = prepared(tmp_path, monkeypatch)
    try:
        reviewed = adapter.review_digest
        adapter.source.revision = "b" * 40
        with pytest.raises(ConfigurationError, match="exact source"):
            await adapter.evaluate(reviewed)
    finally:
        await router.close()


def test_file_preview_does_not_open_a_database_host_or_output(tmp_path, monkeypatch, capsys):
    router, _service, adapter, _path, _ = prepared(tmp_path, monkeypatch)
    plan_file, source_file = tmp_path / "plan.json", tmp_path / "source.json"
    plan_file.write_text(adapter.plan.model_dump_json())
    source_file.write_text(adapter.source.model_dump_json())
    from aeep.router import Router

    monkeypatch.setattr(
        Router, "from_manifest", lambda *args: pytest.fail("preview initialized Router")
    )
    monkeypatch.setattr(
        sqlite3, "connect", lambda *args, **kwargs: pytest.fail("preview opened database")
    )
    monkeypatch.setattr(
        sys, "argv", ["managed", "plan", "--plan", str(plan_file), "--source", str(source_file)]
    )
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    try:
        adapter_module.main()
        preview = json.loads(capsys.readouterr().out)
        assert preview["review_sha256"] == adapter.review_digest
        assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    finally:
        asyncio.run(router.close())


def test_cli_exports_canonical_report_without_another_dispatch(tmp_path, monkeypatch, capsys):
    router, service, adapter, path, _ = prepared(tmp_path, monkeypatch)
    report = record(service, adapter, path)
    plan_file, source_file = tmp_path / "plan.json", tmp_path / "source.json"
    plan_file.write_text(adapter.plan.model_dump_json())
    source_file.write_text(adapter.source.model_dump_json())
    from aeep.assessment.service import AssessmentService
    from aeep.router import Router

    monkeypatch.setattr(Router, "from_manifest", lambda *args: router)
    monkeypatch.setattr(
        AssessmentService, "enqueue", lambda *args: pytest.fail("export enqueued work")
    )
    monkeypatch.setattr(adapter_module, "require_conformance", lambda *args, **kwargs: None)
    output = tmp_path / "export"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "managed",
            "report",
            "--plan",
            str(plan_file),
            "--source",
            str(source_file),
            "--manifest",
            str(tmp_path / "fixture.json"),
            "--directory",
            str(service.directory),
            "--output",
            str(output),
            "--report-id",
            report.report_id,
        ],
    )
    adapter_module.main()
    assert json.loads(capsys.readouterr().out)["normalized_trials"] == 2
    assert json.loads((output / "operation.json").read_text())["state"] == "exported"
    evidence = json.loads((output / "managed-evidence.json").read_text())
    assert evidence["canonical_trials"] == 3 and not evidence["normalization_gaps"]
    assert json.loads((output / "summary.json").read_text())["outcome"] == "NOT_ASSESSED"
    assert (output / "report.html").exists() and (output / "report.md").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "timeout", "unknown"])
async def test_failed_execution_is_not_a_fabricated_failed_grader(tmp_path, monkeypatch, status):
    router, service, adapter, path, _ = prepared(tmp_path, monkeypatch)
    try:
        report = record(service, adapter, path)
        monkeypatch.setattr(adapter_module, "require_conformance", lambda *args, **kwargs: None)
        campaign = BenchmarkCampaignReport.model_validate(
            service.repository.get("campaign", report.campaign_digest)
        )
        trial = campaign.trials[0]
        with sqlite3.connect(path) as connection:
            receipt = ExecutionReceipt.model_validate_json(
                connection.execute(
                    "SELECT payload_json FROM trial_receipts WHERE receipt_id=?",
                    (trial.receipt_ids[0],),
                ).fetchone()[0]
            )
        from aeep.models import ExecutionStatus

        receipt.status = ExecutionStatus(status)
        trial.status = receipt.status
        trial.valid = False
        trial.ok = False
        run = adapter._run(trial, receipt)
        assert run.verification == "unknown" and run.tokens is None
        assert run.status == ("indeterminate" if status == "unknown" else status)
    finally:
        await router.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [True, False, None])
async def test_only_recorded_independent_grader_results_supply_verification(
    tmp_path, monkeypatch, valid
):
    router, service, adapter, path, _ = prepared(tmp_path, monkeypatch)
    try:
        report = record(service, adapter, path)
        monkeypatch.setattr(adapter_module, "require_conformance", lambda *args, **kwargs: None)
        campaign = BenchmarkCampaignReport.model_validate(
            service.repository.get("campaign", report.campaign_digest)
        )
        trial = campaign.trials[0]
        with sqlite3.connect(path) as connection:
            receipt = ExecutionReceipt.model_validate_json(
                connection.execute(
                    "SELECT payload_json FROM trial_receipts WHERE receipt_id=?",
                    (trial.receipt_ids[0],),
                ).fetchone()[0]
            )
        from aeep.models import ValidationResult

        case = adapter.plan.suite.cases[0]
        trial.case_validation = [
            ValidationResult(kind=spec.kind, valid=valid) for spec in case.validators
        ]
        trial.valid = valid
        run = adapter._run(trial, receipt)
        assert run.verification == ("unknown" if valid is None else "pass" if valid else "fail")
        assert (run.verification_ref is not None) == (valid is not None)
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_original_receipt_reference_cannot_escape_plan_storage(tmp_path, monkeypatch):
    router, service, adapter, path, _ = prepared(tmp_path, monkeypatch)
    try:
        report = record(service, adapter, path)
        monkeypatch.setattr(adapter_module, 'require_conformance', lambda *args, **kwargs: None)
        outside = tmp_path / 'unrelated.sqlite3'
        outside.write_text('PRIVATE FIXTURE MUST NOT BE READ')
        with sqlite3.connect(path) as connection:
            trial_id = connection.execute('SELECT trial_id FROM trial_stores LIMIT 1').fetchone()[0]
            connection.execute('UPDATE trial_stores SET database_path=? WHERE trial_id=?', (str(outside), trial_id))
        connect = sqlite3.connect
        def guarded(database, *args, **kwargs):
            assert str(outside) not in str(database)
            return connect(database, *args, **kwargs)
        monkeypatch.setattr(sqlite3, 'connect', guarded)
        assert len(adapter.normalize(report.report_id).runs) == 1
        assert 'outside' in adapter.details['normalization_gaps'][0]['reason']
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_source_pin_binds_all_subject_files_not_only_skill_entry_point(tmp_path, monkeypatch):
    router, service, adapter, _path, _ = prepared(tmp_path, monkeypatch)
    try:
        entry_only = adapter.source.model_copy(update={'artifact_sha256': 'c' * 64})
        before = router.store._connection.total_changes
        with pytest.raises(ConfigurationError, match='source artifact'):
            adapter_module.AEEPAssessmentAdapter(service, adapter.plan.plan_id, entry_only)
        assert router.store._connection.total_changes == before
    finally:
        await router.close()
