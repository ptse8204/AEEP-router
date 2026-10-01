"""Finite composed authority preserves old requests and rejects coerced allowances."""
import pytest
from pydantic import ValidationError

from aeep.assessment.models import ConformanceProbeRequest

pytestmark = pytest.mark.assessment_contract


def request(**changes):
    value = dict(plan_id="fixed", subject_digest="a"*64, recipe_digest="b"*64,
        mapping_digest="c"*64, environment_digest="d"*64, authorization_id="grant",
        definition_digests=["e"*64], worker_digest="f"*64, executable_dependencies={"runtime":"1"*64})
    value.update(changes)
    return value

@pytest.mark.parametrize("turns", [True, False, 0.5, 1.0, "0", "1", -1, 2])
def test_composed_allowance_is_strict(turns):
    with pytest.raises(ValidationError):
        ConformanceProbeRequest.model_validate(request(schema_version="assessment.conformance-request.v4",
            operation="composed_pair_inspection", pair_definition_digest="e"*64, composed_model_turns=turns))

@pytest.mark.parametrize("turns", [0,1])
def test_composed_finite_allowance(turns):
    parsed = ConformanceProbeRequest.model_validate(request(schema_version="assessment.conformance-request.v4",
        operation="composed_pair_inspection", pair_definition_digest="e"*64, composed_model_turns=turns))
    assert parsed.model_dump()["composed_model_turns"] == turns

def test_legacy_request_exact_serialization():
    frozen = request(schema_version="assessment.conformance-request.v1")
    assert ConformanceProbeRequest.model_validate(frozen).model_dump(mode="json") == frozen

def test_old_request_cannot_gain_composed_authority():
    with pytest.raises(ValidationError):
        ConformanceProbeRequest.model_validate(request(composed_model_turns=1))
    with pytest.raises(ValidationError):
        ConformanceProbeRequest.model_validate(request(operation="composed_pair_inspection"))


def test_scripted_callback_cannot_supply_full_native_proof():
    from types import SimpleNamespace

    from aeep.errors import ConfigurationError
    from aeep.hosts.codex_pair_inspection import verify_composed_callback
    class Repo:
        def get(self, kind, identity):
            assert kind == "codex_dynamic_tools"
            return {"identity": {}}
    with pytest.raises(ConfigurationError, match="host receipt"):
        verify_composed_callback(Repo(), SimpleNamespace(callback_binding_digest="a"*64, identity_digest="b"*64),
            SimpleNamespace(host_receipt_digest=None), None, None, None)

def test_dynamic_receipt_metadata_retains_only_safe_scalars():
    from aeep.router import Router
    supplied = {"dynamic_tools_digest": "a"*64, "dynamic_tool_calls": 1,
        "dynamic_cleanup_confirmed": True, "dynamic_schema_bytes": 12,
        "dynamic_declaration_bytes": 15, "raw_callback_arguments": {"secret":"payload"}}
    assert Router._safe_receipt_metadata(supplied) == {key:value for key,value in supplied.items()
        if key != "raw_callback_arguments"}


def legacy_boundary():
    return dict(schema_version="assessment.boundary-conformance.v1", conformance_id="old",
        source_digest="1"*64, worker_digest="2"*64, image_digest="sha256:"+"3"*64,
        binary_digest="4"*64, adapter="fixture", adapter_version="1",
        effective_policy_digest="5"*64, reviewed_inventory_digest="6"*64, identity_digest="7"*64,
        enforcement_definition_digest="8"*64, advertised_tools=[], permitted_tools=[], used_tools=[], probe_digests=[])

def test_legacy_boundary_exact_serialization_and_no_composed_upgrade():
    from aeep.assessment.boundary import BoundaryConformance
    frozen=legacy_boundary()
    assert BoundaryConformance.model_validate(frozen).model_dump(mode="json") == frozen
    with pytest.raises(ValidationError):
        BoundaryConformance.model_validate({**frozen, "callback_binding_digest":"a"*64})

@pytest.mark.parametrize("missing", ["configuration_digest", "effective_inventory",
    "callback_binding_digest", "native_backend_digest", "composed_definition_digest"])
def test_composed_boundary_requires_all_exact_bindings(missing):
    from aeep.assessment.boundary import BoundaryConformance
    value={**legacy_boundary(), "schema_version":"assessment.boundary-conformance.v3",
        "configuration_digest":"a"*64, "effective_inventory":{}, "callback_binding_digest":"b"*64,
        "native_backend_digest":"c"*64, "composed_definition_digest":"d"*64}
    value.pop(missing)
    with pytest.raises(ValidationError):
        BoundaryConformance.model_validate(value)
