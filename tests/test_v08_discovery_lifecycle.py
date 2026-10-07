from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from aeep.assessment.controlled_fixture import run as run_controlled_fixture
from aeep.assessment.models import content_digest
from aeep.assessment.onboarding import reference_spec
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.service import AssessmentService
from aeep.capability_lifecycle import CapabilityLifecycle
from aeep.configuration_profile import capture
from aeep.discovery import DiscoveryRequest, RegistryCandidate, _metadata_digest
from aeep.discovery_service import DiscoveryConfig, DiscoveryService, DiscoverySourceConfig
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import ActionRequest, ExecutorKind, Manifest, TaskScope, utc_now
from aeep.profiles import bind_service, from_scope, inspect, preflight, teardown
from aeep.router import Router

pytestmark = pytest.mark.assessment_lifecycle


def _native_identity(root: Path, launcher: str | None) -> tuple[Path, str, str]:
    python_root = str(Path(sys.prefix).resolve())
    if launcher is None:
        return root / "fixture-launcher", "sha256:" + "a" * 64, python_root
    binary = Path(launcher).resolve(strict=True)
    with binary.open("rb") as stream:
        digest = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
    return binary, digest, python_root


async def _run_lifecycle(tmp_path, *, native_launcher: str | None = None, monkeypatch=None):
    root = tmp_path.resolve()
    binary, binary_digest, python_root = _native_identity(root, native_launcher)
    boundary = NativeSandboxConfig(binary=str(binary), binary_sha256=binary_digest, project_root=str(root),
                                   read_roots=[python_root])
    program = ("import csv,json,sys; value=json.load(sys.stdin); "
               "print(json.dumps({'records':list(csv.DictReader(value['text'].splitlines(), "
               "delimiter=value['delimiter']))}))")
    spec = reference_spec("csv").model_copy(update={
        "id": "fixture.csv", "kind": ExecutorKind.COMMAND, "config": {
            "argv": [sys.executable, "-I", "-c", program], "argv_literal": True,
            "stdin_json": True, "output": {"type": "json"}, "timeout_seconds": 2,
            "native_sandbox": boundary.model_dump(mode="json"),
        },
    })
    manifest = root / "aeep.json"
    manifest.write_text(Manifest(database=str(root / ".aeep" / "state.db"), executors=[spec]).model_dump_json())
    router = Router.from_manifest(manifest)
    repository = AssessmentRepository(router.store)
    try:
        fixture = root / "candidates.json"
        fixture.write_text(json.dumps({"candidates": [{
            "registry_candidate_id": "fixture.csv-helper",
            "name": "CSV helper",
            "description": "A local CSV task helper",
            "version": "1.0",
            "package_locator": {"kind": "https", "value": "https://example.invalid/helper.zip"},
            "provenance": {
                "entry": {"type": "plugin", "license": "MIT"},
                "external_identity": {
                    "scheme": "registry", "identifier": "urn:fixture:csv-helper",
                    "registry_origin": "https://registry.example.invalid",
                },
            },
        }]}))
        discovery = DiscoveryService.from_config(router.store, DiscoveryConfig(sources=[
            DiscoverySourceConfig(source_id="local-fixture", kind="fixture", path=fixture.name,
                                  artifact_types=["plugin"]),
        ]), base_directory=root)
        found = await discovery.search(DiscoveryRequest(public_query="CSV helper",
            source_ids=["local-fixture"], limit=1, artifact_types=["plugin"]))
        assert found.candidate_ids == ["fixture.csv-helper"]
        assert found.source_records[0].status == "complete"

        lifecycle = CapabilityLifecycle.from_router(router)
        before_intake = lifecycle.lookup("fixture.csv-helper")
        assert before_intake.disposition == "assess"
        assert before_intake.reason_codes == ["local_intake_required"]
        selected = root / "selected-plugin.txt"
        selected.write_text("operator-selected inert fixture artifact\n")
        intake = lifecycle.inspect_candidate("fixture.csv-helper", selected)
        repository.review(content_digest(intake))
        missing_evidence = lifecycle.lookup("fixture.csv-helper", intake_id=intake.intake_id)
        assert missing_evidence.disposition == "assess"
        assert missing_evidence.next_action == "assess_candidate"
        assert missing_evidence.reason_codes == ["applicable_admission_missing"]
        assert missing_evidence.explanation.startswith("Keep the current environment")
        assert router.store._connection.execute("SELECT COUNT(*) FROM assessment_jobs").fetchone()[0] == 0
        assert router.store._connection.execute("SELECT COUNT(*) FROM assessment_grants").fetchone()[0] == 0
        assert router.store._connection.execute("SELECT COUNT(*) FROM assessment_admissions").fetchone()[0] == 0

        scope = TaskScope(scope_id="fixture-profile", project_root=str(root),
            executor_fingerprints={spec.id: executor_fingerprint(spec)}, max_attempts=2,
            max_attempt_seconds=2, expires_at=utc_now() + timedelta(minutes=5))
        scope_digest = repository.put("task_scope", scope.scope_id, scope)
        repository.review(scope_digest)
        profile = from_scope(router, scope.scope_id, profile_id="fixture-profile", host="task-service")
        profile_digest = repository.put("capability_profile", profile.profile_id, profile)
        assert not preflight(router, profile.profile_id)["ready"]
        repository.review(profile_digest)
        assert preflight(router, profile.profile_id)["ready"]

        if native_launcher is None:
            assert monkeypatch is not None
            monkeypatch.setattr(NativeSandboxConfig, "argv", lambda self, command: command)
        activation, service = bind_service(router, profile.profile_id)
        result = await service.call("aeep_csv", {"text": "name\nAda\n", "delimiter": ","})
        outcome = result["structuredContent"]
        receipt_details = [
            (receipt.error_type, receipt.error_message)
            for item in outcome["receipts"]
            if (receipt := router.store.get_receipt(item["receipt_id"])) is not None
        ]
        assert outcome["ok"], receipt_details
        assert outcome["output"] == {"records": [{"name": "Ada"}]}
        assert outcome["task_scope_digest"] == scope_digest
        assert inspect(router, profile.profile_id, activation_id=activation.activation_id)["activated"]

        observation = capture(router, profile.profile_id, activation.activation_id,
                              [item["receipt_id"] for item in outcome["receipts"]])
        assert observation.receipts[0].invocation_started is True
        assert observation.actual_host_context_tokens is None
        assert observation.actual_visible_inventory == "unavailable"
        assert all(item.preservation == "unavailable" for item in observation.receipts)
        stored_observation = json.dumps(
            repository.get("configuration_observation", observation.observation_id), sort_keys=True,
        )
        assert "Ada" not in stored_observation
        assert '"records"' not in stored_observation

        repository.review(profile_digest, revoke=True)
        assert (await service.call("aeep_csv", {"text": "name\nGrace\n", "delimiter": ","}))["isError"]
        revoked = inspect(router, profile.profile_id, activation_id=activation.activation_id)
        assert not revoked["activated"]
        assert any("capability profile requires current exact operator review" in item
                   for item in revoked["blockers"])
        assert teardown(router, activation.activation_id)["overlay"] == "absent"
    finally:
        await router.close()


