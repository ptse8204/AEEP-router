from __future__ import annotations

import pytest

from aeep.assessment.boundary import BoundaryConformance, BoundaryProbe
from aeep.assessment.models import (
    AssessmentEnvironment,
    AssessmentLimits,
    ConformanceProbeRequest,
    content_digest,
)
from aeep.errors import ConfigurationError
from aeep.execution import ExecutionEvent, ExecutionEvidence

pytestmark = pytest.mark.assessment_contract


async def _charged_probe(tmp_path, *, probe_worker: str = "a" * 64,
                         request_worker: str = "a" * 64,
                         grant_id: str = "grant", finish: bool = True,
                         include_definition: bool = True):
    from test_v08_assessment import setup_assessment

    router, service, plan, grant = setup_assessment(tmp_path)
    repo = service.repository
    if grant_id != grant.authorization_id:
        other = grant.model_copy(update={"authorization_id": grant_id})
        repo.grant(other)
    implementation = plan.definition_digests[0] if include_definition else "f" * 64
    request = ConformanceProbeRequest(
        subject_digest=plan.subject_digest,
        recipe_digest=plan.recipe_digest,
        mapping_digest=plan.mapping_digest,
        environment_digest=plan.environment_digest,
        authorization_id=grant_id,
        definition_digests=plan.definition_digests,
        worker_digest=request_worker,
        executable_dependencies={},
    )
    repo.put("conformance_request", request.plan_id, request)
    operation_id = "outer-operation-for-boundary-probe"
    repo.reserve(request, operation_id, AssessmentLimits(max_operations=1, max_elapsed_seconds=5),
                 stage="composed_probe")
    if finish:
        repo.finish_operation(operation_id, elapsed_seconds=0.25)
    operation_digest = content_digest(repo.get("operation_start", operation_id))
    evidence = ExecutionEvidence(
        attempt_id="nested-host-attempt",
        adapter="fixture",
        events=[ExecutionEvent(
            attempt_id="nested-host-attempt", sequence=0, kind="execution.completed", source_id="fixture",
        )],
        complete=True,
    )
    evidence_digest = repo.put("execution_evidence", evidence.digest(), evidence)
    probe = BoundaryProbe(
        schema_version="assessment.boundary-probe.v2",
        probe_id="nested-probe",
        name="native_boundary",
        implementation_digest=implementation,
        worker_digest=probe_worker,
        execution_evidence_digest=evidence_digest,
        observed={"observed": True},
        charged_operation_digest=operation_digest,
    )
    probe_digest = repo.put("boundary_probe", probe.probe_id, probe)
    boundary = BoundaryConformance(
        conformance_id="cost-boundary",
        source_digest="1" * 64,
        worker_digest=probe_worker,
        image_digest="sha256:" + "2" * 64,
        binary_digest="3" * 64,
        adapter="fixture",
        adapter_version="1",
        effective_policy_digest="4" * 64,
        reviewed_inventory_digest="5" * 64,
        identity_digest="6" * 64,
        enforcement_definition_digest="7" * 64,
        advertised_tools=[],
        permitted_tools=[],
        used_tools=[],
        probe_digests=[probe_digest],
    )
    boundary_digest = repo.put("boundary_conformance", boundary.conformance_id, boundary)
    environment = AssessmentEnvironment.model_validate(repo.get("environment", plan.environment_digest))
    environment.conformance_digests = {"candidate": boundary_digest}
    environment_digest = repo.put("environment", "cost-environment", environment)
    cost_plan = plan.model_copy(update={"environment_digest": environment_digest, "setup_cost_ids": []})
    return router, service, cost_plan, request, operation_id, operation_digest


