"""One-shot ordinary workbook qualification runner; inert when imported."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
STAGE = Path(__file__).resolve().parent
RUNNER_PATH = Path(__file__).resolve()
SOURCE = "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
PROFILE = STAGE / "b-current-profile-v2.json"
PROFILE_SHA256 = "28ed2a514083beda4ef3fc1fbcfa6320f5fabe2b8dcde74dddac7d7bb489c79a"
PLAN_HELPER = STAGE / "b-prepare-workbook-qualification-plan-20261003.py"
PLAN_HELPER_SHA256 = "3fb3dcd3dcc4b7962b7b7ff461e4fb5c8524827244bfedd8daba4ab033ad6e71"
COMPOSITION = STAGE / "b-qualification-callback-composition.py"
COMPOSITION_SHA256 = "82f602d92a19d8020931d344ad0ce05c7bcccdf9b64908b0723a786c250591e7"
PRODUCER = STAGE / "b-native-workbook-producer-final.py"
PRODUCER_SHA256 = "4d5db1fd761882f90bbaff5d1a6c392e2bab185a248f4a981399f95ee8aa539d"
MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
REVIEW = STAGE / "b-workbook-qualification-execution-review-20261003.json"
PROPOSAL = STAGE / "b-workbook-qualification-plan-proposal.json"
SCOPE_INDEX = STAGE / "b-workbook-qualification-scopes-20261003.json"
STARTED = STAGE / "b-workbook-qualification-started-20261003.json"
RESULT = STAGE / "b-workbook-qualification-result-20261003.json"
ONCE = STAGE / "b-workbook-qualification-once-20261003.json"
GIB = 1024**3
RESERVE_BYTES = 50 * GIB
MAX_PRECHECK_SECONDS = 30
MAX_SCOPE_SECONDS = 600
MAX_CAPACITY_SECONDS = 60
MAX_PROXY_SECONDS = 60
MAX_CAPACITY_AGE_SECONDS = 1800
SCOPE_GRACE_SECONDS = 900
CAMPAIGN_OVERHEAD_SECONDS = 120
PROXY_NAME = "aeep-reviewed-model-proxy"
PROXY_ID = "5f9a44f86633409a250d11a78cf59357495da2078724ee0261bc73acff57f0f3"
PROXY_IMAGE = "sha256:5bf590eb0bf8a06187ff092f0f75cf83b540cc27bd6a75fd8bd91305ca7b13de"
PROXY_NETWORK = "8f657f861de8897d53df66efdf595c6d2e202b174af81f2827db409fe53f19d6"


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _safe_stack(exc: BaseException) -> list[dict[str, Any]]:
    return [{"file": Path(item.filename).name, "line": item.lineno, "function": item.name}
            for item in traceback.extract_tb(exc.__traceback__)[-8:]]


def _docker(review: dict[str, Any], *args: str, timeout: float) -> str:
    docker = review["docker"]
    completed = subprocess.run(
        [docker["runtime"], "--host", docker["socket"], *args],
        check=True, capture_output=True, text=True, timeout=timeout,
    )
    if len(completed.stdout.encode("utf-8")) > 32768:
        raise RuntimeError("Docker metadata output exceeded its reviewed bound")
    return completed.stdout.strip()


def _checked_snapshot_path(requested_value: str, plan_directory_value: str) -> Path:
    requested_sample = Path(requested_value)
    sample_path = requested_sample.resolve()
    plan_directory = Path(plan_directory_value).resolve()
    _require(requested_sample.is_absolute() and not requested_sample.is_symlink()
             and sample_path == plan_directory / "storage-preflight-snapshot.sqlite3"
             and not sample_path.exists(),
             "snapshot sample path escaped the plan-owned assessment directory")
    return sample_path


def _proxy_state(review: dict[str, Any]) -> dict[str, Any]:
    proxy = review["proxy"]
    raw = _docker(
        review, "inspect", "--format",
        "{\"Id\":{{json .Id}},\"Image\":{{json .Image}},\"Running\":{{json .State.Running}},\"Networks\":{{json .NetworkSettings.Networks}}}",
        proxy["name"], timeout=10,
    )
    state = json.loads(raw)
    network_ids = {item.get("NetworkID") for item in state.get("Networks", {}).values()}
    _require(state.get("Id") == proxy["id"], "reviewed proxy container ID changed")
    _require(state.get("Image") == proxy["image"], "reviewed proxy image changed")
    _require(network_ids == {proxy["network_id"]},
             "reviewed proxy network attachment differs from its exact pinned network")
    return state


def _check_store(review: dict[str, Any]) -> None:
    expected = review["canonical_store"]
    database = Path(expected["database"])
    manifest = Path(expected["manifest"])
    _require(manifest == MANIFEST and not manifest.is_symlink() and manifest.is_file(),
             "canonical manifest path changed")
    _require(_sha(manifest) == expected["manifest_sha256"], "canonical manifest digest changed")
    _require(database == ROOT / ".aeep/live-review-v3/aeep.sqlite3"
             and not database.is_symlink() and database.is_file(), "canonical database path changed")
    stat = database.stat()
    _require(stat.st_dev == expected["device"] and stat.st_ino == expected["inode"],
             "canonical database identity changed")
    value = json.loads(manifest.read_text(encoding="utf-8"))
    _require(value.get("database") == str(database), "manifest database target changed")


def _load_pinned_module(path: Path, name: str, expected_sha: str) -> Any:
    _require(path.resolve(strict=True).parent == STAGE, "module path escaped the reviewed report directory")
    _require(_sha(path) == expected_sha, f"pinned module changed: {path.name}")
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, f"module unavailable: {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _accounted(repository: Any, plan: Any, operation_id: str, stage: str,
                     seconds: float, body: Any) -> Any:
    from aeep.assessment.models import AssessmentLimits

    repository.reserve(
        plan, operation_id,
        AssessmentLimits(max_operations=1, max_model_turns=0,
                         max_elapsed_seconds=seconds, max_cash_usd=0),
        stage=stage,
    )
    started = time.perf_counter()
    error: BaseException | None = None
    try:
        return await body() if asyncio.iscoroutinefunction(body) else body()
    except BaseException as exc:
        error = exc
        raise
    finally:
        elapsed = time.perf_counter() - started
        try:
            repository.finish_operation(operation_id, elapsed_seconds=elapsed)
        except BaseException as finish_error:
            if error is not None:
                raise RuntimeError("operation failed and its accounting settlement also failed") from finish_error
            raise
        if error is None and elapsed > seconds:
            raise TimeoutError("reviewed operation exceeded its reserved elapsed time")


async def _preflight(router: Any, assessment: Any, plan: Any,
                     review: dict[str, Any], result: dict[str, Any]) -> None:
    from aeep.assessment.models import content_digest

    operation_id = review["operation_ids"]["preflight"]
    started = time.perf_counter()
    deadline = started + MAX_PRECHECK_SECONDS
    free_before = shutil.disk_usage(ROOT).free
    _require(free_before >= RESERVE_BYTES + review["storage"]["allowance_bytes"],
             "ordinary host free space is below the reviewed 50-GiB reserve plus allowance")
    df = _docker(review, "system", "df", "--format", "{{json .}}", timeout=15)
    docker_rows = [json.loads(line) for line in df.splitlines() if line.strip()]
    _require(bool(docker_rows), "Docker usage inspection returned no metadata")
    image_ids: dict[str, str] = {}
    for image, expected_id in review["image_pins"].items():
        observed_id = _docker(review, "image", "inspect", "--format", "{{.Id}}",
                              image, timeout=5)
        _require(observed_id == expected_id,
                 "a pinned qualification image is unavailable or changed")
        image_ids[image] = observed_id
    proxy = _proxy_state(review)
    _require(proxy.get("Running") is False,
             "reviewed proxy was already running before its lifecycle")

    # Match AssessmentService.run's bound campaign snapshot selection without
    # reading case-set payloads into this helper's output.
    bound = {
        content_digest(plan), plan.subject_digest, plan.recipe_digest,
        plan.mapping_digest, plan.environment_digest, *plan.definition_digests,
        *plan.executable_dependencies.values(),
    }
    if plan.recipe_case_set_digest:
        bound.add(plan.recipe_case_set_digest)
    sample_path = _checked_snapshot_path(
        review["storage"]["sample_snapshot_path"],
        str(assessment.directory / plan.plan_id),
    )
    _require(time.perf_counter() < deadline,
             "preflight deadline expired before snapshot sampling")
    snapshot = router.store.campaign_snapshot(sample_path, bound_digests=bound)
    snapshot.close()
    sample_bytes = sample_path.stat().st_size
    _require(time.perf_counter() < deadline,
             "preflight exceeded its reviewed elapsed bound")
    storage = review["storage"]
    _require(sample_bytes <= storage["snapshot_bytes_upper"],
             "measured scoped snapshot exceeds the reviewed per-copy bound")
    derived = storage["snapshot_count_upper"] * storage["snapshot_bytes_upper"] + storage["artifact_bytes_upper"]
    _require(derived <= storage["allowance_bytes"],
             "reviewed snapshot and artifact bounds exceed the storage allowance")
    free_after = shutil.disk_usage(ROOT).free
    _require(free_after >= RESERVE_BYTES + storage["allowance_bytes"],
             "host free space crossed the reviewed reserve during preflight")
    result["storage_preflight"] = {
        "operation_id": operation_id,
        "sample_snapshot_bytes": sample_bytes,
        "snapshot_count_upper": storage["snapshot_count_upper"],
        "snapshot_bytes_upper": storage["snapshot_bytes_upper"],
        "artifact_bytes_upper": storage["artifact_bytes_upper"],
        "allowance_bytes": storage["allowance_bytes"],
        "ordinary_free_before_bytes": free_before,
        "ordinary_free_after_bytes": free_after,
        "docker_system_df_rows": docker_rows,
        "image_ids": image_ids,
        "proxy_initially_stopped": proxy.get("Running") is False,
        "whole_system_cost_complete": False,
    }
    result["setup_measurements"][operation_id] = max(0.0, time.perf_counter() - started)


async def _capacity_snapshot(router: Any, repository: Any, plan: Any, spec: Any,
                             review: dict[str, Any]) -> dict[str, Any]:
    from aeep.assessment.containment import container_name
    from aeep.assessment.models import AssessmentLimits
    from aeep.capacity.models import CapacityObservation
    from aeep.hosts.codex_app_server import CodexAppServerAdapter

    operation_id = review["operation_ids"]["capacity"]
    repository.reserve(
        plan, operation_id,
        AssessmentLimits(
            max_operations=1, max_model_turns=0,
            max_elapsed_seconds=MAX_CAPACITY_SECONDS, max_cash_usd=0),
        stage="capacity_introspection",
    )
    started = time.perf_counter()
    deadline = asyncio.get_running_loop().time() + MAX_CAPACITY_SECONDS
    adapter = None
    worker_process_id: str | None = None
    observation: CapacityObservation | None = None
    error: BaseException | None = None
    cleanup = False
    try:
        async with asyncio.timeout_at(deadline - 8):
            adapter = CodexAppServerAdapter.from_executor(
                spec, principal_salt=router.store.host_principal_key,
                manifest_directory=router.manifest_path.parent,
            )
            worker_process_id = adapter._worker_process_id
            await adapter.transport.start()
            observation = await adapter.snapshot_capacity()
            if observation.resource_id != "codex.self":
                raise RuntimeError("fresh capacity observation named the wrong resource")
            router.store.save_capacity_observation(observation)
    except BaseException as exc:
        error = exc
    finally:
        if adapter is not None:
            try:
                async with asyncio.timeout_at(deadline - 5):
                    await adapter.close()
            except BaseException as exc:
                error = error or exc
            try:
                if worker_process_id and adapter._worker is not None:
                    remaining_seconds = deadline - asyncio.get_running_loop().time()
                    if remaining_seconds <= 0:
                        raise TimeoutError("capacity cleanup deadline expired")
                    name = container_name(worker_process_id)
                    remaining = _docker(
                        review, "ps", "-a", "--filter", f"name=^/{name}$",
                        "--format", "{{.ID}}", timeout=min(5.0, remaining_seconds),
                    )
                    process = adapter.transport._process
                    cleanup = (not remaining and (process is None or process.returncode is not None)
                               and not adapter.transport._dynamic_tasks)
            except BaseException as exc:
                error = error or exc
        elapsed = max(0.0, time.perf_counter() - started)
        try:
            repository.finish_operation(operation_id, elapsed_seconds=elapsed)
        except BaseException as exc:
            error = error or exc
        if elapsed > MAX_CAPACITY_SECONDS:
            error = error or TimeoutError("capacity operation exceeded its reserved elapsed bound")
    if error is not None:
        raise error
    if observation is None or not cleanup:
        raise RuntimeError("fresh capacity observation or owned-worker cleanup was not confirmed")
    age = (datetime.now(UTC) - observation.observed_at).total_seconds()
    if age < 0 or age > MAX_CAPACITY_AGE_SECONDS:
        raise RuntimeError("capacity observation exceeded its reviewed freshness window")
    return {
        "operation_id": operation_id,
        "resource_id": observation.resource_id,
        "observed_at": observation.observed_at.isoformat(),
        "age_seconds_at_capture": age,
        "canonical_digest": observation.canonical_digest,
        "elapsed_seconds": max(0.0, time.perf_counter() - started),
        "owned_worker_cleanup_confirmed": cleanup,
        "source": observation.source,
        "quota_values_omitted": True,
    }


async def _run(argv: list[str]) -> int:
    if len(argv) != 2 or not all(c in "0123456789abcdef" for c in argv[1]) or len(argv[1]) != 64:
        raise RuntimeError("usage: runner.py <exact-execution-review-sha256>")
    supplied_sha = argv[1]
    _require(not any(path.exists() for path in (STARTED, RESULT, ONCE, SCOPE_INDEX)),
             "one-shot marker or result already exists; replay is forbidden")
    _require(_sha(REVIEW) == supplied_sha, "execution review hash differs")
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    _require(review.get("execution_authorized") is True,
             "exact runner execution review has not been authorized")
    _require(review.get("runner_sha256") == _sha(RUNNER_PATH),
             "runner bytes differ from the reviewed pin")
    _require(review.get("source_digest") == SOURCE, "review source pin differs")
    from aeep.assessment.verification import verification_source_digest
    _require(verification_source_digest(ROOT) == SOURCE, "repository source changed")
    _require(_sha(PROFILE) == PROFILE_SHA256, "current workbook profile changed")
    _require(_sha(PLAN_HELPER) == PLAN_HELPER_SHA256,
             "workbook plan-proposal helper changed")
    _require(_sha(COMPOSITION) == COMPOSITION_SHA256
             and review.get("composition_sha256") == COMPOSITION_SHA256,
             "callback composition helper changed")
    _require(_sha(PRODUCER) == PRODUCER_SHA256
             and review.get("producer_sha256") == PRODUCER_SHA256,
             "native producer changed")
    _require(_sha(PROPOSAL) == review["proposal_sha256"], "qualification proposal changed")
    _check_store(review)
    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    _require(proposal.get("plan_id") == review["plan_id"]
             and proposal.get("plan_digest") == review["plan_digest"]
             and proposal.get("case_set_digest") == review["case_set_digest"],
             "proposal plan/case-set binding differs")
    _require(proposal.get("status") == "proposal_prepared"
             and proposal.get("execution_authorized") is False
             and proposal.get("not_enqueued") is True
             and proposal.get("qualification") is False
             and proposal.get("admission") is False
             and proposal.get("definition_digests") == proposal.get("amendment", {}).get("reviewed_digests"),
             "proposal is not the exact inert, non-admission plan artifact")
    _require(_json_digest(proposal["budget_preview"]) == review["budget_preview_digest"],
             "reviewed budget preview differs from the proposal")
    _require(proposal.get("runner_sha256") == PLAN_HELPER_SHA256,
             "plan proposal was not created by the frozen preparation helper")
    _require(review.get("proxy") == {
        "name": PROXY_NAME, "id": PROXY_ID, "image": PROXY_IMAGE,
        "network_id": PROXY_NETWORK,
    }, "proxy identity differs from the reviewed protected proxy")
    _require(review.get("max_capacity_age_seconds") == MAX_CAPACITY_AGE_SECONDS
             and review.get("scope_setup_seconds") == MAX_SCOPE_SECONDS
             and review.get("preflight_seconds") == MAX_PRECHECK_SECONDS
             and review.get("capacity_seconds") == MAX_CAPACITY_SECONDS
             and review.get("proxy_seconds_each") == MAX_PROXY_SECONDS
             and review.get("cash_ceiling_usd") == 0
             and review.get("additional_model_turns") == 0,
             "runner bounds differ from the exact reviewed limits")
    _require(review["storage"]["reserve_bytes"] == RESERVE_BYTES,
             "ordinary storage reserve differs from AGENTS policy")
    _require(review.get("supplemental_allowance") == {
        "operations": 5, "model_turns": 0, "elapsed_seconds": 810, "cash_usd": "0",
    }, "supplemental setup allowance does not exactly cover the five reviewed operations")
    expected_operation_ids = {
        "preflight": f"{review['plan_id']}:workbook-storage-docker-preflight-v1",
        "capacity": f"{review['plan_id']}:workbook-capacity-snapshot-v1",
        "proxy_start": f"{review['plan_id']}:workbook-proxy-start-v1",
        "proxy_stop": f"{review['plan_id']}:workbook-proxy-stop-v1",
    }
    _require(review.get("operation_ids") == expected_operation_ids,
             "supplemental operation IDs differ from the frozen runner contract")
    full_elapsed = float(
        review["budget_preview"]["campaign_allowance"]["upper_allowance"]["elapsed_seconds"]
    )
    _require(review.get("maximum_campaign_seconds")
             == math.ceil(full_elapsed) + CAMPAIGN_OVERHEAD_SECONDS,
             "campaign deadline does not match the full-operation allowance plus fixed overhead")
    reviewed_at = datetime.fromisoformat(review["reviewed_at"])
    reviewed_deadline = datetime.fromisoformat(review["campaign_deadline"])
    expected_window = (MAX_PRECHECK_SECONDS + MAX_SCOPE_SECONDS + MAX_CAPACITY_SECONDS
                      + MAX_PROXY_SECONDS + review["maximum_campaign_seconds"])
    _require(reviewed_at.tzinfo is not None and reviewed_deadline.tzinfo is not None
             and reviewed_deadline == reviewed_at + timedelta(seconds=expected_window),
             "absolute deadline does not cover exact setup and complete campaign bounds")

    result: dict[str, Any] = {
        "schema_version": "b.workbook-qualification-run-result.v1",
        "review_sha256": supplied_sha,
        "plan_id": review["plan_id"],
        "plan_digest": review["plan_digest"],
        "case_set_digest": review["case_set_digest"],
        "source_digest": SOURCE,
        "replay_allowed": False,
        "qualification_completed": False,
        "admission_state_unchanged": False,
        "setup_measurements": {},
        "whole_system_cost_complete": False,
    }
    _atomic_json(ONCE, {"review_sha256": supplied_sha,
                        "plan_id": review["plan_id"], "replay_allowed": False})
    _atomic_json(STARTED, result)

    router = None
    assessment = None
    plan = None
    repository = None
    proxy_started_or_uncertain = False
    proxy_state_conflict = False
    candidate_admission_before: str | None = None
    start_time = time.perf_counter()
    operation_error: BaseException | None = None
    try:
        from aeep.assessment.boundary import require_differential, require_managed_boundaries
        from aeep.assessment.models import (
            AssessmentPlan,
            AssessmentScopeAmendment,
            ReviewedMapping,
            content_digest,
        )
        from aeep.assessment.service import AssessmentService
        from aeep.router import Router

        router = Router.from_manifest(MANIFEST)
        assessment = AssessmentService(router, ROOT / ".aeep/live-review-v3/.aeep/assessments")
        repository = assessment.repository
        plan = AssessmentPlan.model_validate(repository.get("plan", review["plan_id"]))
        _require(content_digest(plan) == review["plan_digest"], "canonical plan digest changed")
        _require(plan.recipe_case_set_digest == review["case_set_digest"], "canonical case set changed")
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        composed = profile["component"]["composed"]
        _require(plan.candidate_id == composed["treatment"]["id"]
                 and plan.baseline_id == composed["control"]["id"]
                 and plan.subject_digest == proposal["subject_digest"]
                 and plan.recipe_digest == proposal["recipe_digest"]
                 and plan.environment_digest == proposal["environment_digest"],
                 "canonical plan differs from the exact paired workbook proposal")
        _require(plan.comparison is not None and plan.comparison.experiment is not None
                 and plan.comparison.experiment.stage == "qualification"
                 and plan.comparison.experiment.exposure == "required",
                 "plan is not the reviewed required-exposure qualification")
        _require(not plan.blocked_reasons, "qualification plan is blocked")
        _require(plan.suite.suite_id == plan.plan_id and len(plan.suite.cases) == 141
                 and plan.suite.repetitions == 1, "qualification suite shape changed")
        _require({split.value: sum(case.split.value == split.value for case in plan.suite.cases)
                  for split in plan.suite.cases[0].split.__class__}
                 == {"qualification": 8, "training": 28, "holdout": 105},
                 "qualification split counts differ")
        _require(plan.suite.conditions[0].value == "fresh-worker"
                 and len(plan.suite.conditions) == 1
                 and plan.suite.sequential_stages
                 and [route.route_id for route in plan.suite.routes] == [plan.candidate_id],
                 "qualification conditions or route differ from the frozen experiment")
        mapping = ReviewedMapping.model_validate(repository.get("mapping", plan.mapping_digest))
        specs = [item for item in mapping.subjects if item.id in {plan.candidate_id, plan.baseline_id}]
        _require({item.id for item in specs} == {plan.candidate_id, plan.baseline_id}
                 and plan.candidate_id != plan.baseline_id, "qualification pair changed")
        from aeep.hosts.workers import binding_from_config
        treatment_config = next(item for item in specs if item.id == plan.candidate_id).managed_host_config()
        treatment_worker = binding_from_config(treatment_config.managed_worker)
        _require(treatment_worker is not None
                 and treatment_worker.digest() == profile["selected_worker_digest"]
                 and treatment_worker.runtime == review["docker"]["runtime"]
                 and treatment_worker.socket == review["docker"]["socket"]
                 and treatment_worker.network_id == PROXY_NETWORK,
                 "Docker runtime, treatment worker or proxy network differs from the reviewed profile")
        for spec in specs:
            if not router.registry.contains(spec.id):
                router.register(spec)
        router.managed_hosts.configure(
            specs, principal_salt=router.store.host_principal_key,
            manifest_directory=router.manifest_path.parent,
        )
        from aeep.assessment.models import AssessmentEnvironment
        environment = AssessmentEnvironment.model_validate(
            repository.get("environment", plan.environment_digest)
        )
        identities = {role["executor_id"]: role["identity_digest"]
                      for role in review["conformance_identities"]}
        require_managed_boundaries(repository, environment, specs, identities)
        require_differential(repository, environment, plan)
        preview = assessment.budget_preview(plan.plan_id)
        _require(_json_digest(preview) == review["budget_preview_digest"],
                 "fresh budget preview differs from the reviewed full plan")
        allowance = preview["campaign_allowance"]
        _require(not allowance.get("gaps") and allowance.get("fits_remaining") is True,
                 "campaign budget has a gap or does not fit the current grant")
        _require(all(item.get("eligible") is True for item in preview["adapter_eligibility"]),
                 "a qualification adapter is not eligible")
        needed = allowance["upper_allowance"]
        extras = review["supplemental_allowance"]
        remaining = preview.get("remaining") or {}
        for field in ("operations", "model_turns", "elapsed_seconds"):
            required = float(needed[field]) + float(extras[field])
            _require(float(remaining.get(field, 0)) >= required,
                     f"remaining grant cannot cover campaign plus reviewed {field}")
        _require(str(needed["cash_usd"]) == "0" and str(extras["cash_usd"]) in {"0", "0.0"},
                 "cash ceiling is not zero")
        with router.store._lock:
            admission_row = router.store._connection.execute(
                "SELECT admission_id FROM assessment_admissions WHERE executor_id=?",
                (plan.candidate_id,),
            ).fetchone()
        candidate_admission_before = admission_row[0] if admission_row else None
        _require(not router.store._connection.execute(
            "SELECT 1 FROM assessment_jobs WHERE plan_id=? LIMIT 1", (plan.plan_id,)
        ).fetchone(), "qualification plan already has a job")
        # Enact only the exact, reviewed plan definitions after all static checks.
        amendment = AssessmentScopeAmendment.model_validate(proposal["amendment"])
        with router.store._lock:
            definitions = {
                digest: json.loads(row[0])
                for digest in amendment.reviewed_digests
                if (row := router.store._connection.execute(
                    "SELECT payload_json FROM assessment_records WHERE digest=?", (digest,)
                ).fetchone()) is not None
            }
        _require(set(definitions) == set(amendment.reviewed_digests),
                 "an exact reviewed definition is absent from canonical metadata")
        repository.approve_bundle(amendment, definitions)
        repository.authorize(plan)
        result["budget_preview_digest"] = _json_digest(preview)
        result["campaign_allowance"] = needed

        async def preflight_body() -> None:
            await _preflight(router, assessment, plan, review, result)

        await _accounted(repository, plan, review["operation_ids"]["preflight"],
                         "workbook_storage_docker_preflight", MAX_PRECHECK_SECONDS, preflight_body)
        result["setup_measurements"][review["operation_ids"]["preflight"]] = repository.get(
            "operation_measurement", review["operation_ids"]["preflight"]
        ).get("elapsed_seconds")

        composition = _load_pinned_module(COMPOSITION, "b_qualification_composition",
                                          review["composition_sha256"])
        task_manifest = Path(profile["native_project"]) / "aeep.json"
        deadline = datetime.fromisoformat(review["campaign_deadline"])
        _require(deadline.tzinfo is not None and deadline > datetime.now(UTC),
                 "reviewed campaign deadline is expired")
        scope_index = await composition.prepare_trial_scopes(
            assessment, plan, task_manifest,
            campaign_end=deadline,
            expires_at=deadline + timedelta(seconds=SCOPE_GRACE_SECONDS),
        )
        _require(scope_index["scope_count"] == 141, "prepared per-trial scope count differs")
        _atomic_json(SCOPE_INDEX, scope_index)
        result["scope_index_digest"] = scope_index["scope_index_digest"]
        scope_measurement = repository.get(
            "operation_measurement", scope_index["operation_id"]
        )
        result["setup_measurements"][scope_index["operation_id"]] = scope_measurement.get(
            "elapsed_seconds"
        )

        start_id = review["operation_ids"]["proxy_start"]
        async def start_proxy() -> None:
            nonlocal proxy_started_or_uncertain, proxy_state_conflict
            if _proxy_state(review)["Running"]:
                proxy_state_conflict = True
                raise RuntimeError("proxy became active before its reviewed start operation")
            proxy_started_or_uncertain = True
            _docker(review, "start", review["proxy"]["name"], timeout=20)
            if not _proxy_state(review)["Running"]:
                raise RuntimeError("reviewed proxy did not start")
        await _accounted(repository, plan, start_id, "reviewed_proxy_setup", MAX_PROXY_SECONDS, start_proxy)
        result["setup_measurements"][start_id] = repository.get(
            "operation_measurement", start_id
        ).get("elapsed_seconds")

        treatment = next(item for item in specs if item.id == plan.candidate_id)
        result["capacity_snapshot"] = await _capacity_snapshot(router, repository, plan, treatment, review)
        result["setup_measurements"][review["operation_ids"]["capacity"]] = (
            result["capacity_snapshot"]["elapsed_seconds"]
        )

        producer = _load_pinned_module(PRODUCER, "b_native_workbook_producer",
                                       review["producer_sha256"])
        treatment_identity = profile["callback_documents_by_role"]["treatment"]["identity"]
        composition.install_treatment_factory(
            assessment, plan, profile_identity=treatment_identity, scope_index=scope_index,
            manifest_path=task_manifest, services_builder=producer.services,
        )
        assessment_id = assessment.enqueue(plan.plan_id)
        result["assessment_id"] = assessment_id
        _atomic_json(STARTED, result)
        remaining_campaign = (deadline - datetime.now(UTC)).total_seconds()
        campaign_timeout = min(float(review["maximum_campaign_seconds"]), remaining_campaign)
        _require(campaign_timeout >= full_elapsed,
                 "remaining campaign window cannot cover the full frozen budget preview")
        campaign_deadline = asyncio.get_running_loop().time() + campaign_timeout
        async with asyncio.timeout_at(campaign_deadline):
            report = await assessment.run(assessment_id)
        result.update(
            report_id=report.report_id,
            outcome=report.outcome,
            qualification_passed=bool(report.qualification_passed),
        )
        with router.store._lock:
            admission_row = router.store._connection.execute(
                "SELECT admission_id FROM assessment_admissions WHERE executor_id=?",
                (plan.candidate_id,),
            ).fetchone()
        candidate_admission_after = admission_row[0] if admission_row else None
        result["candidate_admission_unchanged"] = (
            candidate_admission_after == candidate_admission_before
        )
        result["admission_state_unchanged"] = result["candidate_admission_unchanged"]
        result["qualification_completed"] = True
        if not result["candidate_admission_unchanged"]:
            raise RuntimeError("qualification unexpectedly changed candidate admission state")
    except BaseException as exc:
        operation_error = exc
        result.update(error_type=type(exc).__name__, safe_stack=_safe_stack(exc))
    finally:
        if proxy_started_or_uncertain and repository is not None and plan is not None:
            cleanup_id = review["operation_ids"]["proxy_stop"]
            reserved = False
            started = time.perf_counter()
            try:
                from aeep.assessment.models import AssessmentLimits
                repository.reserve(
                    plan, cleanup_id,
                    AssessmentLimits(max_operations=1, max_model_turns=0,
                                     max_elapsed_seconds=MAX_PROXY_SECONDS, max_cash_usd=0),
                    stage="reviewed_proxy_cleanup",
                )
                reserved = True
            except BaseException as exc:
                result.update(proxy_cleanup_reservation_error_type=type(exc).__name__,
                              proxy_cleanup_accounting_complete=False)
                if operation_error is None:
                    operation_error = exc
            try:
                if _proxy_state(review)["Running"]:
                    _docker(review, "stop", "--time", "5", review["proxy"]["name"], timeout=20)
                result["proxy_restored"] = not _proxy_state(review)["Running"]
            except BaseException as exc:
                result.update(proxy_restored=False, proxy_cleanup_error_type=type(exc).__name__)
                if operation_error is None:
                    operation_error = exc
            finally:
                if reserved:
                    try:
                        repository.finish_operation(
                            cleanup_id, elapsed_seconds=max(0.0, time.perf_counter() - started)
                        )
                        result["setup_measurements"][cleanup_id] = repository.get(
                            "operation_measurement", cleanup_id
                        ).get("elapsed_seconds")
                        if result["setup_measurements"][cleanup_id] > MAX_PROXY_SECONDS:
                            raise TimeoutError("proxy cleanup exceeded its reserved elapsed bound")
                        result["proxy_cleanup_accounting_complete"] = True
                    except BaseException as exc:
                        result["proxy_cleanup_accounting_error_type"] = type(exc).__name__
                        if operation_error is None:
                            operation_error = exc
        elif proxy_state_conflict:
            result["proxy_restored"] = False
        elif not proxy_started_or_uncertain:
            result["proxy_restored"] = result.get("storage_preflight", {}).get(
                "proxy_initially_stopped", False
            )
        result["elapsed_seconds_through_proxy_close"] = max(0.0, time.perf_counter() - start_time)
        result["source_unchanged"] = False
        try:
            from aeep.assessment.verification import verification_source_digest
            result["source_unchanged"] = verification_source_digest(ROOT) == SOURCE
        except BaseException:
            pass
        if router is not None:
            try:
                row = router.store._connection.execute(
                    "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'"
                ).fetchone()
                result["grant_after"] = dict(zip(
                    ("operations", "model_turns", "elapsed_seconds", "cash_usd"),
                    row,
                    strict=True,
                )) if row else None
            except BaseException as exc:
                result["grant_read_error_type"] = type(exc).__name__
            try:
                await router.close()
                result["coordinator_closed"] = True
            except BaseException as exc:
                result.update(coordinator_closed=False, close_error_type=type(exc).__name__)
        scope_operation_id = result.get("scope_index_digest") and (
            f"{review['plan_id']}:workbook-task-scope-preparation-v1"
        )
        bounds = {
            review["operation_ids"]["preflight"]: MAX_PRECHECK_SECONDS,
            scope_operation_id: MAX_SCOPE_SECONDS,
            review["operation_ids"]["capacity"]: MAX_CAPACITY_SECONDS,
            review["operation_ids"]["proxy_start"]: MAX_PROXY_SECONDS,
            review["operation_ids"]["proxy_stop"]: MAX_PROXY_SECONDS,
        }
        result["setup_accounting_complete"] = all(
            isinstance(result["setup_measurements"].get(operation_id), (int, float))
            and math.isfinite(result["setup_measurements"][operation_id])
            and 0 <= result["setup_measurements"][operation_id] <= bound
            for operation_id, bound in bounds.items()
        )
        result["status"] = "passed" if (
            operation_error is None and result.get("qualification_passed") is True
            and result.get("proxy_restored") is True and result.get("source_unchanged") is True
            and result.get("candidate_admission_unchanged") is True
            and result.get("coordinator_closed") is True
            and result.get("capacity_snapshot", {}).get("owned_worker_cleanup_confirmed") is True
            and result.get("scope_index_digest") is not None
            and result.get("setup_accounting_complete") is True
        ) else "failed"
        _atomic_json(RESULT, result)
        print(json.dumps({key: result.get(key) for key in (
            "status", "plan_id", "report_id", "outcome", "qualification_passed",
            "proxy_restored", "source_unchanged", "elapsed_seconds_through_proxy_close",
        )}, sort_keys=True), flush=True)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run(sys.argv)))
