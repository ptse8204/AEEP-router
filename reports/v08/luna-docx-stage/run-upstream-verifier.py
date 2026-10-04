"""Run the pinned 18-case upstream verifier in its own reviewed image."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
STAGE = OUT / "upstream-verifier-stage.json"
REVIEW = OUT / "upstream-verifier-execution-review.json"
STARTED = OUT / "upstream-verifier-run-started.json"
RESULT = OUT / "upstream-verifier-run-result.json"
MANIFEST = OUT / "upstream-verifier-context" / "stage-manifest.json"
SOURCE_DIR = OUT / "upstream-verifier-context" / "verifier"
INPUT_DIR = OUT / "upstream-verifier-context" / "input"
MAX_SECONDS = 30
MAX_OUTPUT_BYTES = 128_000
CLEANUP_RESERVE_SECONDS = 4.0
FINALIZE_RESERVE_SECONDS = 1.0


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha(path.read_bytes())


def docker(args: list[str], timeout: float = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], check=False, capture_output=True, text=True, timeout=timeout)


def verify_campaign_terminal(review: dict[str, object]) -> None:
    marker_name = review.get("campaign_terminal_record_path")
    marker_digest = review.get("campaign_terminal_record_sha256")
    if not isinstance(marker_name, str) or not isinstance(marker_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", marker_digest):
        raise RuntimeError("fresh campaign-terminal record path and hash are required")
    marker = (OUT / marker_name).resolve()
    if not marker.is_relative_to(OUT.resolve()) or sha_file(marker) != marker_digest:
        raise RuntimeError("campaign-terminal record is outside the stage or its digest differs")
    evidence = json.loads(marker.read_text())
    if evidence.get("terminal") is not True or evidence.get("source_digest") != review.get("source_digest"):
        raise RuntimeError("campaign-terminal record is not terminal for the reviewed source")
    result_name = evidence.get("result_path")
    result_digest = evidence.get("result_sha256")
    if not isinstance(result_name, str) or not isinstance(result_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", result_digest):
        raise RuntimeError("campaign-terminal record lacks exact result path/hash")
    terminal_result = (OUT / result_name).resolve()
    if not terminal_result.is_relative_to(OUT.resolve()) or sha_file(terminal_result) != result_digest:
        raise RuntimeError("campaign result does not match terminal record")


def main() -> None:
    if len(sys.argv) != 2 or not REVIEW.exists() or sha_file(REVIEW) != sys.argv[1]:
        raise RuntimeError("exact reviewed execution-review SHA-256 required")
    review_bytes = REVIEW.read_bytes()
    review = json.loads(review_bytes)
    if review.get("status") != "approved_after_campaign" or review.get("execution_authorized") is not True:
        raise RuntimeError("run is inert until a fresh post-campaign review authorizes it")
    verify_campaign_terminal(review)
    if review.get("runner_sha256") != sha_file(Path(__file__)):
        raise RuntimeError("runner changed after review")
    if review.get("stage_manifest_sha256") != sha_file(STAGE):
        raise RuntimeError("source/input staging record changed")
    build_result_path = OUT / "upstream-verifier-build-result.json"
    if review.get("verifier_build_result_sha256") != sha_file(build_result_path):
        raise RuntimeError("verified image-build result changed or is missing")
    build_result = json.loads(build_result_path.read_text())
    if (build_result.get("status") != "pass" or build_result.get("image_built") is not True
            or build_result.get("image_id_matches") is not True
            or build_result.get("base_tag_unchanged_after_build") is not True
            or build_result.get("source_unchanged") is not True
            or build_result.get("build_inputs_unchanged") is not True
            or build_result.get("assessment_operation_finalized") is not True
            or build_result.get("authorization_id") != "onboarding"
            or build_result.get("trial_worker_started") is not False
            or build_result.get("docker_build_performed") is not True):
        raise RuntimeError("verifier-only image build did not pass its independent checks")
    if review.get("verifier_image_id") != build_result.get("image_id_from_inspect"):
        raise RuntimeError("execution review image ID differs from the built verifier image")
    stage = json.loads(STAGE.read_text())
    expected_files = {
        SOURCE_DIR / "test_outputs.py": "913b9a3ebe579aed9c8f876dededea4d6a957eca9fbd0d9e8f043719cfb8cf05",
        SOURCE_DIR / "LICENSE": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
        INPUT_DIR / "offer_letter_filled.docx": "e5ba556c1b7ef19620b8b3963710714218d0eb21b61ec0ba4964a35be60c42c7",
        INPUT_DIR / "employee_data.json": "64dcb6aad2423051a638efefc85d1b47d306718e462342281553bf00082870c0",
    }
    if review.get("stage_hashes") != {str(path.relative_to(OUT)): digest for path, digest in expected_files.items()}:
        raise RuntimeError("review does not bind the exact staged source and fixture")
    for path, digest in expected_files.items():
        if sha_file(path) != digest or path.stat().st_mode & 0o222:
            raise RuntimeError("staged input changed or is writable")
    if stage.get("status") != "staged_readonly_no_execution":
        raise RuntimeError("staging evidence is not the reviewed inert record")
    if review.get("pytest_assertion_cases") != 18 or review.get("expected_pytest_version") != "8.4.1" or review.get("expected_python_docx_version") != "1.1.2":
        raise RuntimeError("test count or dependency pin changed")
    if review.get("limits") != {"max_operations": 1, "max_seconds": 30, "max_model_turns": 0, "max_cash_usd": 0}:
        raise RuntimeError("run limits changed")
    reservation = review.get("assessment_reservation", {})
    if not all(isinstance(reservation.get(key), str) and reservation[key] for key in ("plan_id", "operation_id")):
        raise RuntimeError("review must bind the separately reserved canonical assessment operation")
    if STARTED.exists() or RESULT.exists():
        raise RuntimeError("prior run evidence exists; do not replay")
    image_id = review.get("verifier_image_id")
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise RuntimeError("review must bind the exact locally built verifier image ID")

    sys.path.insert(0, str(ROOT / "src"))
    from aeep.assessment.verification import verification_source_digest
    if verification_source_digest(ROOT) != review.get("source_digest"):
        raise RuntimeError("reviewed source tree changed before verifier run")
    from aeep.assessment.models import AssessmentOperation
    from aeep.assessment.repository import AssessmentRepository
    from aeep.router import Router

    router = Router.from_manifest(ROOT / ".aeep/live-review-v3/aeep.json")
    repository = AssessmentRepository(router.store)
    operation_id = reservation["operation_id"]
    plan_id = reservation["plan_id"]
    name = "aeep-docx-upstream-verifier-" + sys.argv[1][:12]
    started = False
    run_invoked = False
    begun = time.monotonic()
    deadline = begun + MAX_SECONDS
    result: dict[str, object] = {
        "schema_version": "assessment.skillsbench-docx-upstream-verifier-result.v1",
        "status": "incomplete",
        "review_sha256": sys.argv[1],
        "runner_sha256": sha_file(Path(__file__)),
        "source_digest": review["source_digest"],
        "image_id": image_id,
        "container_name": name,
        "operation_id": operation_id,
        "plan_id": plan_id,
        "authorization_id": "onboarding",
        "pytest_assertion_cases_expected": 18,
        "trial_worker_or_model_started": False,
        "authentication_accessed": False,
        "source_or_fixture_contents_recorded": False,
        "container_preserved": True,
    }
    def run_docker(args: list[str], cap: float) -> subprocess.CompletedProcess[str]:
        remaining = deadline - time.monotonic() - FINALIZE_RESERVE_SECONDS
        if remaining <= 0:
            raise TimeoutError("overall 30 second verifier-operation deadline reached")
        return docker(args, timeout=min(cap, remaining))

    try:
        operation = AssessmentOperation.model_validate(repository.get("operation_start", operation_id))
        if operation.plan_id != plan_id or operation.stage != "skillsbench_upstream_verifier_compatibility":
            raise RuntimeError("assessment operation plan/stage does not match the reviewed verifier")
        limits = operation.reserved
        if limits.max_operations != 1 or limits.max_model_turns != 0 or limits.max_cash_usd != 0 or limits.max_elapsed_seconds != MAX_SECONDS:
            raise RuntimeError("reserved assessment limits exceed the reviewed verifier bounds")
        state = router.store._connection.execute("SELECT grant_id,state FROM assessment_operations WHERE id=?", (operation_id,)).fetchone()
        if state is None or state[0] != "onboarding" or state[1] != "reserved":
            raise RuntimeError("expected one reserved onboarding operation before running the verifier")
        with STARTED.open("x", encoding="utf-8") as stream:
            json.dump({"review_sha256": sys.argv[1], "operation_id": operation_id, "container_name": name, "started": True}, stream)
            stream.write("\n")
        started = True

        image = run_docker(["image", "inspect", "--format", "{{.Id}}", image_id], 2)
        if image.returncode != 0 or image.stdout.strip() != image_id:
            raise RuntimeError("reviewed verifier image ID is not available locally")
        prior = run_docker(["container", "inspect", "--format", "{{.Id}}", name], 2)
        if prior.returncode == 0 or "no such container" not in prior.stderr.lower():
            raise RuntimeError("preserving existing or uncertain verifier container name")

        argv = [
            "run", "--pull=never", "--network=none", "--read-only", "--user", "65534:65534",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cpus=1", "--memory=512m",
            "--memory-swap=512m", "--pids-limit=32", "--name", name,
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=32m",
            "--mount", f"type=bind,src={INPUT_DIR.resolve()},dst=/root,readonly",
            "--mount", f"type=bind,src={SOURCE_DIR.resolve()},dst=/verifier,readonly",
            "--env", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--entrypoint", "python3", image_id,
            "-m", "pytest", "-q", "-p", "no:cacheprovider", "/verifier/test_outputs.py",
        ]
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        remaining_for_run = deadline - time.monotonic() - CLEANUP_RESERVE_SECONDS - FINALIZE_RESERVE_SECONDS
        if remaining_for_run < 1:
            raise TimeoutError("insufficient overall budget remains after cleanup reservation")
        run_invoked = True
        try:
            completed = subprocess.run(["docker", *argv], capture_output=True, timeout=min(20, remaining_for_run), env=env, check=False)
            stdout = completed.stdout or b""
            stderr = completed.stderr or b""
            result.update(container_exit_code=completed.returncode, wall_seconds=time.monotonic() - begun)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or b""
            stderr = exc.stderr or b""
            result.update(container_timeout=True, wall_seconds=time.monotonic() - begun)
        if len(stdout) + len(stderr) > MAX_OUTPUT_BYTES:
            result["output_limit_exceeded"] = True
        result["stdout_bytes"] = len(stdout)
        result["stdout_sha256"] = sha(stdout)
        result["stderr_bytes"] = len(stderr)
        result["stderr_sha256"] = sha(stderr)
        combined = (stdout + b"\n" + stderr).decode("utf-8", "replace")[:MAX_OUTPUT_BYTES]
        match = re.search(r"\b(\d+) passed\b", combined)
        passed = int(match.group(1)) if match else 0
        result["pytest_cases_passed"] = passed
        metadata = run_docker(["container", "inspect", "--format", "{{.Id}}|{{.Image}}|{{.State.Status}}|{{.State.Running}}", name], 1.5)
        if metadata.returncode == 0:
            fields = metadata.stdout.strip().split("|")
            if len(fields) == 4:
                result["container_id"] = fields[0]
                result["container_image_id"] = fields[1]
                result["container_status"] = fields[2]
                result["container_running"] = fields[3] == "true"
        passed_all = (result.get("container_exit_code") == 0 and passed == 18 and not result.get("container_timeout")
                      and not result.get("output_limit_exceeded") and result.get("container_image_id") == image_id
                      and result.get("container_status") == "exited" and result.get("container_running") is False)
        result.update(status="pass" if passed_all else "fail_or_incomplete", exact_upstream_assertions_passed=passed_all)
    except BaseException as exc:
        result.update(status="fail_or_incomplete", error_type=type(exc).__name__)
    finally:
        elapsed = time.monotonic() - begun
        # If docker run was invoked, reconcile only the unique container name
        # derived from this review. Preserve the stopped container as evidence.
        if run_invoked:
            try:
                remaining = deadline - time.monotonic() - FINALIZE_RESERVE_SECONDS
                if remaining > 0.1:
                    metadata = docker(["container", "inspect", "--format", "{{.State.Running}}", name], timeout=min(1.0, remaining))
                    if metadata.returncode != 0 or metadata.stdout.strip() == "true":
                        remaining = deadline - time.monotonic() - FINALIZE_RESERVE_SECONDS
                        if remaining > 0.1:
                            stopped = docker(["stop", "--time", "1", name], timeout=min(2.0, remaining))
                            result["owned_container_stop_attempted"] = True
                            result["owned_container_stop_returncode"] = stopped.returncode
                            remaining = deadline - time.monotonic() - FINALIZE_RESERVE_SECONDS
                            if remaining > 0.1:
                                after = docker(["container", "inspect", "--format", "{{.State.Status}}|{{.State.Running}}", name], timeout=min(1.0, remaining))
                                if after.returncode == 0:
                                    result["owned_container_status_after_cleanup"] = after.stdout.strip()
                    result["owned_container_cleanup_checked"] = metadata.returncode == 0
            except BaseException as cleanup_exc:
                result["owned_container_cleanup_error_type"] = type(cleanup_exc).__name__
        try:
            source_unchanged = (
                verification_source_digest(ROOT) == review["source_digest"]
                and
                sha_file(STAGE) == review["stage_manifest_sha256"]
                and all(sha_file(path) == digest for path, digest in expected_files.items())
            )
        except BaseException:
            source_unchanged = False
        result["source_unchanged"] = source_unchanged
        elapsed = time.monotonic() - begun
        if elapsed > MAX_SECONDS:
            result["overall_deadline_exceeded"] = True
            result["status"] = "fail_or_incomplete"
        if started:
            try:
                repository.finish_operation(operation_id, elapsed_seconds=elapsed)
                result["assessment_operation_finalized"] = True
            except BaseException as accounting_exc:
                result["assessment_operation_finalized"] = False
                result["accounting_finalize_error_type"] = type(accounting_exc).__name__
        result["accounted_wall_seconds"] = elapsed
        if result.get("source_unchanged") is not True or result.get("assessment_operation_finalized") is not True:
            result["status"] = "fail_or_incomplete"
            result["exact_upstream_assertions_passed"] = False
        if result.get("owned_container_status_after_cleanup") not in (None, "exited|false"):
            result["status"] = "fail_or_incomplete"
            result["exact_upstream_assertions_passed"] = False
        with RESULT.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(json.dumps({key: result[key] for key in ("status", "pytest_cases_passed", "container_id", "accounted_wall_seconds") if key in result}))
        router.store.close()


if __name__ == "__main__":
    main()
