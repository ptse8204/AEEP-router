"""Synthetic contract checks, never benchmark or billing evidence."""

import json

import pytest
from jsonschema import validate
from pydantic import ValidationError

from aeep_toolkit.models import (
    AdapterCapabilities,
    ComparisonReport,
    DeveloperIdentity,
    EvaluationRun,
    EvidenceBundle,
    ExtensionManifest,
    ExtensionRegistry,
    TokenObservation,
)

D = "a" * 64
SOURCE = {"repository": "https://example.org/skill", "revision": "b" * 40,
          "artifact_sha256": D, "license_expression": "MIT", "data_rights": "no dataset"}


def run_data():
    return dict(run_id="run-1", plan_ref=D, candidate_sha256=D, adapter_sha256=D,
                host="codex", host_version="fixture-1", model="fixture", effort="medium",
                shared_environment_sha256=D, worker_sha256=D, task_sha256=D,
                task_family="trivial", verifier_sha256=D, prompt_sha256=D,
                arm="treatment", mode="optional", candidate_exposed=True,
                candidate_invoked=None, verification="unknown", status="completed",
                retries=0, evidence_kind="synthetic", receipt_refs=[D])


def adapter_data():
    return dict(adapter_id="fixture", implementation_sha256=D, hosts=["codex"],
                candidate_types=["skill"], optional_invocation=True, telemetry=["tokens"],
                containment="unverified")


def extension_data():
    return dict(extension_id="fixture", purpose="Test metadata", role="evaluator", source=SOURCE,
                hosts=["codex"], platforms=["darwin-arm64"], dependencies=[],
                permissions=dict(network_destinations=[], filesystem_scope="workspace",
                                 authentication="host_owned", financial_exposure="subscription_unpriced"),
                disk_bytes=None, memory_bytes=None, install_effects=[], rollback="No installation",
                status="not_installed")


def test_unknowns_survive_json_and_schema_roundtrip():
    run = EvaluationRun(**run_data())
    bundle = EvidenceBundle(candidate=SOURCE, adapter=AdapterCapabilities(**adapter_data()), runs=(run,))
    raw = json.loads(bundle.model_dump_json())
    validate(raw, EvidenceBundle.model_json_schema())
    restored = EvidenceBundle.model_validate(raw)
    assert restored == bundle
    assert restored.runs[0].tokens is None
    assert restored.runs[0].cash_accounting_ref is None
    assert restored.runs[0].candidate_invoked is None
    assert "prompt" not in raw["runs"][0]


@pytest.mark.parametrize("change", [
    {"schema_version": "aeep.toolkit.run.v2"}, {"plan_ref": ""},
    {"retries": -1}, {"retries": True}, {"receipt_refs": []},
    {"agent_wall_seconds": float("nan"), "timing_source_ref": D},
    {"agent_wall_seconds": -1, "timing_source_ref": D},
    {"agent_wall_seconds": 1}, {"verification": "pass"},
    {"verification": "pass", "verification_ref": D, "status": "timeout"},
    {"arm": "control"}, {"candidate_exposed": False, "candidate_invoked": True},
    {"actual_cost_usd": 0}, {"prompt": "must not persist"},
])
def test_invalid_or_unsupported_run_claims_are_rejected(change):
    with pytest.raises(ValidationError):
        EvaluationRun(**(run_data() | change))


def test_token_subsets_and_unknowns_are_not_additive_totals():
    tokens = TokenObservation(source_ref=D, input_tokens=10, cached_input_tokens=6,
                              output_tokens=4, reasoning_output_tokens=2,
                              cached_semantics="included_in_input", reasoning_semantics="included_in_output")
    assert "total_tokens" not in tokens.model_dump()
    assert TokenObservation(source_ref=D, cached_semantics="unknown", reasoning_semantics="unknown").input_tokens is None
    for change in [{"cached_input_tokens": 11}, {"reasoning_output_tokens": 5},
                   {"cached_semantics": "unknown"}, {"total_tokens": 22}]:
        with pytest.raises(ValidationError):
            TokenObservation.model_validate(tokens.model_dump() | change)


