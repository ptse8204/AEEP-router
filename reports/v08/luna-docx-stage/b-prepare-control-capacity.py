"""Prepare one exact, zero-turn control-worker capacity request."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from pydantic import Field

from aeep.assessment.identity import file_digest
from aeep.assessment.models import (
    AssessmentPlanningRequest,
    ConformanceProbeRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.workers import binding_from_config
from aeep.models import ExecutorSpec, StrictModel
from aeep.router import Router

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE = "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
PROFILE = OUT / "b-current-profile-v2.json"
PROFILE_SHA256 = "28ed2a514083beda4ef3fc1fbcfa6320f5fabe2b8dcde74dddac7d7bb489c79a"
COMPONENT_RESULT = OUT / "b-worker-components-v2-result.json"
COMPONENT_RESULT_SHA256 = "0552cf86620985194c5bd9d1252e88819667730ff9004efc1b82510b98696379"
BASE_REVIEW = OUT / "b-worker-components-execution-review-v3.json"
BASE_REVIEW_SHA256 = "d4215be9e3d202f6e1e32fb1d0cfb22d6646def742e72d36ba2018333c43a21c"
BASE_PREPARATION = OUT / "b-worker-components-preparation-v2.json"
BASE_PREPARATION_SHA256 = "478b6a11c660dd2e2b5cc6e6d6f9bdef51580fd8d5657b9dc9f8cd20da69192d"
CONTROL_WORKER_DIGEST = "e15b7ee0ecabb077cc64ba80f724c739bc51bda8dc71d4038efc92f7678df345"
MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
PREPARE_PATH = Path(__file__).resolve()
RUN_PATH = OUT / "b-run-control-capacity.py"
REQUEST_PATH = OUT / "b-control-capacity-request.json"
REVIEW_PATH = OUT / "b-control-capacity-review.json"
PLAN_ID = "planning_b_control_capacity_449b_e15b7ee0"
DEFINITION_ID = "b-control-capacity-449b-e15b7ee0"
MAX_SECONDS = 60
MAX_AGE_SECONDS = 1800


class CapacityRefreshDefinition(StrictModel):
    schema_version: str = "aeep.capacity-refresh-definition.v1"
    source_digest: str
    base_request_digest: str
    profile_sha256: str
    component_result_sha256: str
    base_preparation_sha256: str
    prepare_script_sha256: str
    runner_sha256: str
    executor_id: str
    adapter_id: str
    worker_digest: str
    resource_id: str
    method: str = "account/rateLimits/read"
    max_age_seconds: int = Field(default=1800, ge=1, le=3600)
    maximum_operations: int = 1
    maximum_model_turns: int = 0
    maximum_elapsed_seconds: int = 60
    cash_ceiling_usd: int = 0
    task_turn: bool = False
    auth_state_access: bool = False
    proxy_lifecycle_owned_here: bool = False


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_dependencies() -> dict[str, str]:
    paths = (
        ROOT / "src/aeep/assessment/identity.py",
        ROOT / "src/aeep/assessment/models.py",
        ROOT / "src/aeep/assessment/repository.py",
        ROOT / "src/aeep/assessment/verification.py",
        ROOT / "src/aeep/capacity/models.py",
        ROOT / "src/aeep/hosts/codex_accounting.py",
        ROOT / "src/aeep/hosts/codex_app_server.py",
        ROOT / "src/aeep/hosts/codex_pair_inspection.py",
        ROOT / "src/aeep/hosts/workers.py",
        ROOT / "src/aeep/router.py",
        ROOT / "src/aeep/store.py",
        PROFILE,
        COMPONENT_RESULT,
        BASE_REVIEW,
        BASE_PREPARATION,
        PREPARE_PATH,
        RUN_PATH,
    )
    return {str(path): file_digest(path) for path in paths}


def _write_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    temporary.replace(path)


def _check_canonical_store(base_review: dict[str, object]) -> dict[str, object]:
    expected = base_review.get("canonical_store")
    if not isinstance(expected, dict):
        raise SystemExit("pinned canonical store identity is absent")
    database = Path(str(expected.get("database", "")))
    manifest_path = Path(str(expected.get("manifest", "")))
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    if (manifest_path != MANIFEST or manifest_path.is_symlink()
            or not manifest_path.is_file() or _sha(manifest_path) != expected.get("manifest_sha256")
            or database != ROOT / ".aeep/live-review-v3/aeep.sqlite3"
            or manifest.get("database") != str(database)
            or database.is_symlink() or not database.is_file()):
        raise SystemExit("canonical manifest/database path or digest changed")
    stat = database.stat()
    if (stat.st_dev != expected.get("device") or stat.st_ino != expected.get("inode")):
        raise SystemExit("canonical database device/inode changed")
    return expected


async def main() -> None:
    if verification_source_digest(ROOT) != SOURCE:
        raise SystemExit("frozen source digest changed")
    for path in (PROFILE, COMPONENT_RESULT, BASE_REVIEW, BASE_PREPARATION, RUN_PATH):
        if not path.is_file():
            raise SystemExit("a reviewed input or runner is missing")
    if REQUEST_PATH.exists() or REVIEW_PATH.exists():
        raise SystemExit("prepared capacity request already exists; no replay")
    if (_sha(PROFILE) != PROFILE_SHA256 or _sha(COMPONENT_RESULT) != COMPONENT_RESULT_SHA256
            or _sha(BASE_REVIEW) != BASE_REVIEW_SHA256
            or _sha(BASE_PREPARATION) != BASE_PREPARATION_SHA256):
        raise SystemExit("current profile, component result or base review changed")

    profile = json.loads(PROFILE.read_text())
    components = json.loads(COMPONENT_RESULT.read_text())
    base_review = json.loads(BASE_REVIEW.read_text())
    base_preparation = json.loads(BASE_PREPARATION.read_text())
    canonical_store = _check_canonical_store(base_review)
    control = ExecutorSpec.model_validate(profile["component"]["composed"]["control"])
    config = control.managed_host_config()
    worker = binding_from_config(config.managed_worker)
    worker_digest = worker.digest()
    control_evidence = components["workers"]["control"]
    callback_bindings = profile["component"]["composed"].get("callback_bindings", {})
    base = ConformanceProbeRequest.model_validate(base_preparation["requests"][0])
    if (profile.get("source_digest") != SOURCE
            or profile.get("component_digest") != components.get("component_digest")
            or components.get("component_digest") != base_review.get("component_digest")
            or base_review.get("source_digest") != SOURCE
            or base_review.get("request_ids", [None])[0] != base.plan_id
            or base_preparation.get("source_digest") != SOURCE
            or base_preparation.get("component_digest") != components.get("component_digest")
            or base.plan_id != "conformance_probe_6be2797fa71d4134ba4b1611ee460ab7"
            or base.worker_digest != CONTROL_WORKER_DIGEST
            or worker_digest != CONTROL_WORKER_DIGEST
            or CONTROL_WORKER_DIGEST not in callback_bindings
            or control.id != "b.luna.discovery" or control.resource_pool != "codex.self"
            or control_evidence.get("worker_digest") != worker_digest
            or control_evidence.get("cleanup_confirmed") is not True
            or control_evidence.get("component_probes_match") is not True
            or control_evidence.get("model_turns") != 0
            or components.get("source_unchanged") is not True
            or components.get("component_evidence_only") is not True
            or components.get("full_conformance") is not False):
        raise SystemExit("current control binding/component evidence does not match")

    if (content_digest(base) != content_digest(base_preparation["requests"][0])
            or base.worker_digest != worker_digest
            or base_review.get("source_digest") != SOURCE):
        raise SystemExit("base request is not the exact current control-worker binding")

    router = Router.from_manifest(MANIFEST)
    try:
        repository = AssessmentRepository(router.store)
        canonical_base = ConformanceProbeRequest.model_validate(
            repository.get("conformance_request", base.plan_id)
        )
        if content_digest(canonical_base) != content_digest(base):
            raise SystemExit("canonical base request differs from reviewed record")
        repository.authorize(canonical_base)

        dependencies = _runtime_dependencies()
        definition = CapacityRefreshDefinition(
            source_digest=SOURCE,
            base_request_digest=content_digest(base),
            profile_sha256=PROFILE_SHA256,
            component_result_sha256=COMPONENT_RESULT_SHA256,
            base_preparation_sha256=BASE_PREPARATION_SHA256,
            prepare_script_sha256=file_digest(PREPARE_PATH),
            runner_sha256=file_digest(RUN_PATH),
            executor_id=control.id,
            adapter_id=config.adapter_id,
            worker_digest=worker_digest,
            resource_id=control.resource_pool or "",
        )
        definition_digest = repository.put(
            "capacity_refresh_definition", DEFINITION_ID, definition
        )
        repository.review(definition_digest)
        request = AssessmentPlanningRequest(
            plan_id=PLAN_ID,
            subject_digest=base.subject_digest,
            recipe_digest=base.recipe_digest,
            mapping_digest=definition_digest,
            environment_digest=base.environment_digest,
            authorization_id=base.authorization_id,
            definition_digests=list(dict.fromkeys([
                *base.definition_digests,
                base.subject_digest,
                base.recipe_digest,
                base.environment_digest,
                definition_digest,
            ])),
            planner=control,
            executable_dependencies=dependencies,
        )
        request_digest = repository.put("planning_request", request.plan_id, request)
        repository.review(request_digest)
        repository.authorize(request)
        operation_id = "capacity:" + request.plan_id
        request_record = {
            "schema_version": "aeep.capacity-refresh-request.v1",
            "definition": definition.model_dump(mode="json"),
            "definition_digest": definition_digest,
            "request": request.model_dump(mode="json"),
            "request_digest": request_digest,
            "operation_id": operation_id,
            "stage": "capacity_introspection",
        }
        _write_json(REQUEST_PATH, request_record)
        review = {
            "schema_version": "aeep.capacity-refresh-review.v1",
            "authority": "standing finite assessment-definition delegation; existing onboarding only",
            "source_digest": SOURCE,
            "profile_path": str(PROFILE),
            "profile_sha256": PROFILE_SHA256,
            "component_result_path": str(COMPONENT_RESULT),
            "component_result_sha256": COMPONENT_RESULT_SHA256,
            "base_review_path": str(BASE_REVIEW),
            "base_review_sha256": BASE_REVIEW_SHA256,
            "base_preparation_path": str(BASE_PREPARATION),
            "base_preparation_sha256": BASE_PREPARATION_SHA256,
            "base_request_id": base.plan_id,
            "base_request_digest": content_digest(base),
            "canonical_store": canonical_store,
            "request_path": str(REQUEST_PATH),
            "request_file_sha256": _sha(REQUEST_PATH),
            "request_id": request.plan_id,
            "request_digest": request_digest,
            "definition_digest": definition_digest,
            "operation_id": operation_id,
            "stage": "capacity_introspection",
            "executor_id": control.id,
            "adapter_id": config.adapter_id,
            "worker_digest": worker_digest,
            "resource_id": control.resource_pool,
            "method": "account/rateLimits/read",
            "max_age_seconds": MAX_AGE_SECONDS,
            "maximum_operations": 1,
            "maximum_model_turns": 0,
            "maximum_elapsed_seconds": MAX_SECONDS,
            "cash_ceiling_usd": 0,
            "proxy_lifecycle_owned_here": False,
            "credential_policy": "No credential files, account/read, login, usage, model list, thread or turn calls.",
            "host_receipt_applicable": False,
            "execution_authorized": False,
            "replay_allowed": False,
            "prepare_script_sha256": file_digest(PREPARE_PATH),
            "runner_sha256": file_digest(RUN_PATH),
            "executable_dependencies": dependencies,
        }
        _write_json(REVIEW_PATH, review)
        print(json.dumps({
            "status": "prepared_and_reviewed",
            "role": "control",
            "request_id": request.plan_id,
            "request_digest": request_digest,
            "worker_digest": worker_digest,
            "review_path": str(REVIEW_PATH),
            "review_sha256": _sha(REVIEW_PATH),
            "execution_authorized": False,
        }, sort_keys=True))
    finally:
        await router.close()


if __name__ == "__main__":
    asyncio.run(main())
