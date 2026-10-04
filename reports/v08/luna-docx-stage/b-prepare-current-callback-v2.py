"""Prepare a fresh one-turn B callback request; import performs no work."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
PROFILE = OUT / "b-current-profile-v2.json"
PROFILE_SHA256 = "28ed2a514083beda4ef3fc1fbcfa6320f5fabe2b8dcde74dddac7d7bb489c79a"
COMPONENT_PREPARATION = OUT / "b-worker-components-preparation-v2.json"
COMPONENT_RESULT = OUT / "b-worker-components-v2-result.json"
COMPONENT_RESULT_SHA256 = "0552cf86620985194c5bd9d1252e88819667730ff9004efc1b82510b98696379"
COMPONENT_TERMINAL_AUDIT = OUT / "b-worker-components-terminal-audit.json"
COMPONENT_TERMINAL_AUDIT_SHA256 = "81ca6e006016204a07977bd137066a2352311839664cf500f9859ac27b49e60a"
SETUP_RESULT = OUT / "b-native-setup-v3-result.json"
SETUP_RESULT_SHA256 = "45f2344b74181d79ca284c8d3d3adc3d8d73a3c9edd1ccc51ef6993ed2968752"
SETUP_REVIEW = OUT / "b-native-setup-v3-review.json"
SETUP_REVIEW_SHA256 = "ab4f78de528080b8684d8d608786d15a5b8aa616755d7f9033957ac0c44ef7b5"
PROXY_LIFECYCLE_RESULT = OUT / "b-worker-proxy-lifecycle-v3-result.json"
PROXY_LIFECYCLE_SHA256 = "1153138d250c32d7720852561936bc0a6d3d5a06293203fe4de444a739cdc5e5"
CAPACITY_REQUEST = OUT / "b-treatment-capacity-request.json"
CAPACITY_REVIEW = OUT / "b-treatment-capacity-review.json"
CAPACITY_RESULT = OUT / "b-treatment-capacity-result.json"
CAPACITY_PREPARER = OUT / "b-prepare-treatment-capacity.py"
CAPACITY_RUNNER = OUT / "b-run-treatment-capacity.py"
PRODUCER = OUT / "b-native-workbook-producer-final.py"
COMPOSITION = ROOT / "reports/v08/original-three-way-profile/native-dynamic-operator-composition.py"
FIXTURE = ROOT / "integrations/assessment-runtime/workbook-grader-fixtures.json"
FIXTURE_SHA256 = "e1342eb43a3daac7ef1dd59ab121d4b1e4f77d07ab8595e4639fc5b8b7c7e5be"
FIXTURE_INPUT_DIGEST = "f7ef188dad768538b171d56cdf655801a45489c6fed6d88b8257284a54520beb"
CANONICAL_MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
CANONICAL_MANIFEST_SHA256 = "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb"
CANONICAL_STORE = ROOT / ".aeep/live-review-v3"
NATIVE_BINARY = Path("/Users/edwintse/.codex/packages/standalone/releases/0.154.0-aarch64-apple-darwin/bin/codex")
NATIVE_BINARY_SHA256 = "4f85982624b3898c8991cb80c0981b2aa71070e3537046c9a95950318a95afcc"
PYTHON_RUNTIME = Path("/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3")
PYTHON_RUNTIME_SHA256 = "5ccd02f7849086e9314db5778ba9085c10a7dd3879c949626f2cf838294c7325"
EXPECTED_WORKER = "19027f56cdc99fc9b728dc2bf7af597f33c6a0d8f4b5d71d19739aa512a56df0"
EXPECTED_COMPONENT = "5438e3aae178909d6d7c765b1590c05308a343d26e8c467097435ba1b1149e8d"
PREPARATION = OUT / "b-current-callback-preparation-v2.json"
PERSISTENCE_REVIEW = OUT / "b-current-callback-persistence-review.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _first_json_value(stream) -> Any:
    """Decode one JSON value by streaming; never load the fixture's later rows."""
    decoder = json.JSONDecoder()
    prefix = ""
    while True:
        char = stream.read(1)
        if not char:
            raise ValueError("fixture ended before its first record")
        if not char.isspace() and char != "[":
            prefix = char
            break
    if prefix != "{":
        raise ValueError("first public fixture record must be an object")
    # The fixture's first key is pinned to `input`; decode just its value.
    key_text = ""
    while True:
        char = stream.read(1)
        if not char:
            raise ValueError("fixture first key is incomplete")
        key_text += char
        try:
            stripped_key = key_text.lstrip()
            key, end = decoder.raw_decode(stripped_key)
            if stripped_key[end:].strip() == "":
                break
        except json.JSONDecodeError:
            continue
    if key != "input":
        raise ValueError("first fixture field must be input; refusing to inspect expected output")
    while True:
        char = stream.read(1)
        if not char:
            raise ValueError("fixture input delimiter is missing")
        if not char.isspace():
            if char != ":":
                raise ValueError("fixture input field is malformed")
            break
    while True:
        char = stream.read(1)
        if not char:
            raise ValueError("fixture input value is missing")
        if not char.isspace():
            first = char
            break
    value_text = first
    if first in "[{":
        depth = 1
        in_string = False
        escaped = False
        while depth:
            char = stream.read(1)
            if not char:
                raise ValueError("fixture input value is incomplete")
            value_text += char
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char in "[{":
                depth += 1
            elif char in "]}":
                depth -= 1
    else:
        raise ValueError("public fixture input must be an object")
    value, end = decoder.raw_decode(value_text)
    if value_text[end:].strip() or not isinstance(value, dict):
        raise ValueError("first public fixture input is malformed")
    return value


