"""Run one reviewed, sequential, one-turn connectivity probe per DOCX worker."""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from aeep.assessment.boundary import execute_model_probe
from aeep.assessment.models import AssessmentLimits, AssessmentScopeAmendment, ConformanceProbeRequest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.router import Router


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
REVIEW = OUT / "connectivity-execution-review-v2.json"
STARTED = OUT / "connectivity-started.json"
RESULT = OUT / "connectivity-result.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def docker(*args: str, timeout: int = 15) -> str:
    return subprocess.check_output(
        ["docker", *args], text=True, timeout=timeout, stderr=subprocess.DEVNULL
    ).strip()


def inspect_proxy(review: dict) -> dict:
    raw = docker(
        "inspect", "--format",
        '{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Networks":{{json .NetworkSettings.Networks}}}',
        review["proxy_name"],
    )
    meta = json.loads(raw)
    if not meta.get("Id", "").startswith(review["proxy_id_prefix"]):
        raise RuntimeError("proxy identity differs")
    if meta.get("Image") != review["proxy_image"]:
        raise RuntimeError("proxy image differs")
    networks = meta.get("Networks")
    if not isinstance(networks, dict) or review["network_id"] not in [
        value.get("NetworkID") for value in networks.values() if isinstance(value, dict)
    ]:
        raise RuntimeError("proxy network differs")
    return meta


async def main() -> None:
    if len(sys.argv) != 2 or not REVIEW.is_file() or sha256(REVIEW) != sys.argv[1]:
        raise RuntimeError("exact execution-review hash required")
    review = json.loads(REVIEW.read_text())
    if sha256(Path(__file__)) != review["runner_sha256"]:
        raise RuntimeError("runner changed")
    if verification_source_digest(ROOT) != review["source_digest"]:
        raise RuntimeError("source changed")
    if sha256(OUT / "connectivity-review.json") != review["connectivity_review_sha256"]:
        raise RuntimeError("connectivity definition review changed")
    if sha256(OUT / "pair-review.json") != review["pair_review_sha256"]:
        raise RuntimeError("paired task profile review changed")
    if sha256(OUT / "pair-result.json") != review["pair_result_sha256"]:
        raise RuntimeError("paired task profile result changed")
    if STARTED.exists() or RESULT.exists():
        raise RuntimeError("connectivity execution is one-shot; blind retry denied")

    capacities = dict(
        line.split("=", 1)
        for line in subprocess.check_output(
            [sys.executable, str(OUT / "storage_probe.py")], text=True, timeout=10
        ).splitlines()
    )
    if int(capacities["NSURLVolumeAvailableCapacityForImportantUsageKey_bytes"]) < 51 * 1024**3:
        raise RuntimeError("available capacity is below the 50 GiB reserve plus probe margin")

    for role, image in review["task_images"].items():
        exact = docker("image", "inspect", "--format", "{{.Id}}", image)
        if exact != image:
            raise RuntimeError(f"{role} worker image is not locally available by exact ID")
    initial_proxy = inspect_proxy(review)

    # The exclusive marker precedes all approvals, reservations, proxy changes,
    # and model calls. Any later failure remains non-replayable.
    with STARTED.open("x", encoding="utf-8") as stream:
        json.dump({"execution_review_sha256": sys.argv[1]}, stream)
        stream.write("\n")

    router = Router.from_manifest(ROOT / ".aeep/live-review-v3/aeep.json")
    service = AssessmentService(router, ROOT / ".aeep/live-review-v3/.aeep/assessments")
    repo = service.repository
    request = ConformanceProbeRequest.model_validate(review["proxy_request"])
    operation = request.plan_id + ":connectivity_proxy_lifecycle"
    result = {
        "execution_review_sha256": sys.argv[1],
        "source_digest": review["source_digest"],
        "request_ids": review["connectivity_request_ids"],
        "connectivity_only": True,
        "qualification": False,
        "admission": False,
        "proxy_was_running": bool(initial_proxy["Running"]),
        "worker_attempts": [],
        "proxy_restored": None,
        "model_turns_reserved_for_probes": 0,
        "cash_ceiling_usd": 0,
        "replay_allowed": False,
    }
    reserved = False
    started_proxy = False
    began = time.monotonic()
    lifecycle_began: float | None = None
    try:
        repo.approve_bundle(
            AssessmentScopeAmendment.model_validate(review["amendment"]),
            review["definitions"],
        )
        repo.reserve(
            request,
            operation,
            AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=600, max_cash_usd=0),
            stage="reviewed_connectivity_proxy_lifecycle",
        )
        reserved = True
        lifecycle_began = time.monotonic()
        repo.authorize(request)

        async with asyncio.timeout(420):
            if not result["proxy_was_running"]:
                current = inspect_proxy(review)
                if current["Running"]:
                    raise RuntimeError("proxy state changed after stopped-state preflight")
                # A timed-out start can still have changed container state, so
                # claim cleanup responsibility before issuing the start request.
                started_proxy = True
                docker("start", review["proxy_name"], timeout=30)
                current = inspect_proxy(review)
                if not current["Running"]:
                    raise RuntimeError("proxy did not enter the running state")
            for role in ("control", "treatment"):
                request_id = review["connectivity_request_ids"][role]
                try:
                    observation = await execute_model_probe(service, request_id)
                    connected = observation.observed == {"connected": True}
                    result["worker_attempts"].append({
                        "role": role,
                        "request_id": request_id,
                        "probe_id": observation.probe_id,
                        "worker_digest": observation.worker_digest,
                        "connected": connected,
                    })
                    if not connected:
                        result["stopped_after_role"] = role
                        break
                except BaseException as exc:
                    result["worker_attempts"].append({
                        "role": role,
                        "request_id": request_id,
                        "connected": False,
                        "error_type": type(exc).__name__,
                    })
                    result["stopped_after_role"] = role
                    break
    except BaseException as exc:
        result["runner_error_type"] = type(exc).__name__
    finally:
        if not result["proxy_was_running"] and started_proxy:
            try:
                current = inspect_proxy(review)
                if current["Running"]:
                    docker("stop", "--time", "5", review["proxy_name"], timeout=20)
                result["proxy_restored"] = not json.loads(
                    docker("inspect", "--format", "{{json .State.Running}}", review["proxy_name"])
                )
            except BaseException as exc:
                result["proxy_restored"] = False
                result["proxy_cleanup_error_type"] = type(exc).__name__
        elif not result["proxy_was_running"]:
            try:
                result["proxy_restored"] = not bool(inspect_proxy(review)["Running"])
            except BaseException as exc:
                result["proxy_restored"] = False
                result["proxy_cleanup_error_type"] = type(exc).__name__
        else:
            try:
                result["proxy_restored"] = bool(inspect_proxy(review)["Running"])
            except BaseException as exc:
                result["proxy_restored"] = False
                result["proxy_cleanup_error_type"] = type(exc).__name__
            result["proxy_prior_running_state_preserved"] = True
        if reserved:
            repo.finish_operation(operation, elapsed_seconds=time.monotonic() - (lifecycle_began or began))
        result["proxy_lifecycle_wall_seconds"] = time.monotonic() - (lifecycle_began or began)
        result["model_turns_reserved_for_probes"] = sum(
            operation.reserved.max_model_turns
            for request_id in review["connectivity_request_ids"].values()
            for operation in repo.operation_ledger(request_id).operations
        )
        result["source_unchanged"] = verification_source_digest(ROOT) == review["source_digest"]
        result["full_task_conformance"] = False
        result["candidate_skill_used"] = False
        with RESULT.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(json.dumps(result))
        await router.close()


asyncio.run(main())
