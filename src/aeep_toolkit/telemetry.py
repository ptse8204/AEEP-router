"""Verify retained Codex capture without upgrading provider claims to observations."""

from __future__ import annotations

import json
import re
from typing import Any

from aeep.assessment.models import content_digest
from aeep.errors import ConfigurationError
from aeep.execution import ExecutionEvidence
from aeep.hosts.codex_accounting import TOKEN_FIELDS
from aeep.hosts.codex_metrics import validate_snapshot
from aeep.models import EvidenceStatus, ExecutionReceipt, ExecutionStatus


def bound_journal(receipt: ExecutionReceipt, payload: dict[str, Any] | None) -> ExecutionEvidence | None:
    """The caller resolves this payload from the original attempt store, read-only."""
    reference = receipt.metadata.get("execution_evidence_digest")
    if payload is None:
        return None
    if not reference or content_digest(payload) != reference:
        raise ConfigurationError("execution journal digest differs from its receipt")
    journal = ExecutionEvidence.model_validate(payload)
    if not all((
        journal.attempt_id == receipt.metadata.get("attempt_id"),
        journal.identity_digest == receipt.metadata.get("host_runtime_digest"),
        journal.boundary_digest == receipt.metadata.get("boundary_digest"),
        journal.identity_digest, journal.boundary_digest, journal.journal_id,
    )):
        raise ConfigurationError("execution journal attempt, runtime or boundary differs from its receipt")
    return journal


def token_capture(receipt: ExecutionReceipt, journal: ExecutionEvidence | None) -> dict[str, Any]:
    """Check wire-field coverage and final cumulative accounting, including explicit zeros.

    This verifies the retained capture chain, never the provider's internal meter.
    Missing old journals remain unknown; conflicting retained evidence fails closed.
    """
    result: dict[str, Any] = {
        "status": "unknown", "receipt_ref": content_digest(receipt),
        "journal_ref": receipt.metadata.get("execution_evidence_digest"),
        "known_fields": [], "provider_usage_independently_verified": False,
    }
    if journal is None:
        return result
    # Also check direct callers, rather than relying on a prior loader.
    bound_journal(receipt, journal.model_dump(mode="json"))
    observed = json.loads(receipt.metadata.get("codex_token_fields", "[]"))
    if (not isinstance(observed, list) or any(type(key) is not str for key in observed)
            or len(observed) != len(set(observed))
            or not set(observed) <= {*TOKEN_FIELDS, "totalTokens"}):
        raise ConfigurationError("invalid token observation mask")
    final = [event for event in journal.events
             if event.kind == "usage.reported" and event.source_id in ("turn-usage", "adapter:turn-usage")]
    if not final or not observed:
        return result
    event = final[-1]
    if event.accounting_mode != "cumulative" or event.accounting is None:
        raise ConfigurationError("final token accounting is not cumulative")
    if len(event.accounting.model_usage) != 1 or len(receipt.accounting.model_usage) != 1:
        return result
    usage, saved = event.accounting.model_usage[0], receipt.accounting.model_usage[0]
    if (usage != saved or usage.provider != "openai"
            or usage.model != receipt.metadata.get("actual_model")):
        raise ConfigurationError("final journal usage differs from receipt accounting or model")
    known = [field for wire, field in TOKEN_FIELDS.items() if wire in observed]
    if any(getattr(usage, field) != getattr(receipt.actual_resources, field) for field in known):
        raise ConfigurationError("journal token counts differ from receipt resources")
    result.update(known_fields=known, source=usage.evidence.source.value, trust=usage.evidence.trust.value,
                  status="partial")
    if (set(known) == set(TOKEN_FIELDS.values()) and journal.complete
            and journal.events[-1].kind == "execution.completed"
            and receipt.status == ExecutionStatus.SUCCESS and usage.evidence.status == EvidenceStatus.COMPLETE):
        result["status"] = "verified"
    return result


def candidate_loading(receipt: ExecutionReceipt, journal: ExecutionEvidence | None, *,
                      skill_sha256: str | None = None) -> dict[str, Any]:
    """Positive native instruction loading is distinct from semantic use or task success."""
    result: dict[str, Any] = {
        "instructions_loaded": None, "invoked": None, "delivery_complete": False,
        "snapshot_ref": None, "skill_sha256": receipt.metadata.get("candidate_skill_sha256"),
    }
    snapshot = receipt.metadata.get("catalog_metrics")
    if snapshot is None or journal is None:
        return result
    bound_journal(receipt, journal.model_dump(mode="json"))
    scope = receipt.metadata.get("catalog_metrics_scope")
    if not isinstance(scope, str) or not re.fullmatch("aeep-metrics-[a-f0-9]{32}", scope):
        raise ConfigurationError("catalog metrics scope is unavailable")
    snapshot = validate_snapshot(snapshot, scope)
    digest = content_digest(snapshot)
    if not any(event.kind == "message.received" and event.action_digest == digest
               and event.source_id in ("catalog:" + digest, "adapter:catalog:" + digest)
               for event in journal.events):
        if not snapshot["observations"] and not snapshot["batches"] and not snapshot["collector_closed"]:
            return result
        raise ConfigurationError("catalog snapshot is not bound to the execution journal")
    result["snapshot_ref"] = digest
    name = receipt.metadata.get("candidate_skill_name_sha256")
    if not name or not skill_sha256:
        return result
    if result["skill_sha256"] != skill_sha256:
        raise ConfigurationError("candidate metric identity differs from the reviewed skill")
    matches = [point for point in snapshot["observations"]
               if point["name"] == "codex.skill.injected" and point["skill_digest"] == name
               and point["status"] == "ok" and point["value"] > 0]
    if matches:
        result.update(instructions_loaded=True, invoke_types=sorted({point["invoke_type"] for point in matches}))
    return result


def capture_summary(records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "runs": len(records),
        **{state: sum(item["tokens"]["status"] == state for item in records.values())
           for state in ("verified", "partial", "unknown")},
        "instructions_loaded": sum(item["candidate"]["instructions_loaded"] is True for item in records.values()),
        "candidate_loading_unknown": sum(item["candidate"]["instructions_loaded"] is None for item in records.values()),
        "notice": "Capture verification checks retained journal-to-receipt consistency. Token quantities remain provider-reported; independent provider usage is unverified. Positive skill injection proves instructions loaded, not semantic use. Missing metrics never prove non-use.",
    }
