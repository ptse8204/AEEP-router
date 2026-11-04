"""Prepare operator review from charged paired-worker observations.

No worker starts here. The existing conformance contracts remain the authority
for consuming these records after their definitions receive operator review.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import model_serializer

from aeep.assessment import verification
from aeep.assessment.boundary import (
    BoundaryConformance,
    BoundaryProbe,
    DifferentialConformance,
)
from aeep.assessment.models import AssessmentAuthorization, AssessmentScopeAmendment, content_digest
from aeep.assessment.service import AssessmentService
from aeep.errors import ConfigurationError
from aeep.execution import ExecutionEvidence
from aeep.hosts.codex_app_server import AppServerOptions
from aeep.hosts.codex_inspection import WorkerInspectionResult
from aeep.hosts.codex_pair_inspection import authorize_pair, expected_probes, observations
from aeep.models import StrictModel


class _Document(StrictModel):
    value: dict[str, Any]

    @model_serializer(mode="plain")
    def document(self) -> dict[str, Any]:
        return self.value


def prepare_readiness(
    service: AssessmentService, control_request: str, treatment_request: str
) -> dict[str, Any]:
    """Store unreviewed definitions; never infer authority from a reported pass."""
    repository = service.repository
    pair, requests, workers, probe_definitions = authorize_pair(
        service, control_request, treatment_request
    )
    root = Path(verification.__file__).resolve().parents[3]
    source = verification.verification_source_digest(root)
    shared = repository.get("shared_environment_definition", pair.differential.shared_definition_digest)
    if content_digest(shared) != pair.differential.shared_definition_digest:
        raise ConfigurationError("shared environment definition differs from the inspected pair")
    documents: dict[str, dict[str, Any]] = {}
    records = {}
    definitions = {pair.differential.shared_definition_digest: shared}
    for request in requests:
        for kind, digest in (("subject", request.subject_digest), ("recipe", request.recipe_digest),
                             ("environment", request.environment_digest)):
            scoped = repository.get(kind, digest)
            if content_digest(scoped) != digest:
                raise ConfigurationError("scoped worker definition changed after inspection")
            definitions[digest] = scoped
    for role, request, worker, expected_definitions in zip(
        ("control", "treatment"), requests, workers, probe_definitions, strict=True
    ):
        operation = "pair-inspection:" + request.plan_id
        record = WorkerInspectionResult.model_validate(
            repository.get("worker_pair_inspection", operation)
        )
        facts = record.observations
        if (
            record.request_id != request.plan_id
            or record.worker_digest != worker.digest()
            or record.execution_evidence_digest is None
            or facts.get("probes_match") is not True
        ):
            raise ConfigurationError("paired worker inspection is incomplete or belongs to another worker")
        try:
            named = observations(pair, role, worker, facts)
        except (KeyError, TypeError, AttributeError, ValueError, ZeroDivisionError) as error:
            raise ConfigurationError("paired worker observations are incomplete") from error
        if named != expected_probes(pair, role):
            raise ConfigurationError("paired worker observations do not establish every required boundary")
        ledger = repository.operation_ledger(request.plan_id)
        charged = [item for item in ledger.operations if item.operation_id == operation]
        with repository.store._lock:
            charge = repository.store._connection.execute(
                "SELECT o.grant_id,o.state,m.digest FROM assessment_operations o "
                "LEFT JOIN assessment_records m ON m.kind='operation_measurement' AND m.id=o.id "
                "WHERE o.id=?", (operation,),
            ).fetchone()
        if (
            len(charged) != 1
            or charged[0].elapsed_seconds is None
            or charged[0].reserved.max_model_turns != 0
            or charged[0].stage != "worker_pair_inspection"
            or charge is None
            or tuple(charge) != (request.authorization_id, "complete", content_digest(charged[0]))
        ):
            raise ConfigurationError("paired inspection has no settled zero-turn operation")
        evidence = ExecutionEvidence.model_validate(
            repository.get("execution_evidence", record.execution_evidence_digest)
        )
        identity = facts["inspection"]["identity_digest"]
        config = getattr(pair, role).managed_host_config()
        if (
            content_digest(evidence) != record.execution_evidence_digest
            or evidence.attempt_id != operation
            or evidence.boundary_digest != worker.digest()
            or evidence.identity_digest != identity
            or not evidence.complete
            or not evidence.events
            or evidence.events[-1].kind != "execution.completed"
        ):
            raise ConfigurationError("paired inspection journal is incomplete or has different identity")
        if AppServerOptions.model_validate(config.adapter_options or {}).catalog_metrics:
            collector = facts["inspection"].get("collector_boundary")
            if collector != {"collector_connection_denied": True} or not any(
                event.kind == "artifact.created"
                and event.source_id == "collector-denied-result"
                and event.evidence_ref == content_digest(collector)
                for event in evidence.events
            ):
                raise ConfigurationError("trusted collector denial is not bound to this inspection")
        probes = {}
        with repository.store._lock:
            rows = repository.store._connection.execute(
                "SELECT digest,payload_json FROM assessment_records WHERE kind='boundary_probe' "
                "AND json_extract(payload_json,'$.execution_evidence_digest')=?",
                (record.execution_evidence_digest,),
            ).fetchall()
        for digest, raw in rows:
            probe = BoundaryProbe.model_validate_json(raw)
            definition = expected_definitions.get(probe.name)
            if (
                definition is None
                or probe.name in probes
                or content_digest(probe) != digest
                or probe.worker_digest != worker.digest()
                or probe.implementation_digest != content_digest(definition)
                or probe.observed != named[probe.name]
                or not any(event.kind == "artifact.created"
                           and event.evidence_ref == content_digest(probe.observed)
                           for event in evidence.events)
            ):
                raise ConfigurationError("paired inspection has conflicting or unbound probes")
            probes[probe.name] = digest
            definitions[probe.implementation_digest] = definition.model_dump(mode="json")
        if set(probes) != set(expected_definitions):
            raise ConfigurationError("paired inspection is missing canonical probes")
        inventory = getattr(pair.differential, role + "_inventory")
        policy = {
            "source_digest": source, "worker_digest": worker.digest(),
            "configuration_digest": worker.configuration_digest, "identity_digest": identity,
            "executor": getattr(pair, role).model_dump(mode="json"),
            "active_policy": facts["active_policy"], "inventory_digest": content_digest(inventory),
            "configuration_probe": probes["configuration"], "candidate_access_probe": probes["candidate_access"],
        }
        enforcement = {
            "source_digest": source, "worker_digest": worker.digest(),
            "inspection_record_digest": content_digest(record), "probe_digests": probes,
            "operation_id": operation, "execution_evidence_digest": record.execution_evidence_digest,
            "scope": "Observed paired-worker boundaries only; no task, token, usefulness or release qualification",
        }
        boundary = BoundaryConformance(
            schema_version="assessment.boundary-conformance.v2",
            conformance_id="toolkit-worker-readiness-" + content_digest({
                "source": source, "role": role, "record": content_digest(record)}),
            source_digest=source, worker_digest=worker.digest(), image_digest=worker.image,
            binary_digest=worker.binary_sha256, adapter=config.adapter_id, adapter_version="1",
            effective_policy_digest=content_digest(policy), reviewed_inventory_digest=content_digest(inventory),
            identity_digest=identity, enforcement_definition_digest=content_digest(enforcement),
            advertised_tools=[], permitted_tools=[], used_tools=[],
            probe_digests=[probes[name] for name in sorted(probes)],
            configuration_digest=worker.configuration_digest, effective_inventory=inventory,
        )
        records[role] = boundary
        for kind, value, identity_key in (
            ("effective_policy_definition", policy, content_digest(policy)),
            ("enforcement_definition", enforcement, content_digest(enforcement)),
            ("reviewed_inventory", inventory, content_digest(inventory)),
            ("worker_binding", worker.model_dump(mode="json"), worker.digest()),
            ("boundary_conformance", boundary.model_dump(mode="json"), boundary.conformance_id),
        ):
            documents[content_digest(value)] = {"kind": kind, "id": identity_key, "document": value}
    differential = DifferentialConformance(definition=pair.differential,
        control_conformance_digest=content_digest(records["control"]),
        treatment_conformance_digest=content_digest(records["treatment"]))
    documents[content_digest(differential)] = {
        "kind": "differential_conformance", "id": content_digest(differential),
        "document": differential.model_dump(mode="json"),
    }
    if verification.verification_source_digest(root) != source:
        raise ConfigurationError("implementation changed while preparing worker readiness")
    definitions.update({digest: item["document"] for digest, item in documents.items()})
    for item in documents.values():
        repository.put(item["kind"], item["id"], _Document(value=item["document"]))
    grant = AssessmentAuthorization.model_validate(repository.get("authorization", requests[0].authorization_id))
    amendment = AssessmentScopeAmendment(authorization_id=grant.authorization_id,
        authorization_digest=content_digest(grant),
        subject_digests=sorted({request.subject_digest for request in requests}),
        recipe_digests=sorted({request.recipe_digest for request in requests}),
        environment_digests=sorted({request.environment_digest for request in requests}),
        reviewed_digests=sorted(definitions))
    return {
        "source_digest": source, "pair_definition_digest": content_digest(pair),
        "request_ids": [request.plan_id for request in requests], "documents": documents,
        "definitions": definitions, "amendment": amendment.model_dump(mode="json"),
        "boundaries": {role: {"conformance_digest": content_digest(record),
            "worker_digest": record.worker_digest, "identity_digest": record.identity_digest,
            "observed_probe_count": len(record.probe_digests)} for role, record in records.items()},
        "differential_conformance_digest": content_digest(differential),
        "reviewed": False, "execution_authorized": False, "workers_started": False,
        "notice": "Unreviewed canonical readiness definitions only. Existing exact operator review and conformance checks are still required before consumption.",
    }