@pytest.mark.skipif(sys.platform == "win32", reason="native task integration requires POSIX; Windows uses WSL")
async def test_local_discovery_intake_and_reviewed_task_profile_lifecycle(tmp_path, monkeypatch):
    await _run_lifecycle(tmp_path, monkeypatch=monkeypatch)


async def test_synthetic_controlled_admission_lookup_dispatch_and_revocation(tmp_path, monkeypatch):
    from aeep.assessment.models import AssessmentPlan, AssessmentReport
    from aeep.router import Router

    fixture_dir = (tmp_path / "controlled-fixture").resolve()
    original_admit = AssessmentService.admit
    original_execute = Router.execute
    observed = {"armed": False}

    def admit_with_local_intake(service, report_id):
        admission = original_admit(service, report_id)
        report = AssessmentReport.model_validate(service.repository.get("report", report_id))
        plan = AssessmentPlan.model_validate(service.repository.get("plan", report.plan_digest))
        assert admission.executor_id == plan.candidate_id
        assert admission.subject_digest == plan.subject_digest
        candidate = RegistryCandidate(
            registry_candidate_id="controlled-fixture.csv-helper",
            adapter_id="controlled-fixture",
            name="Synthetic controlled CSV helper",
            description="Local lifecycle fixture; not a real plugin or benefit claim.",
            version="fixture-only",
            package_locator={"kind": "local", "value": "fixture.txt"},
            provenance={"entry": {"type": "plugin"}},
            retrieved_at=utc_now(),
            raw_metadata_digest=_metadata_digest({"purpose": "synthetic controlled fixture"}),
        )
        service.router.store.save_registry_candidate(candidate)
        lifecycle = CapabilityLifecycle(service)
        intake = lifecycle.inspect_candidate(candidate.registry_candidate_id, fixture_dir / "fixture.txt")
        service.repository.review(content_digest(intake))
        observed.update(
            armed=True, router=service.router, lifecycle=lifecycle,
            candidate_id=candidate.registry_candidate_id, intake_id=intake.intake_id,
            admission_id=admission.admission_id, capability=plan.suite.domain,
            input=plan.suite.cases[0].action.input,
        )
        return admission

    async def lookup_then_execute(router, request_or_decision, **kwargs):
        if (observed.get("armed") and router is observed["router"]
                and isinstance(request_or_decision, ActionRequest)
                and request_or_decision.capability == observed["capability"]
                and request_or_decision.input == observed["input"]):
            decision = observed["lifecycle"].lookup(
                observed["candidate_id"], request_or_decision, intake_id=observed["intake_id"],
            )
            assert decision.disposition == "admit", decision.reason_codes
            assert decision.next_action == "use_admitted_capability"
            assert decision.executor_id == "fixture.candidate"
            assert decision.admission_id == observed["admission_id"]
            observed.update(lookup=decision, request=request_or_decision.model_copy(deep=True))
            result = await original_execute(router, request_or_decision, **kwargs)
            receipt = result.receipts[-1]
            assert receipt.executor_id == decision.executor_id
            assert receipt.metadata.get("assessment_admission_id") == decision.admission_id
            observed.update(receipt_id=receipt.receipt_id)
            observed["armed"] = False
            return result
        return await original_execute(router, request_or_decision, **kwargs)

    monkeypatch.setattr(AssessmentService, "admit", admit_with_local_intake)
    monkeypatch.setattr(Router, "execute", lookup_then_execute)
    record = await run_controlled_fixture(fixture_dir)

    assert record.purpose == "controlled local lifecycle fixture; not plugin savings"
    assert observed["lookup"].admission_id == record.admission_id
    assert observed["receipt_id"] == record.receipt_id
    assert observed["request"].capability == observed["lookup"].evidence_cohort["request_capability"]
    assert observed["request"].input == observed["input"]

    router = Router.from_manifest(fixture_dir / "manifest.json")
    try:
        revoked = CapabilityLifecycle.from_router(router).lookup(
            observed["candidate_id"], observed["request"], intake_id=observed["intake_id"],
        )
        assert revoked.disposition == "restrict"
        assert revoked.reason_codes == ["admission_revoked"]
        assert revoked.admission_id == record.admission_id
    finally:
        await router.close()


@pytest.mark.native_boundary
@pytest.mark.skipif(not os.getenv("AEEP_NATIVE_CODEX"), reason="explicit native launcher required")
async def test_discovery_lifecycle_with_installed_native_sandbox(tmp_path):
    await _run_lifecycle(tmp_path, native_launcher=os.environ["AEEP_NATIVE_CODEX"])
