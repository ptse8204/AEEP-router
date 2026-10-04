# ruff: noqa: ASYNC240 -- bounded local metadata path checks are deliberate preflight work.
"""One separately reviewed, fresh-input native callback delay diagnostic.

No work occurs on import. The host/model call requires a separate exact execution
review and a caller-managed proxy lifecycle; this file does not start/stop the proxy.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import importlib.util
import json
import os
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
HISTORY = OUT.parent / "luna-docx-stage"
SOURCE = "e6b71acba487280dfe50057d17379e5994c9113bc651a262935474f656a5dba6"
PROFILE = OUT / "c-current-profile-v2.json"
COMPONENT_RESULT = OUT / "c-worker-components-result-v2.json"
COMPONENT_AUDIT = OUT / "c-worker-components-terminal-audit.json"
NATIVE_COMPONENT_RESULT = OUT / "native-components-treatment-result.json"
NATIVE_COMPONENT_REVIEW = OUT / "native-components-treatment-review.json"
NATIVE_COMPONENT_RUNNER = OUT / "run-native-components-treatment.py"
SETUP_RESULT = HISTORY / "b-native-setup-v3-result.json"
SETUP_RESULT_SHA256 = "45f2344b74181d79ca284c8d3d3adc3d8d73a3c9edd1ccc51ef6993ed2968752"
SETUP_REVIEW = HISTORY / "b-native-setup-v3-review.json"
SETUP_REVIEW_SHA256 = "ab4f78de528080b8684d8d608786d15a5b8aa616755d7f9033957ac0c44ef7b5"
PROXY_RESULT = OUT / "c-worker-components-v3-proxy-result.json"
PROXY_RESULT_SHA256 = None
CAPACITY_REQUEST = OUT / "c-treatment-capacity-request.json"
CAPACITY_REVIEW = OUT / "c-treatment-capacity-review.json"
CAPACITY_RESULT = OUT / "c-treatment-capacity-result.json"
CAPACITY_PREPARER = OUT / "c-prepare-treatment-capacity-v1.py"
CAPACITY_RUNNER = OUT / "c-run-treatment-capacity-v1.py"
PREPARATION = OUT / "diagnostic-preparation.json"
PREPARER = OUT / "diagnostic-prepare.py"
EXECUTION_REVIEW = OUT / "diagnostic-execution-review.json"
STARTED = OUT / "diagnostic-started.json"
RESULT = OUT / "diagnostic-result.json"
FIXTURE = OUT / "fresh-input.json"
NATIVE_PRODUCER = HISTORY / "b-native-workbook-producer-final.py"
COMPOSITION = ROOT / "reports/v08/original-three-way-profile/native-dynamic-operator-composition.py"
CANONICAL_MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
CANONICAL_MANIFEST_SHA256 = "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb"
CANONICAL_DB = ROOT / ".aeep/live-review-v3/aeep.sqlite3"
CANONICAL_STORE = ROOT / ".aeep/live-review-v3"
EXPECTED_WORKER = "19027f56cdc99fc9b728dc2bf7af597f33c6a0d8f4b5d71d19739aa512a56df0"
EXPECTED_COMPONENT = "bf500fb25b63f78d735fabaf85e1f6ac9ad5ae3e91411fb98f709b805beb225f"
DOCKER = ["/usr/local/bin/docker", "--host", "unix:///Users/edwintse/.docker/run/docker.sock"]
PROXY_NAME = "aeep-reviewed-model-proxy"
PROXY_ID = "5f9a44f86633409a250d11a78cf59357495da2078724ee0261bc73acff57f0f3"
PROXY_IMAGE = "sha256:5bf590eb0bf8a06187ff092f0f75cf83b540cc27bd6a75fd8bd91305ca7b13de"
PROXY_NETWORK = "8f657f861de8897d53df66efdf595c6d2e202b174af81f2827db409fe53f19d6"
FIXTURE_INPUT_DIGEST = "c7ed4a9fe4dd6cd2b2cf1c0cbf2d994ee3f37a2eb22a731a47acd8edc0c582b2"
MAX_CAPACITY_AGE_SECONDS = 1800
MAX_ELAPSED_SECONDS = 208.0


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


COMPONENT_RESULT_SHA256 = _sha(COMPONENT_RESULT) if COMPONENT_RESULT.is_file() else None
COMPONENT_AUDIT_SHA256 = _sha(COMPONENT_AUDIT) if COMPONENT_AUDIT.is_file() else None
PROXY_RESULT_SHA256 = _sha(PROXY_RESULT) if PROXY_RESULT.is_file() else None


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("reviewed report helper cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _first_fixture_input() -> dict[str, Any]:
    """Read only the new, independently frozen diagnostic input."""
    if (FIXTURE.is_symlink() or not FIXTURE.is_file() or FIXTURE.stat().st_size > 1_000_000
            or _sha(FIXTURE) != "0b1fe315b9fe2abea7715520b3eb7f21cf3b82b1ca07c7f48a876b25e77253d9"):
        raise RuntimeError("fresh diagnostic input changed or exceeds one megabyte")
    value = json.loads(FIXTURE.read_bytes())
    if not isinstance(value, dict):
        raise RuntimeError("fresh diagnostic input must be an object")
    return value


def _age_seconds(value: str) -> float:
    observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise RuntimeError("capacity observation timestamp lacks a timezone")
    return (datetime.now(UTC) - observed.astimezone(UTC)).total_seconds()


def _require_capacity(bundle: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    capacity_review = json.loads(CAPACITY_REVIEW.read_text())
    capacity = json.loads(CAPACITY_RESULT.read_text())
    if (_sha(CAPACITY_REVIEW) != bundle.get("capacity_review_sha256")
            or _sha(CAPACITY_RESULT) != bundle.get("capacity_result_sha256")
            or _sha(CAPACITY_REQUEST) != bundle.get("capacity_request_sha256")):
        raise RuntimeError("fresh capacity request/review/result digest changed")
    observation = capacity.get("capacity")
    if (capacity_review.get("source_digest") != SOURCE
            or capacity_review.get("stage") != "capacity_introspection"
            or capacity_review.get("worker_digest") != EXPECTED_WORKER
            or capacity_review.get("max_age_seconds") != MAX_CAPACITY_AGE_SECONDS
            or capacity.get("status") != "passed" or capacity.get("source_digest") != SOURCE
            or capacity.get("stage") != "capacity_introspection"
            or capacity.get("executor_id") != "b.luna.aeep"
            or capacity.get("worker_digest") != EXPECTED_WORKER
            or capacity.get("profile_sha256") != bundle.get("profile_sha256")
            or capacity.get("component_result_sha256") != COMPONENT_RESULT_SHA256
            or capacity.get("request_digest") != capacity_review.get("request_digest")
            or capacity.get("operation_id") != capacity_review.get("operation_id")
            or capacity.get("capacity_digest") != (observation or {}).get("canonical_digest")
            or (observation or {}).get("resource_id") != "codex.self"
            or capacity.get("max_model_turns_reserved") != 0
            or capacity.get("cash_ceiling_usd") != 0
            or capacity.get("host_receipt_applicable") is not False
            or capacity.get("cleanup_confirmed") is not True
            or capacity.get("source_unchanged") is not True
            or not isinstance(capacity.get("elapsed_seconds"), (int, float))
            or not 0 <= capacity["elapsed_seconds"] <= 60
            or capacity.get("replay_allowed") is not False
            or not capacity.get("worker_process_id")
            or not capacity.get("operation_start_digest")
            or not capacity.get("operation_measurement_digest")
            or not isinstance(observation, dict) or not observation.get("windows")):
        raise RuntimeError("capacity result does not prove the current same-worker zero-turn observation")
    age = _age_seconds(str(observation["observed_at"]))
    if not 0 <= age <= MAX_CAPACITY_AGE_SECONDS:
        raise RuntimeError("same-worker capacity snapshot is stale or future-dated")
    if any(window.get("exhausted") is not False for window in observation["windows"]):
        raise RuntimeError("capacity is exhausted or unknown; callback must not start")
    if (capacity_review.get("prepare_script_sha256") != _sha(CAPACITY_PREPARER)
            or capacity_review.get("runner_sha256") != _sha(CAPACITY_RUNNER)):
        raise RuntimeError("capacity helper scripts differ from their reviewed pins")
    if review.get("capacity_result_sha256") != _sha(CAPACITY_RESULT):
        raise RuntimeError("execution review does not pin the current capacity result")
    return capacity


def _require_proxy(review: dict[str, Any]) -> dict[str, Any]:
    if (review.get("proxy_name") != PROXY_NAME or review.get("proxy_id") != PROXY_ID
            or review.get("proxy_image") != PROXY_IMAGE or review.get("proxy_network") != PROXY_NETWORK):
        raise RuntimeError("separately reviewed exact proxy lifecycle is required")
    template = '{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Networks":{{json .NetworkSettings.Networks}}}'
    completed = subprocess.run([*DOCKER, "inspect", "--format", template, PROXY_NAME],
                               check=True, capture_output=True, text=True, timeout=15)
    actual = json.loads(completed.stdout)
    networks = [entry.get("NetworkID") for entry in actual["Networks"].values()]
    if (actual.get("Id") != PROXY_ID or actual.get("Image") != PROXY_IMAGE
            or actual.get("Running") is not True or PROXY_NETWORK not in networks):
        raise RuntimeError("exact reviewed model proxy is not running")
    return {"proxy_id": PROXY_ID, "image": PROXY_IMAGE, "network_id": PROXY_NETWORK, "running": True}


def _canonical_store(router) -> dict[str, Any]:
    if (CANONICAL_MANIFEST.is_symlink() or _sha(CANONICAL_MANIFEST) != CANONICAL_MANIFEST_SHA256
            or CANONICAL_DB.is_symlink()):
        raise RuntimeError("canonical manifest/database pin changed")
    manifest = json.loads(CANONICAL_MANIFEST.read_text())
    if Path(manifest["database"]).resolve() != CANONICAL_DB.resolve():
        raise RuntimeError("canonical manifest database target changed")
    stat = CANONICAL_DB.stat()
    return {"manifest_path": str(CANONICAL_MANIFEST), "manifest_sha256": CANONICAL_MANIFEST_SHA256,
            "database_path": str(CANONICAL_DB), "device": stat.st_dev, "inode": stat.st_ino}


def _require_native_component_result(execution_review: dict[str, Any], repository, pair, callback_digest: str,
                                     native_project: Path) -> None:
    from aeep.assessment.boundary import BoundaryProbe, BoundaryProbeDefinition
    from aeep.assessment.models import content_digest
    from aeep.hosts.codex_invocation import contract_digest

    result_sha = execution_review.get("native_component_result_sha256")
    review_sha = execution_review.get("native_component_review_sha256")
    if (not NATIVE_COMPONENT_RESULT.is_file() or not NATIVE_COMPONENT_REVIEW.is_file()
            or not NATIVE_COMPONENT_RUNNER.is_file()
            or _sha(NATIVE_COMPONENT_RESULT) != result_sha
            or _sha(NATIVE_COMPONENT_REVIEW) != review_sha):
        raise RuntimeError("exact current C native-component result/review is absent or changed")
    result = json.loads(NATIVE_COMPONENT_RESULT.read_text())
    native_review = json.loads(NATIVE_COMPONENT_REVIEW.read_text())
    required = {"native_boundary", "protected_state", "callback_lifecycle"}
    operation_id = "c-native-components:" + str(result.get("request_id"))
    if (result.get("schema_version") != "c-native-components-result.treatment.v1"
            or result.get("result_status") != "pass" or result.get("source_digest") != SOURCE
            or result.get("request_id") != native_review.get("request_id")
            or result.get("review_sha256") != review_sha
            or result.get("operation_id") != operation_id
            or result.get("model_turns") != 0 or result.get("native_attempts") != 2
            or result.get("boundary_probes_complete") is not True
            or set(result.get("supervisor_probe_digests", {})) != required
            or result.get("cleanup_confirmed") is not True
            or result.get("operation_settled") is not True
            or result.get("source_unchanged") is not True
            or result.get("full_conformance") is not False
            or not isinstance(result.get("elapsed_seconds"), (int, float))
            or not 0 <= result["elapsed_seconds"] <= 40):
        raise RuntimeError("current C native-component result is not complete, settled zero-turn evidence")
    if (native_review.get("schema_version") != "c-native-components-review.treatment.v1"
            or native_review.get("source_digest") != SOURCE
            or native_review.get("driver_sha256") != _sha(NATIVE_COMPONENT_RUNNER)
            or native_review.get("selected_worker_digest") != EXPECTED_WORKER
            or native_review.get("project") != str(native_project)
            or contract_digest({"native.composed.workbook": native_review.get("native_backend_digest")})
                != pair.native_backends.get(EXPECTED_WORKER)
            or native_review.get("callback_document_digests", {}).get("treatment") != callback_digest
            or native_review.get("worker_digests", {}).get("treatment") != EXPECTED_WORKER
            or set(native_review.get("probe_definition_digests", {})) != required
            or native_review.get("execution_authorized") is not True
            or native_review.get("full_conformance") is not False):
        raise RuntimeError("C native-component review does not bind the treatment worker/backend")
    if result.get("operation_id") != operation_id:
        raise RuntimeError("C native component operation identity differs")
    for name, definition_digest in native_review["probe_definition_digests"].items():
        definition, actual = _reviewed(repository, "boundary_probe_definition", definition_digest,
                                       BoundaryProbeDefinition)
        probe_id = f"probe_{native_review['request_id']}_{name}"
        probe = BoundaryProbe.model_validate(repository.get("boundary_probe", probe_id))
        start_record = repository.get("operation_start", operation_id)
        if (actual != definition_digest or definition.name != name
                or content_digest(probe) != result["supervisor_probe_digests"][name]
                or probe.schema_version != "assessment.boundary-probe.v2"
                or probe.charged_operation_digest != content_digest(start_record)
                or probe.implementation_digest != definition_digest
                or probe.worker_digest != EXPECTED_WORKER
                or probe.observed != definition.expected):
            raise RuntimeError("C native component probe lacks its exact definition or charge binding")

def _reviewed(repository, kind: str, identity: str, model):
    value = model.model_validate(repository.get(kind, identity))
    from aeep.assessment.models import content_digest
    digest = content_digest(value)
    with repository.store._lock:
        row = repository.store._connection.execute(
            "SELECT revoked FROM assessment_reviews WHERE digest=?", (digest,)
        ).fetchone()
    if row is None or row[0]:
        raise RuntimeError("exact current definition review is absent or revoked")
    return value, digest


async def prepare(service, review_sha256: str) -> tuple[Any, ...]:
    """Preflight the exact bundle and current reviews; performs no reservation."""
    from aeep.assessment.boundary import BoundaryProbeDefinition
    from aeep.assessment.identity import verify_dependencies
    from aeep.assessment.models import ConformanceProbeRequest, content_digest
    from aeep.assessment.verification import verification_source_digest
    from aeep.hosts.codex_pair_inspection import ComposedPairDefinition
    from aeep.models import ActionRequest, SideEffect

    if _sha(EXECUTION_REVIEW) != review_sha256:
        raise RuntimeError("exact callback execution review hash required")
    review = json.loads(EXECUTION_REVIEW.read_text())
    if not PREPARATION.is_file() or _sha(PREPARATION) != review.get("preparation_sha256"):
        raise RuntimeError("exact prepared callback bundle is missing or changed")
    bundle = json.loads(PREPARATION.read_text())
    if (review.get("schema_version") != "assessment.c-current-callback-execution-review.v1"
            or review.get("execution_authorized") is not True or review.get("source_digest") != SOURCE
            or review.get("runner_sha256") != _sha(Path(__file__).resolve())
            or review.get("preparer_sha256") != _sha(PREPARER)
            or review.get("profile_sha256") != _sha(PROFILE)
            or review.get("component_result_sha256") != COMPONENT_RESULT_SHA256
            or review.get("component_terminal_audit_sha256") != COMPONENT_AUDIT_SHA256
            or review.get("setup_result_sha256") != SETUP_RESULT_SHA256
            or review.get("setup_review_sha256") != SETUP_REVIEW_SHA256
            or review.get("proxy_lifecycle_result_sha256") != PROXY_RESULT_SHA256
            or review.get("request_id") != bundle.get("request", {}).get("plan_id")
            or review.get("request_digest") != bundle.get("request_digest")
            or review.get("capacity_review_sha256") != bundle.get("capacity_review_sha256")
            or review.get("capacity_result_sha256") != bundle.get("capacity_result_sha256")
            or not review.get("native_component_result_sha256")
            or not review.get("native_component_review_sha256")
            or review.get("max_operations") != 1 or review.get("max_model_turns") != 1
            or review.get("max_elapsed_seconds") != MAX_ELAPSED_SECONDS
            or review.get("max_cash_usd") != 0 or review.get("task_calls") != 1
            or review.get("task_scope_attempts") != 1
            or review.get("task_call_timeout_seconds") != 10.0
            or review.get("model_id") != "gpt-6-luna"
            or review.get("reasoning_effort") != "xhigh"):
        raise RuntimeError("callback execution review differs from this exact one-turn scope")
    if verification_source_digest(ROOT) != SOURCE:
        raise RuntimeError("frozen source digest changed")
    for path, expected in (
        (PROFILE, bundle.get("profile_sha256")), (COMPONENT_RESULT, COMPONENT_RESULT_SHA256),
        (COMPONENT_AUDIT, COMPONENT_AUDIT_SHA256), (SETUP_RESULT, SETUP_RESULT_SHA256),
        (SETUP_REVIEW, SETUP_REVIEW_SHA256), (PROXY_RESULT, PROXY_RESULT_SHA256),
        (NATIVE_PRODUCER, bundle.get("executable_dependencies", {}).get(str(NATIVE_PRODUCER.resolve()))),
        (COMPOSITION, bundle.get("executable_dependencies", {}).get(str(COMPOSITION.resolve()))),
    ):
        if not path.is_file() or not expected or _sha(path) != expected:
            raise RuntimeError("one current profile, setup, proxy or helper input changed")
    if (bundle.get("source_digest") != SOURCE or bundle.get("worker_digest") != EXPECTED_WORKER
            or bundle.get("component_result_sha256") != COMPONENT_RESULT_SHA256
            or bundle.get("execution_authorized") is not False or bundle.get("full_conformance") is not False):
        raise RuntimeError("inert preparation no longer binds the reviewed current C profile")

    capacity = _require_capacity(bundle, review)
    proxy = _require_proxy(review)
    repository = service.repository
    request = ConformanceProbeRequest.model_validate(bundle["request"])
    if (content_digest(request) != bundle.get("request_digest")
            or request.plan_id == "conformance_probe_bf48e94ea8b6458baadcb19a8f0325e0"
            or request.worker_digest != EXPECTED_WORKER or request.composed_model_turns != 1
            or request.operation != "composed_pair_inspection"
            or request.pair_definition_digest != bundle.get("pair_digest")
            or request.pair_definition_digest not in request.definition_digests
            or bundle.get("capacity_binding_digest") not in request.definition_digests
            or bundle.get("task_scope_binding_digest") not in request.definition_digests
            or bundle.get("fixture_binding_digest") not in request.definition_digests
            or bundle.get("probe_definition_digest") not in request.definition_digests
            or bundle.get("action_template_digest") not in request.definition_digests):
        raise RuntimeError("one-turn request differs, is stale or reuses the completed zero-turn request")
    if request.executable_dependencies.get(str(PREPARER.resolve())) != _sha(PREPARER.resolve()):
        raise RuntimeError("current callback preparer is not pinned in the request")
    verify_dependencies(request.executable_dependencies)
    repository.authorize(request)
    pair, pair_digest = _reviewed(repository, "composed_pair_definition", bundle["pair_digest"], ComposedPairDefinition)
    callback = repository.get("codex_dynamic_tools", bundle["callback_binding_digest"])
    if content_digest(callback) != bundle["callback_binding_digest"]:
        raise RuntimeError("exact current callback document differs")
    with repository.store._lock:
        reviewed = repository.store._connection.execute(
            "SELECT revoked FROM assessment_reviews WHERE digest=?", (bundle["callback_binding_digest"],)
        ).fetchone()
    if reviewed is None or reviewed[0]:
        raise RuntimeError("current callback review is absent or revoked")
    definition, _ = _reviewed(repository, "boundary_probe_definition",
        bundle["probe_definition_digest"], BoundaryProbeDefinition)
    template, _ = _reviewed(repository, "composed_callback_action",
        bundle["action_template_digest"], ActionRequest)
    fixture_binding = repository.get("c_callback_fixture_binding", bundle["fixture_binding_digest"])
    capacity_binding = repository.get("c_callback_capacity_binding", bundle["capacity_binding_digest"])
    if (content_digest(fixture_binding) != bundle["fixture_binding_digest"]
            or content_digest(capacity_binding) != bundle["capacity_binding_digest"]):
        raise RuntimeError("public fixture or capacity evidence binding differs")
    for digest in (bundle["fixture_binding_digest"], bundle["capacity_binding_digest"], bundle["task_scope_binding_digest"]):
        with repository.store._lock:
            row = repository.store._connection.execute(
                "SELECT revoked FROM assessment_reviews WHERE digest=?", (digest,)
            ).fetchone()
        if row is None or row[0]:
            raise RuntimeError("exact fixture/capacity/scope binding review is absent or revoked")
    from aeep.models import StrictModel
    class CallbackScopeBinding(StrictModel):
        schema_version: str
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
        approval_ceiling: str
        max_attempts: int
        max_attempt_seconds: float
        expires_in_seconds: int
        replaces_or_resets_prior_scope: bool
    scope_binding = CallbackScopeBinding.model_validate(
        repository.get("c_treatment_task_scope_binding", bundle["task_scope_binding_digest"]))
    if (content_digest(scope_binding) != bundle["task_scope_binding_digest"]
            or scope_binding.model_dump(mode="json") != bundle.get("task_scope_binding")
            or scope_binding.scope_id != bundle.get("task_scope_id")
            or scope_binding.approval_ceiling != "read" or scope_binding.max_attempts != 1
            or scope_binding.max_attempt_seconds != 10.0 or scope_binding.expires_in_seconds != 600
            or scope_binding.replaces_or_resets_prior_scope is not False):
        raise RuntimeError("C treatment task scope blueprint differs")
    selected = pair.treatment
    config = selected.managed_host_config()
    if (pair_digest != request.pair_definition_digest or selected.id != "b.luna.aeep"
            or config.model_constraints.allowed_model_ids != ("gpt-6-luna",)
            or config.reasoning_efforts != ("xhigh",) or config.approval_ceiling != SideEffect.READ
            or selected.side_effect != SideEffect.READ or selected.estimate.cash.upper_bound_usd != 0
            or config.invocation is None or config.invocation.mode != "dynamic_tool"
            or config.invocation.exposure != "required"
            or config.invocation.dynamic_tools_digest != bundle["callback_binding_digest"]
            or definition.name != "callback_authority" or content_digest(definition.executor) != content_digest(selected)
            or config.timeout_seconds + 5 != review["max_elapsed_seconds"]
            or bundle.get("limits") != {
                "cash_usd": 0, "elapsed_seconds": MAX_ELAPSED_SECONDS,
                "model_turns": 1, "operations": 1,
                "task_call_timeout_seconds": 10.0, "task_calls": 1,
                "task_scope_attempts": 1,
            }
            or bundle["callback_document"].get("max_calls") != 1
            or bundle["callback_document"].get("timeout_seconds") != 10.0
            or template.capability != selected.capability
            or template.constraints.allowed_executor_ids != [selected.id]
            or template.constraints.max_side_effect != SideEffect.READ):
        raise RuntimeError("selected treatment, action template or probe definition differs")
    native_project = Path(json.loads(SETUP_RESULT.read_text())["project"]).resolve()
    _require_native_component_result(review, repository, pair, bundle["callback_binding_digest"], native_project)
    if (review.get("fresh_database") is None or not Path(review["fresh_database"]).is_absolute()
            or Path(review["fresh_database"]).exists() or Path(review["fresh_database"]).is_symlink()
            or not Path(review["fresh_database"]).parent.is_dir()
            or ROOT in Path(review["fresh_database"]).resolve().parents
            or native_project in Path(review["fresh_database"]).resolve().parents
            or Path(review["fresh_database"]).resolve() in (CANONICAL_DB,)):
        raise RuntimeError("fresh isolated outer router database is required")
    expected_store = _canonical_store(service.router)
    if review.get("canonical_store") != expected_store:
        raise RuntimeError("canonical manifest/store identity differs from exact execution review")
    native_manifest = native_project / "aeep.json"
    native_database = Path(scope_binding.database_path)
    if (native_manifest.is_symlink() or not native_manifest.is_file()
            or _sha(native_manifest) != scope_binding.manifest_sha256
            or native_database != native_project / ".aeep" / "state.db"
            or native_database.is_symlink() or not native_database.is_file()):
        raise RuntimeError("pinned C native manifest/database changed")
    stat = native_database.stat()
    if (stat.st_dev, stat.st_ino) != (scope_binding.database_device, scope_binding.database_inode):
        raise RuntimeError("C native database identity changed")
    return (review, bundle, request, definition, template, fixture_binding, capacity,
            scope_binding, proxy, selected, native_project)


def _persist_scoped(repository, scoped, action_id: str):
    from aeep.assessment.models import content_digest
    from aeep.assessment.repository import AssessmentRepository
    from aeep.attempts import ExecutionAttempt
    from aeep.execution import ExecutionEvidence
    from aeep.models import ExecutionReceipt

    local = AssessmentRepository(scoped.store)
    with scoped.store._lock:
        attempts = scoped.store._connection.execute(
            "SELECT a.payload_json FROM execution_attempts a JOIN decisions d ON d.decision_id=a.decision_id WHERE d.action_id=? LIMIT 2",
            (action_id,),
        ).fetchall()
        receipts = scoped.store._connection.execute(
            "SELECT payload_json FROM receipts WHERE action_id=? LIMIT 2", (action_id,),
        ).fetchall()
    attempt_digests = []
    receipt_digests = []
    parsed_receipts = []
    for row in attempts:
        attempt = ExecutionAttempt.model_validate_json(row[0])
        attempt_digests.append(repository.put("conformance_outer_attempt", content_digest(attempt), attempt))
    for row in receipts:
        receipt = ExecutionReceipt.model_validate_json(row[0])
        digest = repository.put("conformance_host_receipt", content_digest(receipt), receipt)
        receipt_digests.append(digest)
        parsed_receipts.append(receipt)
        reference = receipt.metadata.get("execution_evidence_digest")
        if reference:
            evidence = ExecutionEvidence.model_validate(local.get("execution_evidence", reference))
            repository.put("execution_evidence", content_digest(evidence), evidence)
    partial = parsed_receipts[0] if len(parsed_receipts) == 1 else None
    return attempt_digests, receipt_digests, partial


async def _fresh_native_services(bundle: dict[str, Any], scope_binding, native_project: Path):
    """Create a new bounded C task scope only after the caller reserves its operation."""
    from aeep.assessment.models import content_digest
    from aeep.assessment.repository import AssessmentRepository
    from aeep.economic.prepared import executor_fingerprint
    from aeep.hosts.codex_sandbox import NativeSandboxConfig
    from aeep.models import SideEffect, TaskScope, utc_now
    from aeep.router import Router

    manifest_path = native_project / "aeep.json"
    native_router = Router.from_manifest(manifest_path)
    try:
        spec = native_router.registry.get(scope_binding.executor_id)
        fingerprint = executor_fingerprint(spec)
        native = NativeSandboxConfig.model_validate(spec.config["native_sandbox"])
        if (spec.id != "native.composed.workbook"
                or fingerprint != scope_binding.executor_fingerprint
                or scope_binding.project_root != str(native_project)
                or scope_binding.manifest_sha256 != _sha(manifest_path)
                or spec.config.get("native_sandbox") != native.model_dump(mode="json")):
            raise RuntimeError("fresh C task scope does not match the exact native executor")
        local = AssessmentRepository(native_router.store)
        preserved = TaskScope.model_validate(local.get("task_scope", scope_binding.preserves_consumed_scope_id))
        if (content_digest(preserved) != scope_binding.preserves_consumed_scope_digest
                or preserved.scope_id != scope_binding.preserves_consumed_scope_id):
            raise RuntimeError("existing consumed native scope changed; refusing replacement")
        with native_router.store._lock:
            exists = native_router.store._connection.execute(
                "SELECT 1 FROM assessment_records WHERE kind='task_scope' AND id=?",
                (scope_binding.scope_id,),
            ).fetchone()
        if exists is not None:
            raise RuntimeError("fresh callback scope already exists; no replay or reset")
        scope = TaskScope(
            scope_id=scope_binding.scope_id, project_root=str(native_project),
            executor_fingerprints={spec.id: fingerprint}, approval_ceiling=SideEffect.READ,
            max_attempts=1, max_attempt_seconds=10.0,
            expires_at=utc_now() + timedelta(seconds=scope_binding.expires_in_seconds),
        )
        if (scope.executor_fingerprints != {spec.id: scope_binding.executor_fingerprint}
                or scope.approval_ceiling.value != scope_binding.approval_ceiling
                or scope.max_attempts != scope_binding.max_attempts
                or scope.max_attempt_seconds != scope_binding.max_attempt_seconds):
            raise RuntimeError("new C callback scope exceeds its reviewed READ limits")
        digest = local.put("task_scope", scope.scope_id, scope)
        local.review(digest)
        native_router.bind_task_scope(scope.scope_id)
        producer = _load("c_native_workbook_producer", NATIVE_PRODUCER)
        fixed, aeep = producer.services(native_router, scope, spec, native)[4:]
        return native_router, scope, spec, native, fixed, aeep
    except BaseException:
        with contextlib.suppress(BaseException):
            async with asyncio.timeout(10):
                await native_router.close()
        raise


async def _confirm_worker_cleanup(adapter) -> bool:
    from aeep.assessment.containment import container_name
    from aeep.hosts.codex_pair_inspection import docker

    process = adapter.transport._process
    if (process is not None and process.returncode is None) or adapter.transport._dynamic_tasks:
        return False
    worker = adapter._worker
    identity = adapter._worker_process_id
    if worker is None or identity is None:
        return False
    remaining = await docker(worker, "ps", "-a", "--filter",
        "name=^/" + container_name(identity) + "$", "--format", "{{.ID}}")
    return remaining.strip() == ""


async def run_once(service, review_sha256: str) -> dict[str, Any]:
    from aeep.assessment.boundary import BoundaryProbe
    from aeep.assessment.identity import verify_dependencies
    from aeep.assessment.models import AssessmentLimits, content_digest
    from aeep.assessment.repository import AssessmentRepository
    from aeep.assessment.verification import verification_source_digest
    from aeep.errors import ConfigurationError
    from aeep.execution import EventJournal, ExecutionEvidence
    from aeep.hosts.codex_app_server import CodexAppServerAdapter
    from aeep.models import ActionRequest, ExecutionStatus, RawExecution, SideEffect, new_id

    (review, bundle, request, definition, template, fixture_binding, capacity,
     scope_binding, _proxy, selected, native_project) = await prepare(service, review_sha256)
    capacity_age_at_start = _age_seconds(str(capacity["capacity"]["observed_at"]))
    if not 0 <= capacity_age_at_start <= MAX_CAPACITY_AGE_SECONDS:
        raise RuntimeError("same-worker capacity observation expired at callback start")
    if STARTED.exists() or RESULT.exists():
        raise RuntimeError("one-shot marker/result already exists; no replay")
    if verification_source_digest(ROOT) != SOURCE:
        raise RuntimeError("frozen source changed at execution boundary")
    if template.input != {}:
        raise RuntimeError("canonical action template must remain payload-free")
    fixture_input = _first_fixture_input()
    if (content_digest(fixture_input) != FIXTURE_INPUT_DIGEST
            or sorted(fixture_input) != fixture_binding.get("input_fields")
            or fixture_binding.get("source_sha256") != bundle.get("fixture_sha256")
            or fixture_binding.get("record_index") is not None
            or fixture_binding.get("diagnostic_only") is not True
            or fixture_binding.get("qualification") is not False
            or fixture_binding.get("holdout") is not False
            or fixture_binding.get("data_rows") != 3
            or fixture_binding.get("expected_output_read") is not False
            or fixture_binding.get("later_records_read") is not False):
        raise RuntimeError("fresh diagnostic input differs from the reviewed binding")
    config = selected.managed_host_config()
    if len(fixture_input["workbook_b64"]) > config.artifact.max_bytes:
        raise RuntimeError("fixed fixture exceeds the reviewed workbook artifact bound")
    action_document = template.model_dump(mode="json")
    action_document["input"] = fixture_input
    action = ActionRequest.model_validate(action_document)
    operation_id = "composed:" + request.plan_id
    fresh_database = Path(review["fresh_database"]).resolve()
    if _sha(Path(__file__).resolve()) != review.get("runner_sha256"):
        raise RuntimeError("callback runner hash differs from execution review")
    _atomic_json(STARTED, {
        "request_id": request.plan_id, "request_digest": bundle["request_digest"],
        "operation_id": operation_id, "source_digest": SOURCE,
        "capacity_result_sha256": bundle["capacity_result_sha256"],
        "fresh_database": str(fresh_database), "model_turns_reserved": 1,
        "task_payload_recorded": False, "diagnostic_only": True,
        "input_digest": FIXTURE_INPUT_DIGEST,
    })

    repository = service.repository
    seconds = float(config.timeout_seconds)
    started = time.perf_counter()
    deadline = asyncio.get_running_loop().time() + seconds
    scoped = None
    native_router = None
    adapter = None
    receipt = None
    host_digest = None
    evidence_digest = None
    probe_digest = None
    attempt_digests: list[str] = []
    receipt_digests: list[str] = []
    stage = "reservation"
    error_type = None
    cleanup_confirmed = False
    reserved = False
    charged_operation_digest: str | None = None
    task_scope_digest: str | None = None
    operation_settled = False
    operation_start_digest: str | None = None
    operation_measurement_digest: str | None = None
    failure: BaseException | None = None
    failure_stage: str | None = None
    try:
        # One new reviewed operation. No old request, scope or reservation is reused.
        repository.reserve(request, operation_id, AssessmentLimits(
            max_operations=1, max_model_turns=1,
            max_elapsed_seconds=seconds + 5, max_cash_usd=0,
        ), stage="composed_pair_inspection")
        reserved = True
        operation_start = repository.get("operation_start", operation_id)
        operation_start_digest = content_digest(operation_start)
        charged_operation_digest = operation_start_digest
        composition = _load("c_current_union_composition", COMPOSITION)
        native_router, scope, _native_spec, _native_backend, fixed, aeep = await _fresh_native_services(
            bundle, scope_binding, native_project)
        task_scope_digest = content_digest(scope)
        if service.router.manifest.persistence.store_action_inputs:
            raise ConfigurationError("router action-input persistence must remain disabled")
        policy_name = action.policy or service.router.manifest.default_policy
        policy = service.router._policy_for(action).model_copy(deep=True)
        policy.fallback.enabled = False
        policy.fallback.max_attempts = 1
        service.router.manifest.policies[policy_name] = policy

        def services_for_trial(plan_id: str, selected_operation: str):
            if plan_id != request.plan_id or selected_operation != operation_id:
                raise ConfigurationError("callback operation identity differs")
            return fixed, aeep

        dynamic_factory = composition.union_operator_factory(
            assessment=service, plan=request, profile_identity=bundle["callback_document"]["identity"],
            namespace="workbook", max_calls=1, timeout_seconds=10.0,
            services_for_trial=services_for_trial, conformance_request=request,
        )

        def adapter_factory(spec, salt, directory):
            adapter = CodexAppServerAdapter.from_executor(
                spec, principal_salt=salt, manifest_directory=directory)
            adapter.dynamic_tools_factory = dynamic_factory
            return adapter

        service.router.managed_hosts.register_factory("codex-app-server", adapter_factory)
        scoped = service.router._campaign_router([selected], plan_digest=content_digest(request),
            database=fresh_database)
        scoped._callback_conformance_identity = (request.plan_id, operation_id)
        if scoped.manifest.persistence.store_action_inputs:
            raise ConfigurationError("scoped router action-input persistence must remain disabled")
        adapter = scoped.managed_hosts.get(config.adapter_id)
        scoped._trial_deadline = deadline

        def recheck() -> None:
            repository.authorize(request)
            verify_dependencies(request.executable_dependencies)
            if asyncio.get_running_loop().time() >= scoped._trial_deadline:
                raise ConfigurationError("one-turn callback deadline expired")

        scoped._trial_check = recheck
        scoped._trial_boundary_references = {selected.id: request.worker_digest}
        stage = "runtime_identity"
        async with asyncio.timeout_at(deadline):
            await scoped._resolve_host_identity(selected)
            identity = scoped.store.host_runtime_digests.get(selected.id)
            if identity is None:
                raise ConfigurationError("actual host runtime identity is unavailable")
            scoped.store.expected_host_runtime_digests[selected.id] = identity[1]
            stage = "host_execution"
            outcome = await scoped.execute(action, approved_side_effect=SideEffect.READ)
        stage = "receipt_verification"
        if len(outcome.receipts) != 1 or outcome.receipts[0].executor_id != selected.id:
            raise ConfigurationError("one exact treatment host receipt is required")
        receipt = outcome.receipts[0]
        host_digest = repository.put("conformance_host_receipt", content_digest(receipt), receipt)
        local = AssessmentRepository(scoped.store)
        evidence = ExecutionEvidence.model_validate(local.get(
            "execution_evidence", receipt.metadata.get("execution_evidence_digest")))
        repository.put("execution_evidence", content_digest(evidence), evidence)
        from aeep.economic.prepared import executor_fingerprint
        from aeep.models import ExecutorKind
        if (not isinstance(adapter, CodexAppServerAdapter)
                or receipt.executor_kind is not ExecutorKind.MANAGED_HOST
                or receipt.executor_fingerprint != executor_fingerprint(selected)
                or receipt.metadata.get("adapter_id") != config.adapter_id
                or not config.adapter_id.startswith("codex-app-server:")
                or evidence.adapter != "ManagedHostExecutor"
                or evidence.identity_digest != identity[1]
                or evidence.boundary_digest != request.worker_digest
                or receipt.metadata.get("host_runtime_digest") != identity[1]
                or receipt.metadata.get("dynamic_tools_digest") != bundle["callback_binding_digest"]):
            raise ConfigurationError("callback origin does not match the actual pinned App Server execution")
        complete = [event for event in evidence.events
                    if event.kind == "action.completed" and isinstance(event.source_id, str)
                    and event.source_id.startswith(("dynamic-complete:", "adapter:dynamic-complete:"))]
        links = [event for event in evidence.events
                 if isinstance(event.source_id, str)
                 and event.source_id.startswith(("dynamic-link:", "adapter:dynamic-link:"))]
        if (len(complete) != 1 or len(links) != 1
                or not isinstance(complete[0].action_digest, str)
                or links[0].action_digest != complete[0].action_digest):
            raise ConfigurationError("one exact linked native callback claim is required")
        claim_id = content_digest({
            "outer_operation": hashlib.sha256(operation_id.encode()).hexdigest(),
            "call": complete[0].action_digest,
        })
        claim = repository.get("callback_claim", claim_id)
        if (claim.get("outer_operation_digest") != hashlib.sha256(operation_id.encode()).hexdigest()
                or claim.get("call_digest") != complete[0].action_digest
                or claim.get("request_digest") != bundle["request_digest"]
                or claim.get("binding_digest") != bundle["callback_binding_digest"]
                or claim.get("operation_reference") != charged_operation_digest
                or claim.get("context_kind") != "conformance"
                or claim.get("model_turn_allowance") != 1):
            raise ConfigurationError("native callback claim is not charged to this exact reserved operation")
        observed = {
            "callback_origin": "native_app_server",
            "native_callback_observed": bool(
                len(complete) == 1 and len(links) == 1 and evidence.complete
                and receipt.accounting.model_usage
                and receipt.metadata.get("model_turn_count") == 1
                and receipt.metadata.get("dynamic_cleanup_confirmed") is True),
        }
        if (not outcome.ok or receipt.status is not ExecutionStatus.SUCCESS
                or observed != definition.expected):
            raise ConfigurationError("actual host-issued callback observation failed")
        journal = EventJournal(evidence.attempt_id)
        for event in evidence.events:
            if event.kind not in {"execution.completed", "execution.failed"}:
                journal.append(event.kind, event.source_id, action_digest=event.action_digest,
                    evidence_ref=event.evidence_ref, accounting=event.accounting,
                    accounting_mode=event.accounting_mode)
        journal.append("artifact.created", "composed-observation", evidence_ref=content_digest(observed))
        journal.append("execution.completed", "composed-terminal")
        canonical = journal.evidence(evidence.adapter, RawExecution(status=receipt.status,
            metadata={"host_runtime_digest": identity[1], "boundary_digest": request.worker_digest}))
        evidence_digest = repository.put("execution_evidence", content_digest(canonical), canonical)
        if not charged_operation_digest:
            raise ConfigurationError("current callback operation-start binding is unavailable")
        probe = BoundaryProbe(schema_version="assessment.boundary-probe.v2",
            probe_id=new_id("composed-probe"), name=definition.name,
            implementation_digest=bundle["probe_definition_digest"], worker_digest=request.worker_digest,
            execution_evidence_digest=evidence_digest, host_receipt_digest=host_digest, observed=observed,
            charged_operation_digest=charged_operation_digest)
        probe_digest = repository.put("boundary_probe", content_digest(probe), probe)
        stage = "callback_probe_recorded"
    except BaseException as exc:
        failure_stage = stage
        error_type = type(exc).__name__
        failure = exc
    finally:
        try:
            if scoped is not None:
                attempt_digests, receipt_digests, partial = _persist_scoped(repository, scoped, action.action_id)
                if receipt is None and partial is not None:
                    receipt = partial
                    host_digest = receipt_digests[0] if len(receipt_digests) == 1 else None
            async with asyncio.timeout_at(deadline + 5):
                if scoped is not None:
                    await scoped.close()
                cleanup_confirmed = adapter is not None and await _confirm_worker_cleanup(adapter)
            if scoped is not None and not cleanup_confirmed:
                raise ConfigurationError("owned worker/transport cleanup could not be confirmed")
        except BaseException as exc:
            if error_type is None:
                error_type = type(exc).__name__
            stage = "cleanup_unconfirmed"
            if failure is None:
                failure = exc
        finally:
            if native_router is not None:
                try:
                    async with asyncio.timeout_at(deadline + 5):
                        await native_router.close()
                except BaseException as exc:
                    if error_type is None:
                        error_type = type(exc).__name__
                    stage = "native_router_close_unconfirmed"
                    if failure is None:
                        failure = exc
            elapsed = time.perf_counter() - started
            if reserved:
                try:
                    repository.finish_operation(operation_id, elapsed_seconds=elapsed,
                        accounting=receipt.accounting if receipt is not None else None,
                        resources=receipt.actual_resources if receipt is not None else None)
                    measured = repository.get("operation_measurement", operation_id)
                    start_value = repository.get("operation_start", operation_id)
                    operation_start_digest = content_digest(start_value)
                    operation_measurement_digest = content_digest(measured)
                    operation_settled = (
                        measured.get("elapsed_seconds") is not None
                        and 0 <= measured["elapsed_seconds"] <= MAX_ELAPSED_SECONDS
                        and operation_start_digest == charged_operation_digest
                    )
                    if not operation_settled:
                        raise RuntimeError("callback operation exceeded or missed its exact measured allowance")
                except BaseException as exc:
                    if error_type is None:
                        error_type = type(exc).__name__
                    stage = "operation_finish_unconfirmed"
                    if failure is None:
                        failure = exc
            source_unchanged = verification_source_digest(ROOT) == SOURCE
            record = {
                "schema_version": "assessment.live-delay-diagnostic-result.v1",
                "request_id": request.plan_id, "request_digest": bundle["request_digest"],
                "review_sha256": review_sha256,
                "operation_id": operation_id, "source_digest": SOURCE,
                "stage": stage, "error_type": error_type,
                "failure_stage": failure_stage,
                "failure_summary": f"{failure_stage}:{error_type}" if failure_stage else None,
                "canonical_result_error_type": None,
                "worker_digest": EXPECTED_WORKER,
                "callback_binding_digest": bundle["callback_binding_digest"],
                "capacity_result_sha256": bundle["capacity_result_sha256"],
                "capacity_age_seconds_at_start": capacity_age_at_start,
                "host_receipt_digest": host_digest, "evidence_digest": evidence_digest,
                "probe_digest": probe_digest, "charged_operation_digest": charged_operation_digest,
                "operation_start_digest": operation_start_digest,
                "operation_measurement_digest": operation_measurement_digest,
                "operation_settled": operation_settled,
                "result_status": "passed" if (failure is None and probe_digest is not None
                    and cleanup_confirmed and operation_settled and source_unchanged
                    and 0 <= elapsed <= MAX_ELAPSED_SECONDS) else "failed",
                "task_scope_id": scope_binding.scope_id, "task_scope_digest": task_scope_digest,
                "outer_attempt_digests": attempt_digests,
                "outer_receipt_digests": receipt_digests,
                "model_turns_reserved": 1, "model_turn_count_observed": (
                    receipt.metadata.get("model_turn_count") if receipt is not None else None),
                "cash_ceiling_usd": 0, "cash_cost_usd": None,
                "cleanup_confirmed": cleanup_confirmed,
                "source_unchanged": source_unchanged,
                "full_conformance": False, "qualification": False, "admission": False,
                "diagnostic_only": True, "holdout": False,
                "input_digest": FIXTURE_INPUT_DIGEST,
                "outer_database": str(fresh_database),
                "host_receipt_status": receipt.status.value if receipt is not None else None,
                "host_execution_success": receipt.execution_success if receipt is not None else None,
                "host_progress": receipt.metadata.get("host_progress") if receipt is not None else None,
                "host_failure_code": receipt.metadata.get("host_failure_code") if receipt is not None else None,
                "partial_execution_evidence_digest": receipt.metadata.get("execution_evidence_digest") if receipt is not None else None,
                "host_accounting": receipt.accounting.model_dump(mode="json") if receipt is not None else None,
                "host_resources": receipt.actual_resources.model_dump(mode="json") if receipt is not None else None,
                "value_trial": False, "payload_recorded": False,
                "elapsed_seconds": elapsed,
            }
            try:
                repository.put("composed_runner_result", operation_id,
                    _load_result_model(record))
            except BaseException as exc:
                record["canonical_result_error_type"] = type(exc).__name__
                record["error_type"] = type(exc).__name__
                record["stage"] = "canonical_result_persistence_unconfirmed"
            _atomic_json(RESULT, record)
    if failure is not None:
        raise failure
    if (record["error_type"] is not None or record["source_unchanged"] is not True
            or record.get("canonical_result_error_type") is not None):
        raise RuntimeError("callback probe did not finish with a source-stable result")
    return record


def _load_result_model(value: dict[str, Any]):
    from aeep.models import StrictModel

    class RunnerResult(StrictModel):
        schema_version: str
        request_id: str
        request_digest: str
        review_sha256: str
        operation_id: str
        source_digest: str
        stage: str
        error_type: str | None
        failure_stage: str | None
        failure_summary: str | None
        canonical_result_error_type: str | None
        worker_digest: str
        callback_binding_digest: str
        capacity_result_sha256: str
        capacity_age_seconds_at_start: float
        host_receipt_digest: str | None
        evidence_digest: str | None
        probe_digest: str | None
        charged_operation_digest: str | None
        operation_start_digest: str | None
        operation_measurement_digest: str | None
        operation_settled: bool
        result_status: str
        task_scope_id: str
        task_scope_digest: str | None
        outer_attempt_digests: list[str]
        outer_receipt_digests: list[str]
        model_turns_reserved: int
        model_turn_count_observed: int | None
        cash_ceiling_usd: int
        cash_cost_usd: float | None
        cleanup_confirmed: bool
        source_unchanged: bool
        full_conformance: bool
        qualification: bool
        admission: bool
        diagnostic_only: bool
        holdout: bool
        input_digest: str
        outer_database: str
        host_receipt_status: str | None
        host_execution_success: bool | None
        host_progress: str | None
        host_failure_code: str | None
        partial_execution_evidence_digest: str | None
        host_accounting: dict[str, Any] | None
        host_resources: dict[str, Any] | None
        value_trial: bool
        payload_recorded: bool
        elapsed_seconds: float

    return RunnerResult.model_validate(value)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


async def execute(review_sha256: str) -> dict[str, Any]:
    """Entry point for an exact reviewed outer proxy-lifecycle supervisor."""
    from aeep.assessment.service import AssessmentService
    from aeep.router import Router

    if _sha(EXECUTION_REVIEW) != review_sha256:
        raise RuntimeError("exact separately reviewed one-turn execution bundle required")
    router = Router.from_manifest(CANONICAL_MANIFEST)
    try:
        service = AssessmentService(router, CANONICAL_STORE)
        return await run_once(service, review_sha256)
    finally:
        await router.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-reviewed-sha256", required=True)
    args = parser.parse_args()
    try:
        result = asyncio.run(execute(args.execute_reviewed_sha256))
    except BaseException as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "result_path": str(RESULT), "started_path": str(STARTED)}, sort_keys=True))
        raise SystemExit(1) from None
    print(json.dumps({"status": "completed", "stage": result["stage"],
                      "probe_digest": result["probe_digest"],
                      "cleanup_confirmed": result["cleanup_confirmed"],
                      "source_unchanged": result["source_unchanged"],
                      "full_conformance": False}, sort_keys=True))


if __name__ == "__main__":
    main()