async def test_v2_probe_costs_follow_exact_measured_parent_operation(tmp_path):
    router, service, plan, request, operation_id, operation_digest = await _charged_probe(tmp_path)
    try:
        operation_ids, source_plans = service._cost_sources(plan)
        assert operation_ids == []
        assert request.plan_id in source_plans
        assert operation_id not in source_plans  # The charged op is represented by its request plan.
        ledger = service.repository.operation_ledger(plan.plan_id, operation_ids, source_plans)
        measured = [item for item in ledger.operations if item.operation_id == operation_id]
        assert len(measured) == 1
        assert measured[0].elapsed_seconds == 0.25
        assert content_digest(service.repository.get("operation_start", operation_id)) == operation_digest
        v2_probe = BoundaryProbe.model_validate(service.repository.get("boundary_probe", "nested-probe"))
        assert v2_probe.charged_operation_digest == operation_digest
        legacy_probe = v2_probe.model_copy(update={
            "schema_version": "assessment.boundary-probe.v1",
            "charged_operation_digest": None,
        })
        direct_evidence = ExecutionEvidence(
            attempt_id=operation_id,
            adapter="fixture",
            events=[ExecutionEvent(
                attempt_id=operation_id, sequence=0, kind="execution.completed", source_id="legacy",
            )],
            complete=True,
        )
        assert service._probe_cost_source(
            legacy_probe, direct_evidence, authorization_id=plan.authorization_id
        ) == request.plan_id
    finally:
        await router.close()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"finish": False}, "not settled under this grant"),
        ({"probe_worker": "b" * 64}, "differs from its reviewed request"),
        ({"include_definition": False}, "differs from its reviewed request"),
        ({"grant_id": "other-grant"}, "not settled under this grant"),
    ],
)
async def test_v2_probe_rejects_unsettled_or_unbound_cost_sources(tmp_path, kwargs, message):
    router, service, plan, *_ = await _charged_probe(tmp_path, **kwargs)
    try:
        with pytest.raises(ConfigurationError, match=message):
            service._cost_sources(plan)
    finally:
        await router.close()


async def test_v2_probe_requires_a_canonical_measured_record(tmp_path):
    router, service, plan, _request, operation_id, _digest = await _charged_probe(tmp_path)
    try:
        with service.router.store._immediate_transaction() as connection:
            connection.execute(
                "DELETE FROM assessment_records WHERE kind='operation_measurement' AND id=?",
                (operation_id,),
            )
        with pytest.raises(ConfigurationError, match="no valid measurement"):
            service._cost_sources(plan)
    finally:
        await router.close()


async def test_v2_probe_does_not_accept_an_unresolvable_operation_digest(tmp_path):
    router, service, plan, _request, _operation_id, _digest = await _charged_probe(tmp_path)
    try:
        probe = BoundaryProbe.model_validate(service.repository.get("boundary_probe", "nested-probe"))
        tampered = probe.model_copy(update={"charged_operation_digest": "e" * 64})
        with pytest.raises(ConfigurationError, match="charged operation is unavailable"):
            service._probe_cost_source(
                tampered, ExecutionEvidence(attempt_id="nested", adapter="fixture", events=[], complete=False),
                authorization_id=plan.authorization_id,
            )
    finally:
        await router.close()


def test_boundary_probe_v1_serialization_is_unchanged_and_v2_requires_digest():
    legacy = BoundaryProbe(
        probe_id="legacy",
        name="events",
        implementation_digest="1" * 64,
        worker_digest="2" * 64,
        execution_evidence_digest="3" * 64,
        observed={"ok": True},
    )
    assert legacy.model_dump(mode="json") == {
        "schema_version": "assessment.boundary-probe.v1",
        "probe_id": "legacy",
        "name": "events",
        "implementation_digest": "1" * 64,
        "worker_digest": "2" * 64,
        "execution_evidence_digest": "3" * 64,
        "observed": {"ok": True},
    }
    with pytest.raises(ValueError, match="v2 requires"):
        BoundaryProbe(
            schema_version="assessment.boundary-probe.v2",
            probe_id="missing-charge",
            name="events",
            implementation_digest="1" * 64,
            worker_digest="2" * 64,
            execution_evidence_digest="3" * 64,
            observed={"ok": True},
        )