def _fixture_input() -> dict[str, Any]:
    # Only the first `input` property is parsed. The expected output and later
    # fixture records are neither decoded nor copied into the preparation.
    with FIXTURE.open("r", encoding="utf-8") as stream:
        return _first_json_value(stream)


def _capacity_review(review_sha256: str, result_sha256: str) -> dict[str, Any]:
    for path in (CAPACITY_REQUEST, CAPACITY_REVIEW, CAPACITY_RESULT, CAPACITY_PREPARER, CAPACITY_RUNNER):
        if not path.is_file():
            raise ValueError("fresh same-worker capacity request, review, result or runner is missing")
    review = json.loads(CAPACITY_REVIEW.read_text())
    result = json.loads(CAPACITY_RESULT.read_text())
    if (_sha(CAPACITY_REVIEW) != review_sha256 or _sha(CAPACITY_RESULT) != result_sha256
            or _sha(CAPACITY_REQUEST) != review.get("request_file_sha256")):
        raise ValueError("fresh capacity request/result hashes do not match the supplied pins")
    if (review.get("prepare_script_sha256") != _sha(CAPACITY_PREPARER)
            or review.get("runner_sha256") != _sha(CAPACITY_RUNNER)):
        raise ValueError("capacity preparation/runner differs from its exact reviewed pins")
    if (review.get("source_digest") != SOURCE or review.get("stage") != "capacity_introspection"
            or review.get("worker_digest") != EXPECTED_WORKER or review.get("executor_id") != "b.luna.aeep"
            or review.get("resource_id") != "codex.self" or review.get("method") != "account/rateLimits/read"
            or review.get("maximum_model_turns") != 0 or review.get("maximum_operations") != 1
            or review.get("cash_ceiling_usd") != 0 or review.get("max_age_seconds") != 1800
            or review.get("proxy_lifecycle_owned_here") is not False):
        raise ValueError("capacity preparation scope differs from current B treatment")
    capacity = result.get("capacity")
    if (result.get("status") != "passed" or result.get("source_digest") != SOURCE
            or result.get("stage") != "capacity_introspection" or result.get("worker_digest") != EXPECTED_WORKER
            or result.get("executor_id") != "b.luna.aeep" or result.get("resource_id") not in (None, "codex.self")
            or result.get("profile_sha256") != PROFILE_SHA256
            or result.get("component_result_sha256") != COMPONENT_RESULT_SHA256
            or result.get("request_digest") != review.get("request_digest")
            or result.get("operation_id") != review.get("operation_id")
            or result.get("max_model_turns_reserved") != 0 or result.get("cash_ceiling_usd") != 0
            or result.get("host_receipt_applicable") is not False
            or result.get("cleanup_confirmed") is not True or result.get("source_unchanged") is not True
            or result.get("replay_allowed") is not False or not result.get("worker_process_id")
            or not result.get("operation_start_digest") or not result.get("operation_measurement_digest")
            or not isinstance(capacity, dict) or capacity.get("resource_id") != "codex.self"
            or result.get("capacity_digest") != capacity.get("canonical_digest")):
        raise ValueError("completed same-worker 0-turn capacity evidence differs")
    observed = datetime.fromisoformat(str(capacity["observed_at"]).replace("Z", "+00:00"))
    age = (datetime.now(UTC) - observed.astimezone(UTC)).total_seconds()
    if not 0 <= age <= 1800:
        raise ValueError("same-worker capacity observation is outside its reviewed 30-minute window")
    if not capacity.get("windows") or any(item.get("exhausted") is not False for item in capacity["windows"]):
        raise ValueError("capacity windows are absent, exhausted or unknown")
    return {
        "schema_version": "assessment.b-current-callback-capacity-binding.v1",
        "source_digest": SOURCE,
        "profile_sha256": PROFILE_SHA256,
        "component_result_sha256": COMPONENT_RESULT_SHA256,
        "request_file_sha256": _sha(CAPACITY_REQUEST),
        "review_sha256": review_sha256,
        "result_sha256": result_sha256,
        "request_digest": result["request_digest"],
        "operation_id": result["operation_id"],
        "capacity_digest": result["capacity_digest"],
        "worker_digest": EXPECTED_WORKER,
        "resource_id": "codex.self",
        "observed_at": capacity["observed_at"],
        "max_age_seconds": 1800,
        "cleanup_confirmed": True,
        "source_unchanged": True,
        "model_turns": 0,
        "cash_ceiling_usd": 0,
    }


