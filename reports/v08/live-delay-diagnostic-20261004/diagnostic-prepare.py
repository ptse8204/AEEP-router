"""Prepare one inert fresh-input delay diagnostic; import performs no work."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
HISTORY = OUT.parent / "luna-docx-stage"
SOURCE = "e6b71acba487280dfe50057d17379e5994c9113bc651a262935474f656a5dba6"
PROFILE = OUT / "c-current-profile-v2.json"
PROFILE_SHA256 = "ac096d106954d86433f4743333ac7004765a9dbc2db229c9fbecc5efa3db2eb8"
COMPONENT_PREPARATION = OUT / "c-worker-components-preparation-v2.json"
COMPONENT_RESULT = OUT / "c-worker-components-result-v2.json"
COMPONENT_RESULT_SHA256 = None
COMPONENT_TERMINAL_AUDIT = OUT / "c-worker-components-terminal-audit.json"
COMPONENT_TERMINAL_AUDIT_SHA256 = None
SETUP_RESULT = HISTORY / "b-native-setup-v3-result.json"
SETUP_RESULT_SHA256 = "45f2344b74181d79ca284c8d3d3adc3d8d73a3c9edd1ccc51ef6993ed2968752"
SETUP_REVIEW = HISTORY / "b-native-setup-v3-review.json"
SETUP_REVIEW_SHA256 = "ab4f78de528080b8684d8d608786d15a5b8aa616755d7f9033957ac0c44ef7b5"
PROXY_LIFECYCLE_RESULT = OUT / "c-worker-components-v3-proxy-result.json"
PROXY_LIFECYCLE_SHA256 = None
CAPACITY_REQUEST = OUT / "c-treatment-capacity-request.json"
CAPACITY_REVIEW = OUT / "c-treatment-capacity-review.json"
CAPACITY_RESULT = OUT / "c-treatment-capacity-result.json"
CAPACITY_PREPARER = OUT / "c-prepare-treatment-capacity-v1.py"
CAPACITY_RUNNER = OUT / "c-run-treatment-capacity-v1.py"
PRODUCER = HISTORY / "b-native-workbook-producer-final.py"
COMPOSITION = ROOT / "reports/v08/original-three-way-profile/native-dynamic-operator-composition.py"
FIXTURE = OUT / "fresh-input.json"
FIXTURE_SHA256 = "0b1fe315b9fe2abea7715520b3eb7f21cf3b82b1ca07c7f48a876b25e77253d9"
FIXTURE_INPUT_DIGEST = "c7ed4a9fe4dd6cd2b2cf1c0cbf2d994ee3f37a2eb22a731a47acd8edc0c582b2"
CANONICAL_MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
CANONICAL_MANIFEST_SHA256 = "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb"
CANONICAL_STORE = ROOT / ".aeep/live-review-v3"
NATIVE_BINARY = Path("/Users/edwintse/.codex/packages/standalone/releases/0.154.0-aarch64-apple-darwin/bin/codex")
NATIVE_BINARY_SHA256 = "4f85982624b3898c8991cb80c0981b2aa71070e3537046c9a95950318a95afcc"
PYTHON_RUNTIME = Path("/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3")
PYTHON_RUNTIME_SHA256 = "5ccd02f7849086e9314db5778ba9085c10a7dd3879c949626f2cf838294c7325"
EXPECTED_WORKER = "19027f56cdc99fc9b728dc2bf7af597f33c6a0d8f4b5d71d19739aa512a56df0"
EXPECTED_COMPONENT = "bf500fb25b63f78d735fabaf85e1f6ac9ad5ae3e91411fb98f709b805beb225f"
PREPARATION = OUT / "diagnostic-preparation.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


COMPONENT_RESULT_SHA256 = _sha(COMPONENT_RESULT) if COMPONENT_RESULT.is_file() else None
COMPONENT_TERMINAL_AUDIT_SHA256 = _sha(COMPONENT_TERMINAL_AUDIT) if COMPONENT_TERMINAL_AUDIT.is_file() else None
PROXY_LIFECYCLE_SHA256 = _sha(PROXY_LIFECYCLE_RESULT) if PROXY_LIFECYCLE_RESULT.is_file() else None
COMPONENT_PREPARATION_SHA256 = _sha(COMPONENT_PREPARATION) if COMPONENT_PREPARATION.is_file() else None


def _fixture_input() -> dict[str, Any]:
    """Read only the frozen fresh diagnostic input; no fixture/oracle access."""
    if (FIXTURE.is_symlink() or not FIXTURE.is_file() or FIXTURE.stat().st_size > 1_000_000
            or _sha(FIXTURE) != FIXTURE_SHA256):
        raise ValueError("fresh diagnostic input changed or exceeds one megabyte")
    value = json.loads(FIXTURE.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("fresh diagnostic input must be an object")
    return value


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
        raise ValueError("capacity preparation scope differs from current C treatment")
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
            or not isinstance(result.get("elapsed_seconds"), (int, float))
            or not 0 <= result["elapsed_seconds"] <= 60
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
        "schema_version": "assessment.c-current-callback-capacity-binding.v1",
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
        schema_version: str = "assessment.c-current-callback-fixture-binding.v1"
        source_path: str
        source_sha256: str
        record_index: int | None = None
        input_digest: str
        input_fields: list[str]
        public_literal: bool = False
        diagnostic_only: bool = True
        qualification: bool = False
        holdout: bool = False
        data_rows: int = 3
        expected_output_read: bool = False
        later_records_read: bool = False

    class CallbackScopeBinding(StrictModel):
        schema_version: str = "assessment.c-treatment-task-scope-binding.v1"
        scope_id: str
        project_root: str
        manifest_sha256: str
        database_path: str
        database_device: int
        database_inode: int
        preserves_consumed_scope_id: str
        preserves_consumed_scope_digest: str
        executor_id: str
        executor_fingerprint: str
        approval_ceiling: str = "read"
        max_attempts: int = 1
        max_attempt_seconds: float = 10.0
        expires_in_seconds: int = 600
        replaces_or_resets_prior_scope: bool = False

    if verification_source_digest(ROOT) != SOURCE:
        raise ValueError("frozen source changed")
    expected_files = {
        PROFILE: PROFILE_SHA256,
        COMPONENT_RESULT: COMPONENT_RESULT_SHA256,
        COMPONENT_TERMINAL_AUDIT: COMPONENT_TERMINAL_AUDIT_SHA256,
        SETUP_RESULT: SETUP_RESULT_SHA256,
        SETUP_REVIEW: SETUP_REVIEW_SHA256,
        PROXY_LIFECYCLE_RESULT: PROXY_LIFECYCLE_SHA256,
        FIXTURE: FIXTURE_SHA256,
        COMPONENT_PREPARATION: COMPONENT_PREPARATION_SHA256,
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
            or setup.get("source_digest") != "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
            or setup.get("setup_complete") is not True or setup.get("operation_settled") is not True
            or any(setup.get(key) != 0 for key in ("model_turns", "task_calls", "worker_launches"))
            or setup.get("review_sha256") != SETUP_REVIEW_SHA256
            or proxy.get("source_digest") != SOURCE or proxy.get("status") != "passed"
            or proxy.get("inner_result_sha256") != COMPONENT_RESULT_SHA256
            or proxy.get("proxy_restored_stopped") is not True or proxy.get("cleanup_operation_settled") is not True
            or proxy.get("source_unchanged") is not True or proxy.get("model_turns") != 0):
        raise ValueError("current C component, setup or settled proxy lifecycle evidence is not valid")

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
    native_manifest = setup_project / "aeep.json"
    if native_manifest.is_symlink() or not native_manifest.is_file():
        raise ValueError("current native task manifest is unavailable")
    native = json.loads(native_manifest.read_text())
    native_database = setup_project / ".aeep" / "state.db"
    if (native.get("database") != str(native_database) or native_database.is_symlink()
            or not native_database.is_file()):
        raise ValueError("native setup database is not the exact project-local state store")
    native_database_stat = native_database.stat()

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
        raise ValueError("fresh diagnostic input differs or exceeds the artifact limit")
    fixture_binding = FixtureBinding(
        source_path=str(FIXTURE.relative_to(ROOT)), source_sha256=FIXTURE_SHA256,
        input_digest=FIXTURE_INPUT_DIGEST, input_fields=sorted(fixture_input),
    )
    fixture_binding_digest = content_digest(fixture_binding)
    template = ActionRequest(
        action_id=new_id("c-callback-action"), capability=treatment.capability, input={},
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
    setup_scope_id = setup.get("scope_id")
    setup_scope_digest = setup.get("scope_digest")
    native_fp = callback.get("identity", {}).get("executor_fingerprints", {}).get("native.composed.workbook")
    if (setup_scope_id != "current-composed-workbook" or not isinstance(setup_scope_digest, str)
            or len(setup_scope_digest) != 64 or not isinstance(native_fp, str)):
        raise ValueError("historical consumed scope or current native executor binding is unavailable")
    scope_binding = CallbackScopeBinding(
        scope_id="delay-diagnostic-callback-20261004-v1", project_root=str(setup_project),
        manifest_sha256=_sha(native_manifest), database_path=str(native_database),
        database_device=native_database_stat.st_dev, database_inode=native_database_stat.st_ino,
        preserves_consumed_scope_id=setup_scope_id, preserves_consumed_scope_digest=setup_scope_digest,
        executor_id="native.composed.workbook", executor_fingerprint=native_fp,
    )
    scope_binding_digest = content_digest(scope_binding)

    source_matches = [ConformanceProbeRequest.model_validate(item)
                      for item in component_prep.get("requests", [])
                      if ConformanceProbeRequest.model_validate(item).worker_digest == EXPECTED_WORKER]
    if len(source_matches) != 1:
        raise ValueError("exact C treatment worker request is not unique")
    source_request = source_matches[0]
    treatment_evidence = component["workers"]["treatment"]
    if (source_request.worker_digest != EXPECTED_WORKER or source_request.composed_model_turns != 0
            or source_request.plan_id != treatment_evidence.get("request_id")
            or source_request.pair_definition_digest != content_digest(pair)):
        raise ValueError("only the exact completed zero-turn request may supply shared source digests")
    dependencies = runtime_dependencies()
    for path in (Path(__file__).resolve(), PRODUCER, COMPOSITION, PROFILE, COMPONENT_PREPARATION,
                 COMPONENT_RESULT, COMPONENT_TERMINAL_AUDIT, SETUP_REVIEW, SETUP_RESULT,
                 PROXY_LIFECYCLE_RESULT, CAPACITY_PREPARER, CAPACITY_RUNNER,
                 CAPACITY_REQUEST, CAPACITY_REVIEW, CAPACITY_RESULT, FIXTURE, OUT / "input-provenance.json", native_manifest):
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
            scope_binding_digest,
        ])),
        worker_digest=EXPECTED_WORKER, executable_dependencies=dependencies,
        operation="composed_pair_inspection", pair_definition_digest=content_digest(pair),
        composed_model_turns=1,
    )
    return {
        "schema_version": "assessment.c-current-callback-preparation.v1",
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
        "task_scope_id": scope_binding.scope_id,
        "task_scope_binding": scope_binding.model_dump(mode="json"),
        "task_scope_binding_digest": scope_binding_digest,
        "native_database_path": str(native_database),
        "native_database_device": native_database_stat.st_dev,
        "native_database_inode": native_database_stat.st_ino,
        "worker_digest": EXPECTED_WORKER, "executor_id": treatment.id,
        "model_id": "gpt-6-luna", "reasoning_effort": "xhigh",
        "pair": pair.model_dump(mode="json"), "pair_digest": content_digest(pair),
        "callback_document": callback, "callback_binding_digest": callback_digest,
        "probe_definition": definition.model_dump(mode="json"), "probe_definition_digest": definition_digest,
        "action_template": template.model_dump(mode="json"), "action_template_digest": action_template_digest,
        "fixture_binding": fixture_binding.model_dump(mode="json"),
        "fixture_binding_digest": fixture_binding_digest,
        "fixture_source": str(FIXTURE.relative_to(ROOT)),
        "fixture_sha256": FIXTURE_SHA256, "fixture_input_digest": FIXTURE_INPUT_DIGEST,
        "request": request.model_dump(mode="json"), "request_digest": content_digest(request),
        "records_to_store_and_review": [
            {"kind": "boundary_probe_definition", "identity": definition_digest,
             "digest": definition_digest, "value": definition.model_dump(mode="json")},
            {"kind": "composed_callback_action", "identity": action_template_digest,
             "digest": action_template_digest, "value": template.model_dump(mode="json")},
            {"kind": "c_callback_fixture_binding", "identity": fixture_binding_digest,
             "digest": fixture_binding_digest, "value": fixture_binding.model_dump(mode="json")},
            {"kind": "c_callback_capacity_binding", "identity": capacity_binding_digest,
             "digest": capacity_binding_digest, "value": capacity_binding},
            {"kind": "c_treatment_task_scope_binding", "identity": scope_binding_digest,
             "digest": scope_binding_digest, "value": scope_binding.model_dump(mode="json")},
            {"kind": "conformance_request", "identity": request.plan_id,
             "digest": content_digest(request), "value": request.model_dump(mode="json")},
        ],
        "executable_dependencies": dependencies,
        "limits": {"operations": 1, "model_turns": 1,
                   "elapsed_seconds": treatment.managed_host_config().timeout_seconds + 5,
                   "cash_usd": 0, "task_calls": 1, "task_call_timeout_seconds": 10.0,
                   "task_scope_attempts": 1},
        "diagnostic_only": True, "holdout": False,
        "inert_only": True, "persistence_authorized": False,
        "execution_authorized": False, "full_conformance": False,
        "qualification": False, "admission": False, "value_trial": False,
        "payload_policy": "Fresh synthetic diagnostic input is pinned locally and injected into the ephemeral action; no expected output, future case or holdout is read; canonical definitions remain payload-free.",
        "proxy_policy": "Use the separately reviewed v3 proxy lifecycle wrapper; this runner never starts or stops the shared proxy.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-inert", action="store_true", required=True)
    parser.add_argument("--profile-sha256", required=True)
    parser.add_argument("--capacity-review-sha256", required=True)
    parser.add_argument("--capacity-result-sha256", required=True)
    args = parser.parse_args()
    if args.profile_sha256 != PROFILE_SHA256:
        raise SystemExit("exact current profile hash is required")
    value = build(capacity_review_sha256=args.capacity_review_sha256,
                  capacity_result_sha256=args.capacity_result_sha256)
    with PREPARATION.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({"status": "inert_prepared", "path": str(PREPARATION),
                      "sha256": _sha(PREPARATION), "request_id": value["request"]["plan_id"],
                      "model_turns": 0, "persistence_authorized": False,
                      "execution_authorized": False}, sort_keys=True))


if __name__ == "__main__":
    main()