@pytest.mark.parametrize("change", [
    {"host": "unsupported"}, {"adapter_sha256": "b" * 64},
    {"agent_wall_seconds": 1, "timing_source_ref": D},
])
def test_adapter_rejects_unsupported_host_identity_or_telemetry(change):
    with pytest.raises(ValidationError):
        EvidenceBundle(candidate=SOURCE, adapter=AdapterCapabilities(**adapter_data()),
                       runs=(EvaluationRun(**(run_data() | change)),))


def test_duplicates_optional_invocation_and_containment():
    run = EvaluationRun(**run_data())
    for capabilities, runs in [(adapter_data(), (run, run)),
                               (adapter_data() | {"optional_invocation": False}, (run,))]:
        with pytest.raises(ValidationError):
            EvidenceBundle(candidate=SOURCE, adapter=AdapterCapabilities(**capabilities), runs=runs)
    with pytest.raises(ValidationError):
        AdapterCapabilities(**(adapter_data() | {"containment": "controlled_workers"}))


def test_extension_permissions_and_pins_are_required():
    manifest = ExtensionManifest(**extension_data())
    validate(json.loads(manifest.model_dump_json()), ExtensionManifest.model_json_schema())
    for change in [{"permissions": {}}, {"source": SOURCE | {"revision": "main"}},
                   {"source": SOURCE | {"repository": "https://user:secret@example.org/repo"}},
                   {"status": "qualified"}, {"status": "blocked"},
                   {"disk_bytes": -1}, {"hosts": []},
                   {"dependencies": [{"extension_id": "fixture", "manifest_sha256": D}]},
                   {"permissions": extension_data()["permissions"] | {"network_destinations": ["https://example.org/?key=secret"]}}]:
        with pytest.raises(ValidationError):
            ExtensionManifest(**(extension_data() | change))


def test_developer_claim_does_not_authenticate_itself():
    identity = dict(source=SOURCE, identity="maintainer", assertion_ref=D)
    for change in [{"verified": True}, {"support_url": "https://example.org/support"},
                   {"support_url": "javascript:alert(1)", "support_kind": "donation"}]:
        with pytest.raises(ValidationError):
            DeveloperIdentity(**(identity | change))


def test_synthetic_report_cannot_claim_demonstrated_benefit():
    report = dict(evidence_bundle_ref=D, plan_ref=D, outcome="INCONCLUSIVE",
                  evidence_kind="synthetic", limitations=["Fixture only"])
    assert ComparisonReport(**report).analysis_ref is None
    with pytest.raises(ValidationError):
        ComparisonReport(**(report | {"outcome": "DEMONSTRATED_BENEFIT", "analysis_ref": D}))
    with pytest.raises(ValidationError):
        ComparisonReport(**(report | {"outcome": "DEMONSTRATED_REGRESSION", "evidence_kind": "live"}))


def test_contract_import_does_not_load_legacy_runtime():
    import os
    import subprocess
    import sys
    from pathlib import Path

    result = subprocess.run(
        [sys.executable, "-c", "import sys; import aeep_toolkit.models; assert 'aeep' not in sys.modules"],
        capture_output=True, text=True, check=False,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert result.returncode == 0, result.stderr


def test_registry_is_inert_and_rejects_ambiguous_identity():
    manifest = ExtensionManifest(**extension_data())
    registry = ExtensionRegistry(extensions=(manifest,))
    assert registry.get("fixture") == manifest
    with pytest.raises(KeyError):
        registry.get("missing")
    with pytest.raises(ValidationError):
        ExtensionRegistry(extensions=(manifest, manifest))


def test_bundle_binds_candidate_artifact():
    with pytest.raises(ValidationError):
        EvidenceBundle(candidate=SOURCE, adapter=AdapterCapabilities(**adapter_data()),
                       runs=(EvaluationRun(**(run_data() | {"candidate_sha256": "b" * 64})),))
