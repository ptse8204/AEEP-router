"""Report-local, inert bridge from a qualification plan to its reviewed callback.

This module adds no runtime capability.  The operator runner must bind its
exact bytes and prepare the task scopes before enqueueing the reviewed plan.
Importing it does not read credentials, start a worker, or mutate a store.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import math
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from aeep.assessment.models import (
    AssessmentLimits,
    AssessmentOperation,
    AssessmentPlan,
    AssessmentRunBinding,
    ReviewedMapping,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.benchmarking import AssessmentBenchmarkCondition, BenchmarkSplit
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_app_server import CodexAppServerAdapter
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import (
    ExecutorSpec,
    Manifest,
    ResourceVector,
    SideEffect,
    TaskScope,
    utc_now,
)
from aeep.router import Router

ROOT = Path(__file__).resolve().parents[3]
STAGE = Path(__file__).resolve().parent
SOURCE_DIGEST = "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
PROFILE_PATH = STAGE / "b-current-profile-v2.json"
PROFILE_SHA256 = "28ed2a514083beda4ef3fc1fbcfa6320f5fabe2b8dcde74dddac7d7bb489c79a"
NATIVE_SETUP_PATH = STAGE / "b-native-setup-v3-result.json"
NATIVE_SETUP_SHA256 = "45f2344b74181d79ca284c8d3d3adc3d8d73a3c9edd1ccc51ef6993ed2968752"
NATIVE_MANIFEST_SHA256 = "11707d498ce6a285c85c0e7c90314e9f24ff355e1be987021898896e9e920d60"
COMPOSITION_PATH = STAGE.parent / "original-three-way-profile" / "native-dynamic-operator-composition.py"
COMPOSITION_SHA256 = "d158ed54641e062f2a2d484fd0f5ebc212fccaee25e4186b56ccf1a3395d9c8a"
PRODUCER_PATH = STAGE / "b-native-workbook-producer-final.py"
PRODUCER_SHA256 = "4d5db1fd761882f90bbaff5d1a6c392e2bab185a248f4a981399f95ee8aa539d"
SCOPE_SETUP_STAGE = "workbook_trial_task_scopes"
SCOPE_SETUP_SECONDS = 600.0
SCOPE_EXPIRY_GRACE_SECONDS = 900
TASK_ATTEMPTS = 1
TASK_SECONDS = 10.0


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require_frozen_inputs() -> dict[str, Any]:
    """Check only the report-local profile/setup metadata and source pin."""
    if verification_source_digest(ROOT) != SOURCE_DIGEST:
        raise ValueError("qualification composition source pin changed")
    if _sha256(PROFILE_PATH) != PROFILE_SHA256:
        raise ValueError("current B profile pin changed")
    if _sha256(NATIVE_SETUP_PATH) != NATIVE_SETUP_SHA256:
        raise ValueError("native workbook setup result pin changed")
    if _sha256(COMPOSITION_PATH) != COMPOSITION_SHA256:
        raise ValueError("dynamic composition implementation pin changed")
    if _sha256(PRODUCER_PATH) != PRODUCER_SHA256:
        raise ValueError("native workbook producer implementation pin changed")
    profile = json.loads(PROFILE_PATH.read_text())
    setup = json.loads(NATIVE_SETUP_PATH.read_text())
    project = Path(profile["native_project"]).resolve(strict=True)
    if (str(project) != profile["native_project"]
            or str(project) != setup["project"]
            or setup.get("setup_complete") is not True
            or _sha256(project / "aeep.json") != NATIVE_MANIFEST_SHA256
            or profile.get("selected_worker_digest")
            != profile["callback_documents_by_role"]["treatment"]["identity"].get("worker_digest")):
        raise ValueError("current B profile/native project binding differs")
    return profile


def qualification_trial_ids(plan: AssessmentPlan) -> list[str]:
    """Derive the exact outer operation IDs without reading case payloads."""
    if not isinstance(plan, AssessmentPlan):
        raise ValueError("a frozen, digest-valid AssessmentPlan is required")
    experiment = plan.comparison.experiment if plan.comparison is not None else None
    suite = plan.suite
    if (experiment is None or experiment.stage != "qualification"
            or experiment.exposure != "required" or plan.blocked_reasons
            or suite.suite_id != plan.plan_id or suite.repetitions != 1
            or suite.conditions != [AssessmentBenchmarkCondition.FRESH_WORKER]
            or not suite.sequential_stages
            or [route.route_id for route in suite.routes] != [plan.candidate_id]
            or len(suite.cases) != 141):
        raise ValueError("plan is not the frozen one-route required qualification shape")
    counts = {split: sum(case.split == split for case in suite.cases)
              for split in (BenchmarkSplit.QUALIFICATION, BenchmarkSplit.TRAINING,
                            BenchmarkSplit.HOLDOUT)}
    if counts != {BenchmarkSplit.QUALIFICATION: 8, BenchmarkSplit.TRAINING: 28,
                  BenchmarkSplit.HOLDOUT: 105}:
        raise ValueError("qualification split counts differ")
    ids = [f"trial_{suite.suite_id}_{case.case_id}_{plan.candidate_id}_fresh-worker_0"
           for case in suite.cases]
    if len(ids) != len(set(ids)):
        raise ValueError("qualification trial operation identities are not unique")
    return ids


def _reviewed_native_spec(manifest_path: Path, profile: dict[str, Any]) -> tuple[ExecutorSpec, str]:
    manifest = Manifest.model_validate_json(manifest_path.read_text())
    specs = [item for item in manifest.executors if item.id == "native.composed.workbook"]
    if len(specs) != 1:
        raise ValueError("pinned native manifest lacks one workbook executor")
    spec = specs[0]
    fingerprint = executor_fingerprint(spec)
    expected = profile["callback_documents_by_role"]["treatment"]["identity"][
        "executor_fingerprints"
    ].get(spec.id)
    if fingerprint != expected:
        raise ValueError("native workbook executor differs from the reviewed callback profile")
    return spec, fingerprint


def _scope_index_digest(index: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in index.items() if key != "scope_index_digest"}
    return hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def prepare_trial_scopes(
    assessment: AssessmentService,
    plan: AssessmentPlan,
    manifest_path: Path,
    *,
    expires_at: datetime,
    campaign_end: datetime,
) -> dict[str, Any]:
    """Pre-review one new READ scope per exact trial under a finite 0-turn op.

    Call only from the separately reviewed scope-preparation runner, before
    enqueue.  A partial/uncertain setup is retained and must not be replayed.
    """
    profile = require_frozen_inputs()
    ids = qualification_trial_ids(plan)
    manifest_path = await asyncio.to_thread(Path(manifest_path).resolve, strict=True)
    project = await asyncio.to_thread(Path(profile["native_project"]).resolve, strict=True)
    if (manifest_path.parent != project or manifest_path.name != "aeep.json"
            or not await asyncio.to_thread(project.is_dir)):
        raise ValueError("native task manifest is outside the reviewed project")
    preflight_spec, expected_fp = _reviewed_native_spec(manifest_path, profile)
    stored_plan = AssessmentPlan.model_validate(
        assessment.repository.get("plan", plan.plan_id)
    )
    if content_digest(stored_plan) != content_digest(plan):
        raise ValueError("scope preparation plan differs from the reviewed canonical plan")
    with assessment.router.store._lock:
        if assessment.router.store._connection.execute(
            "SELECT 1 FROM assessment_jobs WHERE plan_id=? LIMIT 1", (plan.plan_id,)
        ).fetchone():
            raise ValueError("task scopes must be prepared before campaign enqueue")
    if (expires_at.tzinfo is None or campaign_end.tzinfo is None
            or campaign_end <= utc_now()
            or expires_at != campaign_end + timedelta(seconds=SCOPE_EXPIRY_GRACE_SECONDS)):
        raise ValueError("scope expiry must equal the finite post-campaign grace")
    grant = assessment.repository.authorize(plan)
    if expires_at > grant.expires_at:
        raise ValueError("task-scope expiry exceeds the existing authorization")
    operation_id = f"{plan.plan_id}:workbook-task-scope-preparation-v1"
    assessment.repository.reserve(
        plan,
        operation_id,
        AssessmentLimits(max_operations=1, max_model_turns=0,
                         max_elapsed_seconds=SCOPE_SETUP_SECONDS, max_cash_usd=0),
        stage=SCOPE_SETUP_STAGE,
    )
    started, cpu_started = time.monotonic(), time.process_time()
    deadline = started + SCOPE_SETUP_SECONDS

    def check_setup_deadline() -> None:
        if time.monotonic() >= deadline:
            raise TimeoutError("per-trial task-scope preparation deadline exceeded")

    task_router: Router | None = None
    result: dict[str, Any] | None = None
    failure: BaseException | None = None
    try:
        task_router = Router.from_manifest(manifest_path)
        task_repo = AssessmentRepository(task_router.store)
        spec = task_router.registry.get("native.composed.workbook")
        fp = executor_fingerprint(spec)
        if (str(project) != str(manifest_path.parent)
                or spec.model_dump(mode="json") != preflight_spec.model_dump(mode="json")
                or fp != expected_fp):
            raise ValueError("native project path changed")
        scopes: dict[str, dict[str, str]] = {}
        # Refuse a partial prior set; task scopes and grant operations are never reset.
        for trial_id in ids:
            check_setup_deadline()
            scope_id = "bqual_" + hashlib.sha256(
                f"{plan.plan_id}\0{trial_id}".encode()
            ).hexdigest()[:40]
            with task_router.store._lock:
                existing = task_router.store._connection.execute(
                    "SELECT 1 FROM assessment_records WHERE kind='task_scope' AND id=?",
                    (scope_id,),
                ).fetchone()
            if existing is not None:
                raise ValueError("a derived per-trial task scope already exists; no replay")
            scope = TaskScope(
                scope_id=scope_id,
                project_root=str(project),
                executor_fingerprints={spec.id: fp},
                approval_ceiling="read",
                max_attempts=TASK_ATTEMPTS,
                max_attempt_seconds=TASK_SECONDS,
                expires_at=expires_at,
            )
            digest = task_repo.put("task_scope", scope_id, scope)
            check_setup_deadline()
            task_repo.review(digest)
            check_setup_deadline()
            scopes[trial_id] = {"scope_id": scope_id, "scope_digest": digest}
        for trial_id, reference in scopes.items():
            scope = TaskScope.model_validate(task_repo.get("task_scope", reference["scope_id"]))
            if (content_digest(scope) != reference["scope_digest"]
                    or scope.executor_fingerprints != {spec.id: fp}
                    or scope.max_attempts != TASK_ATTEMPTS
                    or scope.max_attempt_seconds != TASK_SECONDS):
                raise ValueError(f"prepared scope failed exact binding check for {trial_id}")
        result = {
            "schema_version": "assessment.b-workbook-trial-task-scopes.v1",
            "source_digest": SOURCE_DIGEST,
            "plan_id": plan.plan_id,
            "plan_digest": content_digest(plan),
            "profile_sha256": PROFILE_SHA256,
            "native_project": str(project),
            "campaign_end": campaign_end.isoformat(),
            "scope_expiry": expires_at.isoformat(),
            "task_executor_id": spec.id,
            "task_executor_fingerprint": fp,
            "scope_count": len(scopes),
            "scopes": scopes,
            "operation_id": operation_id,
            "operation_stage": SCOPE_SETUP_STAGE,
            "operation_max_model_turns": 0,
            "operation_cash_ceiling_usd": 0,
            "replay_allowed": False,
        }
        result["operation_max_elapsed_seconds"] = SCOPE_SETUP_SECONDS
        result["scope_expiry_grace_seconds"] = SCOPE_EXPIRY_GRACE_SECONDS
        result["scope_index_digest"] = _scope_index_digest(result)
    except BaseException as exc:
        failure = exc
    finally:
        close_error: BaseException | None = None
        if task_router is not None:
            try:
                await task_router.close()
            except BaseException as exc:
                close_error = exc
        elapsed = max(0.0, time.monotonic() - started)
        try:
            assessment.repository.finish_operation(
                operation_id,
                elapsed_seconds=elapsed,
                resources=ResourceVector(
                    cpu_ms=max(0.0, (time.process_time() - cpu_started) * 1000),
                    latency_ms=elapsed * 1000,
                ),
            )
        except BaseException as exc:
            close_error = close_error or exc
        if close_error is not None:
            failure = failure or close_error
    if failure is not None:
        raise failure
    assert result is not None
    return result


class _RouterOwningAdapter:
    """Delegate the outer worker adapter; close trial task Routers at trial end."""

    def __init__(self, adapter: CodexAppServerAdapter,
                 task_routers: list[Router]) -> None:
        self._adapter = adapter
        self._task_routers = task_routers

    def __getattr__(self, name: str) -> Any:
        return getattr(self._adapter, name)

    async def close(self) -> None:
        first_error: BaseException | None = None
        try:
            await self._adapter.close()
        except BaseException as exc:
            first_error = exc
        routers, self._task_routers = self._task_routers, []
        for router in routers:
            try:
                await router.close()
            except BaseException as exc:
                first_error = first_error or exc
        if first_error is not None:
            raise first_error


def install_treatment_factory(
    assessment: AssessmentService,
    plan: AssessmentPlan,
    *,
    profile_identity: dict[str, Any],
    scope_index: dict[str, Any],
    manifest_path: Path,
    services_builder: Callable[[Router, TaskScope, ExecutorSpec, NativeSandboxConfig], tuple[Any, ...]],
) -> None:
    """Register the frozen treatment callback factory on the ordinary Router.

    `services_builder` is the existing `services` function in
    b-native-workbook-producer-final.py.  Scope creation/review is deliberately
    absent here: this factory only selects the scope for the already reserved
    canonical trial operation.  Construct the existing canonical Router from
    its ordinary coordinator manifest, before enqueue, and install this once.
    Registration adds a factory for the isolated campaign Router; it does not
    replace adapters already configured on the ordinary Router.
    The campaign deadline supplied to scope preparation must include the
    reviewed generator, grader, router/setup and all 141 trial reservations.
    """
    profile = require_frozen_inputs()
    ids = qualification_trial_ids(plan)
    composed = profile["component"]["composed"]
    if (plan.candidate_id != composed["treatment"]["id"]
            or plan.baseline_id != composed["control"]["id"]):
        raise ValueError("qualification route roles differ from the reviewed B profile")
    mapping = ReviewedMapping.model_validate(
        assessment.repository.get("mapping", plan.mapping_digest)
    )
    expected_executor_ids = {item.id for item in mapping.subjects}
    if plan.candidate_id not in expected_executor_ids:
        raise ValueError("qualification candidate is absent from its reviewed mapping")
    scope_entries = scope_index.get("scopes")
    if not isinstance(scope_entries, dict) or any(
        not isinstance(value, dict) or set(value) != {"scope_id", "scope_digest"}
        for value in scope_entries.values()
    ):
        raise ValueError("per-trial scope index entries are malformed")
    if (scope_index.get("schema_version") != "assessment.b-workbook-trial-task-scopes.v1"
            or scope_index.get("plan_digest") != content_digest(plan)
            or scope_index.get("profile_sha256") != PROFILE_SHA256
            or scope_index.get("source_digest") != SOURCE_DIGEST
            or scope_index.get("scope_count") != len(ids)
            or set(scope_entries) != set(ids)
            or scope_index.get("scope_index_digest") != _scope_index_digest(scope_index)
            or scope_index.get("operation_id")
            != f"{plan.plan_id}:workbook-task-scope-preparation-v1"
            or scope_index.get("operation_stage") != SCOPE_SETUP_STAGE
            or scope_index.get("operation_max_model_turns") != 0
            or scope_index.get("operation_max_elapsed_seconds") != SCOPE_SETUP_SECONDS
            or scope_index.get("operation_cash_ceiling_usd") != 0
            or profile_identity != profile["callback_documents_by_role"]["treatment"]["identity"]):
        raise ValueError("per-trial scopes or treatment identity are not exactly bound")
    operation = AssessmentOperation.model_validate(
        assessment.repository.get("operation_start", scope_index["operation_id"])
    )
    with assessment.router.store._lock:
        op_state = assessment.router.store._connection.execute(
            "SELECT state FROM assessment_operations WHERE id=?", (scope_index["operation_id"],)
        ).fetchone()
    measured = assessment.repository.get("operation_measurement", scope_index["operation_id"])
    measured_elapsed = measured.get("elapsed_seconds")
    if (operation.plan_id != plan.plan_id or operation.stage != SCOPE_SETUP_STAGE
            or operation.reserved.max_operations != 1
            or operation.reserved.max_model_turns != 0
            or operation.reserved.max_elapsed_seconds != SCOPE_SETUP_SECONDS
            or operation.reserved.max_cash_usd != 0
            or op_state is None or op_state[0] != "complete"
            or not isinstance(measured_elapsed, (int, float))
            or not math.isfinite(measured_elapsed) or measured_elapsed < 0
            or measured_elapsed > SCOPE_SETUP_SECONDS):
        raise ValueError("per-trial scope preparation operation is not complete under its exact bound")
    expected_expiry = datetime.fromisoformat(scope_index["scope_expiry"])
    campaign_end = datetime.fromisoformat(scope_index["campaign_end"])
    if (expected_expiry.tzinfo is None or campaign_end.tzinfo is None
            or campaign_end <= utc_now()
            or expected_expiry != campaign_end + timedelta(seconds=SCOPE_EXPIRY_GRACE_SECONDS)
            or expected_expiry > assessment.repository.authorize(plan).expires_at
            or scope_index.get("scope_expiry_grace_seconds") != SCOPE_EXPIRY_GRACE_SECONDS):
        raise ValueError("per-trial scope expiry is not the reviewed finite window")
    builder_path = Path(services_builder.__code__.co_filename).resolve(strict=True)
    if builder_path != PRODUCER_PATH or _sha256(builder_path) != PRODUCER_SHA256:
        raise ValueError("workbook service builder is not the pinned reviewed producer")
    manifest_path = Path(manifest_path).resolve(strict=True)
    project = Path(profile["native_project"]).resolve(strict=True)
    if manifest_path.parent != project or scope_index.get("native_project") != str(project):
        raise ValueError("scope index and native project differ")
    expected_scope_expiry = datetime.fromisoformat(scope_index["scope_expiry"])
    if expected_scope_expiry.tzinfo is None:
        raise ValueError("scope index expiry is not timezone-aware")
    composition_spec = importlib.util.spec_from_file_location(
        "aeep_report_native_dynamic_composition", COMPOSITION_PATH
    )
    if composition_spec is None or composition_spec.loader is None:
        raise ValueError("reviewed dynamic composition module is unavailable")
    composition = importlib.util.module_from_spec(composition_spec)
    composition_spec.loader.exec_module(composition)

    def host_factory(spec: ExecutorSpec, salt: bytes, directory: Path | None) -> Any:
        if spec.id != plan.candidate_id:
            return CodexAppServerAdapter.from_executor(
                spec, principal_salt=salt, manifest_directory=directory
            )
        config = spec.managed_host_config()
        treatment = profile["component"]["composed"]["treatment"]
        if (spec.id != treatment["id"]
                or config.adapter_id != treatment["config"]["adapter_id"]):
            raise ValueError("treatment adapter identity differs from the reviewed B profile")
        from aeep.hosts.codex_app_server import binding_from_config
        worker = binding_from_config(config.managed_worker)
        if worker is None or worker.digest() != profile["selected_worker_digest"]:
            raise ValueError("treatment worker differs from the reviewed B profile")
        run_binding = AssessmentRunBinding.model_validate(
            assessment.repository.get("run_binding", plan.plan_id)
        )
        if run_binding.source_digest != SOURCE_DIGEST:
            raise ValueError("current source-bound AssessmentRunBinding is required")
        adapter = CodexAppServerAdapter.from_executor(
            spec, principal_salt=salt, manifest_directory=directory
        )
        owned_routers: list[Router] = []

        def services_for_trial(assessment_id: str, operation_id: str) -> tuple[Any, Any]:
            if operation_id not in scope_index["scopes"] or len(owned_routers) != 0:
                raise ValueError("trial has no unique pre-reviewed task scope")
            active = assessment.status(assessment_id)
            if active.get("state") != "running" or active.get("plan_id") != plan.plan_id:
                raise ValueError("outer assessment is not running")
            operation = AssessmentOperation.model_validate(
                assessment.repository.get("operation_start", operation_id)
            )
            with assessment.router.store._lock:
                state = assessment.router.store._connection.execute(
                    "SELECT state FROM assessment_operations WHERE id=?", (operation_id,)
                ).fetchone()
            if (operation.plan_id != plan.plan_id or operation.stage != "trial"
                    or state is None or state[0] != "reserved"):
                raise ValueError("canonical trial operation is not currently reserved")
            reference = scope_index["scopes"][operation_id]
            expected_scope = reference["scope_digest"]
            expected_scope_id = "bqual_" + hashlib.sha256(
                f"{plan.plan_id}\0{operation_id}".encode()
            ).hexdigest()[:40]
            if reference.get("scope_id") != expected_scope_id:
                raise ValueError("scope index points to a non-derived task scope")
            task_router = Router.from_manifest(manifest_path)
            # Track it before any fallible binding work so adapter.close always owns it.
            owned_routers.append(task_router)
            task_repo = AssessmentRepository(task_router.store)
            scope = TaskScope.model_validate(task_repo.get("task_scope", reference["scope_id"]))
            if (content_digest(scope) != expected_scope
                    or scope.scope_id != expected_scope_id
                    or scope.project_root != str(project)
                    or scope.approval_ceiling is not SideEffect.READ
                    or scope.max_attempts != TASK_ATTEMPTS
                    or scope.max_attempt_seconds != TASK_SECONDS
                    or scope.executor_fingerprints != {
                        "native.composed.workbook": profile_identity["executor_fingerprints"][
                            "native.composed.workbook"
                        ]
                    }
                    or scope.expires_at <= utc_now()
                    or scope.expires_at != expected_scope_expiry):
                raise ValueError("selected task scope differs from its reviewed index")
            with task_router.store._lock:
                reviewed = task_router.store._connection.execute(
                    "SELECT revoked FROM assessment_reviews WHERE digest=?", (expected_scope,)
                ).fetchone()
            if reviewed is None or reviewed[0]:
                raise ValueError("selected task scope is not currently reviewed")
            task_router.bind_task_scope(scope.scope_id)
            native_spec = task_router.registry.get("native.composed.workbook")
            native = NativeSandboxConfig.model_validate(native_spec.config["native_sandbox"])
            built = services_builder(task_router, scope, native_spec, native)
            if (not isinstance(built, tuple) or len(built) != 6
                    or built[0] is not task_router or built[1].scope_id != scope.scope_id
                    or built[2].id != native_spec.id):
                raise ValueError("workbook service builder returned an unexpected binding")
            return built[4], built[5]

        adapter.dynamic_tools_factory = composition.union_operator_factory(
            assessment=assessment,
            plan=plan,
            profile_identity=profile_identity,
            namespace="workbook",
            max_calls=1,
            timeout_seconds=TASK_SECONDS,
            services_for_trial=services_for_trial,
        )
        return _RouterOwningAdapter(adapter, owned_routers)

    # _campaign_router clones registered factories, not configured adapters.
    # Standard adapters already on this ordinary Router remain untouched.
    assessment.router.managed_hosts.register_factory("codex-app-server", host_factory)
