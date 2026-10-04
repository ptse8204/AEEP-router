"""Reviewed proxy bracket for one exact current B callback execution."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aeep.assessment.identity import runtime_dependencies, verify_dependencies
from aeep.assessment.models import (
    AssessmentLimits,
    AssessmentScopeAmendment,
    ConformanceProbeRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import StrictModel
from aeep.router import Router


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
SETUP_REVIEW = OUT / "b-native-setup-v3-review.json"
SETUP_SHA256 = "ab4f78de528080b8684d8d608786d15a5b8aa616755d7f9033957ac0c44ef7b5"
PROFILE = OUT / "b-current-profile-v2.json"
PROFILE_SHA256 = "28ed2a514083beda4ef3fc1fbcfa6320f5fabe2b8dcde74dddac7d7bb489c79a"
COMPONENT_RESULT = OUT / "b-worker-components-v2-result.json"
COMPONENT_RESULT_SHA256 = "0552cf86620985194c5bd9d1252e88819667730ff9004efc1b82510b98696379"
COMPONENT_AUDIT = OUT / "b-worker-components-terminal-audit.json"
COMPONENT_AUDIT_SHA256 = "81ca6e006016204a07977bd137066a2352311839664cf500f9859ac27b49e60a"
SETUP_RESULT = OUT / "b-native-setup-v3-result.json"
SETUP_RESULT_SHA256 = "45f2344b74181d79ca284c8d3d3adc3d8d73a3c9edd1ccc51ef6993ed2968752"
PROXY_V3_RESULT = OUT / "b-worker-proxy-lifecycle-v3-result.json"
PROXY_V3_RESULT_SHA256 = "1153138d250c32d7720852561936bc0a6d3d5a06293203fe4de444a739cdc5e5"
CAPACITY_REQUEST = OUT / "b-treatment-capacity-request.json"
CAPACITY_REVIEW = OUT / "b-treatment-capacity-review.json"
CAPACITY_REVIEW_SHA256 = "8817bcaac60cae0068b609bd3f4c634ecbd328412dd5f58047fe4f664825e324"
CAPACITY_REQUEST_SHA256 = "ae56fb2fb27eb594f2376b19d1b32c1a5bb6d4bde6d0616341f64a79fd53b971"
CAPACITY_RESULT = OUT / "b-treatment-capacity-result.json"
CAPACITY_RESULT_SHA256 = "261d4e5a15f5ac25c745efc19836e15556bbb25d8dc76053ef0866d1ceef7191"
CAPACITY_PREPARER = OUT / "b-prepare-treatment-capacity.py"
CAPACITY_PREPARER_SHA256 = "421761230c208eb9d4854581a0dadc16854e53cfb7ddc40cfb614170820c2c00"
CAPACITY_RUNNER = OUT / "b-run-treatment-capacity.py"
CAPACITY_RUNNER_SHA256 = "7832a89651b06636359ce44a1b16a3783a89e91229d26e4f9c2f0b240174ce51"
INNER_PREPARATION = OUT / "b-current-callback-preparation-v2.json"
INNER_PREPARER = OUT / "b-prepare-current-callback-v2.py"
INNER_RUNNER = OUT / "b-run-current-callback-v2.py"
INNER_REVIEW = OUT / "b-current-callback-execution-review-v2.json"
INNER_STARTED = OUT / "b-current-callback-started-v2.json"
INNER_RESULT = OUT / "b-current-callback-result-v2.json"
NATIVE_COMPONENT_RESULT = OUT / "b-native-components-v4-result.json"
NATIVE_COMPONENT_REVIEW = OUT / "b-native-components-v4-review.json"
NATIVE_COMPONENT_RUNNER = OUT / "b-run-native-components-v4.py"
REVIEW = OUT / "b-current-callback-proxy-lifecycle-review.json"
STARTED = OUT / "b-current-callback-proxy-lifecycle-started.json"
RESULT = OUT / "b-current-callback-proxy-lifecycle-result.json"
DOCKER = [
    "/usr/local/bin/docker",
    "--host",
    "unix:///Users/edwintse/.docker/run/docker.sock",
]
PROXY_NAME = "aeep-reviewed-model-proxy"
PROXY_ID = "5f9a44f86633409a250d11a78cf59357495da2078724ee0261bc73acff57f0f3"
PROXY_IMAGE = "sha256:5bf590eb0bf8a06187ff092f0f75cf83b540cc27bd6a75fd8bd91305ca7b13de"
NETWORK_ID = "8f657f861de8897d53df66efdf595c6d2e202b174af81f2827db409fe53f19d6"
WORKER_DIGEST = "19027f56cdc99fc9b728dc2bf7af597f33c6a0d8f4b5d71d19739aa512a56df0"
START_SECONDS = 60
STOP_SECONDS = 60
MAX_CAPACITY_AGE_SECONDS = 1800
INNER_MODEL = "gpt-6-luna"
INNER_EFFORT = "xhigh"
INNER_TASK_TIMEOUT_SECONDS = 10.0
INNER_EXECUTOR_TIMEOUT_SECONDS = 203.0
INNER_MAX_ELAPSED_SECONDS = INNER_EXECUTOR_TIMEOUT_SECONDS + 5.0
INNER_CALL_TIMEOUT_SECONDS = INNER_MAX_ELAPSED_SECONDS + 5.0
OUTER_TIMEOUT_SECONDS = START_SECONDS + INNER_CALL_TIMEOUT_SECONDS + STOP_SECONDS


class CallbackProxyLifecycleDefinition(StrictModel):
    source_digest: str
    inner_execution_review_sha256: str
    inner_preparation_sha256: str
    inner_request_id: str
    inner_request_digest: str
    inner_runner_sha256: str
    worker_digest: str
    model_id: str
    reasoning_effort: str
    task_calls: int = 1
    task_call_timeout_seconds: float = INNER_TASK_TIMEOUT_SECONDS
    model_turns: int = 0
    cash_ceiling_usd: float = 0
    proxy_name: str
    proxy_id: str
    proxy_image: str
    network_id: str
    start_seconds: int = START_SECONDS
    stop_seconds: int = STOP_SECONDS
    inner_max_elapsed_seconds: float = INNER_MAX_ELAPSED_SECONDS
    outer_timeout_seconds: float = OUTER_TIMEOUT_SECONDS


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def docker(*args: str, timeout: int = 15) -> str:
    return subprocess.check_output(
        DOCKER + list(args), text=True, timeout=timeout, stderr=subprocess.DEVNULL
    ).strip()


def inspect_proxy() -> dict[str, Any]:
    rendered = docker(
        "inspect",
        "--format",
        '{"Id":{{json .Id}},"Name":{{json .Name}},"Image":{{json .Image}},'
        '"Running":{{json .State.Running}},"Networks":{{json .NetworkSettings.Networks}}}',
        PROXY_ID,
    )
    value = json.loads(rendered)
    networks = value["Networks"]
    if (
        value["Id"] != PROXY_ID
        or value["Name"] != "/" + PROXY_NAME
        or value["Image"] != PROXY_IMAGE
        or not isinstance(networks, dict)
        or NETWORK_ID not in [item.get("NetworkID") for item in networks.values()]
    ):
        raise ValueError("exact reviewed proxy identity changed")
    return value


def check_canonical_store(setup: dict[str, Any], capacity_review: dict[str, Any]) -> dict[str, Any]:
    expected = setup["canonical_store"]
    if expected != capacity_review["canonical_store"]:
        raise ValueError("setup and capacity canonical store pins differ")
    database = Path(expected["database"])
    if (
        SETUP_REVIEW.is_symlink()
        or sha(SETUP_REVIEW) != SETUP_SHA256
        or MANIFEST.is_symlink()
        or sha(MANIFEST) != expected["manifest_sha256"]
        or database != ROOT / ".aeep/live-review-v3/aeep.sqlite3"
        or database.is_symlink()
        or not database.is_file()
    ):
        raise ValueError("canonical manifest/database path or digest changed")
    manifest = json.loads(MANIFEST.read_text())
    stat = database.stat()
    if (
        manifest["database"] != str(database)
        or stat.st_dev != expected["device"]
        or stat.st_ino != expected["inode"]
    ):
        raise ValueError("canonical database identity changed")
    return expected


def capacity_is_fresh() -> tuple[dict[str, Any], dict[str, Any]]:
    review = json.loads(CAPACITY_REVIEW.read_text())
    result = json.loads(CAPACITY_RESULT.read_text())
    if (
        sha(CAPACITY_REQUEST) != CAPACITY_REQUEST_SHA256
        or sha(CAPACITY_REVIEW) != CAPACITY_REVIEW_SHA256
        or sha(CAPACITY_RESULT) != CAPACITY_RESULT_SHA256
        or sha(CAPACITY_PREPARER) != CAPACITY_PREPARER_SHA256
        or sha(CAPACITY_RUNNER) != CAPACITY_RUNNER_SHA256
        or review["source_digest"] != SOURCE
        or review["worker_digest"] != WORKER_DIGEST
        or review["executor_id"] != "b.luna.aeep"
        or review["resource_id"] != "codex.self"
        or review["method"] != "account/rateLimits/read"
        or review["max_age_seconds"] != MAX_CAPACITY_AGE_SECONDS
        or review["maximum_model_turns"] != 0
        or review["cash_ceiling_usd"] != 0
        or review["proxy_lifecycle_owned_here"] is not False
        or result["status"] != "passed"
        or result["source_digest"] != SOURCE
        or result["request_digest"] != review["request_digest"]
        or result["operation_id"] != review["operation_id"]
        or result["worker_digest"] != WORKER_DIGEST
        or result["stage"] != "capacity_introspection"
        or result["method"] != "account/rateLimits/read"
        or result["max_model_turns_reserved"] != 0
        or result["model_turns"] != 0
        or result["cash_ceiling_usd"] != 0
        or result["cleanup_confirmed"] is not True
        or result["source_unchanged"] is not True
        or result["replay_allowed"] is not False
    ):
        raise ValueError("exact current zero-turn capacity result is unavailable")
    observation = result["capacity"]
    if (
        not isinstance(observation, dict)
        or observation.get("resource_id") != "codex.self"
        or result.get("capacity_digest") != observation.get("canonical_digest")
        or not isinstance(observation.get("windows"), list)
        or not observation["windows"]
        or any(item.get("exhausted") is not False for item in observation["windows"])
    ):
        raise ValueError("capacity window state is absent, exhausted or unknown")
    observed = datetime.fromisoformat(str(observation["observed_at"]).replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
    if not 0 <= age <= MAX_CAPACITY_AGE_SECONDS:
        raise ValueError("capacity observation is stale or future-dated")
    return review, result


def validate_inner_review(inner_review_sha256: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not INNER_REVIEW.is_file() or sha(INNER_REVIEW) != inner_review_sha256:
        raise ValueError("exact frozen callback execution review is required")
    if (
        sha(PROFILE) != PROFILE_SHA256
        or sha(COMPONENT_RESULT) != COMPONENT_RESULT_SHA256
        or sha(COMPONENT_AUDIT) != COMPONENT_AUDIT_SHA256
        or sha(SETUP_RESULT) != SETUP_RESULT_SHA256
        or sha(PROXY_V3_RESULT) != PROXY_V3_RESULT_SHA256
    ):
        raise ValueError("current B profile or component evidence changed")
    review = json.loads(INNER_REVIEW.read_text())
    if (
        review.get("schema_version") != "assessment.b-current-callback-execution-review.v2"
        or review.get("execution_authorized") is not True
        or review.get("source_digest") != SOURCE
        or review.get("runner_sha256") != sha(INNER_RUNNER)
        or review.get("preparer_sha256") != sha(INNER_PREPARER)
        or review.get("profile_sha256") != PROFILE_SHA256
        or review.get("component_result_sha256") != COMPONENT_RESULT_SHA256
        or review.get("component_terminal_audit_sha256") != COMPONENT_AUDIT_SHA256
        or review.get("setup_result_sha256") != SETUP_RESULT_SHA256
        or review.get("setup_review_sha256") != SETUP_SHA256
        or review.get("proxy_lifecycle_result_sha256") != PROXY_V3_RESULT_SHA256
        or review.get("preparation_sha256") != sha(INNER_PREPARATION)
        or review.get("capacity_review_sha256") != CAPACITY_REVIEW_SHA256
        or review.get("capacity_result_sha256") != CAPACITY_RESULT_SHA256
        or review.get("max_operations") != 1
        or review.get("max_model_turns") != 1
        or review.get("max_elapsed_seconds") != INNER_MAX_ELAPSED_SECONDS
        or review.get("max_cash_usd") != 0
        or review.get("task_calls") != 1
        or review.get("task_call_timeout_seconds") != INNER_TASK_TIMEOUT_SECONDS
        or review.get("task_scope_attempts") != 1
        or review.get("model_id") != INNER_MODEL
        or review.get("reasoning_effort") != INNER_EFFORT
        or not review.get("native_component_result_sha256")
        or not review.get("native_component_review_sha256")
        or review.get("proxy_name") != PROXY_NAME
        or review.get("proxy_id") != PROXY_ID
        or review.get("proxy_image") != PROXY_IMAGE
        or review.get("proxy_network") != NETWORK_ID
        or review.get("request_id") is None
        or review.get("request_digest") is None
    ):
        raise ValueError("inner execution review differs from the exact one-turn Luna/xhigh scope")
    if not NATIVE_COMPONENT_RESULT.is_file() or not NATIVE_COMPONENT_REVIEW.is_file():
        raise ValueError("reviewed current native component evidence is missing")
    if (
        sha(NATIVE_COMPONENT_RESULT) != review["native_component_result_sha256"]
        or sha(NATIVE_COMPONENT_REVIEW) != review["native_component_review_sha256"]
        or not NATIVE_COMPONENT_RUNNER.is_file()
    ):
        raise ValueError("native component evidence no longer matches the callback review")
    setup = json.loads(SETUP_REVIEW.read_text())
    capacity_review, capacity_result = capacity_is_fresh()
    store = check_canonical_store(setup, capacity_review)
    profile = json.loads(PROFILE.read_text())
    treatment = profile.get("component", {}).get("composed", {}).get("treatment", {})
    config = treatment.get("config", {})
    if (
        profile.get("selected_worker_digest") != WORKER_DIGEST
        or config.get("timeout_seconds") != INNER_EXECUTOR_TIMEOUT_SECONDS
    ):
        raise ValueError("profile no longer selects the reviewed treatment worker")
    return review, store, {"capacity_review": capacity_review, "capacity_result": capacity_result}


def prepare(inner_review_sha256: str) -> None:
    if REVIEW.exists() or STARTED.exists() or RESULT.exists() or INNER_STARTED.exists() or INNER_RESULT.exists():
        raise ValueError("existing callback/lifecycle attempt found; preserve it and do not replay")
    if verification_source_digest(ROOT) != SOURCE:
        raise ValueError("frozen source digest changed")
    if inspect_proxy()["Running"] is not False:
        raise ValueError("exact reviewed proxy must be stopped before preparation")
    inner_review, store, capacity = validate_inner_review(inner_review_sha256)
    setup = json.loads(SETUP_REVIEW.read_text())
    capacity_request_record = json.loads(CAPACITY_REQUEST.read_text())
    base = setup["request"]
    capacity_definition_digest = capacity_request_record["definition_digest"]
    if (
        capacity_request_record["request"]["planner"]["id"] != "b.luna.aeep"
        or capacity_request_record["definition"]["worker_digest"] != WORKER_DIGEST
        or inner_review["worker_digest"] != WORKER_DIGEST
        or inner_review["request_id"] == "conformance_probe_bf48e94ea8b6458baadcb19a8f0325e0"
    ):
        raise ValueError("one-turn request reuses a prior ID or has a different worker binding")
    definition = CallbackProxyLifecycleDefinition(
        source_digest=SOURCE,
        inner_execution_review_sha256=inner_review_sha256,
        inner_preparation_sha256=inner_review["preparation_sha256"],
        inner_request_id=inner_review["request_id"],
        inner_request_digest=inner_review["request_digest"],
        inner_runner_sha256=inner_review["runner_sha256"],
        worker_digest=WORKER_DIGEST,
        model_id=INNER_MODEL,
        reasoning_effort=INNER_EFFORT,
        proxy_name=PROXY_NAME,
        proxy_id=PROXY_ID,
        proxy_image=PROXY_IMAGE,
        network_id=NETWORK_ID,
    )
    definitions = dict(setup["definitions"])
    definitions[capacity_definition_digest] = capacity_request_record["definition"]
    capacity_request_digest = content_digest(capacity_request_record["request"])
    definitions[capacity_request_digest] = capacity_request_record["request"]
    mapping_digest = content_digest(definition)
    definitions[mapping_digest] = definition.model_dump(mode="json")
    request = ConformanceProbeRequest(
        schema_version="assessment.conformance-request.v2",
        subject_digest=base["subject_digest"],
        recipe_digest=base["recipe_digest"],
        mapping_digest=mapping_digest,
        environment_digest=base["environment_digest"],
        authorization_id="onboarding",
        definition_digests=list(definitions),
        worker_digest=WORKER_DIGEST,
        executable_dependencies=runtime_dependencies()
        | {
            str(path.resolve()): sha(path)
            for path in (
                Path(__file__),
                INNER_RUNNER,
                INNER_PREPARER,
                INNER_REVIEW,
                INNER_PREPARATION,
                COMPONENT_RESULT,
                COMPONENT_AUDIT,
                SETUP_RESULT,
                PROXY_V3_RESULT,
                NATIVE_COMPONENT_RESULT,
                NATIVE_COMPONENT_REVIEW,
                NATIVE_COMPONENT_RUNNER,
                PROFILE,
                SETUP_REVIEW,
                CAPACITY_REQUEST,
                CAPACITY_REVIEW,
                CAPACITY_RESULT,
                MANIFEST,
            )
        },
        operation="worker_inspection",
    )
    amendment = AssessmentScopeAmendment(
        authorization_id="onboarding",
        authorization_digest=setup["amendment"]["authorization_digest"],
        subject_digests=[request.subject_digest],
        recipe_digests=[request.recipe_digest],
        environment_digests=[request.environment_digest],
        reviewed_digests=list(definitions),
    )
    record = {
        "schema_version": "aeep.current-callback-proxy-lifecycle-review.v1",
        "source_digest": SOURCE,
        "authority": "existing onboarding plus standing finite assessment-definition delegation",
        "purpose": "temporarily start the exact reviewed proxy for one already-reviewed one-turn current B treatment callback, then restore its stopped state",
        "request": request.model_dump(mode="json"),
        "request_digest": content_digest(request),
        "definitions": definitions,
        "definition": definition.model_dump(mode="json"),
        "definition_digest": mapping_digest,
        "amendment": amendment.model_dump(mode="json"),
        "canonical_store": store,
        "inner_execution_review_path": str(INNER_REVIEW),
        "inner_execution_review_sha256": inner_review_sha256,
        "inner_preparation_sha256": inner_review["preparation_sha256"],
        "inner_runner_sha256": inner_review["runner_sha256"],
        "inner_preparer_sha256": inner_review["preparer_sha256"],
        "inner_request_id": inner_review["request_id"],
        "inner_request_digest": inner_review["request_digest"],
        "inner_operation_id": "composed:" + inner_review["request_id"],
        "inner_model_id": INNER_MODEL,
        "inner_reasoning_effort": INNER_EFFORT,
        "inner_max_operations": 1,
        "inner_max_model_turns": 1,
        "inner_max_cash_usd": 0,
        "inner_task_calls": 1,
        "inner_task_call_timeout_seconds": INNER_TASK_TIMEOUT_SECONDS,
        "inner_max_elapsed_seconds": INNER_MAX_ELAPSED_SECONDS,
        "inner_call_timeout_seconds": INNER_CALL_TIMEOUT_SECONDS,
        "capacity_review_sha256": CAPACITY_REVIEW_SHA256,
        "capacity_result_sha256": CAPACITY_RESULT_SHA256,
        "capacity_digest": capacity["capacity_result"]["capacity_digest"],
        "capacity_observed_at": capacity["capacity_result"]["capacity"]["observed_at"],
        "capacity_max_age_seconds": MAX_CAPACITY_AGE_SECONDS,
        "capacity_window_count": len(capacity["capacity_result"]["capacity"]["windows"]),
        "proxy_name": PROXY_NAME,
        "proxy_id": PROXY_ID,
        "proxy_image": PROXY_IMAGE,
        "network_id": NETWORK_ID,
        "initial_proxy_running": False,
        "start_operation_id": request.plan_id + ":proxy_start",
        "stop_operation_id": request.plan_id + ":proxy_stop",
        "proxy_operations": 2,
        "proxy_start_seconds": START_SECONDS,
        "proxy_stop_seconds": STOP_SECONDS,
        "proxy_model_turns": 0,
        "proxy_cash_ceiling_usd": 0,
        "total_model_turns_including_inner": 1,
        "cash_ceiling_usd": 0,
        "outer_timeout_seconds": OUTER_TIMEOUT_SECONDS,
        "execution_authorized": False,
        "replay_allowed": False,
        "preparation_only": True,
    }
    with REVIEW.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"review_path": str(REVIEW), "review_sha256": sha(REVIEW), "request_id": request.plan_id}))


def validate_lifecycle_review(review_sha256: str) -> tuple[dict[str, Any], ConformanceProbeRequest]:
    if not REVIEW.is_file() or sha(REVIEW) != review_sha256:
        raise ValueError("exact lifecycle review hash differs")
    record = json.loads(REVIEW.read_text())
    inner, store, _capacity = validate_inner_review(record["inner_execution_review_sha256"])
    request = ConformanceProbeRequest.model_validate(record["request"])
    definition = CallbackProxyLifecycleDefinition.model_validate(record["definition"])
    if (
        record["source_digest"] != SOURCE
        or verification_source_digest(ROOT) != SOURCE
        or record["request_digest"] != content_digest(request)
        or request.mapping_digest != content_digest(definition)
        or record["definition_digest"] != request.mapping_digest
        or record["inner_execution_review_sha256"] != sha(INNER_REVIEW)
        or record["inner_request_id"] != inner["request_id"]
        or record["inner_request_digest"] != inner["request_digest"]
        or record["inner_operation_id"] != "composed:" + inner["request_id"]
        or record["inner_runner_sha256"] != sha(INNER_RUNNER)
        or record["inner_preparer_sha256"] != sha(INNER_PREPARER)
        or record["inner_preparation_sha256"] != sha(INNER_PREPARATION)
        or record["capacity_review_sha256"] != CAPACITY_REVIEW_SHA256
        or record["capacity_result_sha256"] != CAPACITY_RESULT_SHA256
        or record["proxy_id"] != PROXY_ID
        or record["proxy_name"] != PROXY_NAME
        or record["proxy_image"] != PROXY_IMAGE
        or record["network_id"] != NETWORK_ID
        or record["initial_proxy_running"] is not False
        or record["proxy_operations"] != 2
        or record["proxy_start_seconds"] != START_SECONDS
        or record["proxy_stop_seconds"] != STOP_SECONDS
        or record["proxy_model_turns"] != 0
        or record["proxy_cash_ceiling_usd"] != 0
        or record["total_model_turns_including_inner"] != 1
        or record["cash_ceiling_usd"] != 0
        or record["start_operation_id"] != request.plan_id + ":proxy_start"
        or record["stop_operation_id"] != request.plan_id + ":proxy_stop"
        or record["canonical_store"] != store
        or record["execution_authorized"] is not False
        or record["replay_allowed"] is not False
        or request.worker_digest != WORKER_DIGEST
    ):
        raise ValueError("reviewed one-turn proxy lifecycle scope differs")
    verify_dependencies(request.executable_dependencies)
    return record, request


async def execute(review_sha256: str) -> dict[str, Any]:
    review, request = validate_lifecycle_review(review_sha256)
    if STARTED.exists() or RESULT.exists() or INNER_STARTED.exists() or INNER_RESULT.exists():
        raise ValueError("preserve existing callback/lifecycle attempt; replay is denied")
    if inspect_proxy()["Running"] is not False:
        raise ValueError("proxy is not in the reviewed initially stopped state")

    router = Router.from_manifest(MANIFEST)
    repository = AssessmentRepository(router.store)
    result: dict[str, Any] = {
        "schema_version": "aeep.current-callback-proxy-lifecycle-result.v1",
        "source_digest": SOURCE,
        "request_id": request.plan_id,
        "request_digest": review["request_digest"],
        "review_sha256": review_sha256,
        "inner_execution_review_sha256": review["inner_execution_review_sha256"],
        "inner_request_id": review["inner_request_id"],
        "inner_request_digest": review["inner_request_digest"],
        "proxy_id": PROXY_ID,
        "total_model_turns_including_inner": 1,
        "proxy_lifecycle_model_turns": 0,
        "cash_ceiling_usd": 0,
        "actual_cash_cost_usd": None,
        "subscription_usage": "unknown; not read by these operations",
        "proxy_restored_stopped": False,
        "callback_passed": False,
        "whole_system_cost_complete": False,
    }
    start_operation = str(review["start_operation_id"])
    stop_operation = str(review["stop_operation_id"])
    start_reserved = stop_reserved = start_attempted = False
    start_elapsed = stop_elapsed = proxy_running_wall = 0.0
    start_began: float | None = None
    start_ended: float | None = None
    proxy_started_at: float | None = None
    error_type: str | None = None
    try:
        definition = CallbackProxyLifecycleDefinition.model_validate(review["definition"])
        if content_digest(definition) != request.mapping_digest:
            raise ValueError("callback proxy definition changed")
        repository.put("current_callback_proxy_lifecycle_definition", request.mapping_digest, definition)
        repository.put("conformance_request", request.plan_id, request)
        repository.approve_bundle(
            AssessmentScopeAmendment.model_validate(review["amendment"]),
            review["definitions"],
        )
        repository.authorize(request)
        with STARTED.open("x", encoding="utf-8") as stream:
            json.dump({"review_sha256": review_sha256, "request_id": request.plan_id}, stream)
            stream.write("\n")
        repository.reserve(
            request,
            start_operation,
            AssessmentLimits(max_operations=1, max_elapsed_seconds=START_SECONDS, max_model_turns=0, max_cash_usd=0),
            stage="reviewed_proxy_setup",
        )
        start_reserved = True
        start_began = time.monotonic()
        repository.reserve(
            request,
            stop_operation,
            AssessmentLimits(max_operations=1, max_elapsed_seconds=STOP_SECONDS, max_model_turns=0, max_cash_usd=0),
            stage="reviewed_proxy_cleanup",
        )
        stop_reserved = True
        if inspect_proxy()["Running"] is not False:
            raise ValueError("proxy changed before reviewed start")
        start_attempted = True
        docker("start", PROXY_ID, timeout=25)
        proxy_started_at = time.monotonic()
        if inspect_proxy()["Running"] is not True:
            raise ValueError("proxy start was not confirmed")
        result["proxy_started"] = True
        start_ended = time.monotonic()

        loader = importlib.util.spec_from_file_location("reviewed_current_callback_runner", INNER_RUNNER)
        if loader is None or loader.loader is None:
            raise RuntimeError("exact callback runner cannot be loaded")
        module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(module)
        async with asyncio.timeout(INNER_CALL_TIMEOUT_SECONDS):
            inner_result = await module.execute(review["inner_execution_review_sha256"])
        if not isinstance(inner_result, dict) or not INNER_RESULT.is_file():
            raise RuntimeError("callback runner returned without its exact durable result")
        persisted = json.loads(INNER_RESULT.read_text())
        result["inner_result_sha256"] = sha(INNER_RESULT)
        result["inner_operation_id"] = inner_result.get("operation_id")
        result["inner_probe_digest"] = inner_result.get("probe_digest")
        result["inner_execution_evidence_digest"] = inner_result.get("evidence_digest")
        result["inner_host_receipt_digest"] = inner_result.get("host_receipt_digest")
        result["inner_elapsed_seconds"] = inner_result.get("elapsed_seconds")
        result["inner_model_turn_count_observed"] = inner_result.get("model_turn_count_observed")
        result["callback_passed"] = (
            persisted == inner_result
            and inner_result.get("request_id") == review["inner_request_id"]
            and inner_result.get("request_digest") == review["inner_request_digest"]
            and inner_result.get("operation_id") == review["inner_operation_id"]
            and inner_result.get("source_digest") == SOURCE
            and inner_result.get("worker_digest") == WORKER_DIGEST
            and inner_result.get("model_turns_reserved") == 1
            and inner_result.get("model_turn_count_observed") == 1
            and inner_result.get("cash_ceiling_usd") == 0
            and inner_result.get("cash_cost_usd") is None
            and inner_result.get("error_type") is None
            and inner_result.get("cleanup_confirmed") is True
            and inner_result.get("source_unchanged") is True
            and inner_result.get("full_conformance") is False
            and inner_result.get("qualification") is False
            and inner_result.get("admission") is False
            and inner_result.get("value_trial") is False
            and inner_result.get("payload_recorded") is False
            and bool(inner_result.get("probe_digest"))
        )
        if proxy_started_at is not None:
            proxy_running_wall = time.monotonic() - proxy_started_at
    except BaseException as exc:
        error_type = type(exc).__name__
    finally:
        stop_began = time.monotonic()
        try:
            if start_attempted and inspect_proxy()["Running"] is True:
                docker("stop", "--time", "5", PROXY_ID, timeout=20)
            result["proxy_restored_stopped"] = inspect_proxy()["Running"] is False
        except BaseException as exc:
            result["proxy_restored_stopped"] = False
            result["cleanup_error_type"] = type(exc).__name__
            if error_type is None:
                error_type = type(exc).__name__
        if proxy_started_at is not None:
            proxy_running_wall = max(proxy_running_wall, time.monotonic() - proxy_started_at)
        if stop_reserved:
            stop_elapsed = time.monotonic() - stop_began
            try:
                repository.finish_operation(stop_operation, elapsed_seconds=stop_elapsed)
                result["cleanup_operation_settled"] = True
            except BaseException as exc:
                result["cleanup_operation_settled"] = False
                result["cleanup_accounting_error_type"] = type(exc).__name__
                if error_type is None:
                    error_type = type(exc).__name__
        if start_reserved:
            if start_began is not None:
                start_elapsed = max(0.0, (start_ended or time.monotonic()) - start_began)
            try:
                repository.finish_operation(start_operation, elapsed_seconds=start_elapsed)
                result["start_operation_settled"] = True
            except BaseException as exc:
                result["start_operation_settled"] = False
                result["start_accounting_error_type"] = type(exc).__name__
                if error_type is None:
                    error_type = type(exc).__name__
        result["proxy_start_elapsed_seconds"] = start_elapsed
        result["proxy_stop_elapsed_seconds"] = stop_elapsed
        result["proxy_running_wall_seconds"] = proxy_running_wall
        result["source_unchanged"] = verification_source_digest(ROOT) == SOURCE
        result["error_type"] = error_type
        try:
            async with asyncio.timeout(5):
                await router.close()
            result["router_closed"] = True
        except BaseException as exc:
            result["router_closed"] = False
            result["router_close_error_type"] = type(exc).__name__
            if error_type is None:
                error_type = type(exc).__name__
                result["error_type"] = error_type
        if (
            result.get("callback_passed") is not True
            or result.get("proxy_restored_stopped") is not True
            or result.get("cleanup_operation_settled") is not True
            or result.get("start_operation_settled") is not True
            or result.get("router_closed") is not True
            or result.get("source_unchanged") is not True
            or error_type is not None
        ):
            result["status"] = "failed"
        else:
            result["status"] = "passed"
        with RESULT.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
    print(json.dumps(result, sort_keys=True))
    if result.get("status") != "passed":
        raise SystemExit(1)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="action", required=True)
    prepare_parser = actions.add_parser("prepare")
    prepare_parser.add_argument("--inner-execution-review-sha256", required=True)
    execute_parser = actions.add_parser("execute")
    execute_parser.add_argument("--lifecycle-review-sha256", required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.inner_execution_review_sha256)
    else:
        asyncio.run(execute(args.lifecycle_review_sha256))


if __name__ == "__main__":
    main()
