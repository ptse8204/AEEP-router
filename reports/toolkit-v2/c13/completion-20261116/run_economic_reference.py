"""Prepare or execute the exact protected economic reference and controls."""

import argparse
import asyncio
import shutil
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from audit_economic_oracle import TASK, audit
from check_linux_install import (
    DOCKER,
    FROZEN,
    HERE,
    IMAGE,
    SOCKET,
    WORK,
    Scope,
    docker,
    get,
    put,
    verified_image,
)
from economic_protected_grader import IDS, precise_answer

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

NAME = "aeep-c13-economic-reference-20261116"
MOUNT = Path("/private/tmp", NAME, "verifier")
REVIEW = WORK / "economic-reference-operation-review.json"
APPROVAL = WORK / "economic-reference-approval.json"
OUTPUT = WORK / "economic-reference-execution"


def expected_outcomes():
    def role(grade, upstream=True, *, failed=(), skipped=()):
        outcomes = dict.fromkeys(IDS, "passed")
        outcomes.update(dict.fromkeys(failed, "failed"))
        outcomes.update(dict.fromkeys(skipped, "skipped"))
        return {
            "protocol_verified": True,
            "upstream_valid": upstream,
            "protected_grade": grade,
            "precision_valid": bool(grade),
            "observations": outcomes,
        }

    return {
        "reference": role(1),
        "excluded_2024": role(0),
        "excess_precision": role(0),
        "quarterly_smoothing": role(0, False, failed=("test_correlation_value_correct",)),
        "missing": role(
            0,
            False,
            failed=("test_answer_file_exists",),
            skipped=tuple(node for node in IDS if node != "test_answer_file_exists"),
        ),
    }


def plan():
    environment = AssessmentEnvironment(
        environment_id=NAME,
        kind="container",
        identity={"protected_fixture_sha256": file_digest(MOUNT / "fixtures.json")},
        container_image=IMAGE,
        container_runtime=DOCKER,
        container_socket=SOCKET,
        network=False,
        cpu_count=1.0,
        memory_mb=512,
        process_limit=96,
        container_tmpfs_mb=32,
        read_only_roots=[str(MOUNT)],
    )
    spec = ExecutorSpec(
        id="skillsbench.economic-reference",
        capability="toolkit.upstream-engineering@1",
        kind="command",
        side_effect="read",
        description="Original protected test plus exact scalar validation",
        config={
            "argv": ["python3", "-I", "-B", str(MOUNT / "economic_protected_grader.py")],
            "argv_literal": True,
            "timeout_seconds": 40,
            "max_output_bytes": 8000,
            "output": {"type": "json"},
        },
    )
    context = ExecutionContext(
        request=ActionRequest(action_id=NAME, capability=spec.capability, input={}),
        spec=spec,
        estimate=spec.estimate,
        attempt=1,
        attempt_id=NAME,
        approved_side_effect=spec.side_effect,
    )
    executor = ContainerExecutor(environment)
    argv, container_name = executor.command(context)
    mounts = {arg for arg in argv if arg.startswith("type=bind,")}
    if (
        mounts != {f"type=bind,src={p},dst={p},readonly" for p in (MOUNT, FROZEN / "src")}
        or argv[argv.index("--network") + 1] != "none"
        or argv[argv.index("--user") + 1] != "65534:65534"
        or not {"--read-only", "--pull=never", "--cap-drop=ALL", "--security-opt=no-new-privileges"}
        <= set(argv)
    ):
        raise ValueError("unexpected economic-grader boundary")
    return (
        executor,
        context,
        {"docker": argv, "container": container_name, "spec": spec.model_dump(mode="json")},
    )


def files():
    contents = sorted(MOUNT.iterdir())
    if any(not p.is_file() or p.is_symlink() for p in contents):
        raise ValueError("unexpected protected input type")
    return {p.name: file_digest(p) for p in contents}