def build(*, capacity_review_sha256: str, capacity_result_sha256: str) -> dict[str, Any]:
    from aeep.assessment.boundary import BoundaryProbeDefinition
    from aeep.assessment.identity import file_digest, runtime_dependencies
    from aeep.assessment.models import ConformanceProbeRequest, content_digest
    from aeep.assessment.verification import verification_source_digest
    from aeep.hosts.codex_dynamic_tools import CodexDynamicTools
    from aeep.hosts.codex_invocation import contract_digest
    from aeep.hosts.codex_pair_inspection import ComposedPairDefinition
    from aeep.hosts.workers import binding_from_config
    from aeep.models import ActionConstraints, ActionRequest, SideEffect, StrictModel, new_id

    class FixtureBinding(StrictModel):
        schema_version: str = "assessment.b-current-callback-fixture-binding.v1"
        source_path: str
        source_sha256: str
        record_index: int = 0
        input_digest: str
        input_fields: list[str]
        public_literal: bool = True
        expected_output_read: bool = False
        later_records_read: bool = False

    if verification_source_digest(ROOT) != SOURCE:
        raise ValueError("frozen source changed")
    expected_files = {
        PROFILE: PROFILE_SHA256,
        COMPONENT_RESULT: COMPONENT_RESULT_SHA256,
        COMPONENT_TERMINAL_AUDIT: COMPONENT_TERMINAL_AUDIT_SHA256,
        SETUP_RESULT: SETUP_RESULT_SHA256,
        SETUP_REVIEW: SETUP_REVIEW_SHA256,
        PROXY_LIFECYCLE_RESULT: PROXY_LIFECYCLE_SHA256,
        COMPONENT_PREPARATION: "478b6a11c660dd2e2b5cc6e6d6f9bdef51580fd8d5657b9dc9f8cd20da69192d",
        NATIVE_BINARY: NATIVE_BINARY_SHA256,
        PYTHON_RUNTIME: PYTHON_RUNTIME_SHA256,
        COMPOSITION: "d158ed54641e062f2a2d484fd0f5ebc212fccaee25e4186b56ccf1a3395d9c8a",
        PRODUCER: "4d5db1fd761882f90bbaff5d1a6c392e2bab185a248f4a981399f95ee8aa539d",
    }
    if PREPARATION.exists():
        raise ValueError("callback preparation already exists; do not replace or replay it")
    if any(not path.is_file() or _sha(path) != expected for path, expected in expected_files.items()):
        raise ValueError("a current profile, component, native setup or helper pin changed")
    profile = json.loads(PROFILE.read_text())
    component = json.loads(COMPONENT_RESULT.read_text())
    component_prep = json.loads(COMPONENT_PREPARATION.read_text())
    setup = json.loads(SETUP_RESULT.read_text())
    proxy = json.loads(PROXY_LIFECYCLE_RESULT.read_text())
    if (profile.get("source_digest") != SOURCE or profile.get("component_digest") != EXPECTED_COMPONENT
            or profile.get("selected_worker_digest") != EXPECTED_WORKER
            or component.get("source_digest") != SOURCE or component.get("source_unchanged") is not True
            or component.get("component_digest") != EXPECTED_COMPONENT
            or component.get("component_probes_match") is not True
            or component.get("component_evidence_only") is not True
            or component.get("full_conformance") is not False
            or component.get("qualification") is not False or component.get("model_turns") != 0
            or component.get("workers", {}).get("treatment", {}).get("worker_digest") != EXPECTED_WORKER
            or component.get("workers", {}).get("treatment", {}).get("cleanup_confirmed") is not True
            or component.get("workers", {}).get("treatment", {}).get("xhigh_available") is not True
            or component.get("workers", {}).get("treatment", {}).get("luna_present_once") is not True
            or component_prep.get("component_digest") != EXPECTED_COMPONENT
            or component_prep.get("source_digest") != SOURCE or component_prep.get("maximum_model_turns") != 0
            or setup.get("setup_complete") is not True or setup.get("operation_settled") is not True
            or any(setup.get(key) != 0 for key in ("model_turns", "task_calls", "worker_launches"))
            or setup.get("review_sha256") != SETUP_REVIEW_SHA256
            or proxy.get("source_digest") != SOURCE or proxy.get("worker_component_passed") is not True
            or proxy.get("proxy_restored_stopped") is not True or proxy.get("cleanup_operation_settled") is not True
            or proxy.get("source_unchanged") is not True or proxy.get("model_turns") != 0):
        raise ValueError("current B component, setup or settled proxy lifecycle evidence is not valid")

    pair = ComposedPairDefinition.model_validate(profile["component"]["composed"])
    treatment = pair.treatment
    config = treatment.managed_host_config()
    worker = binding_from_config(config.managed_worker)
    if (worker is None or worker.digest() != EXPECTED_WORKER or treatment.id != "b.luna.aeep"
            or treatment.capability != "assessment.workbook@1" or config.approval_ceiling != SideEffect.READ
            or treatment.side_effect != SideEffect.READ or treatment.estimate.cash.upper_bound_usd != 0
            or config.model_constraints.allowed_model_ids != ("gpt-6-luna",)
            or config.reasoning_efforts != ("xhigh",) or config.store_prompt or config.store_output
            or config.invocation is None or config.invocation.mode != "dynamic_tool"
            or config.invocation.exposure != "required" or config.invocation.server != "workbook"
            or config.invocation.tool != "aeep_recipe_f468b36bc594"):
        raise ValueError("treatment no longer matches the exact current Luna/xhigh profile")
    setup_project = Path(setup["project"]).resolve()
    if profile.get("native_project") != str(setup_project):
        raise ValueError("current profile and fresh native setup project differ")
    expiry = datetime.fromisoformat(str(setup["scope_expires_at"]).replace("Z", "+00:00"))
    if expiry.astimezone(UTC) <= datetime.now(UTC):
        raise ValueError("current project task scope is expired")
    native_manifest = setup_project / "aeep.json"
    if native_manifest.is_symlink() or not native_manifest.is_file():
        raise ValueError("current native task manifest is unavailable")
    native = json.loads(native_manifest.read_text())
    if native.get("database") != str(setup_project / ".aeep/state.db"):
        raise ValueError("native setup database is not the exact project-local state store")

    docs = profile.get("callback_documents_by_role", {})
    callback = docs.get("treatment")
    callback_digest = content_digest(callback)
    if (callback_digest != pair.callback_bindings.get(EXPECTED_WORKER)
            or callback.get("identity", {}).get("worker_digest") != EXPECTED_WORKER
            or callback.get("max_calls") != 1 or callback.get("timeout_seconds") != 10.0
            or callback.get("identity", {}).get("approval_ceiling") != "read"
            or callback.get("identity", {}).get("scope_limits") != {"max_attempts": 1, "max_attempt_seconds": 10.0}
            or callback.get("identity", {}).get("implementation_digest") != CodexDynamicTools.implementation_digest()
            or config.invocation.dynamic_tools_digest != callback_digest):
        raise ValueError("exact one-call READ callback declaration differs from current profile")
    declaration = [tool for tool in callback["tools"] if tool.get("name") == config.invocation.tool]
    if (len(declaration) != 1 or contract_digest(declaration[0]) != config.invocation.tool_sha256
            or callback.get("identity", {}).get("native_backend_digest") != pair.native_backends.get(EXPECTED_WORKER)):
        raise ValueError("treatment callback target/backend is not the exact reviewed declaration")

    fixture_input = _fixture_input()
    if (set(fixture_input) != {"workbook_b64", "task", "variation", "row_bound"}
            or content_digest(fixture_input) != FIXTURE_INPUT_DIGEST
            or len(fixture_input["workbook_b64"]) > config.artifact.max_bytes):
        raise ValueError("first public fixture input differs or exceeds the artifact limit")
    fixture_binding = FixtureBinding(
        source_path=str(FIXTURE.relative_to(ROOT)), source_sha256=FIXTURE_SHA256,
        input_digest=FIXTURE_INPUT_DIGEST, input_fields=sorted(fixture_input),
    )
    fixture_binding_digest = content_digest(fixture_binding)
    template = ActionRequest(
        action_id=new_id("b-callback-action"), capability=treatment.capability, input={},
        policy="balanced", constraints=ActionConstraints(
            max_side_effect=SideEffect.READ, allow_network=True,
            allowed_executor_ids=[treatment.id]),
    )
    action_template_digest = content_digest(template)
    definition = BoundaryProbeDefinition(name="callback_authority", executor=treatment,
        expected={"callback_origin": "native_app_server", "native_callback_observed": True})
    definition_digest = content_digest(definition)
    capacity_binding = _capacity_review(capacity_review_sha256, capacity_result_sha256)
    capacity_binding_digest = content_digest(capacity_binding)

    source_request_value = component_prep["requests"][1]
    source_request = ConformanceProbeRequest.model_validate(source_request_value)
    treatment_evidence = component["workers"]["treatment"]
    if (source_request.worker_digest != EXPECTED_WORKER or source_request.composed_model_turns != 0
            or source_request.plan_id != treatment_evidence.get("request_id")
            or source_request.pair_definition_digest != content_digest(pair)):
        raise ValueError("only the exact completed zero-turn request may supply shared source digests")
    dependencies = runtime_dependencies()
    for path in (Path(__file__).resolve(), PRODUCER, COMPOSITION, PROFILE, COMPONENT_PREPARATION,
                 COMPONENT_RESULT, COMPONENT_TERMINAL_AUDIT, SETUP_REVIEW, SETUP_RESULT,
                 PROXY_LIFECYCLE_RESULT, CAPACITY_PREPARER, CAPACITY_RUNNER,
                 CAPACITY_REQUEST, CAPACITY_REVIEW, CAPACITY_RESULT, native_manifest):
        dependencies[str(path.resolve())] = file_digest(path.resolve())
    request = ConformanceProbeRequest(
        schema_version="assessment.conformance-request.v4",
        plan_id=new_id("conformance_probe"), subject_digest=source_request.subject_digest,
        recipe_digest=source_request.recipe_digest, mapping_digest=source_request.mapping_digest,
        environment_digest=source_request.environment_digest,
        authorization_id=source_request.authorization_id,
        definition_digests=list(dict.fromkeys([
            *source_request.definition_digests, content_digest(pair), callback_digest,
            definition_digest, action_template_digest, fixture_binding_digest, capacity_binding_digest,
        ])),
        worker_digest=EXPECTED_WORKER, executable_dependencies=dependencies,
        operation="composed_pair_inspection", pair_definition_digest=content_digest(pair),
        composed_model_turns=1,
    )
    return {
        "schema_version": "assessment.b-current-callback-preparation.v2",
        "source_digest": SOURCE,
        "profile_path": str(PROFILE.relative_to(ROOT)), "profile_sha256": PROFILE_SHA256,
        "component_result_path": str(COMPONENT_RESULT.relative_to(ROOT)),
        "component_result_sha256": COMPONENT_RESULT_SHA256,
        "component_terminal_audit_sha256": COMPONENT_TERMINAL_AUDIT_SHA256,
        "setup_review_sha256": SETUP_REVIEW_SHA256, "setup_result_sha256": SETUP_RESULT_SHA256,
        "native_manifest_path": str(native_manifest), "native_manifest_sha256": _sha(native_manifest),
        "proxy_lifecycle_result_path": str(PROXY_LIFECYCLE_RESULT.relative_to(ROOT)),
        "proxy_lifecycle_result_sha256": PROXY_LIFECYCLE_SHA256,
        "capacity_request_path": str(CAPACITY_REQUEST.relative_to(ROOT)),
        "capacity_request_sha256": capacity_binding["request_file_sha256"],
        "capacity_review_path": str(CAPACITY_REVIEW.relative_to(ROOT)),
        "capacity_review_sha256": capacity_review_sha256,
        "capacity_result_path": str(CAPACITY_RESULT.relative_to(ROOT)),
        "capacity_result_sha256": capacity_result_sha256,
        "capacity_binding": capacity_binding, "capacity_binding_digest": capacity_binding_digest,
        "worker_digest": EXPECTED_WORKER, "executor_id": treatment.id,
        "model_id": "gpt-6-luna", "reasoning_effort": "xhigh",
        "pair": pair.model_dump(mode="json"), "pair_digest": content_digest(pair),
        "callback_document": callback, "callback_binding_digest": callback_digest,
        "probe_definition": definition.model_dump(mode="json"), "probe_definition_digest": definition_digest,
        "action_template": template.model_dump(mode="json"), "action_template_digest": action_template_digest,
        "fixture_binding": fixture_binding.model_dump(mode="json"),
        "fixture_binding_digest": fixture_binding_digest,
        "fixture_source": "integrations/assessment-runtime/workbook-grader-fixtures.json[0].input",
        "fixture_sha256": FIXTURE_SHA256, "fixture_input_digest": FIXTURE_INPUT_DIGEST,
        "request": request.model_dump(mode="json"), "request_digest": content_digest(request),
        "records_to_store_and_review": [
            {"kind": "boundary_probe_definition", "identity": definition_digest,
             "digest": definition_digest, "value": definition.model_dump(mode="json")},
            {"kind": "composed_callback_action", "identity": action_template_digest,
             "digest": action_template_digest, "value": template.model_dump(mode="json")},
            {"kind": "b_callback_fixture_binding", "identity": fixture_binding_digest,
             "digest": fixture_binding_digest, "value": fixture_binding.model_dump(mode="json")},
            {"kind": "b_callback_capacity_binding", "identity": capacity_binding_digest,
             "digest": capacity_binding_digest, "value": capacity_binding},
            {"kind": "conformance_request", "identity": request.plan_id,
             "digest": content_digest(request), "value": request.model_dump(mode="json")},
        ],
        "executable_dependencies": dependencies,
        "limits": {"operations": 1, "model_turns": 1,
                   "elapsed_seconds": treatment.managed_host_config().timeout_seconds + 5,
                   "cash_usd": 0, "task_calls": 1, "task_call_timeout_seconds": 10.0,
                   "task_scope_attempts": 1},
        "inert_only": True, "persistence_authorized": False,
        "execution_authorized": False, "full_conformance": False,
        "qualification": False, "admission": False, "value_trial": False,
        "payload_policy": "Fixture bytes are parsed only from first input and injected into ephemeral action; no fixture output/later row is decoded; no raw task input/output is written to the preparation or canonical definitions.",
        "proxy_policy": "Use the separately reviewed v3 proxy lifecycle wrapper; this runner never starts or stops the shared proxy.",
    }


