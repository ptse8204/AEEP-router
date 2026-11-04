"""Synthetic protocol fixtures; these never establish actual worker readiness."""

import asyncio
import json

import pytest
from test_v08_assessment import setup_assessment
from test_v08_pair_inspection import approve, definition, mock_workers, prepare

from aeep.assessment.boundary import BoundaryProbe, require_candidate_access, require_conformance
from aeep.assessment.models import AssessmentAuthorization, AssessmentScopeAmendment, content_digest
from aeep.errors import ConfigurationError
from aeep.hosts import codex_pair_inspection as paired
from aeep.models import new_id
from aeep_toolkit import worker_readiness, workflow

pytestmark = pytest.mark.assessment_lifecycle


async def configured(tmp_path, monkeypatch, *, collector=False, collector_event=True):
    router, service, plan, grant = setup_assessment(tmp_path)
    value = definition(task_profile=True)
    shared = {"kind": "first-party synthetic shared environment", "models": 0}
    value.differential.shared_definition_digest = content_digest(shared)
    if collector:
        for spec in (value.control, value.treatment):
            spec.config["adapter_options"] = {"catalog_metrics": True}
    service.repository.put("shared_environment_definition", content_digest(shared),
        worker_readiness._Document(value=shared))
    requests = prepare(service, plan, value)
    approve(service, grant, requests)
    mock_workers(monkeypatch, value)
    if collector:
        original = paired.collect

        async def collect(adapter, config, journal, recheck):
            facts = await original(adapter, config, journal, recheck)
            facts["collector_boundary"] = {"collector_connection_denied": True}
            if collector_event:
                journal.append("artifact.created", "collector-denied-result",
                    evidence_ref=content_digest(facts["collector_boundary"]))
            return facts

        monkeypatch.setattr(paired, "collect", collect)
    observed = await paired.execute_pair(service, *(request.plan_id for request in requests))
    assert observed["probes_match"]
    monkeypatch.setattr(worker_readiness.verification, "verification_source_digest", lambda _root: "a" * 64)
    return router, service, requests, observed, value


@pytest.mark.parametrize("collector", [False, True])
async def test_readiness_preparation_reuses_real_contracts_without_review_or_new_operations(
    tmp_path, monkeypatch, collector
):
    router, service, requests, _observed, pair = await configured(tmp_path, monkeypatch, collector=collector)
    try:
        repo = service.repository
        before = tuple(router.store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds FROM assessment_grants WHERE id='grant'"
        ).fetchone())
        result = worker_readiness.prepare_readiness(service, *(request.plan_id for request in requests))
        assert result["reviewed"] is result["execution_authorized"] is result["workers_started"] is False
        assert len(result["documents"]) == 11
        for boundary in result["boundaries"].values():
            assert boundary["observed_probe_count"] == 11
            with pytest.raises(ConfigurationError, match="review missing"):
                require_conformance(repo, boundary["conformance_digest"], source_digest="a" * 64,
                    worker_digest=boundary["worker_digest"], identity_digest=boundary["identity_digest"])
        # The existing operator review closes the gap; preparation cannot supply it.
        amendment = AssessmentScopeAmendment.model_validate(result["amendment"])
        repo.approve_bundle(amendment, result["definitions"])
        for role, boundary in result["boundaries"].items():
            record = require_conformance(repo, boundary["conformance_digest"], source_digest="a" * 64,
                worker_digest=boundary["worker_digest"], identity_digest=boundary["identity_digest"])
            require_candidate_access(repo, record, pair.differential, available=role == "treatment")
        again = worker_readiness.prepare_readiness(service, *(request.plan_id for request in requests))
        assert again["boundaries"] == result["boundaries"]
        assert again["differential_conformance_digest"] == result["differential_conformance_digest"]
        assert tuple(router.store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds FROM assessment_grants WHERE id='grant'"
        ).fetchone()) == before
    finally:
        await router.close()


