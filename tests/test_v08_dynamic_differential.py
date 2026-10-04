"""Offline contracts for exact dynamic-tool differential evidence."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from aeep.assessment.boundary import (
    BoundaryConformance,
    BoundaryProbe,
    DifferentialConformance,
    require_candidate_access,
    require_differential,
    require_dynamic_candidate_target,
)
from aeep.assessment.models import DifferentialEnvironment, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.errors import ConfigurationError
from aeep.hosts.codex_dynamic_tools import CodexDynamicTools
from aeep.hosts.codex_invocation import contract_digest
from aeep.hosts.codex_pair_inspection import dynamic_candidate_access_observation
from aeep.models import ManagedHostInvocation, SideEffect, StrictModel
from aeep.store import ReceiptStore

pytestmark = pytest.mark.assessment_contract

COMMON_TOOL = {
    "name": "fixed_workbook",
    "description": "Fixed shared workbook task operation.",
    "inputSchema": {
        "type": "object",
        "properties": {"input": {"type": "string"}},
        "required": ["input"],
        "additionalProperties": False,
    },
}
CANDIDATE_TOOL = {
    "name": "aeep_workbook_task",
    "description": "Reviewed task-only AEEP workbook capability.",
    "inputSchema": {
        "type": "object",
        "properties": {"input": {"type": "string"}},
        "required": ["input"],
        "additionalProperties": False,
    },
}
CONTROL_WORKER = "1" * 64
TREATMENT_WORKER = "2" * 64


class DynamicToolDocument(StrictModel):
    namespace: str
    tools: list[dict[str, Any]]
    identity: dict[str, Any]
    max_calls: int
    timeout_seconds: float


class SharedDefinition(StrictModel):
    purpose: str


class MappingFixture(StrictModel):
    label: str


async def _unused_call(_name: str, _arguments: dict[str, Any]) -> dict[str, Any]:
    raise AssertionError("declaration-only fixture must not dispatch a tool")


def _binding(worker_digest: str, tools: list[dict[str, Any]]) -> CodexDynamicTools:
    checked: dict[str, str] = {}
    binding = CodexDynamicTools(
        namespace="workbook",
        tools=tools,
        identity={
            "worker_digest": worker_digest,
            "native_backend_digest": "3" * 64,
            "implementation_digest": CodexDynamicTools.implementation_digest(),
            "approval_ceiling": SideEffect.READ.value,
        },
        max_calls=1,
        timeout_seconds=10.0,
        call=_unused_call,
        check=lambda: checked["digest"],
    )
    checked["digest"] = binding.digest
    return binding


def _declaration(binding: CodexDynamicTools) -> dict[str, Any]:
    return {
        "binding_digest": binding.digest,
        "dynamic_inventory": binding.inventory(),
        "declaration_digest": content_digest({"dynamicTools": binding.declarations()}),
        "declaration_acknowledged": True,
        "model_tool_exposure": "unknown",
        "model_turns": 0,
        "task_calls": 0,
        "active_policy": {
            "profile_matches": True,
            "approval_never": True,
            "cwd_matches": True,
        },
    }


def _environment(*, candidate_digest: str | None = None) -> DifferentialEnvironment:
    candidate = dict(CANDIDATE_TOOL)
    candidate_tools = {
        f"dynamic:workbook:{candidate['name']}": candidate_digest or contract_digest(candidate),
    }
    common_inventory = {
        "python": "4" * 64,
        f"dynamic:workbook:{COMMON_TOOL['name']}": contract_digest(COMMON_TOOL),
    }
    return DifferentialEnvironment(
        shared_definition_digest="5" * 64,
        control_inventory=common_inventory,
        treatment_inventory={**common_inventory, **candidate_tools},
        candidate_inventory=candidate_tools,
        candidate_paths=[],
        candidate_aliases=[],
        candidate_dynamic_tools=candidate_tools,
    )


def _plain_worker_environment() -> DifferentialEnvironment:
    candidate_tools = {
        f"dynamic:workbook:{CANDIDATE_TOOL['name']}": contract_digest(CANDIDATE_TOOL),
    }
    control_inventory = {"python": "4" * 64}
    return DifferentialEnvironment(
        shared_definition_digest="5" * 64,
        control_inventory=control_inventory,
        treatment_inventory={**control_inventory, **candidate_tools},
        candidate_inventory=candidate_tools,
        candidate_paths=[],
        candidate_aliases=[],
        candidate_dynamic_tools=candidate_tools,
    )


def _invocation_spec(identity: str, invocation: ManagedHostInvocation) -> SimpleNamespace:
    return SimpleNamespace(
        id=identity,
        managed_host_config=lambda: SimpleNamespace(invocation=invocation),
    )


def _treatment_invocation(binding_digest: str, *, tool_sha256: str | None = None) -> ManagedHostInvocation:
    return ManagedHostInvocation(
        mode="dynamic_tool",
        server="workbook",
        tool=CANDIDATE_TOOL["name"],
        tool_sha256=tool_sha256 or contract_digest(CANDIDATE_TOOL),
        dynamic_tools_digest=binding_digest,
    )


def _store_binding(
    repository: AssessmentRepository,
    binding: CodexDynamicTools,
    *,
    reviewed: bool = True,
) -> str:
    document = DynamicToolDocument.model_validate(binding.definition())
    digest = repository.put("codex_dynamic_tools", binding.digest, document)
    assert digest == binding.digest == content_digest(document)
    if reviewed:
        repository.review(digest)
    return digest


def _boundary(
    repository: AssessmentRepository,
    *,
    expected: DifferentialEnvironment,
    worker_digest: str,
    callback_binding_digest: str,
    effective_inventory: dict[str, str],
    available: bool,
    probe_changes: dict[str, Any] | None = None,
) -> BoundaryConformance:
    observed: dict[str, str | int | bool] = {
        "definition_digest": content_digest(expected),
        "candidate_available": available,
        "candidate_kind": "dynamic_tool",
        "candidate_tools_digest": content_digest(expected.candidate_dynamic_tools),
        "callback_binding_digest": callback_binding_digest,
    }
    observed.update(probe_changes or {})
    probe = BoundaryProbe(
        probe_id=f"candidate-access-{worker_digest[:8]}-{content_digest(observed)[:8]}",
        name="candidate_access",
        implementation_digest="6" * 64,
        worker_digest=worker_digest,
        execution_evidence_digest="7" * 64,
        observed=observed,
    )
    probe_digest = repository.put("boundary_probe", probe.probe_id, probe)
    return BoundaryConformance(
        schema_version="assessment.boundary-conformance.v3",
        conformance_id=f"fixture-{worker_digest[:8]}",
        source_digest="8" * 64,
        worker_digest=worker_digest,
        image_digest="sha256:" + "9" * 64,
        binary_digest="a" * 64,
        adapter="codex-app-server:fixture",
        adapter_version="1",
        effective_policy_digest="b" * 64,
        reviewed_inventory_digest=content_digest(effective_inventory),
        identity_digest="c" * 64,
        enforcement_definition_digest="d" * 64,
        advertised_tools=list(effective_inventory),
        permitted_tools=list(effective_inventory),
        used_tools=[],
        probe_digests=[probe_digest],
        configuration_digest="e" * 64,
        effective_inventory=effective_inventory,
        callback_binding_digest=callback_binding_digest,
        native_backend_digest="f" * 64,
        composed_definition_digest="0" * 64,
    )


@pytest.fixture
def dynamic_pair(tmp_path):
    store = ReceiptStore(tmp_path / "differential.db")
    repository = AssessmentRepository(store)
    expected = _environment()
    control = _binding(CONTROL_WORKER, [COMMON_TOOL])
    treatment = _binding(TREATMENT_WORKER, [COMMON_TOOL, CANDIDATE_TOOL])
    control_digest = _store_binding(repository, control)
    treatment_digest = _store_binding(repository, treatment)
    control_boundary = _boundary(
        repository,
        expected=expected,
        worker_digest=CONTROL_WORKER,
        callback_binding_digest=control_digest,
        effective_inventory=expected.control_inventory,
        available=False,
    )
    treatment_boundary = _boundary(
        repository,
        expected=expected,
        worker_digest=TREATMENT_WORKER,
        callback_binding_digest=treatment_digest,
        effective_inventory=expected.treatment_inventory,
        available=True,
    )
    yield {
        "store": store,
        "repository": repository,
        "expected": expected,
        "control_binding_digest": control_digest,
        "treatment_binding_digest": treatment_digest,
        "control_boundary": control_boundary,
        "treatment_boundary": treatment_boundary,
    }
    store.close()


def _with_probe(
    repository: AssessmentRepository,
    boundary: BoundaryConformance,
    *,
    expected: DifferentialEnvironment,
    available: bool,
    worker_digest: str | None = None,
    callback_binding_digest: str | None = None,
    changes: dict[str, Any] | None = None,
) -> BoundaryConformance:
    return _boundary(
        repository,
        expected=expected,
        worker_digest=worker_digest or boundary.worker_digest,
        callback_binding_digest=callback_binding_digest or boundary.callback_binding_digest or "",
        effective_inventory=boundary.effective_inventory or {},
        available=available,
        probe_changes=changes,
    )


def test_dynamic_candidate_access_binds_real_declaration_and_control_absence(dynamic_pair):
    repository = dynamic_pair["repository"]
    expected = dynamic_pair["expected"]

    require_candidate_access(
        repository,
        dynamic_pair["control_boundary"],
        expected,
        available=False,
    )
    require_candidate_access(
        repository,
        dynamic_pair["treatment_boundary"],
        expected,
        available=True,
    )


def test_plain_worker_proves_only_normal_dynamic_candidate_absence(tmp_path):
    store = ReceiptStore(tmp_path / "plain-dynamic-absence.db")
    repository = AssessmentRepository(store)
    try:
        expected = _plain_worker_environment()
        worker_digest = "8" * 64
        inventory = expected.control_inventory
        observed = {
            "definition_digest": content_digest(expected),
            "candidate_available": False,
            "candidate_kind": "dynamic_tool",
            "candidate_tools_digest": content_digest(expected.candidate_dynamic_tools),
            "callback_binding_digest": "absent",
        }
        probe = BoundaryProbe(
            probe_id="plain-dynamic-absence",
            name="candidate_access",
            implementation_digest="6" * 64,
            worker_digest=worker_digest,
            execution_evidence_digest="7" * 64,
            observed=observed,
        )
        probe_digest = repository.put("boundary_probe", probe.probe_id, probe)
        boundary = BoundaryConformance(
            schema_version="assessment.boundary-conformance.v2",
            conformance_id="plain-dynamic-absence",
            source_digest="8" * 64,
            worker_digest=worker_digest,
            image_digest="sha256:" + "9" * 64,
            binary_digest="a" * 64,
            adapter="plain-worker:fixture",
            adapter_version="1",
            effective_policy_digest="b" * 64,
            reviewed_inventory_digest=content_digest(inventory),
            identity_digest="c" * 64,
            enforcement_definition_digest="d" * 64,
            advertised_tools=list(inventory),
            permitted_tools=list(inventory),
            used_tools=[],
            probe_digests=[probe_digest],
            configuration_digest="e" * 64,
            effective_inventory=inventory,
        )

        require_candidate_access(repository, boundary, expected, available=False)
        with pytest.raises(ConfigurationError, match="plain worker cannot claim"):
            require_candidate_access(repository, boundary, expected, available=True)

        dynamic_inventory = {
            **inventory,
            "dynamic:workbook:unreviewed": "f" * 64,
        }
        with pytest.raises(ConfigurationError, match="plain worker cannot claim"):
            require_candidate_access(
                repository,
                boundary.model_copy(update={"effective_inventory": dynamic_inventory}),
                expected,
                available=False,
            )
    finally:
        store.close()


def test_declaration_observation_keeps_tool_exposure_unknown_and_turn_free(dynamic_pair):
    expected = dynamic_pair["expected"]
    common = _binding(CONTROL_WORKER, [COMMON_TOOL])
    candidate = _binding(TREATMENT_WORKER, [COMMON_TOOL, CANDIDATE_TOOL])
    control_declaration = _declaration(common)
    candidate_declaration = _declaration(candidate)

    absent = dynamic_candidate_access_observation(
        expected,
        binding=common,
        worker=SimpleNamespace(digest=lambda: CONTROL_WORKER),
        declaration=control_declaration,
    )
    present = dynamic_candidate_access_observation(
        expected,
        binding=candidate,
        worker=SimpleNamespace(digest=lambda: TREATMENT_WORKER),
        declaration=candidate_declaration,
    )

    assert absent["candidate_available"] is False
    assert present["candidate_available"] is True
    for declaration in (control_declaration, candidate_declaration):
        assert declaration["model_tool_exposure"] == "unknown"
        assert declaration["model_turns"] == declaration["task_calls"] == 0
    assert "model_tool_exposure" not in present
    assert "model_turns" not in present and "task_calls" not in present
    assert "host_receipt_digest" not in present


def test_dynamic_invocation_target_accepts_exact_candidate_and_control(dynamic_pair):
    expected = dynamic_pair["expected"]
    control = _invocation_spec(
        "control",
        ManagedHostInvocation(
            mode="turn",
            dynamic_tools_digest=dynamic_pair["control_binding_digest"],
        ),
    )
    treatment = _invocation_spec(
        "treatment",
        _treatment_invocation(dynamic_pair["treatment_binding_digest"]),
    )

    require_dynamic_candidate_target(
        control,
        dynamic_pair["control_boundary"],
        expected,
        available=False,
    )
    require_dynamic_candidate_target(
        treatment,
        dynamic_pair["treatment_boundary"],
        expected,
        available=True,
    )


@pytest.mark.parametrize(
    "fault",
    ["binding", "boundary_binding", "server", "tool", "hash", "mode", "control_mode"],
)
def test_dynamic_invocation_target_rejects_mismatch(dynamic_pair, fault):
    expected = dynamic_pair["expected"]
    invocation = _treatment_invocation(dynamic_pair["treatment_binding_digest"])
    boundary = dynamic_pair["treatment_boundary"]
    available = True

    if fault == "binding":
        invocation = invocation.model_copy(update={"dynamic_tools_digest": "0" * 64})
    elif fault == "boundary_binding":
        boundary = boundary.model_copy(update={"callback_binding_digest": "0" * 64})
    elif fault == "server":
        invocation = invocation.model_copy(update={"server": "other"})
    elif fault == "tool":
        invocation = invocation.model_copy(update={"tool": "other_tool"})
    elif fault == "hash":
        invocation = invocation.model_copy(update={"tool_sha256": "0" * 64})
    elif fault == "mode":
        invocation = ManagedHostInvocation(
            mode="turn",
            dynamic_tools_digest=dynamic_pair["treatment_binding_digest"],
        )
    else:
        invocation = _treatment_invocation(dynamic_pair["control_binding_digest"])
        boundary = dynamic_pair["control_boundary"]
        available = False

    with pytest.raises(ConfigurationError):
        require_dynamic_candidate_target(
            _invocation_spec("faulty", invocation),
            boundary,
            expected,
            available=available,
        )


@pytest.mark.parametrize("wrong_target", [False, True])
def test_current_differential_verifier_joins_candidate_access_to_invocation(
    dynamic_pair, monkeypatch, wrong_target
):
    """Exercise the verifier's new target-check call after real dynamic access checks.

    The broader execution-backed conformance validator is tested separately; this
    fixture isolates the differential verifier's candidate-access and invocation
    linkage while retaining the actual reviewed declaration and probe records.
    """
    from aeep.assessment import boundary as boundary_module
    from aeep.assessment import models as assessment_models

    repository = dynamic_pair["repository"]
    expected = dynamic_pair["expected"]
    shared_digest = repository.put(
        "definition", "dynamic-shared-definition", SharedDefinition(purpose="synthetic shared tools")
    )
    repository.review(shared_digest)
    expected = expected.model_copy(update={"shared_definition_digest": shared_digest})

    control_boundary = _boundary(
        repository,
        expected=expected,
        worker_digest=CONTROL_WORKER,
        callback_binding_digest=dynamic_pair["control_binding_digest"],
        effective_inventory=expected.control_inventory,
        available=False,
    )
    treatment_boundary = _boundary(
        repository,
        expected=expected,
        worker_digest=TREATMENT_WORKER,
        callback_binding_digest=dynamic_pair["treatment_binding_digest"],
        effective_inventory=expected.treatment_inventory,
        available=True,
    )
    control_ref = repository.put(
        "boundary_conformance", "dynamic-control-boundary", control_boundary
    )
    treatment_ref = repository.put(
        "boundary_conformance", "dynamic-treatment-boundary", treatment_boundary
    )
    differential = DifferentialConformance(
        definition=expected,
        control_conformance_digest=control_ref,
        treatment_conformance_digest=treatment_ref,
    )
    differential_ref = repository.put(
        "differential_conformance", "dynamic-pair-conformance", differential
    )

    control_spec = _invocation_spec(
        "control",
        ManagedHostInvocation(
            mode="turn",
            dynamic_tools_digest=dynamic_pair["control_binding_digest"],
        ),
    )
    treatment_spec = _invocation_spec(
        "treatment",
        _treatment_invocation(
            dynamic_pair["treatment_binding_digest"],
            tool_sha256=("0" * 64 if wrong_target else None),
        ),
    )
    mapping = SimpleNamespace(subjects=[treatment_spec, control_spec])
    monkeypatch.setattr(
        assessment_models.ReviewedMapping,
        "model_validate",
        lambda _document: mapping,
    )
    monkeypatch.setattr(boundary_module, "require_conformance", lambda *_args, **_kwargs: None)

    mapping_ref = "dynamic-mapping-fixture"
    repository.put("mapping", mapping_ref, MappingFixture(label="synthetic linkage only"))
    environment = SimpleNamespace(
        differential_conformance_digest=differential_ref,
        conformance_digests={"control": control_ref, "treatment": treatment_ref},
    )
    plan = SimpleNamespace(
        comparison=SimpleNamespace(
            experiment=SimpleNamespace(environment=expected, stage="qualification")
        ),
        baseline_id="control",
        candidate_id="treatment",
        mapping_digest=mapping_ref,
    )

    if wrong_target:
        with pytest.raises(ConfigurationError, match="does not target the reviewed"):
            require_differential(repository, environment, plan)
    else:
        require_differential(repository, environment, plan)


@pytest.mark.parametrize(
    "change",
    [
        {"binding_digest": "0" * 64},
        {"dynamic_inventory": {}},
        {"declaration_digest": "0" * 64},
        {"declaration_acknowledged": False},
        {"active_policy": {"profile_matches": True, "approval_never": False, "cwd_matches": True}},
        {"model_tool_exposure": "visible"},
        {"model_turns": 1},
    ],
)
def test_declaration_observation_rejects_changed_binding_inventory_ack_and_policy(dynamic_pair, change):
    binding = _binding(TREATMENT_WORKER, [COMMON_TOOL, CANDIDATE_TOOL])
    declaration = _declaration(binding) | change

    with pytest.raises(ConfigurationError):
        dynamic_candidate_access_observation(
            dynamic_pair["expected"],
            binding=binding,
            worker=SimpleNamespace(digest=lambda: TREATMENT_WORKER),
            declaration=declaration,
        )


def test_declaration_observation_rejects_wrong_candidate_digest(dynamic_pair):
    binding = _binding(TREATMENT_WORKER, [COMMON_TOOL, CANDIDATE_TOOL])
    expected = _environment(candidate_digest="0" * 64)

    with pytest.raises(ConfigurationError, match="incomplete or changed"):
        dynamic_candidate_access_observation(
            expected,
            binding=binding,
            worker=SimpleNamespace(digest=lambda: TREATMENT_WORKER),
            declaration=_declaration(binding),
        )


@pytest.mark.parametrize("review_state", ["missing", "revoked"])
def test_dynamic_candidate_requires_current_callback_review(dynamic_pair, review_state):
    repository = dynamic_pair["repository"]
    digest = dynamic_pair["treatment_binding_digest"]
    if review_state == "missing":
        with repository.store._immediate_transaction() as connection:
            connection.execute("DELETE FROM assessment_reviews WHERE digest=?", (digest,))
    else:
        repository.review(digest, revoke=True)

    with pytest.raises(ConfigurationError, match="unreviewed or changed"):
        require_candidate_access(
            repository,
            dynamic_pair["treatment_boundary"],
            dynamic_pair["expected"],
            available=True,
        )


def test_dynamic_candidate_rejects_wrong_target_digest(dynamic_pair):
    repository = dynamic_pair["repository"]
    expected = _environment(candidate_digest="0" * 64)
    boundary = _with_probe(
        repository,
        dynamic_pair["treatment_boundary"],
        expected=expected,
        available=True,
    )

    with pytest.raises(ConfigurationError, match="target or availability"):
        require_candidate_access(repository, boundary, expected, available=True)


def test_dynamic_candidate_rejects_false_presence_observation(dynamic_pair):
    repository = dynamic_pair["repository"]
    boundary = _with_probe(
        repository,
        dynamic_pair["treatment_boundary"],
        expected=dynamic_pair["expected"],
        available=True,
        changes={"candidate_available": False},
    )

    with pytest.raises(ConfigurationError, match="does not bind the reviewed candidate"):
        require_candidate_access(repository, boundary, dynamic_pair["expected"], available=True)


def test_dynamic_candidate_rejects_callback_from_another_worker(dynamic_pair):
    repository = dynamic_pair["repository"]
    boundary = _with_probe(
        repository,
        dynamic_pair["treatment_boundary"],
        expected=dynamic_pair["expected"],
        available=True,
        callback_binding_digest=dynamic_pair["control_binding_digest"],
    )

    with pytest.raises(ConfigurationError, match="unreviewed or changed"):
        require_candidate_access(repository, boundary, dynamic_pair["expected"], available=True)


def test_dynamic_candidate_rejects_probe_from_another_worker(dynamic_pair):
    repository = dynamic_pair["repository"]
    boundary = _with_probe(
        repository,
        dynamic_pair["treatment_boundary"],
        expected=dynamic_pair["expected"],
        available=True,
        worker_digest="9" * 64,
    )
    boundary = boundary.model_copy(update={"worker_digest": dynamic_pair["treatment_boundary"].worker_digest})

    with pytest.raises(ConfigurationError, match="exact worker"):
        require_candidate_access(repository, boundary, dynamic_pair["expected"], available=True)


def test_dynamic_candidate_requires_exact_effective_inventory_and_unique_probe(dynamic_pair):
    repository = dynamic_pair["repository"]
    expected = dynamic_pair["expected"]
    treatment = dynamic_pair["treatment_boundary"]
    extra = {**treatment.effective_inventory, "dynamic:workbook:unreviewed": "a" * 64}
    with pytest.raises(ConfigurationError, match="effective tool inventory"):
        require_candidate_access(
            repository,
            treatment.model_copy(update={"effective_inventory": extra}),
            expected,
            available=True,
        )

    with pytest.raises(ConfigurationError, match="availability probe"):
        require_candidate_access(
            repository,
            treatment.model_copy(update={"probe_digests": treatment.probe_digests * 2}),
            expected,
            available=True,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"candidate_paths": ["/opt/candidate"]},
        {"candidate_aliases": ["candidate-alias"]},
        {"candidate_inventory": {"dynamic:workbook:other": "a" * 64}},
    ],
)
def test_dynamic_candidate_rejects_mixed_or_inconsistent_physical_access(change):
    original = _environment().model_dump(mode="json")
    with pytest.raises(ValidationError):
        DifferentialEnvironment.model_validate({**original, **change})


def test_legacy_differential_environment_serialization_is_byte_stable():
    legacy_record = json.loads(
        (Path(__file__).with_name("legacy-experiment-v1-f55.json")).read_text()
    )
    legacy_document = legacy_record["environment"]
    environment = DifferentialEnvironment.model_validate(legacy_document)
    expected_bytes = json.dumps(legacy_document, separators=(",", ":"))

    assert environment.model_dump_json() == expected_bytes
    assert "candidate_dynamic_tools" not in environment.model_dump_json()
    assert DifferentialEnvironment.model_validate_json(expected_bytes).model_dump_json() == expected_bytes


@pytest.mark.parametrize("available", [False, True])
def test_legacy_physical_candidate_probe_contract_remains_exact(tmp_path, available):
    store = ReceiptStore(tmp_path / f"legacy-{available}.db")
    repository = AssessmentRepository(store)
    try:
        expected = DifferentialEnvironment(
            shared_definition_digest="1" * 64,
            control_inventory={"python": "2" * 64},
            treatment_inventory={"python": "2" * 64, "plugin": "3" * 64},
            candidate_inventory={"plugin": "3" * 64},
            candidate_paths=["/opt/plugin"],
        )
        inventory = expected.treatment_inventory if available else expected.control_inventory
        probe = BoundaryProbe(
            probe_id="legacy-candidate-access",
            name="candidate_access",
            implementation_digest="4" * 64,
            worker_digest="8" * 64,
            execution_evidence_digest="6" * 64,
            observed={
                "definition_digest": content_digest(expected),
                "candidate_available": available,
            },
        )
        probe_digest = repository.put("boundary_probe", probe.probe_id, probe)
        boundary = BoundaryConformance(
            schema_version="assessment.boundary-conformance.v2",
            conformance_id="legacy-physical",
            source_digest="7" * 64,
            worker_digest="8" * 64,
            image_digest="sha256:" + "9" * 64,
            binary_digest="a" * 64,
            adapter="fixture",
            adapter_version="1",
            effective_policy_digest="b" * 64,
            reviewed_inventory_digest=content_digest(inventory),
            identity_digest="c" * 64,
            enforcement_definition_digest="d" * 64,
            advertised_tools=list(inventory),
            permitted_tools=list(inventory),
            used_tools=[],
            probe_digests=[probe_digest],
            configuration_digest="e" * 64,
            effective_inventory=inventory,
        )

        require_candidate_access(repository, boundary, expected, available=available)
    finally:
        store.close()
