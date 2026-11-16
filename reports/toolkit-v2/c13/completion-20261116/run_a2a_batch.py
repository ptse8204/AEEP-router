"""Prepare one offline grader reproduction batch with isolated per-role inputs."""

import argparse
import asyncio
import shutil
import time
import tomllib
from datetime import datetime, timedelta
from pathlib import Path

from check_linux_install import (
    DOCKER,
    FROZEN,
    HERE,
    IMAGE,
    ROOT,
    SOCKET,
    WORK,
    Scope,
    docker,
    get,
    put,
    verified_image,
)
from run_a2a_reference import extract_support

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import archive_files, pack_files
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

NAME = "aeep-c13-a2a-batch-20261116"
MOUNT = Path("/private/tmp") / NAME
SHARED = MOUNT / "shared"
REVIEW = WORK / "a2a-batch-reference-review.json"
APPROVAL = WORK / "a2a-batch-reference-approval.json"
OLD_REVIEW = WORK / "a2a-protected-reference-review.json"
OLD_DIGEST = "9a31c7acb11ecc83fd9893a33f47e06af9c9205d632c8b3e53a2d2784107cbaa"
WHEEL_LOCK = WORK / "a2a-offline-assets/wheel-lock.json"
CASE_ROOT = WORK / "patch-batch-verified"
SOURCE_CASES = {
    "a2aproject__a2a-python-472": (4, 77),
    "a2aproject__a2a-python-576": (2, 37),
    "a2aproject__a2a-python-682_interface": (2, 5),
}
ROLES = ("reference", "original")
STARLETTE = (
    ROOT / ".aeep/repository-supported-suite-wheels-20261027/starlette-0.48.0-py3-none-any.whl"
)
STARLETTE_SHA = "0764ca97b097582558ecb498132ed0c7d942f233f365b86ba37770e026510659"
CAPTURE = FROZEN / "integrations/assessment-runtime/repository_suite_native_capture.py"