def prepare():
    if (
        REVIEW.exists()
        or MOUNT.parent.exists()
        or shutil.disk_usage(MOUNT.parents[1]).free < 52 * 1024**3
    ):
        raise ValueError("use a fresh private mount with sufficient storage")
    source = get(HERE / "economic-case-review.json")
    verifier = TASK / "verifier/test_outputs.py"
    pin = next(
        row["sha256"]
        for row in source["source_pins"]
        if row["path"].endswith("/verifier/test_outputs.py")
    )
    results = {}
    if file_digest(verifier) != pin or audit(protected_values=results) != source["oracle_check"]:
        raise ValueError("published verifier or independent reference drift")
    correct = results["reference"]
    artifacts = {
        name: results[name] for name in ("reference", "excluded_2024", "quarterly_smoothing")
    }
    artifacts.update(excess_precision=correct + "0", missing=None)
    for name, text in artifacts.items():
        assert precise_answer(None if text is None else text.encode("ascii"), Decimal(correct)) == (
            name == "reference"
        )
    layers = verified_image()
    MOUNT.parent.mkdir(mode=0o700)
    MOUNT.mkdir(mode=0o755)
    shutil.copyfile(verifier, MOUNT / "upstream_test.py")
    shutil.copyfile(HERE / "economic_protected_grader.py", MOUNT / "economic_protected_grader.py")
    put(
        MOUNT / "fixtures.json",
        {"verifier_sha256": pin, "expected": correct, "artifacts": artifacts},
    )
    for path in MOUNT.iterdir():
        path.chmod(0o444)
    MOUNT.chmod(0o555)
    put(
        REVIEW,
        {
            "purpose": "First protected verification of four unchanged tests and a prospective five-decimal rule",
            "source": verification_source_digest(FROZEN),
            "launch": plan()[2],
            "driver_sha256": file_digest(Path(__file__)),
            "docker_sha256": file_digest(Path(DOCKER)),
            "image_layers": layers,
            "files": files(),
            "expected_observations": expected_outcomes(),
            "expires_at": (utc_now() + timedelta(days=7)).isoformat(),
            "max_operations": 1,
            "max_reserved_seconds": 75,
            "model_turns": 0,
            "cash_usd": 0,
            "network": False,
            "maximum_retries": 0,
            "downloads": 0,
            "builds": 0,
            "adaptation": "Run the unchanged unittest class with the retained interpreter. Preserve the original score alongside the supplemental output check.",
        },
    )
    print(file_digest(REVIEW))


async def run(exact):
    if file_digest(REVIEW) != exact:
        raise ValueError("exact operation review changed")
    review = get(REVIEW)
    approval = get(APPROVAL) if APPROVAL.is_file() else {}
    if approval.get("approved") is not True or approval.get("review_sha256") != exact:
        raise ValueError("operator approval missing for this protected suite")
    executor, context, launch = plan()
    expires = datetime.fromisoformat(review["expires_at"])
    if (
        expires <= utc_now()
        or review["source"] != verification_source_digest(FROZEN)
        or review["driver_sha256"] != file_digest(Path(__file__))
        or review["docker_sha256"] != file_digest(Path(DOCKER))
        or review["image_layers"] != verified_image()
        or review["files"] != files()
        or review["launch"] != launch
        or review["expected_observations"] != expected_outcomes()
    ):
        raise ValueError("protected reference drift")
    name_filter = f"name=^/{launch['container']}$"
    if docker("ps", "-aq", "--filter", name_filter) or shutil.disk_usage(MOUNT).free < 52 * 1024**3:
        raise ValueError("operation requires a fresh container identity and sufficient host space")
    OUTPUT.mkdir(mode=0o700)
    scope = Scope(review_sha256=exact)
    ref = content_digest(scope)
    bounds = AssessmentLimits(max_operations=1, max_elapsed_seconds=75, max_model_turns=0)
    request = RecipeMaterializationRequest(
        plan_id=NAME,
        authorization_id=NAME,
        subject_digest=ref,
        recipe_digest=ref,
        mapping_digest=ref,
        environment_digest=ref,
        definition_digests=[ref],
        seed=0,
    )
    grant = AssessmentAuthorization(
        authorization_id=NAME,
        subject_digests=[ref],
        recipe_digests=[ref],
        environment_digests=[ref],
        allowed_destinations=["local"],
        limits=bounds,
        expires_at=expires,
        remote_disclosure=False,
    )
    with ReceiptStore(OUTPUT / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("toolkit_c13_economic_scope", ref, scope)
        repo.approve_bundle(grant, {ref: scope.model_dump(mode="json")})
        repo.reserve(request, NAME, bounds, stage="protected_economic_grader")
        clock, started = time.monotonic(), utc_now()
        raw = await executor.execute(context)
        if docker("ps", "-aq", "--filter", name_filter):
            raise RuntimeError("uncertain owned cleanup; preserve the open reservation")
        passed = (
            raw.status.value == "success"
            and isinstance(raw.output, dict)
            and content_digest(raw.output) == content_digest(review["expected_observations"])
        )
        receipt = ExecutionReceipt(
            decision_id=NAME,
            action_id=NAME,
            capability=context.spec.capability,
            executor_id=context.spec.id,
            executor_kind=context.spec.kind,
            status="success" if passed else "failed",
            execution_success=passed,
            started_at=started,
            ended_at=utc_now(),
            estimated=context.estimate,
            actual_resources=raw.resources,
            error_type=None if passed else "PROTECTED_GRADE_UNVERIFIED",
            metadata={
                "review_sha256": exact,
                "observations": raw.output if passed else None,
                "container_absent": True,
            },
        )
        store.save_receipt(receipt)
        repo.finish_operation(
            NAME, elapsed_seconds=time.monotonic() - clock, resources=raw.resources
        )
        put(OUTPUT / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))
        put(
            OUTPUT / "result.json",
            {
                "review_sha256": exact,
                "verified": passed,
                "receipt": receipt.model_dump(mode="json"),
                "new_model_turns": 0,
                "cash_usd": 0,
            },
        )
    return passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        raise SystemExit(not asyncio.run(run(args.exact_review)))
