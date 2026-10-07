"""A composed callback charge must bind to its canonical parent operation."""
import sys
from types import SimpleNamespace

import pytest

from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.assessment.models import ConformanceProbeRequest, content_digest
from aeep.attempts import ExecutionAttempt
from aeep.economic.prepared import executor_fingerprint
from aeep.errors import ConfigurationError
from aeep.execution import ExecutionEvent, ExecutionEvidence
from aeep.hosts.codex_invocation import contract_digest
from aeep.models import (
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    ManagedHostExecutorConfig,
    ManagedHostInvocation,
    ModelTokenUsage,
    ResourceAccounting,
    RouteEstimate,
    SideEffect,
)

pytestmark = pytest.mark.assessment_contract


def _callback_case(*, charge_parent: bool):
    from aeep.assessment.boundary import BoundaryProbe

    callback_digest = "a" * 64
    pair_digest = "b" * 64
    worker_digest = "c" * 64
    identity_digest = "d" * 64
    executor = ExecutorSpec(
        id="codex.synthetic",
        capability="workbook.inspect@1",
        kind=ExecutorKind.MANAGED_HOST,
        description="Synthetic composed callback verifier fixture",
        resource_pool="codex.self",
        config=ManagedHostExecutorConfig(
            adapter_id="codex-app-server:1",
            argv=(sys.executable, "app-server"),
            instructions="Synthetic verifier fixture only.",
            invocation=ManagedHostInvocation(
                mode="dynamic_tool",
                server="aeep",
                tool="fixed_workbook",
                tool_sha256="e" * 64,
                dynamic_tools_digest=callback_digest,
            ),
        ).model_dump(mode="json"),
    )
    executor_digest = executor_fingerprint(executor)
    usage = ModelTokenUsage(provider="openai", model="gpt-6-luna", input_tokens=1)
    receipt = ExecutionReceipt(
        decision_id="decision-synthetic",
        action_id="outer-synthetic",
        capability=executor.capability,
        executor_id=executor.id,
        executor_kind=executor.kind,
        status=ExecutionStatus.SUCCESS,
        estimated=RouteEstimate(),
        executor_fingerprint=executor_digest,
        accounting=ResourceAccounting(model_usage=[usage]),
        metadata={
            "host_runtime_digest": identity_digest,
            "dynamic_tools_digest": callback_digest,
            "dynamic_cleanup_confirmed": True,
            "model_turn_count": 1,
        },
    )
    receipt_digest = content_digest(receipt)

    outer = ExecutionAttempt(
        attempt_id="outer-attempt-synthetic",
        decision_id=receipt.decision_id,
        action_digest="f" * 64,
        executor_id=executor.id,
        executor_fingerprint=executor_digest,
        side_effect=SideEffect.READ,
        idempotent=True,
        owner_id="synthetic-fixture",
        state="INVOKING",
        invocation_start_digest="sha256:" + "1" * 64,
    )
    outer_reference = content_digest(outer)

    probe_definition = BoundaryProbeDefinition(
        name="callback_authority",
        executor=executor,
        expected={"native_callback_observed": True},
    )
    definition_digest = content_digest(probe_definition)
    request = ConformanceProbeRequest(
        schema_version="assessment.conformance-request.v4",
        plan_id="plan-synthetic",
        subject_digest="2" * 64,
        recipe_digest="3" * 64,
        mapping_digest="4" * 64,
        environment_digest="5" * 64,
        authorization_id="grant-synthetic",
        definition_digests=[callback_digest, pair_digest, definition_digest],
        worker_digest=worker_digest,
        executable_dependencies={"synthetic-runtime": "6" * 64},
        operation="composed_pair_inspection",
        pair_definition_digest=pair_digest,
        composed_model_turns=1,
    )
    # Deliberately fail at the next lineage guard once the matching callback
    # operation reference has passed the claim-vs-probe check.
    operation = {
        "plan_id": "different-plan",
        "stage": "composed_pair_inspection",
        "reserved": {"max_model_turns": 1},
    }
    operation_reference = content_digest(operation)
    call_digest = "7" * 64
    claim = {
        "context_kind": "conformance",
        "model_turn_allowance": 1,
        "binding_digest": callback_digest,
        "task_scope_digest": "8" * 64,
        "operation_reference": operation_reference,
        "request_digest": content_digest(request),
        "outer_attempt_reference": outer_reference,
        "outer_attempt_digest": contract_digest({"attempt_id": outer.attempt_id}),
        "call_digest": call_digest,
    }
    claim_digest = content_digest(claim)
    child = {
        "claim_digest": claim_digest,
        "task_scope_digest": claim["task_scope_digest"],
        "child_attempt_digests": ["9" * 64],
        "child_receipt_digests": ["a" * 64],
    }
    child_digest = content_digest(child)

    record = SimpleNamespace(
        callback_binding_digest=callback_digest,
        identity_digest=identity_digest,
        composed_definition_digest=pair_digest,
    )
    events = [
        ExecutionEvent(
            attempt_id=outer.attempt_id,
            sequence=0,
            kind="action.completed",
            source_id="dynamic-complete:synthetic",
            accounting=ResourceAccounting(model_usage=[usage]),
        ),
        ExecutionEvent(
            attempt_id=outer.attempt_id,
            sequence=1,
            kind="action.completed",
            source_id="dynamic-link:synthetic",
            evidence_ref=child_digest,
            action_digest=call_digest,
        ),
        ExecutionEvent(
            attempt_id=outer.attempt_id,
            sequence=2,
            kind="execution.completed",
            source_id="terminal:synthetic",
        ),
    ]
    evidence = ExecutionEvidence(
        attempt_id=outer.attempt_id,
        adapter="codex-app-server:1",
        events=events,
        complete=True,
    )
    observed = {
        "callback_origin": "native_app_server",
        "native_callback_observed": True,
    }
    probe = BoundaryProbe(
        schema_version="assessment.boundary-probe.v2",
        probe_id="probe-synthetic",
        name="callback_authority",
        implementation_digest=definition_digest,
        worker_digest=worker_digest,
        execution_evidence_digest=content_digest(evidence),
        observed=observed,
        host_receipt_digest=receipt_digest,
        charged_operation_digest=operation_reference if charge_parent else "d" * 64,
    )

    class Repository:
        records = {
            ("codex_dynamic_tools", callback_digest): {
                "identity": {
                    "worker_digest": worker_digest,
                    "scope_limits": {"max_attempts": 1, "max_attempt_seconds": 10},
                    "executor_fingerprints": {"native": "e" * 64},
                    "approval_ceiling": "read",
                }
            },
            ("conformance_host_receipt", receipt_digest): receipt.model_dump(mode="json"),
            ("callback_evidence", child_digest): child,
            ("callback_claim", claim_digest): claim,
            ("conformance_request", claim["request_digest"]): request.model_dump(mode="json"),
            ("operation_start", operation_reference): operation,
            ("callback_outer_attempt", outer_reference): outer.model_dump(mode="json"),
        }

        def get(self, kind, key):
            return self.records[(kind, key)]

        def authorize(self, _request):
            raise AssertionError("fixture should stop before authorization")

    return Repository(), record, probe, probe_definition, evidence, executor


def test_v2_callback_charge_must_match_canonical_claim_operation():
    from aeep.hosts.codex_pair_inspection import verify_composed_callback

    repo, record, probe, definition, evidence, executor = _callback_case(charge_parent=False)
    with pytest.raises(ConfigurationError, match="not bound to a model conformance allowance"):
        verify_composed_callback(repo, record, probe, definition, evidence, executor)


def test_matching_v2_callback_charge_passes_claim_guard():
    from aeep.hosts.codex_pair_inspection import verify_composed_callback

    repo, record, probe, definition, evidence, executor = _callback_case(charge_parent=True)
    with pytest.raises(ConfigurationError, match="request/reservation/host attempt lineage differs"):
        verify_composed_callback(repo, record, probe, definition, evidence, executor)
