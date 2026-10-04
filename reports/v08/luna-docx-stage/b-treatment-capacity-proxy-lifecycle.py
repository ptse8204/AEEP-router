"""Reviewed lifecycle for one zero-turn capacity refresh on the B worker."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

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
CAPACITY_REQUEST = OUT / "b-treatment-capacity-request.json"
CAPACITY_REVIEW = OUT / "b-treatment-capacity-review.json"
CAPACITY_REVIEW_SHA256 = "8817bcaac60cae0068b609bd3f4c634ecbd328412dd5f58047fe4f664825e324"
CAPACITY_PREPARER = OUT / "b-prepare-treatment-capacity.py"
CAPACITY_RUNNER = OUT / "b-run-treatment-capacity.py"
REVIEW = OUT / "b-treatment-capacity-proxy-lifecycle-review.json"
STARTED = OUT / "b-treatment-capacity-proxy-lifecycle-started.json"
RESULT = OUT / "b-treatment-capacity-proxy-lifecycle-result.json"
DOCKER = [
    "/usr/local/bin/docker",
    "--host",
    "unix:///Users/edwintse/.docker/run/docker.sock",
]
PROXY_NAME = "aeep-reviewed-model-proxy"
PROXY_ID = "5f9a44f86633409a250d11a78cf59357495da2078724ee0261bc73acff57f0f3"
PROXY_IMAGE = "sha256:5bf590eb0bf8a06187ff092f0f75cf83b540cc27bd6a75fd8bd91305ca7b13de"
NETWORK_ID = "8f657f861de8897d53df66efdf595c6d2e202b174af81f2827db409fe53f19d6"
START_SECONDS = 60
STOP_SECONDS = 60
CAPACITY_SECONDS = 60
OUTER_SECONDS = 180


class ProxyLifecycleDefinition(StrictModel):
    source_digest: str
    capacity_review_sha256: str
    capacity_request_digest: str
    capacity_operation_id: str
    worker_digest: str
    proxy_name: str
    proxy_id: str
    proxy_image: str
    network_id: str
    start_seconds: int = START_SECONDS
    stop_seconds: int = STOP_SECONDS
    capacity_seconds: int = CAPACITY_SECONDS
    model_turns: int = 0
    cash_ceiling_usd: float = 0


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def docker(*args: str, timeout: int = 15) -> str:
    return subprocess.check_output(
        DOCKER + list(args), text=True, timeout=timeout, stderr=subprocess.DEVNULL
    ).strip()


def inspect_proxy() -> dict[str, object]:
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


def verify_canonical_store(setup: dict[str, object], capacity: dict[str, object]) -> None:
    expected = setup["canonical_store"]
    if expected != capacity["canonical_store"]:
        raise ValueError("setup and capacity review canonical store pins differ")
    manifest_pin = expected["manifest_sha256"]
    database = Path(expected["database"])
    if (
        SETUP_REVIEW.is_symlink()
        or sha(SETUP_REVIEW) != SETUP_SHA256
        or MANIFEST.is_symlink()
        or sha(MANIFEST) != manifest_pin
        or database != ROOT / ".aeep/live-review-v3/aeep.sqlite3"
        or database.is_symlink()
        or not database.is_file()
    ):
        raise ValueError("canonical manifest or database path changed")
    manifest = json.loads(MANIFEST.read_text())
    stat = database.stat()
    if (
        manifest["database"] != str(database)
        or str(database) != expected["database"]
        or stat.st_dev != expected["device"]
        or stat.st_ino != expected["inode"]
    ):
        raise ValueError("canonical database identity changed")


def load_capacity_inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    setup = json.loads(SETUP_REVIEW.read_text())
    review = json.loads(CAPACITY_REVIEW.read_text())
    request_record = json.loads(CAPACITY_REQUEST.read_text())
    if (
        verification_source_digest(ROOT) != SOURCE
        or sha(SETUP_REVIEW) != SETUP_SHA256
        or sha(CAPACITY_REVIEW) != CAPACITY_REVIEW_SHA256
        or sha(CAPACITY_REQUEST) != review["request_file_sha256"]
        or review["source_digest"] != SOURCE
        or review["request_digest"] != request_record["request_digest"]
        or content_digest(request_record["request"]) != review["request_digest"]
        or review["request_id"] != request_record["request"]["plan_id"]
        or review["definition_digest"] != request_record["definition_digest"]
        or content_digest(request_record["definition"]) != review["definition_digest"]
        or review["operation_id"] != request_record["operation_id"]
        or request_record["stage"] != "capacity_introspection"
        or review["worker_digest"] != setup["request"]["worker_digest"]
        or review["resource_id"] != "codex.self"
        or review["method"] != "account/rateLimits/read"
        or review["maximum_operations"] != 1
        or review["maximum_model_turns"] != 0
        or review["maximum_elapsed_seconds"] != CAPACITY_SECONDS
        or review["cash_ceiling_usd"] != 0
        or review["execution_authorized"] is not False
        or review["proxy_lifecycle_owned_here"] is not False
        or review["runner_sha256"] != sha(CAPACITY_RUNNER)
        or review["prepare_script_sha256"] != sha(CAPACITY_PREPARER)
    ):
        raise ValueError("fresh exact capacity preparation is unavailable")
    verify_canonical_store(setup, review)
    return setup, review, request_record


def prepare() -> None:
    if REVIEW.exists() or STARTED.exists() or RESULT.exists():
        raise ValueError("preserve existing lifecycle records; replay is denied")
    if inspect_proxy()["Running"] is not False:
        raise ValueError("proxy must be stopped before lifecycle preparation")
    setup, capacity, capacity_record = load_capacity_inputs()
    base = setup["request"]
    capacity_request = capacity_record["request"]
    capacity_definition_digest = capacity_record["definition_digest"]
    if (
        capacity_request["authorization_id"] != "onboarding"
        or capacity_request["subject_digest"] != base["subject_digest"]
        or capacity_request["recipe_digest"] != base["recipe_digest"]
        or capacity_request["environment_digest"] != base["environment_digest"]
        or capacity_request["planner"]["id"] != capacity["executor_id"]
        or capacity_record["definition"]["worker_digest"] != capacity["worker_digest"]
        or capacity["worker_digest"] != base["worker_digest"]
    ):
        raise ValueError("capacity request does not share the reviewed task and worker scope")

    definition = ProxyLifecycleDefinition(
        source_digest=SOURCE,
        capacity_review_sha256=CAPACITY_REVIEW_SHA256,
        capacity_request_digest=capacity["request_digest"],
        capacity_operation_id=capacity["operation_id"],
        worker_digest=capacity["worker_digest"],
        proxy_name=PROXY_NAME,
        proxy_id=PROXY_ID,
        proxy_image=PROXY_IMAGE,
        network_id=NETWORK_ID,
    )
    definitions = dict(setup["definitions"])
    definitions[capacity_definition_digest] = capacity_record["definition"]
    capacity_request_digest = content_digest(capacity_request)
    definitions[capacity_request_digest] = capacity_request
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
        worker_digest=capacity["worker_digest"],
        executable_dependencies=runtime_dependencies()
        | {
            str(path.resolve()): sha(path)
            for path in (
                Path(__file__),
                CAPACITY_PREPARER,
                CAPACITY_RUNNER,
                CAPACITY_REQUEST,
                CAPACITY_REVIEW,
                SETUP_REVIEW,
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
        "schema_version": "aeep.capacity-proxy-lifecycle-review.v1",
        "source_digest": SOURCE,
        "authority": "existing onboarding and standing finite assessment-definition delegation",
        "purpose": "temporarily start the exact reviewed proxy for one zero-turn rate-limit observation and restore its stopped state",
        "request": request.model_dump(mode="json"),
        "request_digest": content_digest(request),
        "definitions": definitions,
        "definition": definition.model_dump(mode="json"),
        "definition_digest": mapping_digest,
        "amendment": amendment.model_dump(mode="json"),
        "capacity_review_path": str(CAPACITY_REVIEW),
        "capacity_review_sha256": CAPACITY_REVIEW_SHA256,
        "capacity_request_path": str(CAPACITY_REQUEST),
        "capacity_request_file_sha256": sha(CAPACITY_REQUEST),
        "capacity_request_digest": capacity["request_digest"],
        "capacity_operation_id": capacity["operation_id"],
        "capacity_runner_sha256": sha(CAPACITY_RUNNER),
        "runner_path": str(Path(__file__).resolve()),
        "runner_sha256": sha(Path(__file__)),
        "proxy_name": PROXY_NAME,
        "proxy_id": PROXY_ID,
        "proxy_image": PROXY_IMAGE,
        "network_id": NETWORK_ID,
        "initial_proxy_running": False,
        "start_operation_id": request.plan_id + ":proxy_start",
        "stop_operation_id": request.plan_id + ":proxy_stop",
        "proxy_operations": 2,
        "proxy_reserved_seconds": START_SECONDS + STOP_SECONDS,
        "capacity_operation_allowance": 1,
        "total_model_turns": 0,
        "cash_ceiling_usd": 0,
        "outer_timeout_seconds": OUTER_SECONDS,
        "execution_authorized": False,
        "replay_allowed": False,
        "preparation_only": True,
    }
    with REVIEW.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"review_path": str(REVIEW), "review_sha256": sha(REVIEW), "request_id": request.plan_id}))


def validate_review(review_sha256: str) -> tuple[dict[str, object], ConformanceProbeRequest]:
    if sha(REVIEW) != review_sha256 or sha(REVIEW) == "":
        raise ValueError("exact lifecycle review hash differs")
    review = json.loads(REVIEW.read_text())
    _, capacity, capacity_record = load_capacity_inputs()
    request = ConformanceProbeRequest.model_validate(review["request"])
    definition = ProxyLifecycleDefinition.model_validate(review["definition"])
    if (
        review["source_digest"] != SOURCE
        or verification_source_digest(ROOT) != SOURCE
        or review["request_digest"] != content_digest(request)
        or request.plan_id != review["request"]["plan_id"]
        or request.authorization_id != "onboarding"
        or review["definition_digest"] != content_digest(definition)
        or request.mapping_digest != review["definition_digest"]
        or review["capacity_review_sha256"] != CAPACITY_REVIEW_SHA256
        or review["capacity_request_digest"] != capacity["request_digest"]
        or review["capacity_operation_id"] != capacity["operation_id"]
        or review["start_operation_id"] != request.plan_id + ":proxy_start"
        or review["stop_operation_id"] != request.plan_id + ":proxy_stop"
        or review["capacity_runner_sha256"] != sha(CAPACITY_RUNNER)
        or review["runner_sha256"] != sha(Path(__file__))
        or review["capacity_request_file_sha256"] != sha(CAPACITY_REQUEST)
        or review["proxy_id"] != PROXY_ID
        or review["proxy_name"] != PROXY_NAME
        or review["proxy_image"] != PROXY_IMAGE
        or review["network_id"] != NETWORK_ID
        or review["initial_proxy_running"] is not False
        or review["proxy_operations"] != 2
        or review["proxy_reserved_seconds"] != START_SECONDS + STOP_SECONDS
        or review["capacity_operation_allowance"] != 1
        or review["total_model_turns"] != 0
        or review["cash_ceiling_usd"] != 0
        or review["execution_authorized"] is not False
        or review["replay_allowed"] is not False
        or request.worker_digest != capacity["worker_digest"]
        or capacity_record["operation_id"] != review["capacity_operation_id"]
    ):
        raise ValueError("reviewed capacity proxy lifecycle scope differs")
    verify_dependencies(request.executable_dependencies)
    return review, request


async def execute(review_sha256: str) -> dict[str, object]:
    review, request = validate_review(review_sha256)
    if STARTED.exists() or RESULT.exists():
        raise ValueError("preserve prior lifecycle result; replay is denied")
    if inspect_proxy()["Running"] is not False:
        raise ValueError("proxy is not in the reviewed initially stopped state")

    router = Router.from_manifest(MANIFEST)
    repository = AssessmentRepository(router.store)
    result: dict[str, object] = {
        "source_digest": SOURCE,
        "request_id": request.plan_id,
        "request_digest": review["request_digest"],
        "review_sha256": review_sha256,
        "capacity_review_sha256": CAPACITY_REVIEW_SHA256,
        "proxy_id": PROXY_ID,
        "model_turns": 0,
        "cash_ceiling_usd": 0,
        "actual_cash_cost_usd": None,
        "subscription_usage": "unknown; not read by these operations",
        "capacity_operation_allowance": 1,
        "proxy_restored_stopped": False,
        "capacity_refresh_passed": False,
        "whole_system_cost_complete": False,
    }
    start_operation = str(review["start_operation_id"])
    stop_operation = str(review["stop_operation_id"])
    start_reserved = stop_reserved = start_attempted = False
    start_elapsed = stop_elapsed = running_wall = 0.0
    started_at: float | None = None
    start_operation_began: float | None = None
    start_operation_ended: float | None = None
    error_type: str | None = None
    capacity_result_path = OUT / "b-treatment-capacity-result.json"
    try:
        # Verify exact definitions before recording or reserving any operation.
        definition = ProxyLifecycleDefinition.model_validate(review["definition"])
        if content_digest(definition) != request.mapping_digest:
            raise ValueError("proxy lifecycle definition changed")
        repository.put("proxy_lifecycle_definition", request.mapping_digest, definition)
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
        start_operation_began = time.monotonic()
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
        started_at = time.monotonic()
        running = inspect_proxy()
        if running["Running"] is not True:
            raise ValueError("proxy start was not confirmed")
        result["proxy_started"] = True
        start_operation_ended = time.monotonic()

        loader = importlib.util.spec_from_file_location("reviewed_b_capacity_runner", CAPACITY_RUNNER)
        if loader is None or loader.loader is None:
            raise RuntimeError("capacity runner cannot be loaded")
        module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(module)
        async with asyncio.timeout(OUTER_SECONDS - START_SECONDS - STOP_SECONDS):
            capacity_result = await module.execute(CAPACITY_REVIEW_SHA256)
        if not isinstance(capacity_result, dict):
            raise RuntimeError("capacity runner returned no structured result")
        if not capacity_result_path.is_file():
            raise RuntimeError("capacity result was not durably written")
        persisted_capacity_result = json.loads(capacity_result_path.read_text())
        result["capacity_result_sha256"] = sha(capacity_result_path)
        result["capacity_digest"] = capacity_result.get("capacity_digest")
        result["capacity_observed_at"] = (
            capacity_result.get("capacity", {}).get("observed_at")
            if isinstance(capacity_result.get("capacity"), dict)
            else None
        )
        result["capacity_refresh_passed"] = (
            persisted_capacity_result == capacity_result
            and capacity_result.get("status") == "passed"
            and capacity_result.get("stage") == "capacity_introspection"
            and capacity_result.get("method") == "account/rateLimits/read"
            and capacity_result.get("operation_id") == review["capacity_operation_id"]
            and capacity_result.get("request_digest") == review["capacity_request_digest"]
            and capacity_result.get("cleanup_confirmed") is True
            and capacity_result.get("source_unchanged") is True
            and capacity_result.get("worker_digest") == request.worker_digest
            and capacity_result.get("max_operations_reserved") == 1
            and capacity_result.get("max_model_turns_reserved") == 0
            and capacity_result.get("model_turns") == 0
            and capacity_result.get("cash_ceiling_usd") == 0
            and isinstance(capacity_result.get("capacity_digest"), str)
            and capacity_result.get("capacity_digest", "").startswith("sha256:")
            and isinstance(capacity_result.get("capacity"), dict)
            and capacity_result["capacity"].get("resource_id") == "codex.self"
            and bool(capacity_result["capacity"].get("observed_at"))
            and isinstance(capacity_result["capacity"].get("windows"), list)
        )
        result["capacity_result_path"] = str(capacity_result_path)
        if capacity_result_path.is_file():
            result["capacity_result_sha256"] = sha(capacity_result_path)
        result["capacity_operation_id"] = capacity_result.get("operation_id")
        result["capacity_elapsed_seconds"] = capacity_result.get("elapsed_seconds")
        if started_at is not None:
            running_wall = time.monotonic() - started_at
    except BaseException as exc:
        error_type = type(exc).__name__
    finally:
        stop_begin = time.monotonic()
        try:
            if start_attempted and inspect_proxy()["Running"] is True:
                docker("stop", "--time", "5", PROXY_ID, timeout=20)
            result["proxy_restored_stopped"] = inspect_proxy()["Running"] is False
        except BaseException as exc:
            result["proxy_restored_stopped"] = False
            result["cleanup_error_type"] = type(exc).__name__
            if error_type is None:
                error_type = type(exc).__name__
        if started_at is not None:
            running_wall = max(running_wall, time.monotonic() - started_at)
        if stop_reserved:
            stop_elapsed = time.monotonic() - stop_begin
            try:
                repository.finish_operation(stop_operation, elapsed_seconds=stop_elapsed)
                result["cleanup_operation_settled"] = True
            except BaseException as exc:
                result["cleanup_operation_settled"] = False
                result["cleanup_accounting_error_type"] = type(exc).__name__
                if error_type is None:
                    error_type = type(exc).__name__
        if start_reserved:
            if start_operation_began is not None:
                end = start_operation_ended or time.monotonic()
                start_elapsed = max(0.0, end - start_operation_began)
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
        result["proxy_running_wall_seconds"] = running_wall
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
            result.get("capacity_refresh_passed") is not True
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

    print(json.dumps(result))
    if result.get("status") != "passed":
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    if sys.argv[1:] == ["prepare"]:
        prepare()
    elif len(sys.argv) == 3 and sys.argv[1] == "execute":
        asyncio.run(execute(sys.argv[2]))
    else:
        raise SystemExit("usage: b-treatment-capacity-proxy-lifecycle.py prepare | execute REVIEW_SHA")
