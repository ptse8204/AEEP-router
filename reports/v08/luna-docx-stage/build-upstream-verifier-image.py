"""Build one separate local verifier image after a reviewed reservation."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
CONTEXT = OUT / "verifier-image-context"
PLAN = OUT / "upstream-verifier-image-plan.json"
REVIEW = OUT / "upstream-verifier-build-review.json"
STARTED = OUT / "upstream-verifier-build-started.json"
RESULT = OUT / "upstream-verifier-build-result.json"
DOCKERFILE = CONTEXT / "Dockerfile.verifier"
LOCK = CONTEXT / "requirements-verifier.lock"
WHEELS = CONTEXT / "wheels"
MAX_SECONDS = 180
MAX_GROWTH = 1_000_000_000
MIN_IMPORTANT_FREE = 50 * 1024**3 + MAX_GROWTH
FINALIZE_RESERVE_SECONDS = 2.0
DEADLINE: float | None = None
OUTPUT_TAG = "aeep-skillsbench-docx-verifier:upstream-9a1f4dd-20261002"
BASE_TAG = "aeep-skillsbench-docx-control:luna-xhigh-20261002"
BASE_ID = "sha256:4817f921c3001597acd0fc3d22f35f1f0ee012dda866bdd1ac66bd386cc6de27"
EXPECTED_WHEELS = {
    "pytest-8.4.1-py3-none-any.whl": (365474, "539c70ba6fcead8e78eebbf1115e8b589e7565830d7d006a8723f19ac8a0afb7"),
    "iniconfig-2.1.0-py3-none-any.whl": (6050, "9deba5723312380e77435581c6bf4935c94cbfab9b1ed33ef8d238ea168eb760"),
    "packaging-25.0-py3-none-any.whl": (66469, "29572ef2b1f17581046b3a2227d5c611fb25ec70ca1ba8554b24b0e69331a484"),
    "pluggy-1.6.0-py3-none-any.whl": (20538, "e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746"),
    "pygments-2.19.2-py3-none-any.whl": (1225217, "86540386c03d588bb81d44bc3928634ff26449851e99741617ecb9037ee5ec0b"),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha(path.read_bytes())


def docker(args: list[str], timeout: float = 15) -> subprocess.CompletedProcess[str]:
    if DEADLINE is not None:
        remaining = DEADLINE - time.monotonic() - FINALIZE_RESERVE_SECONDS
        if remaining <= 0.1:
            raise TimeoutError("overall verifier-build deadline reached")
        timeout = min(timeout, remaining)
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, check=False)


def image_id(tag: str) -> str:
    result = docker(["image", "inspect", "--format", "{{.Id}}", tag])
    if result.returncode != 0:
        raise RuntimeError("image inspection failed; preserve state")
    return result.stdout.strip()


def important_capacity() -> int:
    timeout = 5.0
    if DEADLINE is not None:
        remaining = DEADLINE - time.monotonic() - FINALIZE_RESERVE_SECONDS
        if remaining <= 0.1:
            raise TimeoutError("overall verifier-build deadline reached")
        timeout = min(timeout, remaining)
    output = subprocess.check_output([sys.executable, str(OUT / "storage_probe.py")], text=True, timeout=timeout)
    values = dict(line.split("=", 1) for line in output.splitlines())
    return int(values["NSURLVolumeAvailableCapacityForImportantUsageKey_bytes"])


def check_disk(initial_free: int) -> int:
    current = shutil.disk_usage(ROOT).free
    if initial_free - current > MAX_GROWTH:
        raise RuntimeError("verifier image setup exceeded 1 GB host-growth cap")
    if important_capacity() < 50 * 1024**3:
        raise RuntimeError("important-usage capacity fell below 50 GiB reserve")
    return current


def verify_campaign_terminal(review: dict[str, object]) -> None:
    marker_name = review.get("campaign_terminal_record_path")
    marker_digest = review.get("campaign_terminal_record_sha256")
    if not isinstance(marker_name, str) or not isinstance(marker_digest, str) or len(marker_digest) != 64:
        raise RuntimeError("fresh campaign-terminal record path and hash are required")
    marker = (OUT / marker_name).resolve()
    if not marker.is_relative_to(OUT.resolve()) or sha_file(marker) != marker_digest:
        raise RuntimeError("campaign-terminal record is outside the stage or its digest differs")
    evidence = json.loads(marker.read_text())
    if evidence.get("terminal") is not True or evidence.get("source_digest") != review.get("source_digest"):
        raise RuntimeError("campaign-terminal record is not terminal for the reviewed source")
    result_name = evidence.get("result_path")
    result_digest = evidence.get("result_sha256")
    if not isinstance(result_name, str) or not isinstance(result_digest, str) or len(result_digest) != 64:
        raise RuntimeError("campaign-terminal record lacks exact result path/hash")
    terminal_result = (OUT / result_name).resolve()
    if not terminal_result.is_relative_to(OUT.resolve()) or sha_file(terminal_result) != result_digest:
        raise RuntimeError("campaign result does not match terminal record")


def main() -> None:
    if len(sys.argv) != 2 or not REVIEW.exists() or sha_file(REVIEW) != sys.argv[1]:
        raise RuntimeError("exact post-campaign verifier-build review SHA-256 required")
    review = json.loads(REVIEW.read_text())
    if review.get("status") != "approved_after_campaign" or review.get("execution_authorized") is not True:
        raise RuntimeError("verifier image build remains inert until a fresh post-campaign review")
    verify_campaign_terminal(review)
    if review.get("runner_sha256") != sha_file(Path(__file__)):
        raise RuntimeError("build runner changed after review")
    if review.get("plan_sha256") != sha_file(PLAN) or review.get("dockerfile_sha256") != sha_file(DOCKERFILE) or review.get("lock_sha256") != sha_file(LOCK):
        raise RuntimeError("image plan or build context changed after review")
    if review.get("output_tag") != OUTPUT_TAG or review.get("base_tag") != BASE_TAG or review.get("expected_base_image_id") != BASE_ID:
        raise RuntimeError("review does not bind the exact new tag and plain control base ID")
    if review.get("fetch_result_sha256") != sha_file(OUT / "upstream-verifier-wheel-fetch-result.json"):
        raise RuntimeError("successful wheel-fetch result changed or is missing")
    fetch_result = json.loads((OUT / "upstream-verifier-wheel-fetch-result.json").read_text())
    if fetch_result.get("status") != "all_pinned_wheels_verified":
        raise RuntimeError("wheel fetch did not complete with every pinned digest verified")
    if (fetch_result.get("assessment_operation_finalized") is not True or fetch_result.get("authorization_id") != "onboarding"
            or fetch_result.get("source_unchanged") is not True or fetch_result.get("source_digest") != review.get("source_digest")):
        raise RuntimeError("wheel-fetch operation is missing its canonical grant receipt")
    if review.get("limits") != {"max_operations": 1, "max_seconds": MAX_SECONDS, "max_model_turns": 0, "max_cash_usd": 0, "max_growth_bytes": MAX_GROWTH}:
        raise RuntimeError("build bounds changed after review")
    if STARTED.exists() or RESULT.exists() or (OUT / "upstream-verifier-image-id").exists() or (OUT / "verifier-build.log").exists():
        raise RuntimeError("prior build evidence exists; preserve it and do not retry")
    wheel_files = sorted(path.name for path in WHEELS.iterdir() if path.is_file())
    if wheel_files != sorted(EXPECTED_WHEELS):
        raise RuntimeError("wheel stage contains missing or unreviewed files")
    for filename, (size, digest) in EXPECTED_WHEELS.items():
        path = WHEELS / filename
        if path.stat().st_size != size or sha_file(path) != digest:
            raise RuntimeError("wheel bytes do not match the pinned metadata")

    sys.path.insert(0, str(ROOT / "src"))
    from aeep.assessment.verification import verification_source_digest
    if verification_source_digest(ROOT) != review.get("source_digest"):
        raise RuntimeError("frozen source digest changed before verifier build")
    from aeep.assessment.models import AssessmentOperation
    from aeep.assessment.repository import AssessmentRepository
    from aeep.router import Router

    router = Router.from_manifest(ROOT / ".aeep/live-review-v3/aeep.json")
    repository = AssessmentRepository(router.store)
    reservation = review.get("assessment_reservation", {})
    operation_id = reservation.get("operation_id")
    plan_id = reservation.get("plan_id")
    if not isinstance(operation_id, str) or not operation_id or not isinstance(plan_id, str) or not plan_id:
        router.store.close()
        raise RuntimeError("review must bind the separately reserved build operation")
    began = time.monotonic()
    global DEADLINE
    DEADLINE = began + MAX_SECONDS
    started = False
    build_started = False
    result: dict[str, object] = {
        "schema_version": "assessment.skillsbench-docx-verifier-build-result.v1",
        "status": "incomplete",
        "review_sha256": sys.argv[1],
        "runner_sha256": sha_file(Path(__file__)),
        "output_tag": OUTPUT_TAG,
        "expected_base_image_id": BASE_ID,
        "operation_id": operation_id,
        "plan_id": plan_id,
        "authorization_id": "onboarding",
        "model_turns": 0,
        "cash_usd": 0,
        "trial_worker_started": False,
        "docker_build_performed": False,
        "cleanup_performed": False,
    }
    try:
        operation = AssessmentOperation.model_validate(repository.get("operation_start", operation_id))
        if operation.plan_id != plan_id or operation.stage != "skillsbench_upstream_verifier_image_setup":
            raise RuntimeError("reserved assessment plan/stage does not match verifier image setup")
        limits = operation.reserved
        state = router.store._connection.execute("SELECT grant_id,state FROM assessment_operations WHERE id=?", (operation_id,)).fetchone()
        if state is None or state[0] != "onboarding" or state[1] != "reserved":
            raise RuntimeError("expected one reserved onboarding build operation")
        if limits.max_operations != 1 or limits.max_model_turns != 0 or limits.max_cash_usd != 0 or limits.max_elapsed_seconds != MAX_SECONDS:
            raise RuntimeError("reserved build limits exceed the reviewed bounds")
        with STARTED.open("x", encoding="utf-8") as stream:
            json.dump({"review_sha256": sys.argv[1], "operation_id": operation_id, "started": True}, stream)
            stream.write("\n")
        started = True

        if important_capacity() < MIN_IMPORTANT_FREE:
            raise RuntimeError("important-usage capacity is below 50 GiB plus 1 GB setup allowance")
        initial_free = shutil.disk_usage(ROOT).free
        if image_id(BASE_TAG) != BASE_ID:
            raise RuntimeError("control base tag does not resolve to the reviewed image ID")
        absent = docker(["image", "inspect", OUTPUT_TAG])
        if absent.returncode == 0 or "no such image" not in absent.stderr.lower():
            raise RuntimeError("preserving existing or uncertain output image tag")
        result["host_free_bytes_before"] = initial_free
        result["important_capacity_before"] = important_capacity()
        df_before = docker(["system", "df"])
        if df_before.returncode == 0:
            result["docker_system_df_before"] = df_before.stdout
        iidfile = OUT / "upstream-verifier-image-id"
        log_path = OUT / "verifier-build.log"
        remaining = DEADLINE - time.monotonic() - 20.0 - FINALIZE_RESERVE_SECONDS
        if remaining < 1:
            raise TimeoutError("insufficient whole-operation time remains for bounded build and verification")
        build_timeout = min(120.0, remaining)
        command = [
            "docker", "build", "--network=none", "--pull=false", "--platform", "linux/arm64",
            "--progress=plain", "--file", str(DOCKERFILE.resolve()), "--tag", OUTPUT_TAG,
            "--iidfile", str(iidfile.resolve()), str(CONTEXT.resolve()),
        ]
        with log_path.open("xb") as log:
            build_started = True
            result["docker_build_performed"] = True
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=build_timeout, check=False)
        result["build_exit_code"] = completed.returncode
        if completed.returncode == 0 and iidfile.exists():
            iid = iidfile.read_text().strip()
            result["image_id_from_iidfile"] = iid
            result["image_id_from_inspect"] = image_id(OUTPUT_TAG)
            result["base_image_id_after_build"] = image_id(BASE_TAG)
            result["image_id_matches"] = iid == result["image_id_from_inspect"]
            result["base_tag_unchanged_after_build"] = result["base_image_id_after_build"] == BASE_ID
        result["host_free_bytes_after"] = check_disk(initial_free)
        result["important_capacity_after"] = important_capacity()
        df_after = docker(["system", "df"])
        if df_after.returncode == 0:
            result["docker_system_df_after"] = df_after.stdout
        success = (result.get("build_exit_code") == 0 and result.get("image_id_matches") is True
                   and result.get("base_tag_unchanged_after_build") is True)
        result.update(status="pass" if success else "fail_or_incomplete", image_built=success)
    except subprocess.TimeoutExpired as exc:
        result.update(status="timeout_unknown_build_state", timeout_seconds=MAX_SECONDS, error_type=type(exc).__name__)
    except BaseException as exc:
        result.update(status="fail_or_incomplete", error_type=type(exc).__name__, error_summary=str(exc)[:160])
    finally:
        if build_started and "base_image_id_after_build" not in result:
            try:
                result["base_image_id_after_build"] = image_id(BASE_TAG)
                result["base_tag_unchanged_after_build"] = result["base_image_id_after_build"] == BASE_ID
            except BaseException as base_exc:
                result["base_id_after_error_type"] = type(base_exc).__name__
        if build_started and "image_id_from_inspect" not in result:
            try:
                result["image_id_from_inspect"] = image_id(OUTPUT_TAG)
            except BaseException:
                result["output_tag_image_id_unknown"] = True
        try:
            result["source_unchanged"] = verification_source_digest(ROOT) == review["source_digest"]
            result["build_inputs_unchanged"] = (
                sha_file(PLAN) == review["plan_sha256"]
                and sha_file(DOCKERFILE) == review["dockerfile_sha256"]
                and sha_file(LOCK) == review["lock_sha256"]
                and sha_file(OUT / "upstream-verifier-wheel-fetch-result.json") == review["fetch_result_sha256"]
                and all(
                    (WHEELS / name).stat().st_size == size and sha_file(WHEELS / name) == digest
                    for name, (size, digest) in EXPECTED_WHEELS.items()
                )
            )
        except OSError:
            result["source_unchanged"] = False
            result["build_inputs_unchanged"] = False
        elapsed = time.monotonic() - began
        if started:
            try:
                repository.finish_operation(operation_id, elapsed_seconds=elapsed)
                result["assessment_operation_finalized"] = True
            except BaseException as accounting_exc:
                result["assessment_operation_finalized"] = False
                result["accounting_finalize_error_type"] = type(accounting_exc).__name__
        result["accounted_wall_seconds"] = elapsed
        if result.get("status") == "pass" and not (
            result.get("source_unchanged") is True
            and result.get("build_inputs_unchanged") is True
            and result.get("base_tag_unchanged_after_build") is True
            and result.get("image_id_matches") is True
            and result.get("assessment_operation_finalized") is True
        ):
            result["status"] = "fail_or_incomplete"
            result["image_built"] = False
        with RESULT.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(json.dumps({key: result[key] for key in ("status", "image_id_from_inspect", "accounted_wall_seconds") if key in result}))
        router.store.close()


if __name__ == "__main__":
    main()
