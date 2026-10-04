"""Prepare fresh inert B worker-component requests; starts no worker or model."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.assessment.identity import file_digest, runtime_dependencies, verify_dependencies
from aeep.assessment.models import (
    AssessmentEnvironment, AssessmentScopeAmendment, AssessmentSubject,
    ConformanceProbeRequest, RecipeRuntimeBinding, content_digest,
)
from aeep.assessment.verification import verification_source_digest
from aeep.assessment.workbook import workbook_recipe
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_dynamic_tools import CodexDynamicTools
from aeep.errors import ConfigurationError
from aeep.hosts.codex_pair_inspection import ComposedPairDefinition
from aeep.hosts.codex_sandbox import NativeSandboxConfig, native_backend_digest
from aeep.hosts.workers import ManagedWorkerBinding, binding_from_config, validate_worker_pair
from aeep.models import Manifest, StrictModel

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
PROFILE = OUT / "b-current-profile-v2.json"
PROFILE_SHA256 = "28ed2a514083beda4ef3fc1fbcfa6320f5fabe2b8dcde74dddac7d7bb489c79a"
SETUP_REVIEW = OUT / "b-native-setup-v3-review.json"
SETUP_REVIEW_SHA256 = "ab4f78de528080b8684d8d608786d15a5b8aa616755d7f9033957ac0c44ef7b5"
SETUP_RESULT = OUT / "b-native-setup-v3-result.json"
SETUP_RESULT_SHA256 = "45f2344b74181d79ca284c8d3d3adc3d8d73a3c9edd1ccc51ef6993ed2968752"
COLLECTOR = OUT / "b-composed-worker-collector-v2.py"
PREPARED = OUT / "b-worker-components-preparation-v2.json"


class DynamicDefinition(StrictModel):
    namespace: str
    tools: list[dict]
    identity: dict
    max_calls: int
    timeout_seconds: float


async def forbidden_call(_name, _arguments):
    raise ConfigurationError("zero-turn component inspection has no task-call authority")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_map(values):
    return {content_digest(value): value.model_dump(mode="json") for value in values}


def build(profile_sha256: str, setup_review_sha256: str) -> dict:
    if verification_source_digest(ROOT) != SOURCE:
        raise ValueError("current source differs from the reviewed B pin")
    if (profile_sha256 != PROFILE_SHA256 or setup_review_sha256 != SETUP_REVIEW_SHA256
            or sha(PROFILE) != PROFILE_SHA256 or sha(SETUP_REVIEW) != SETUP_REVIEW_SHA256
            or sha(SETUP_RESULT) != SETUP_RESULT_SHA256):
        raise ValueError("exact current profile and setup review hashes are required")
    profile = json.loads(PROFILE.read_text())
    setup_review = json.loads(SETUP_REVIEW.read_text())
    setup = json.loads(SETUP_RESULT.read_text())
    if (profile.get("source_digest") != SOURCE
            or setup.get("setup_complete") is not True
            or setup.get("operation_settled") is not True
            or setup.get("review_sha256") != setup_review_sha256
            or profile.get("native_setup_result_sha256") != SETUP_RESULT_SHA256
            or profile.get("native_project") != setup.get("project")
            or profile.get("callback_documents_by_role") != setup.get("callback_documents_by_role")
            or any(setup.get(key) != 0 for key in ("model_turns", "task_calls", "worker_launches"))):
        raise ValueError("fresh settled zero-turn B setup and assembled profile are required")
    setup_request = setup_review.get("request", {})
    if (setup_review.get("source_digest") != SOURCE
            or setup_review.get("request_digest") != content_digest(setup_request)
            or setup_request.get("authorization_id") != "onboarding"):
        raise ValueError("exact existing onboarding setup request is required")

    loader = importlib.util.spec_from_file_location("aeep_b_component_collector", COLLECTOR)
    collector = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(collector)

    component = collector.WorkerComponentDefinition.model_validate(profile["component"])
    if content_digest(component) != profile.get("component_digest"):
        raise ValueError("assembled component digest differs")
    composed = ComposedPairDefinition.model_validate(component.composed)
    profile_callbacks = profile.get("callback_documents_by_role")
    if not isinstance(profile_callbacks, dict) or set(profile_callbacks) != {"control", "treatment"}:
        raise ValueError("fresh two-role callback documents are required")

    native_manifest = Path(profile["native_project"]).resolve() / "aeep.json"
    if native_manifest.is_symlink() or not native_manifest.is_file():
        raise ValueError("actual protected native project manifest is unavailable")
    manifest = Manifest.model_validate_json(native_manifest.read_text())
    manifest_specs = {item.id: item for item in manifest.executors}
    callbacks = {}
    workers = {}
    for role in ("control", "treatment"):
        selected = getattr(component, role)
        worker = binding_from_config(selected.managed_host_config().managed_worker)
        if worker is None:
            raise ValueError("selected B role has no managed worker")
        validate = profile_callbacks[role]
        document = DynamicDefinition.model_validate(validate)
        digest = content_digest(document)
        if digest != composed.callback_bindings.get(worker.digest()):
            raise ValueError("callback document differs from assembled current worker binding")
        identity = document.identity
        native = {key: manifest_specs[key] for key in identity["executor_fingerprints"] if key in manifest_specs}
        if ({key: executor_fingerprint(value) for key, value in native.items()} != identity["executor_fingerprints"]
                or any(key not in manifest_specs for key in identity["executor_fingerprints"])):
            raise ValueError("actual native manifest differs from the reviewed callback scope")
        backends = {}
        for name, child in native.items():
            config = NativeSandboxConfig.model_validate(child.config.get("native_sandbox", {}))
            config.validate_single_process()
            config.argv([])
            backends[name] = native_backend_digest(config)
        from aeep.hosts.codex_invocation import contract_digest
        if (contract_digest(backends) != identity["native_backend_digest"]
                or identity["implementation_digest"] != CodexDynamicTools.implementation_digest()
                or identity["worker_digest"] != worker.digest()):
            raise ValueError("callback implementation, worker or native backend differs")
        binding = CodexDynamicTools(**document.model_dump(mode="json"), call=forbidden_call,
                                    check=lambda digest=digest: digest)
        if binding.digest != digest:
            raise ValueError("callback binding digest differs from the actual operator declaration")
        callbacks[role] = (document, binding)
        workers[role] = worker
    validate_worker_pair(workers["control"], workers["treatment"])
    if (workers["control"].image != workers["treatment"].image
            or workers["control"].reviewed_files != workers["treatment"].reviewed_files):
        raise ValueError("B roles must retain the same physical Spreadsheets image and file")

    dependencies = runtime_dependencies()
    dependencies[str(COLLECTOR.resolve())] = file_digest(COLLECTOR)
    verify_dependencies(dependencies)
    runtime = RecipeRuntimeBinding(dependencies=dependencies)
    runtime_digest = content_digest(runtime)
    pair_digest = content_digest(composed)
    component_digest = content_digest(component)
    environment = AssessmentEnvironment(
        environment_id="b-worker-component-" + component_digest[:16],
        kind="codex_sandbox",
        identity={"purpose": "paired zero-turn B worker component observations",
                  "component_digest": component_digest,
                  "control_worker_digest": workers["control"].digest(),
                  "treatment_worker_digest": workers["treatment"].digest()},
    )
    environment_digest = content_digest(environment)
    subject_digest = setup_request["subject_digest"]
    recipe_digest = setup_request["recipe_digest"]
    setup_definitions = setup_review.get("definitions", {})
    subject = AssessmentSubject.model_validate(setup_definitions[subject_digest])
    recipe = workbook_recipe()
    if content_digest(subject) != subject_digest or content_digest(recipe) != recipe_digest:
        raise ValueError("existing setup subject or workbook recipe changed")

    records: list[dict] = []
    definitions: dict[str, dict] = {}

    def add(kind: str, identity: str, value):
        digest = content_digest(value)
        records.append({"kind": kind, "identity": identity, "value": value.model_dump(mode="json")})
        definitions[digest] = value.model_dump(mode="json")
        return digest

    add("subject", subject.subject_id, subject)
    add("recipe", recipe.recipe_id, recipe)
    add("environment", environment.environment_id, environment)
    add("probe_runtime", runtime_digest, runtime)
    add("composed_pair_definition", pair_digest, composed)
    add("composed_worker_component", component_digest, component)
    add("b_shared_spreadsheets_definition", content_digest(component.spreadsheets), component.spreadsheets)
    for role in ("control", "treatment"):
        document, _binding = callbacks[role]
        add("codex_dynamic_tools", content_digest(document), document)

    request_values = []
    reviewed_digests = [environment_digest, runtime_digest, pair_digest, component_digest,
                        content_digest(component.spreadsheets), composed.differential.shared_definition_digest,
                        *(content_digest(item[0]) for item in callbacks.values())]
    for role in ("control", "treatment"):
        selected = getattr(component, role)
        binding_digest = composed.callback_bindings[workers[role].digest()]
        probe_digests = []
        document, binding = callbacks[role]
        for name, expected in collector.expected_component_probes(component, role, binding).items():
            probe = BoundaryProbeDefinition(name=name, executor=selected, expected=expected)
            probe_digests.append(add("boundary_probe_definition", content_digest(probe), probe))
        mapping = BoundaryProbeDefinition(name="worker_pair_inspection", executor=selected,
            expected={"component_digest": component_digest})
        mapping_digest = add("boundary_probe_definition", content_digest(mapping), mapping)
        definition_digests = list(dict.fromkeys([
            subject_digest, recipe_digest, environment_digest, runtime_digest, pair_digest,
            component_digest, content_digest(component.spreadsheets),
            composed.differential.shared_definition_digest, binding_digest,
            mapping_digest, *probe_digests,
        ]))
        request = ConformanceProbeRequest(
            schema_version="assessment.conformance-request.v4",
            subject_digest=subject_digest, recipe_digest=recipe_digest,
            mapping_digest=mapping_digest, environment_digest=environment_digest,
            authorization_id=setup_request["authorization_id"],
            definition_digests=definition_digests, worker_digest=workers[role].digest(),
            executable_dependencies=dependencies, operation="composed_pair_inspection",
            pair_definition_digest=pair_digest, composed_model_turns=0,
        )
        add("conformance_request", request.plan_id, request)
        request_values.append(request.model_dump(mode="json"))
        reviewed_digests.extend([mapping_digest, *probe_digests])
    reviewed_digests = list(dict.fromkeys(reviewed_digests))
    amendment = AssessmentScopeAmendment(
        authorization_id=setup_request["authorization_id"],
        authorization_digest=setup_review["amendment"]["authorization_digest"],
        subject_digests=[subject_digest], recipe_digests=[recipe_digest],
        environment_digests=[environment_digest], reviewed_digests=reviewed_digests,
    )
    return {
        "schema_version": "luna.b-worker-component-preparation.v1",
        "source_digest": SOURCE,
        "inputs": {str(path): sha(path) for path in (PROFILE, SETUP_REVIEW, SETUP_RESULT, COLLECTOR, native_manifest)},
        "component_digest": component_digest, "pair_definition_digest": pair_digest,
        "shared_physical_inventory_observed": False,
        "requests": request_values, "request_ids": [item["plan_id"] for item in request_values],
        "records": records, "definitions": definitions,
        "amendment": amendment.model_dump(mode="json"),
        "maximum_operations": 2, "maximum_model_turns": 0,
        "maximum_reserved_seconds": 480, "cash_ceiling_usd": 0,
        "component_evidence_only": True, "full_conformance": False,
        "qualification": False, "execution_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-inert", action="store_true")
    parser.add_argument("--profile-sha256", required=True)
    parser.add_argument("--setup-review-sha256", required=True)
    args = parser.parse_args()
    if not args.prepare_inert or PREPARED.exists():
        raise SystemExit("INERT: use --prepare-inert with fresh inputs; existing preparation is preserved")
    value = build(args.profile_sha256, args.setup_review_sha256)
    with PREPARED.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"preparation": str(PREPARED), "sha256": sha(PREPARED),
                      "request_ids": value["request_ids"], "execution_authorized": False}))


if __name__ == "__main__":
    main()