async def _persist(review_sha256: str) -> dict[str, Any]:
    from aeep.assessment.models import ConformanceProbeRequest, content_digest
    from aeep.assessment.repository import AssessmentRepository
    from aeep.hosts.codex_pair_inspection import ComposedPairDefinition
    from aeep.models import ActionRequest
    from aeep.router import Router

    if not PREPARATION.is_file() or not PERSISTENCE_REVIEW.is_file() or _sha(PERSISTENCE_REVIEW) != review_sha256:
        raise ValueError("exact separate inert persistence review is required")
    prep_hash = _sha(PREPARATION)
    approval = json.loads(PERSISTENCE_REVIEW.read_text())
    bundle = json.loads(PREPARATION.read_text())
    if (approval.get("schema_version") != "assessment.b-current-callback-persistence-review.v1"
            or approval.get("persistence_authorized") is not True
            or approval.get("execution_authorized") is not False
            or approval.get("source_digest") != SOURCE
            or approval.get("preparation_sha256") != prep_hash
            or approval.get("request_digest") != bundle.get("request_digest")):
        raise ValueError("persistence review differs or attempts to authorize execution")
    if _sha(CANONICAL_MANIFEST) != CANONICAL_MANIFEST_SHA256:
        raise ValueError("canonical manifest pin changed")
    router = Router.from_manifest(CANONICAL_MANIFEST)
    try:
        repository = AssessmentRepository(router.store)
        pair = ComposedPairDefinition.model_validate(bundle["pair"])
        callback = repository.get("codex_dynamic_tools", bundle["callback_binding_digest"])
        request = ConformanceProbeRequest.model_validate(bundle["request"])
        if (content_digest(callback) != bundle["callback_binding_digest"]
                or content_digest(pair) != bundle["pair_digest"]):
            raise ValueError("current pair or callback digest changed")
        for kind, identity, digest in (
            ("composed_pair_definition", bundle["pair_digest"], bundle["pair_digest"]),
            ("codex_dynamic_tools", bundle["callback_binding_digest"], bundle["callback_binding_digest"]),
        ):
            existing = repository.get(kind, identity)
            if content_digest(existing) != digest:
                raise ValueError("canonical current composition record differs")
            with router.store._lock:
                reviewed = router.store._connection.execute(
                    "SELECT revoked FROM assessment_reviews WHERE digest=?", (digest,)
                ).fetchone()
            if reviewed is None or reviewed[0]:
                raise ValueError("current pair/callback review is absent or revoked")
        for item in bundle["records_to_store_and_review"]:
            kind, identity, digest = item["kind"], item["identity"], item["digest"]
            with router.store._lock:
                old = router.store._connection.execute(
                    "SELECT digest FROM assessment_records WHERE kind=? AND id=?", (kind, identity)
                ).fetchone()
            if old is not None:
                raise ValueError("one-shot callback record already exists; no replay")
            value = item["value"]
            if kind == "boundary_probe_definition":
                from aeep.assessment.boundary import BoundaryProbeDefinition
                value = BoundaryProbeDefinition.model_validate(value)
            elif kind == "composed_callback_action":
                value = ActionRequest.model_validate(value)
            elif kind == "conformance_request":
                value = request
            else:
                from aeep.models import StrictModel
                class FixtureBinding(StrictModel):
                    schema_version: str
                    source_path: str
                    source_sha256: str
                    record_index: int
                    input_digest: str
                    input_fields: list[str]
                    public_literal: bool
                    expected_output_read: bool
                    later_records_read: bool

                class CapacityBinding(StrictModel):
                    schema_version: str
                    source_digest: str
                    profile_sha256: str
                    component_result_sha256: str
                    request_file_sha256: str
                    review_sha256: str
                    result_sha256: str
                    request_digest: str
                    operation_id: str
                    capacity_digest: str
                    worker_digest: str
                    resource_id: str
                    observed_at: str
                    max_age_seconds: int
                    cleanup_confirmed: bool
                    source_unchanged: bool
                    model_turns: int
                    cash_ceiling_usd: int

                value = (FixtureBinding.model_validate(value)
                         if kind == "b_callback_fixture_binding"
                         else CapacityBinding.model_validate(value))
            if content_digest(value) != digest:
                raise ValueError("prepared one-shot record digest differs")
            repository.put(kind, identity, value)
            repository.review(digest)
        repository.authorize(request)
        return {"status": "persisted_reviewed_inert", "request_id": request.plan_id,
                "request_digest": content_digest(request), "records_reviewed": 5,
                "operations_reserved": 0, "model_turns": 0, "execution_authorized": False}
    finally:
        await router.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-inert", action="store_true")
    parser.add_argument("--profile-sha256", required=True)
    parser.add_argument("--capacity-review-sha256")
    parser.add_argument("--capacity-result-sha256")
    parser.add_argument("--persist-reviewed-sha256")
    args = parser.parse_args()
    if args.prepare_inert and args.persist_reviewed_sha256 is None:
        if args.profile_sha256 != PROFILE_SHA256 or not args.capacity_review_sha256 or not args.capacity_result_sha256:
            raise SystemExit("exact v2 profile and fresh capacity review/result hashes required")
        value = build(capacity_review_sha256=args.capacity_review_sha256,
                      capacity_result_sha256=args.capacity_result_sha256)
        if PREPARATION.exists():
            raise SystemExit("preserve prior preparation; no replacement or replay")
        with PREPARATION.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
        print(json.dumps({"status": "inert_prepared", "path": str(PREPARATION),
                          "sha256": _sha(PREPARATION), "request_id": value["request"]["plan_id"],
                          "model_turns": 0, "persistence_authorized": False,
                          "execution_authorized": False}, sort_keys=True))
        return
    if args.persist_reviewed_sha256 and not args.prepare_inert:
        import asyncio
        result = asyncio.run(_persist(args.persist_reviewed_sha256))
        print(json.dumps(result, sort_keys=True))
        return
    raise SystemExit("select exactly one explicit --prepare-inert or --persist-reviewed-sha256 operation")


if __name__ == "__main__":
    main()
