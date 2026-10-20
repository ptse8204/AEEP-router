"""Synthetic capture-chain faults; these do not establish provider usage or live use."""

import hashlib
import json

import pytest

from aeep.assessment.models import content_digest
from aeep.errors import ConfigurationError
from aeep.execution import EventJournal, ExecutionEvidence
from aeep.hosts.codex_accounting import TOKEN_FIELDS, turn_accounting
from aeep.hosts.codex_metrics import snapshot
from aeep.models import ExecutionReceipt, RouteEstimate
from aeep.router import Router
from aeep_toolkit.telemetry import bound_journal, candidate_loading, capture_summary, token_capture


def capture(*, missing=None, terminal=True, metric=None):
    wire = dict.fromkeys(TOKEN_FIELDS, 0)
    wire.update(inputTokens=12, cachedInputTokens=4, outputTokens=3)
    if missing:
        del wire[missing]
    resources, accounting = turn_accounting(wire, model="fixture", resource_pool="fixture")
    stream = EventJournal("fixture")
    stream.append("execution.started", "start")
    if metric:
        stream.append("message.received", "catalog:" + content_digest(metric), action_digest=content_digest(metric))
    stream.append("usage.reported", "turn-usage", accounting=accounting, accounting_mode="cumulative")
    if terminal:
        stream.append("execution.completed", "terminal")
    journal = ExecutionEvidence(attempt_id="fixture", adapter="fixture", events=list(stream.items),
        journal_id=stream.journal_id, complete=terminal, identity_digest="a"*64, boundary_digest="b"*64)
    receipt = ExecutionReceipt(decision_id="fixture", action_id="fixture", capability="fixture",
        executor_id="fixture", executor_kind="host_managed", status="success", estimated=RouteEstimate(),
        actual_resources=resources, accounting=accounting, metadata={
            "execution_evidence_digest": content_digest(journal), "attempt_id": "fixture",
            "host_runtime_digest": "a"*64, "boundary_digest": "b"*64, "actual_model": "fixture",
            "codex_token_fields": json.dumps(sorted(wire)),
        })
    if metric:
        receipt.metadata.update(catalog_metrics=metric, catalog_metrics_scope=metric["scope"],
            candidate_skill_name_sha256=hashlib.sha256(b"fixture").hexdigest(), candidate_skill_sha256="c"*64)
    return receipt, journal


def test_verified_capture_preserves_reported_trust_and_zero_categories():
    receipt, journal = capture()
    check = token_capture(receipt, bound_journal(receipt, journal.model_dump(mode="json")))
    assert check["status"] == "verified"
    assert set(check["known_fields"]) == set(TOKEN_FIELDS.values())
    assert check["source"] == "provider_report" and check["trust"] == "self_asserted"
    assert check["provider_usage_independently_verified"] is False
    from aeep.assessment.reporting import resource_measurements
    assert all(v is None for v in resource_measurements(receipt.accounting, receipt.actual_resources).values())


@pytest.mark.parametrize("missing", list(TOKEN_FIELDS))
def test_partial_counts_never_become_complete_zeros(missing):
    receipt, journal = capture(missing=missing)
    check = token_capture(receipt, journal)
    assert check["status"] in {"unknown", "partial"}
    assert TOKEN_FIELDS[missing] not in check["known_fields"]


def test_missing_and_interrupted_journals_are_not_complete():
    receipt, journal = capture(terminal=False)
    assert token_capture(receipt, None)["status"] == "unknown"
    assert token_capture(receipt, journal)["status"] == "partial"


@pytest.mark.parametrize("fault", ["hash", "attempt", "runtime", "boundary", "counts", "accounting", "mask"])
def test_misbound_or_changed_evidence_fails_closed(fault):
    receipt, journal = capture()
    if fault == "hash":
        receipt.metadata["execution_evidence_digest"] = "d"*64
    elif fault in ("attempt", "runtime", "boundary"):
        receipt.metadata[{"attempt":"attempt_id", "runtime":"host_runtime_digest", "boundary":"boundary_digest"}[fault]] = "changed"
    elif fault == "counts":
        receipt.actual_resources.input_tokens += 1
    elif fault == "accounting":
        receipt.accounting = receipt.accounting.model_copy(deep=True)
        receipt.accounting.model_usage[0].output_tokens += 1
    else:
        receipt.metadata["codex_token_fields"] = '["inputTokens", "inputTokens"]'
    with pytest.raises((ConfigurationError, ValueError)):
        token_capture(receipt, journal)


@pytest.mark.parametrize("fault", [None, "other", "error", "zero", "dropped", "overflow", "rejected"])
def test_only_matching_positive_injection_proves_instruction_loading(fault):
    metric = snapshot("aeep-metrics-" + "d"*32)
    point = {"name":"codex.skill.injected", "skill_digest":hashlib.sha256(b"fixture").hexdigest(),
             "status":"ok", "invoke_type":"implicit", "count":1, "value":1}
    if fault == "other":
        point["skill_digest"] = "f"*64
    if fault == "error":
        point["status"] = "error"
    if fault == "zero":
        point["value"] = 0
    metric["observations"] = [] if fault == "dropped" else [point]
    metric["overflow"] = fault == "overflow"
    metric["rejected_batches"] = int(fault == "rejected")
    receipt, journal = capture(metric=metric)
    retained = Router._safe_receipt_metadata(receipt.metadata)
    assert retained["catalog_metrics"] == metric
    receipt.metadata = retained
    check = candidate_loading(receipt, journal, skill_sha256="c"*64)
    assert check["instructions_loaded"] is (True if fault in (None, "overflow", "rejected") else None)
    assert check["invoked"] is None and check["delivery_complete"] is False
    assert capture_summary({"fixture":{"tokens":token_capture(receipt,journal),"candidate":check}})["runs"] == 1


def test_changed_metrics_and_foreign_scope_fail_closed():
    metric = snapshot("aeep-metrics-" + "d"*32)
    receipt, journal = capture(metric=metric)
    receipt.metadata["catalog_metrics"]["collector_closed"] = True
    with pytest.raises(ConfigurationError, match="not bound"):
        candidate_loading(receipt, journal)


def test_candidate_digest_must_match_the_reviewed_target():
    metric = snapshot("aeep-metrics-" + "d"*32)
    receipt, journal = capture(metric=metric)
    assert candidate_loading(receipt, journal)["instructions_loaded"] is None
    with pytest.raises(ConfigurationError, match="reviewed skill"):
        candidate_loading(receipt, journal, skill_sha256="e"*64)
    receipt.metadata["catalog_metrics_scope"] = "aeep-metrics-" + "e"*32
    with pytest.raises(ValueError, match="invalid catalog"):
        candidate_loading(receipt, journal)


def test_collector_with_no_delivered_snapshot_stays_unknown():
    receipt, journal = capture()
    receipt.metadata.update(catalog_metrics=snapshot("aeep-metrics-" + "d"*32),
                            catalog_metrics_scope="aeep-metrics-" + "d"*32)
    assert candidate_loading(receipt, journal)["instructions_loaded"] is None
