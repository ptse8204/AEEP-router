"""Fetch only the exact review-pinned pytest wheels after separate approval."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
CONTEXT = OUT / "verifier-image-context"
WHEELS = CONTEXT / "wheels"
REVIEW = OUT / "upstream-verifier-wheel-fetch-review.json"
STARTED = OUT / "upstream-verifier-wheel-fetch-started.json"
RESULT = OUT / "upstream-verifier-wheel-fetch-result.json"
WORKER = OUT / "download-one-verifier-wheel.py"
PACKAGES = [
    {"filename": "pytest-8.4.1-py3-none-any.whl", "sha256": "539c70ba6fcead8e78eebbf1115e8b589e7565830d7d006a8723f19ac8a0afb7", "size": 365474, "url": "https://files.pythonhosted.org/packages/29/16/c8a903f4c4dffe7a12843191437d7cd8e32751d5de349d45d3fe69544e87/pytest-8.4.1-py3-none-any.whl"},
    {"filename": "iniconfig-2.1.0-py3-none-any.whl", "sha256": "9deba5723312380e77435581c6bf4935c94cbfab9b1ed33ef8d238ea168eb760", "size": 6050, "url": "https://files.pythonhosted.org/packages/2c/e1/e6716421ea10d38022b952c159d5161ca1193197fb744506875fbb87ea7b/iniconfig-2.1.0-py3-none-any.whl"},
    {"filename": "packaging-25.0-py3-none-any.whl", "sha256": "29572ef2b1f17581046b3a2227d5c611fb25ec70ca1ba8554b24b0e69331a484", "size": 66469, "url": "https://files.pythonhosted.org/packages/20/12/38679034af332785aac8774540895e234f4d07f7545804097de4b666afd8/packaging-25.0-py3-none-any.whl"},
    {"filename": "pluggy-1.6.0-py3-none-any.whl", "sha256": "e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746", "size": 20538, "url": "https://files.pythonhosted.org/packages/54/20/4d324d65cc6d9205fabedc306948156824eb9f0ee1633355a8f7ec5c66bf/pluggy-1.6.0-py3-none-any.whl"},
    {"filename": "pygments-2.19.2-py3-none-any.whl", "sha256": "86540386c03d588bb81d44bc3928634ff26449851e99741617ecb9037ee5ec0b", "size": 1225217, "url": "https://files.pythonhosted.org/packages/c7/21/705964c7812476f378728bdf590ca4b771ec72385c533964653c68e86bdc/pygments-2.19.2-py3-none-any.whl"},
]
MAX_TOTAL = 1_700_000
MAX_SECONDS = 60
DOWNLOAD_SECONDS = 50


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_campaign_terminal(review: dict[str, object]) -> None:
    marker_name = review.get("campaign_terminal_record_path")
    marker_digest = review.get("campaign_terminal_record_sha256")
    if not isinstance(marker_name, str) or not isinstance(marker_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", marker_digest):
        raise RuntimeError("fresh campaign-terminal record path and hash are required")
    marker = (OUT / marker_name).resolve()
    if not marker.is_relative_to(OUT.resolve()) or sha(marker.read_bytes()) != marker_digest:
        raise RuntimeError("campaign-terminal record is outside the stage or its digest differs")
    evidence = json.loads(marker.read_text())
    if evidence.get("terminal") is not True or evidence.get("source_digest") != review.get("source_digest"):
        raise RuntimeError("campaign-terminal record is not terminal for the reviewed source")
    result_name = evidence.get("result_path")
    result_digest = evidence.get("result_sha256")
    if not isinstance(result_name, str) or not isinstance(result_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", result_digest):
        raise RuntimeError("campaign-terminal record lacks exact result path/hash")
    result_path = (OUT / result_name).resolve()
    if not result_path.is_relative_to(OUT.resolve()) or sha(result_path.read_bytes()) != result_digest:
        raise RuntimeError("campaign result does not match terminal record")


def main() -> None:
    if len(sys.argv) != 2 or not REVIEW.exists() or sha(REVIEW.read_bytes()) != sys.argv[1]:
        raise RuntimeError("exact post-campaign wheel-fetch review SHA-256 required")
    review = json.loads(REVIEW.read_text())
    if review.get("status") != "approved_after_campaign" or review.get("execution_authorized") is not True:
        raise RuntimeError("wheel fetch remains inert until a fresh post-campaign review")
    verify_campaign_terminal(review)
    if review.get("fetcher_sha256") != sha(Path(__file__).read_bytes()):
        raise RuntimeError("wheel fetcher changed after review")
    if review.get("download_worker_sha256") != sha(WORKER.read_bytes()):
        raise RuntimeError("bounded download worker changed after review")
    if review.get("packages") != PACKAGES or review.get("total_bytes") != sum(item["size"] for item in PACKAGES):
        raise RuntimeError("wheel set changed after review")
    if review.get("limits") != {"max_seconds": MAX_SECONDS, "max_download_seconds": DOWNLOAD_SECONDS, "max_bytes": MAX_TOTAL}:
        raise RuntimeError("wheel download bounds changed after review")
    if STARTED.exists() or RESULT.exists():
        raise RuntimeError("prior download evidence exists; do not replay")
    if WHEELS.exists() and any(WHEELS.iterdir()):
        raise RuntimeError("preserving existing wheel files; no overwrite or reuse")
    if sum(package["size"] for package in PACKAGES) > MAX_TOTAL:
        raise RuntimeError("pinned download total exceeded its fixed bound")

    sys.path.insert(0, str(ROOT / "src"))
    from aeep.assessment.verification import verification_source_digest
    if verification_source_digest(ROOT) != review.get("source_digest"):
        raise RuntimeError("frozen source digest changed before wheel download")
    from aeep.assessment.models import AssessmentOperation
    from aeep.assessment.repository import AssessmentRepository
    from aeep.router import Router

    reservation = review.get("assessment_reservation", {})
    operation_id = reservation.get("operation_id")
    plan_id = reservation.get("plan_id")
    if not isinstance(operation_id, str) or not operation_id or not isinstance(plan_id, str) or not plan_id:
        raise RuntimeError("review must bind the separately reserved canonical download operation")
    router = Router.from_manifest(ROOT / ".aeep/live-review-v3/aeep.json")
    repository = AssessmentRepository(router.store)
    operation = AssessmentOperation.model_validate(repository.get("operation_start", operation_id))
    state = router.store._connection.execute("SELECT grant_id,state FROM assessment_operations WHERE id=?", (operation_id,)).fetchone()
    if operation.plan_id != plan_id or operation.stage != "skillsbench_upstream_verifier_wheel_fetch":
        router.store.close()
        raise RuntimeError("reserved plan/stage differs from reviewed wheel download")
    if state is None or state[0] != "onboarding" or state[1] != "reserved":
        router.store.close()
        raise RuntimeError("expected a reserved onboarding wheel-download operation")
    if (operation.reserved.max_operations != 1 or operation.reserved.max_model_turns != 0
            or operation.reserved.max_cash_usd != 0 or operation.reserved.max_elapsed_seconds != MAX_SECONDS):
        router.store.close()
        raise RuntimeError("reserved wheel-download operation exceeds exact bounds")
    with STARTED.open("x", encoding="utf-8") as stream:
        json.dump({"review_sha256": sys.argv[1], "fetcher_sha256": sha(Path(__file__).read_bytes()), "operation_id": operation_id}, stream)
        stream.write("\n")
    began = time.monotonic()
    download_deadline = began + DOWNLOAD_SECONDS
    completed = []
    status = "failed_partial_or_unknown"
    error_type = None
    try:
        WHEELS.mkdir(parents=True, exist_ok=True)
        if any(WHEELS.iterdir()):
            raise RuntimeError("preserving prior wheel files; no overwrite or reuse")
        for package in PACKAGES:
            elapsed = time.monotonic() - began
            remaining = download_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("50 second total download-work deadline")
            destination = WHEELS / package["filename"]
            timeout = min(10.0, remaining)
            completed_download = subprocess.run(
                [sys.executable, str(WORKER), package["url"], str(destination), str(package["size"]), package["sha256"]],
                capture_output=True, text=True, timeout=timeout, check=False,
            )
            if completed_download.returncode != 0:
                raise RuntimeError("pinned wheel download subprocess failed; partials preserved")
            downloaded = json.loads(completed_download.stdout)
            if downloaded != {"filename": package["filename"], "bytes": package["size"], "sha256": package["sha256"]}:
                raise RuntimeError("download subprocess returned unexpected wheel evidence")
            completed.append(downloaded)
        status = "all_pinned_wheels_verified"
    except BaseException as exc:
        error_type = type(exc).__name__
    source_unchanged = verification_source_digest(ROOT) == review.get("source_digest")
    elapsed = time.monotonic() - began
    try:
        repository.finish_operation(operation_id, elapsed_seconds=elapsed)
        accounting_finished = True
    except BaseException as exc:
        accounting_finished = False
        error_type = error_type or type(exc).__name__
    result = {"status": status, "review_sha256": sys.argv[1], "plan_id": plan_id, "operation_id": operation_id,
              "authorization_id": "onboarding", "source_digest": review.get("source_digest"), "source_unchanged": source_unchanged,
              "elapsed_seconds": elapsed, "assessment_operation_finalized": accounting_finished,
              "downloaded_verified": completed, "error_type": error_type,
              "partial_files_preserved": sorted(path.name for path in WHEELS.iterdir())}
    if not source_unchanged or not accounting_finished or elapsed > MAX_SECONDS:
        result["status"] = "failed_partial_or_unknown"
        result["error_type"] = result["error_type"] or "source_accounting_or_deadline_check_failed"
        status = result["status"]
    with RESULT.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": status, "elapsed_seconds": elapsed, "verified_count": len(completed), "assessment_operation_finalized": accounting_finished, "error_type": error_type}))
    router.store.close()
    if status != "all_pinned_wheels_verified":
        raise RuntimeError("wheel fetch failed; preserve partials and result, no retry")


if __name__ == "__main__":
    main()