def inventory():
    files = {}
    for path in sorted(MOUNT.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("protected mount entry is outside its regular-file contract")
        if path.is_file():
            files[path.relative_to(MOUNT).as_posix()] = file_digest(path)
    return files


def call(case, role):
    input_root = MOUNT / case / role
    env = AssessmentEnvironment(
        environment_id=NAME,
        kind="container",
        identity={"binding_sha256": file_digest(input_root / "binding.json")},
        container_image=IMAGE,
        container_runtime=DOCKER,
        container_socket=SOCKET,
        network=False,
        cpu_count=1.0,
        memory_mb=512,
        process_limit=96,
        container_tmpfs_mb=32,
        read_only_roots=[str(SHARED), str(input_root)],
    )
    spec = ExecutorSpec(
        id="toolkit.repository-batch",
        capability="toolkit.upstream-engineering@1",
        kind="command",
        side_effect="read",
        description="Published repository reference or original-source control",
        config={
            "argv": [
                "python3",
                "-I",
                "-B",
                str(SHARED / "guest.py"),
                str(input_root),
                str(FROZEN / "src"),
            ],
            "argv_literal": True,
            "timeout_seconds": 45,
            "max_output_bytes": 58000,
            "output": {"type": "json"},
        },
    )
    identity = NAME + ":" + case + ":" + role
    ctx = ExecutionContext(
        request=ActionRequest(action_id=identity, capability=spec.capability, input={}),
        spec=spec,
        estimate=spec.estimate,
        attempt=1,
        attempt_id=identity,
        approved_side_effect=spec.side_effect,
    )
    executor = ContainerExecutor(env)
    argv, container_name = executor.command(ctx)
    binds = {arg for arg in argv if arg.startswith("type=bind,")}
    if (
        binds
        != {f"type=bind,src={p},dst={p},readonly" for p in (FROZEN / "src", SHARED, input_root)}
        or argv[argv.index("--network") + 1] != "none"
        or argv[argv.index("--user") + 1] != "65534:65534"
        or not {"--read-only", "--pull=never", "--cap-drop=ALL", "--security-opt=no-new-privileges"}
        <= set(argv)
    ):
        raise ValueError("protected invocation boundary changed")
    return (
        ctx,
        executor,
        {"argv": argv, "container": container_name, "spec": spec.model_dump(mode="json")},
    )


def stage_case(record):
    case = record["case_id"]
    if record["status"] != "ready_for_runtime_review":
        raise ValueError("case no longer passed transport screening")
    paths = {}
    for asset in record["assets"]:
        path = CASE_ROOT / case / asset["file"]
        if file_digest(path) != asset["sha256"]:
            raise ValueError("staged repository asset changed")
        paths[asset["file"]] = path
    source = archive_files(paths["source.tar.gz"].read_bytes(), large=True)
    config = tomllib.loads(source["pyproject.toml"].decode())["tool"]["pytest"]["ini_options"]
    if config["addopts"].removesuffix(" --dist loadgroup") != "-ra --strict-markers":
        raise ValueError("pytest configuration requires a new adaptation review")
    overlay = archive_files(paths["tests.tar.gz"].read_bytes(), large=True)
    patch = {key: value.encode() for key, value in get(paths["repair.json"]).items()}
    if set(patch) != set(record["editable_changes"]) or not (
        set(patch) <= source.keys() and patch.keys().isdisjoint(overlay)
    ):
        raise ValueError("reference patch crosses its reviewed source scope")
    required = get(paths["required.json"])
    fail, preserve = required["fail_to_pass"], required["pass_to_pass"]
    if (len(fail), len(preserve)) != SOURCE_CASES[case] or len(set(fail + preserve)) != len(
        fail
    ) + len(preserve):
        raise ValueError("published identities changed")
    for role in ROLES:
        is_reference = role == "reference"
        output = MOUNT / case / role
        output.mkdir(parents=True, mode=0o755)
        files = {**source, **overlay, **(patch if is_reference else {})}
        (output / "fixture.tar.gz").write_bytes(pack_files(files, large=True))
        expectations = dict.fromkeys(fail + preserve, "PASSED")
        if not is_reference:
            expectations.update(dict.fromkeys(fail, "FAILED"))
        put(
            output / "binding.json",
            {
                "case_id": case,
                "role": role,
                "source_revision": record["revision"],
                "archive_sha256": file_digest(output / "fixture.tar.gz"),
                "outcomes": expectations,
                "exit_code": 0 if is_reference else 1,
                **(
                    {
                        "required_original_failure": "does not support the asynchronous context manager protocol"
                    }
                    if not is_reference and case.endswith("682_interface")
                    else {}
                ),
            },
        )


def launches():
    return {case: {role: call(case, role)[2] for role in ROLES} for case in SOURCE_CASES}


def prepare():
    if REVIEW.exists() or MOUNT.exists() or shutil.disk_usage(MOUNT.parent).free < 52 * 1024**3:
        raise ValueError("review already prepared or not enough free space")
    if (
        file_digest(OLD_REVIEW) != OLD_DIGEST
        or (WORK / "a2a-protected-reference-execution").exists()
    ):
        raise ValueError("prior standalone case is no longer in the reviewed unstarted state")
    if (
        file_digest(WHEEL_LOCK) != get(OLD_REVIEW)["wheel_lock_sha256"]
        or file_digest(STARLETTE) != STARLETTE_SHA
    ):
        raise ValueError("reviewed wheel closure changed")
    if (
        file_digest(CASE_ROOT / "private-index.json")
        != get(HERE / "repository-patch-batch-intake.json")["private_index_sha256"]
    ):
        raise ValueError("protected case intake changed")
    index = {row["case_id"]: row for row in get(CASE_ROOT / "private-index.json")["records"]}
    environment_layers = verified_image()
    SHARED.mkdir(parents=True, mode=0o755)
    MOUNT.chmod(0o700)
    shutil.copyfile(HERE / "repository_batch_guest.py", SHARED / "guest.py")
    shutil.copyfile(CAPTURE, SHARED / "capture.py")
    for item in get(WHEEL_LOCK)["wheels"].values():
        path = ROOT / item["path"]
        if file_digest(path) != item["sha256"]:
            raise ValueError("reviewed support wheel changed")
        extract_support(path, SHARED / "support")
    extract_support(STARLETTE, SHARED / "support")
    for case in SOURCE_CASES:
        stage_case(index[case])
    for path in MOUNT.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    put(
        REVIEW,
        {
            "purpose": "First protected reproduction pair for each of three independently sourced A2A issues",
            "source": verification_source_digest(FROZEN),
            "docker_pin": file_digest(Path(DOCKER)),
            "layers": environment_layers,
            "files": inventory(),
            "driver": file_digest(Path(__file__)),
            "launches": launches(),
            "case_order": list(SOURCE_CASES),
            "expires_at": (utc_now() + timedelta(days=7)).isoformat(),
            "max_operations": 6,
            "max_reserved_seconds": 360,
            "cash_usd": 0,
            "model_turns": 0,
            "maximum_retries": 0,
            "builds": 0,
            "downloads": 0,
            "network": False,
            "prior_unstarted_standalone_covered_by_this_batch": OLD_DIGEST,
            "adaptations": [
                "Use the retained CPython 3.13.15 carrier and exact async plugin.",
                "Run all required nodes in one process, without the optional xdist flag of the 682 snapshot.",
                "Keep optional gRPC and SQL database services absent. The selected tests use mocked or in-memory transports.",
                "Whole batch approval covers the standalone 682 pair once. Preserve its old unstarted review.",
            ],
        },
    )
    print(file_digest(REVIEW))


def verified_role(binding, raw):
    reply = raw.output
    return (
        raw.status.value == "success"
        and isinstance(reply, dict)
        and reply.get("passed") is True
        and reply.get("source_verified") is True
        and reply.get("case_id") == binding["case_id"]
        and reply.get("role") == binding["role"]
        and reply.get("exit_code") == binding["exit_code"]
        and reply.get("archive_sha256") == binding["archive_sha256"]
        and reply.get("statuses") == binding["outcomes"]
        and reply.get("collected") == len(binding["outcomes"])
    )


def retained_observation(binding, raw):
    reply = raw.output
    if not isinstance(reply, dict):
        return None
    statuses = reply.get("statuses")
    reported = {}
    if isinstance(statuses, dict):
        known = {"PASSED", "FAILED", "SKIPPED", "XFAIL", "ERROR"}
        reported = {
            node: status
            for node, status in statuses.items()
            if node in binding["outcomes"] and isinstance(status, str) and status in known
        }
    code = reply.get("exit_code")
    count = reply.get("collected")
    return {
        "worker_status": raw.status.value,
        "source_verified": reply.get("source_verified") is True,
        "input_verified": reply.get("archive_sha256") == binding["archive_sha256"],
        "exit_code": code if type(code) is int and 0 <= code <= 5 else None,
        "collected": count if type(count) is int and 0 <= count <= 10000 else None,
        "statuses": reported,
    }


async def run(exact):
    review = get(REVIEW)
    if (
        file_digest(REVIEW) != exact
        or review["source"] != verification_source_digest(FROZEN)
        or review["driver"] != file_digest(Path(__file__))
        or review["docker_pin"] != file_digest(Path(DOCKER))
        or review["files"] != inventory()
        or review["layers"] != verified_image()
        or review["launches"] != launches()
        or review["case_order"] != list(SOURCE_CASES)
        or datetime.fromisoformat(review["expires_at"]) <= utc_now()
        or (WORK / "a2a-protected-reference-execution").exists()
    ):
        raise ValueError("batch review changed or the standalone pair already started")
    approval = get(APPROVAL) if APPROVAL.is_file() else {}
    if approval.get("approved") is not True or approval.get("review_sha256") != exact:
        raise ValueError("operator approval does not bind this batch")
    output = WORK / "a2a-batch-reference-execution"
    output.mkdir(mode=0o700)
    scope = Scope(review_sha256=exact)
    ref = content_digest(scope)
    grant = AssessmentAuthorization(
        authorization_id=NAME,
        subject_digests=[ref],
        recipe_digests=[ref],
        environment_digests=[ref],
        allowed_destinations=["local"],
        limits=AssessmentLimits(max_operations=6, max_model_turns=0, max_elapsed_seconds=360),
        expires_at=datetime.fromisoformat(review["expires_at"]),
        remote_disclosure=False,
    )
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
    report = {}
    with ReceiptStore(output / "receipts.sqlite3") as store:
        repository = AssessmentRepository(store)
        repository.put("toolkit_c13_a2a_batch_scope", ref, scope)
        repository.approve_bundle(grant, {ref: scope.model_dump(mode="json")})
        for case in SOURCE_CASES:
            observed = report.setdefault(case, {})
            for role in ROLES:
                ctx, executor, launch = call(case, role)
                lookup = f"name=^/{launch['container']}$"
                if (
                    docker("ps", "-aq", "--filter", lookup)
                    or shutil.disk_usage(MOUNT).free < 52 * 1024**3
                    or file_digest(REVIEW) != exact
                    or inventory() != review["files"]
                ):
                    raise ValueError("before-dispatch identity or space changed")
                repository.reserve(
                    request,
                    ctx.attempt_id,
                    AssessmentLimits(max_operations=1, max_elapsed_seconds=60),
                    stage="protected_repository_reproduction",
                )
                started, clock = utc_now(), time.monotonic()
                raw = await executor.execute(ctx)
                if docker("ps", "-aq", "--filter", lookup):
                    raise RuntimeError(
                        "owned cleanup uncertain; preserve the unresolved reservation"
                    )
                bound = get(MOUNT / case / role / "binding.json")
                verified = verified_role(bound, raw)
                receipt = ExecutionReceipt(
                    decision_id=ctx.attempt_id,
                    action_id=ctx.attempt_id,
                    capability=ctx.spec.capability,
                    executor_id=ctx.spec.id,
                    executor_kind=ctx.spec.kind,
                    status="success" if verified else "failed",
                    execution_success=verified,
                    error_type=None if verified else "PROTECTED_REPRODUCTION_UNVERIFIED",
                    started_at=started,
                    ended_at=utc_now(),
                    estimated=ctx.estimate,
                    actual_resources=raw.resources,
                    metadata={
                        "review_sha256": exact,
                        "case_id": case,
                        "role": role,
                        "observation": retained_observation(bound, raw),
                        "container_absent": True,
                    },
                )
                store.save_receipt(receipt)
                repository.finish_operation(
                    ctx.attempt_id,
                    elapsed_seconds=time.monotonic() - clock,
                    resources=raw.resources,
                )
                put(output / (case + "-" + role + "-receipt.json"), receipt.model_dump(mode="json"))
                observed[role] = {"receipt_id": receipt.receipt_id, "verified": verified}
                if not verified:
                    break
        put(output / "ledger.json", repository.operation_ledger(NAME).model_dump(mode="json"))
    reproduced = [
        case
        for case, roles in report.items()
        if set(roles) == set(ROLES) and all(role["verified"] for role in roles.values())
    ]
    put(
        output / "result.json",
        {
            "review_sha256": exact,
            "roles": report,
            "reproduced": reproduced,
            "models": 0,
            "cash_usd": 0,
            "formal_stage_assigned": False,
        },
    )
    if len(reproduced) != len(SOURCE_CASES):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        asyncio.run(run(args.exact_review))
