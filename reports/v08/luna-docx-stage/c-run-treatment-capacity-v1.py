"""One reviewed rate-limit snapshot on the exact current C treatment binding."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

from aeep.assessment.containment import container_name
from aeep.assessment.identity import file_digest, verify_dependencies
from aeep.assessment.models import AssessmentLimits, AssessmentPlanningRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.capacity.models import CapacityObservation
from aeep.hosts.codex_app_server import CodexAppServerAdapter
from aeep.hosts.codex_pair_inspection import docker
from aeep.hosts.workers import binding_from_config
from aeep.models import ExecutorSpec
from aeep.router import Router

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE = "50de999eb8fcd15ffef056c6b67db9f1dc0e491a3b32a3f236bbd81cd52651f7"
PROFILE = OUT / "c-current-profile-v1.json"
PROFILE_SHA256 = "8d3f49299452a7b4ea1e8cbc46abcd6ef8b81989ca24e131b35fbc8ed6bcd449"
COMPONENT_RESULT = OUT / "c-worker-components-result-v1.json"
BASE_REVIEW = OUT / "c-worker-components-execution-review-v1.json"
BASE_PREPARATION = OUT / "c-worker-components-preparation-v1.json"
MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
REQUEST_PATH = OUT / "c-treatment-capacity-request.json"
REVIEW_PATH = OUT / "c-treatment-capacity-review.json"
RESULT_PATH = OUT / "c-treatment-capacity-result.json"
ONCE_PATH = OUT / "c-treatment-capacity-once.json"
PLAN_ID = "planning_c_treatment_capacity_50de_19027f56_20261003"
MAX_SECONDS = 60
MAX_AGE_SECONDS = 1800


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


COMPONENT_RESULT_SHA256 = _sha(COMPONENT_RESULT) if COMPONENT_RESULT.is_file() else None
BASE_REVIEW_SHA256 = _sha(BASE_REVIEW) if BASE_REVIEW.is_file() else None
BASE_PREPARATION_SHA256 = _sha(BASE_PREPARATION) if BASE_PREPARATION.is_file() else None


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _check_canonical_store(review: dict[str, object]) -> dict[str, object]:
    expected = review.get("canonical_store")
    if not isinstance(expected, dict):
        raise RuntimeError("canonical store identity is not pinned in the capacity review")
    database = Path(str(expected.get("database", "")))
    manifest_path = Path(str(expected.get("manifest", "")))
    if (manifest_path != MANIFEST or manifest_path.is_symlink()
            or not manifest_path.is_file() or _sha(manifest_path) != expected.get("manifest_sha256")
            or database != ROOT / ".aeep/live-review-v3/aeep.sqlite3"
            or database.is_symlink() or not database.is_file()):
        raise RuntimeError("canonical manifest/database path or digest changed")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("database") != str(database):
        raise RuntimeError("canonical manifest database path differs")
    stat = database.stat()
    if stat.st_dev != expected.get("device") or stat.st_ino != expected.get("inode"):
        raise RuntimeError("canonical database device/inode changed")
    return expected


def _check_files() -> tuple[dict[str, object], dict[str, object]]:
    if verification_source_digest(ROOT) != SOURCE:
        raise RuntimeError("frozen source changed")
    if (_sha(PROFILE) != PROFILE_SHA256 or COMPONENT_RESULT_SHA256 is None or BASE_REVIEW_SHA256 is None or BASE_PREPARATION_SHA256 is None
            or _sha(COMPONENT_RESULT) != COMPONENT_RESULT_SHA256
            or _sha(BASE_REVIEW) != BASE_REVIEW_SHA256
            or _sha(BASE_PREPARATION) != BASE_PREPARATION_SHA256):
        raise RuntimeError("profile, component result or base review changed")
    review = json.loads(REVIEW_PATH.read_text())
    request_record = json.loads(REQUEST_PATH.read_text())
    profile = json.loads(PROFILE.read_text())
    expected_worker = profile.get("selected_worker_digest")
    if review.get("execution_authorized") is not False:
        raise RuntimeError("preparation review must remain non-executing")
    if (review.get("source_digest") != SOURCE or review.get("stage") != "capacity_introspection"
            or review.get("request_id") != PLAN_ID or review.get("worker_digest") != expected_worker
            or review.get("profile_sha256") != PROFILE_SHA256
            or review.get("component_result_sha256") != COMPONENT_RESULT_SHA256
            or review.get("base_review_sha256") != BASE_REVIEW_SHA256
            or review.get("base_preparation_sha256") != BASE_PREPARATION_SHA256
            or review.get("resource_id") != "codex.self" or review.get("method") != "account/rateLimits/read"
            or review.get("maximum_operations") != 1 or review.get("maximum_model_turns") != 0
            or review.get("maximum_elapsed_seconds") != MAX_SECONDS
            or review.get("cash_ceiling_usd") != 0 or review.get("max_age_seconds") != MAX_AGE_SECONDS
            or review.get("proxy_lifecycle_owned_here") is not False):
        raise RuntimeError("capacity preparation review scope differs")
    if _sha(REQUEST_PATH) != review.get("request_file_sha256"):
        raise RuntimeError("prepared request file changed")
    if (request_record.get("request_digest") != review.get("request_digest")
            or request_record.get("definition_digest") != review.get("definition_digest")
            or request_record.get("stage") != "capacity_introspection"
            or request_record.get("operation_id") != review.get("operation_id")
            or review.get("prepare_script_sha256") != file_digest(OUT / "c-prepare-treatment-capacity-v1.py")
            or review.get("runner_sha256") != file_digest(Path(__file__).resolve())):
        raise RuntimeError("exact request or wrapper source differs from the prepared review")
    _check_canonical_store(review)
    return review, request_record


async def _run(review: dict[str, object], request_record: dict[str, object]) -> dict[str, object]:
    profile = json.loads(PROFILE.read_text())
    components = json.loads(COMPONENT_RESULT.read_text())
    spec = ExecutorSpec.model_validate(profile["component"]["composed"]["treatment"])
    config = spec.managed_host_config()
    worker = binding_from_config(config.managed_worker)
    expected_worker = profile.get("selected_worker_digest")
    treatment_evidence = components["workers"]["treatment"]
    request = AssessmentPlanningRequest.model_validate(request_record["request"])
    if (content_digest(request) != review.get("request_digest")
            or request.plan_id != PLAN_ID or request.authorization_id != "onboarding"
            or request.mapping_digest != review.get("definition_digest")
            or request.planner.id != spec.id or content_digest(request.planner) != content_digest(spec)
            or worker.digest() != expected_worker or spec.id != "b.luna.aeep"
            or spec.resource_pool != "codex.self"
            or treatment_evidence.get("worker_digest") != expected_worker
            or treatment_evidence.get("cleanup_confirmed") is not True
            or treatment_evidence.get("component_probes_match") is not True
            or components.get("source_unchanged") is not True):
        raise RuntimeError("request no longer binds the observed current C treatment worker")
    if content_digest(request_record["definition"]) != review.get("definition_digest"):
        raise RuntimeError("capacity definition digest differs")
    verify_dependencies(request.executable_dependencies)

    router = Router.from_manifest(MANIFEST)
    repository = AssessmentRepository(router.store)
    try:
        canonical_request = AssessmentPlanningRequest.model_validate(
            repository.get("planning_request", request.plan_id)
        )
        if content_digest(canonical_request) != content_digest(request):
            raise RuntimeError("canonical request differs from exact reviewed request")
        repository.authorize(request)
    except BaseException:
        try:
            async with asyncio.timeout(5):
                await router.close()
        except BaseException:
            pass
        raise
    adapter = None
    observation: CapacityObservation | None = None
    error_type: str | None = None
    cleanup_confirmed = False
    worker_process_id: str | None = None
    started = time.perf_counter()
    deadline = asyncio.get_running_loop().time() + MAX_SECONDS
    operation_id = str(review["operation_id"])
    capacity_digest: str | None = None
    reserved = False
    try:
        if RESULT_PATH.exists() or ONCE_PATH.exists():
            raise RuntimeError("one-shot result or marker already exists")
        repository.reserve(
            request,
            operation_id,
            AssessmentLimits(
                max_operations=1,
                max_model_turns=0,
                max_elapsed_seconds=MAX_SECONDS,
                max_cash_usd=0,
            ),
            stage="capacity_introspection",
        )
        reserved = True
        _atomic_json(ONCE_PATH, {
            "operation_id": operation_id,
            "request_digest": content_digest(request),
            "review_sha256": _sha(REVIEW_PATH),
            "replay_allowed": False,
        })
        async with asyncio.timeout_at(deadline - 8):
            adapter = CodexAppServerAdapter.from_executor(
                spec,
                principal_salt=b"capacity-snapshot-does-not-read-identity",
                manifest_directory=ROOT,
            )
            worker_process_id = adapter._worker_process_id
            await adapter.transport.start()
            observation = await adapter.snapshot_capacity()
            if observation.resource_id != "codex.self":
                raise RuntimeError("capacity resource differs from the reviewed treatment resource")
            router.store.save_capacity_observation(observation)
            capacity_digest = observation.canonical_digest
    except BaseException as exc:
        error_type = type(exc).__name__
    finally:
        if adapter is not None:
            try:
                async with asyncio.timeout_at(deadline):
                    await adapter.close()
            except BaseException as exc:
                if error_type is None:
                    error_type = type(exc).__name__
            try:
                if worker_process_id is not None and adapter._worker is not None:
                    async with asyncio.timeout_at(deadline):
                        remaining = await docker(
                            adapter._worker,
                            "ps", "-a", "--filter",
                            "name=^/" + container_name(worker_process_id) + "$",
                            "--format", "{{.ID}}",
                        )
                        process = adapter.transport._process
                        cleanup_confirmed = (
                            remaining.strip() == ""
                            and (process is None or process.returncode is not None)
                            and not adapter.transport._dynamic_tasks
                        )
            except BaseException as exc:
                if error_type is None:
                    error_type = type(exc).__name__

        elapsed = time.perf_counter() - started
        try:
            if reserved:
                repository.finish_operation(operation_id, elapsed_seconds=elapsed)
        except BaseException as exc:
            if error_type is None:
                error_type = type(exc).__name__
        source_unchanged = verification_source_digest(ROOT) == SOURCE
        output: dict[str, object] = {
            "schema_version": "aeep.capacity-refresh-result.v1",
            "status": "passed" if (observation is not None and cleanup_confirmed
                                    and source_unchanged and error_type is None) else "failed",
            "source_digest": SOURCE,
            "profile_path": str(PROFILE),
            "profile_sha256": PROFILE_SHA256,
            "component_result_path": str(COMPONENT_RESULT),
            "component_result_sha256": COMPONENT_RESULT_SHA256,
            "stage": "capacity_introspection",
            "method": "account/rateLimits/read",
            "operation_id": operation_id,
            "plan_id": request.plan_id,
            "request_digest": content_digest(request),
            "definition_digest": request.mapping_digest,
            "component_request_id": treatment_evidence.get("request_id"),
            "component_execution_evidence_digest": treatment_evidence.get("execution_evidence_digest"),
            "component_identity_digest": treatment_evidence.get("identity_digest"),
            "executor_id": spec.id,
            "adapter_id": config.adapter_id,
            "worker_digest": worker.digest(),
            "worker_process_id": worker_process_id,
            "container_name": container_name(worker_process_id) if worker_process_id else None,
            "capacity": observation.model_dump(mode="json") if observation else None,
            "capacity_digest": capacity_digest,
            "capacity_max_age_seconds": MAX_AGE_SECONDS,
            "elapsed_seconds": elapsed,
            "max_operations_reserved": 1,
            "max_model_turns_reserved": 0,
            "model_turns": 0,
            "cash_ceiling_usd": 0,
            "actual_cash_cost_usd": None,
            "subscription_usage": "unknown; not read by this operation",
            "host_receipt_applicable": False,
            "host_receipt_digest": None,
            "execution_evidence_digest": None,
            "cleanup_confirmed": cleanup_confirmed,
            "proxy_lifecycle_owned_here": False,
            "source_unchanged": source_unchanged,
            "error_type": error_type,
            "replay_allowed": False,
        }
        if reserved:
            try:
                started_record = repository.get("operation_start", operation_id)
                measured_record = repository.get("operation_measurement", operation_id)
                output["operation_start_digest"] = content_digest(started_record)
                output["operation_measurement_digest"] = content_digest(measured_record)
            except BaseException as exc:
                output["lineage_error_type"] = type(exc).__name__
                if error_type is None:
                    error_type = type(exc).__name__
                output["error_type"] = error_type
        try:
            async with asyncio.timeout_at(deadline):
                await router.close()
        except BaseException as exc:
            output["router_close_error_type"] = type(exc).__name__
            if error_type is None:
                error_type = type(exc).__name__
                output["error_type"] = error_type
        if (error_type is not None or output.get("lineage_error_type") is not None
                or not cleanup_confirmed or not source_unchanged
                or not 0 <= elapsed <= MAX_SECONDS):
            output["status"] = "failed"
        _atomic_json(RESULT_PATH, output)
    return output


async def execute(review_sha256: str) -> dict[str, object]:
    """Entry for the outer exact reviewed proxy lifecycle wrapper; no direct CLI."""
    if _sha(REVIEW_PATH) != review_sha256:
        raise RuntimeError("prepared review hash differs from the outer reviewed launcher")
    review, request_record = _check_files()
    return await _run(review, request_record)


if __name__ == "__main__":
    raise SystemExit("invoke only through the exact reviewed proxy lifecycle wrapper")