@pytest.mark.parametrize("fault", [
    "failed_record", "wrong_request", "wrong_worker", "missing_fact", "wrong_observation",
    "unsettled", "wrong_stage", "unknown_probe", "duplicate_probe", "missing_probe",
    "wrong_probe_worker", "missing_probe_event", "journal_identity", "missing_shared", "source_drift", "foreign_grant",
])
async def test_partial_or_tampered_worker_records_cannot_become_readiness(tmp_path, monkeypatch, fault):
    router, service, requests, observed, _pair = await configured(tmp_path, monkeypatch)
    repo = service.repository
    connection = router.store._connection
    operation = "pair-inspection:" + requests[1].plan_id
    record = repo.get("worker_pair_inspection", operation)
    evidence_ref = record["execution_evidence_digest"]

    def alter(kind, identity, document):
        connection.execute("UPDATE assessment_records SET payload_json=? WHERE kind=? AND id=?",
            (json.dumps(document), kind, identity))

    try:
        if fault in {"failed_record", "wrong_request", "wrong_worker", "missing_fact", "wrong_observation"}:
            if fault == "failed_record":
                record["observations"]["probes_match"] = False
            elif fault == "wrong_request":
                record["request_id"] = "another-fixture"
            elif fault == "wrong_worker":
                record["worker_digest"] = "f" * 64
            elif fault == "missing_fact":
                record["observations"].pop("inspection")
            else:
                record["observations"]["active_policy"]["approval_never"] = False
            alter("worker_pair_inspection", operation, record)
        elif fault == "unsettled":
            connection.execute("DELETE FROM assessment_records WHERE kind='operation_measurement' AND id=?", (operation,))
        elif fault == "wrong_stage":
            measurement = repo.get("operation_measurement", operation)
            measurement["stage"] = "unrelated"
            alter("operation_measurement", operation, measurement)
        elif fault in {"unknown_probe", "duplicate_probe", "wrong_probe_worker"}:
            probe = BoundaryProbe.model_validate(repo.get("boundary_probe", observed["workers"]["treatment"]["probe_digests"][0]))
            update = {"probe_id": new_id("fixture_probe")}
            if fault == "unknown_probe":
                update["name"] = "unreviewed"
            elif fault == "wrong_probe_worker":
                update["worker_digest"] = "f" * 64
            extra = probe.model_copy(update=update)
            repo.put("boundary_probe", extra.probe_id, extra)
        elif fault == "missing_probe":
            connection.execute("DELETE FROM assessment_records WHERE kind='boundary_probe' AND digest=?",
                (observed["workers"]["treatment"]["probe_digests"][0],))
        elif fault in {"journal_identity", "missing_probe_event"}:
            evidence = repo.get("execution_evidence", evidence_ref)
            if fault == "journal_identity":
                evidence["identity_digest"] = "f" * 64
            else:
                # Rebind the synthetic journal after removing one probe event.
                evidence["events"] = [event for event in evidence["events"]
                    if event["source_id"] != "probe-configuration"]
                for i, event in enumerate(evidence["events"]):
                    event["sequence"] = i
            # Retained digest disagreement itself must stop preparation.
            connection.execute("UPDATE assessment_records SET payload_json=? WHERE kind='execution_evidence' AND digest=?",
                (json.dumps(evidence), evidence_ref))
        elif fault == "foreign_grant":
            original = AssessmentAuthorization.model_validate(repo.get("authorization", "grant"))
            repo.grant(original.model_copy(update={"authorization_id": "another-fixture-grant"}))
            connection.execute("UPDATE assessment_operations SET grant_id=? WHERE id=?",
                ("another-fixture-grant", operation))
        elif fault == "missing_shared":
            connection.execute("DELETE FROM assessment_records WHERE kind='shared_environment_definition'")
        else:
            values = iter(["a" * 64, "b" * 64])
            monkeypatch.setattr(worker_readiness.verification, "verification_source_digest", lambda _root: next(values))
        connection.commit()
        with pytest.raises(ConfigurationError):
            worker_readiness.prepare_readiness(service, *(request.plan_id for request in requests))
        assert connection.execute("SELECT count(*) FROM assessment_records WHERE kind='boundary_conformance'").fetchone()[0] == 0
    finally:
        await router.close()


async def test_collector_claim_without_its_journal_event_is_rejected(tmp_path, monkeypatch):
    router, service, requests, _observed, _pair = await configured(
        tmp_path, monkeypatch, collector=True, collector_event=False)
    try:
        with pytest.raises(ConfigurationError, match="collector denial"):
            worker_readiness.prepare_readiness(service, *(request.plan_id for request in requests))
    finally:
        await router.close()


async def test_ordinary_cli_exports_unreviewed_packet_and_preserves_existing_output(tmp_path, monkeypatch, capsys):
    router, _service, requests, _observed, _pair = await configured(tmp_path, monkeypatch)
    output = tmp_path / "worker-readiness.json"
    original_close = router.close

    async def no_close():
        pass

    monkeypatch.setattr(router, "close", no_close)
    from aeep.router import Router

    monkeypatch.setattr(Router, "from_manifest", lambda *_args: router)
    argv = ["prepare-worker-readiness", "--manifest", str(tmp_path / "manifest.json"),
        "--control-request", requests[0].plan_id, "--treatment-request", requests[1].plan_id,
        "--output", str(output)]
    try:
        await asyncio.to_thread(workflow.main, argv)
        response = json.loads(capsys.readouterr().out)
        assert response["reviewed"] is response["workers_started"] is False
        packet = json.loads(output.read_text())
        assert len(packet["boundaries"]) == 2
        retained = output.read_bytes()
        with pytest.raises(SystemExit) as failure:
            await asyncio.to_thread(workflow.main, argv)
        assert failure.value.code == 2 and output.read_bytes() == retained
    finally:
        await original_close()
