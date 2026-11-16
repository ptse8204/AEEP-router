"""Prepare and run a bounded, offline A2A reference and original-source control."""

import argparse
import asyncio
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

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
from run_fusesoc_reference import extract_support

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import archive_files
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

CASE = "a2aproject__a2a-python-682_interface"
NAME = "aeep-c13-a2a-protected-reference-20261116"
MOUNT = Path("/private/tmp") / NAME / "protected"
STAGED = WORK / "patch-batch-verified"
WHEEL_LOCK = WORK / "a2a-offline-assets/wheel-lock.json"
REVIEW = WORK / "a2a-protected-reference-review.json"
APPROVAL = WORK / "a2a-protected-reference-approval.json"
ROLES = ("reference", "original")


def inventory() -> dict[str, str]:
    files = {}
    for path in sorted(MOUNT.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("protected mount contains an unsupported entry")
        if path.is_file():
            files[path.relative_to(MOUNT).as_posix()] = file_digest(path)
    return files


def context(role: str) -> ExecutionContext:
    identity = NAME + ":" + role
    spec = ExecutorSpec(id="toolkit.a2a-reference", capability="toolkit.upstream-engineering@1",
        kind="command", side_effect="read", description="Protected published A2A transport assertions",
        config={"argv": ["python3", "-I", "-B", str(MOUNT / "guest.py"), role], "argv_literal": True,
                "timeout_seconds": 35, "max_output_bytes": 16384, "output": {"type": "json"}})
    return ExecutionContext(request=ActionRequest(action_id=identity, capability=spec.capability, input={}),
        spec=spec, estimate=spec.estimate, attempt=1, attempt_id=identity, approved_side_effect=spec.side_effect)


def commands(env: AssessmentEnvironment) -> dict:
    executor = ContainerExecutor(env)
    launches = {}
    for role in ROLES:
        call = context(role)
        args, name = executor.command(call)
        mounts = {arg for arg in args if arg.startswith("type=bind,")}
        if (mounts != {f"type=bind,src={p},dst={p},readonly" for p in (MOUNT, FROZEN / "src")}
                or not {"--read-only", "--pull=never", "--cap-drop=ALL", "--security-opt=no-new-privileges"} <= set(args)
                or args[args.index("--network") + 1] != "none" or args[args.index("--user") + 1] != "65534:65534"):
            raise ValueError("unreviewed protection in launch")
        launches[role] = {"argv": args, "container": name, "context": call.spec.model_dump(mode="json")}
    return launches


def prepare() -> None:
    if REVIEW.exists() or MOUNT.parent.exists() or shutil.disk_usage(MOUNT.parent.parent).free < 52 * 1024**3:
        raise ValueError("existing review or insufficient host reserve")
    batch = get(HERE / "repository-patch-batch-intake.json")
    index = STAGED / "private-index.json"
    if file_digest(index) != batch["private_index_sha256"]:
        raise ValueError("screened cohort drifted")
    record, = [row for row in get(index)["records"] if row["case_id"] == CASE]
    if record["status"] != "ready_for_runtime_review":
        raise ValueError("case no longer passed inert screening")
    assets = {}
    for item in record["assets"]:
        path = STAGED / CASE / item["file"]
        if file_digest(path) != item["sha256"]:
            raise ValueError("staged source or protected test bytes drifted")
        assets[item["file"]] = path
    source = archive_files(assets["source.tar.gz"].read_bytes(), large=True)
    tests = archive_files(assets["tests.tar.gz"].read_bytes(), large=True)
    repair = get(assets["repair.json"])
    selectors = get(assets["required.json"])
    if (set(repair) != set(record["editable_changes"]) or not set(repair) <= source.keys()
            or not selectors["fail_to_pass"] or not selectors["pass_to_pass"]):
        raise ValueError("reviewed source scope mismatch")
    locked = get(WHEEL_LOCK)
    if not locked["closure_verified"] or locked["installed"] or locked["source_executed"]:
        raise ValueError("runtime package review changed")
    layers = verified_image()
    MOUNT.mkdir(parents=True, mode=0o755)
    MOUNT.parent.chmod(0o700)
    for tree, items in (("source", source), ("tests", tests),
                        ("reference", {key: value.encode() for key, value in repair.items()})):
        for name, data in items.items():
            path = MOUNT / tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    shutil.copyfile(assets["required.json"], MOUNT / "required.json")
    shutil.copyfile(HERE / "a2a_reference_guest.py", MOUNT / "guest.py")
    for wheel in locked["wheels"].values():
        path = WORK.parents[1] / wheel["path"]
        if file_digest(path) != wheel["sha256"]:
            raise ValueError("pinned support dependency drift")
        extract_support(path, MOUNT / "support")
    for path in MOUNT.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    MOUNT.chmod(0o555)
    files = inventory()
    env = AssessmentEnvironment(environment_id=NAME, kind="container",
        identity={"protected_mount_sha256": content_digest(files)}, container_image=IMAGE,
        container_runtime=DOCKER, container_socket=SOCKET, network=False,
        cpu_count=1.0, memory_mb=512, process_limit=96, container_tmpfs_mb=32, read_only_roots=[str(MOUNT)])
    put(REVIEW, {"purpose": "Check all seven published A2A transport assertions on the exact repair and original.",
        "source": verification_source_digest(FROZEN), "docker_sha256": file_digest(Path(DOCKER)),
        "base_revision": record["revision"], "archive_sha256": record["source_archive_sha256"], "layers": layers,
        "driver_sha256": file_digest(Path(__file__)), "wheel_lock_sha256": file_digest(WHEEL_LOCK),
        "files": files, "environment": env.model_dump(mode="json"), "launches": commands(env),
        "expires_at": (utc_now() + timedelta(days=7)).isoformat(), "max_operations": 2, "max_reserved_seconds": 100,
        "model_turns": 0, "cash_usd": 0, "maximum_retries": 0,
        "adaptations": ["Use the retained CPython 3.13.15 carrier within the upstream support range.",
            "Use one pytest process with the exact async plugin and declared markers. Omit the xdist distribution flag.",
            "Use the original mocked transport and all seven required identities. No SDK installation or hosted endpoint."],
        "approval_required": "New untrusted-suite execution and container provisioning.",
    })
    print(file_digest(REVIEW))


async def run(exact: str) -> None:
    review = get(REVIEW)
    env = AssessmentEnvironment.model_validate(review["environment"])
    if (file_digest(REVIEW) != exact or review["source"] != verification_source_digest(FROZEN)
            or review["docker_sha256"] != file_digest(Path(DOCKER)) or review["layers"] != verified_image()
            or review["files"] != inventory() or review["launches"] != commands(env)
            or review["driver_sha256"] != file_digest(Path(__file__)) or review["wheel_lock_sha256"] != file_digest(WHEEL_LOCK)
            or datetime.fromisoformat(review["expires_at"]) <= utc_now()):
        raise ValueError("exact reference review changed")
    approval = get(APPROVAL)
    if approval["approved"] is not True or approval["review_sha256"] != exact:
        raise ValueError("operator approval does not bind this exact review")
    output = WORK / "a2a-protected-reference-execution"
    output.mkdir(mode=0o700)
    scope = Scope(review_sha256=exact)
    ref = content_digest(scope)
    grant = AssessmentAuthorization(authorization_id=NAME,
        subject_digests=[ref], recipe_digests=[ref], environment_digests=[ref],
        limits=AssessmentLimits(max_operations=2, max_elapsed_seconds=100, max_model_turns=0),
        expires_at=datetime.fromisoformat(review["expires_at"]), allowed_destinations=["local"], remote_disclosure=False)
    request = RecipeMaterializationRequest(plan_id=NAME, authorization_id=NAME, subject_digest=ref,
        recipe_digest=ref, environment_digest=ref, mapping_digest=ref, definition_digests=[ref], seed=0)
    results = {}
    with ReceiptStore(output / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("toolkit_c13_a2a_reference_scope", ref, scope)
        repo.approve_bundle(grant, {ref: scope.model_dump(mode="json")})
        executor = ContainerExecutor(env)
        for role in ROLES:
            call = context(role)
            _, name = executor.command(call)
            lookup = f"name=^/{name}$"
            if (docker("ps", "-aq", "--filter", lookup) or shutil.disk_usage(MOUNT).free < 52 * 1024**3
                    or file_digest(REVIEW) != exact or inventory() != review["files"]):
                raise ValueError("protected scope changed before dispatch")
            repo.reserve(request, call.attempt_id, AssessmentLimits(max_operations=1, max_elapsed_seconds=50),
                         stage="a2a_protected_reference")
            started, clock = utc_now(), time.monotonic()
            raw = await executor.execute(call)
            if docker("ps", "-aq", "--filter", lookup):
                raise RuntimeError("owned cleanup is uncertain; reservation remains recorded")
            observation = raw.output if raw.status.value == "success" and isinstance(raw.output, dict) else {}
            passed = observation.get("role") == role and observation.get("verified") is True
            receipt = ExecutionReceipt(decision_id=call.attempt_id, action_id=call.attempt_id,
                capability=call.spec.capability, executor_id=call.spec.id, executor_kind=call.spec.kind,
                status="success" if passed else "failed", execution_success=passed, error_type=raw.error_type,
                started_at=started, ended_at=utc_now(), estimated=call.estimate, actual_resources=raw.resources,
                metadata={"review_sha256": exact, "role": role, "observation": observation, "container_absent": True})
            store.save_receipt(receipt)
            repo.finish_operation(call.attempt_id, elapsed_seconds=time.monotonic() - clock, resources=raw.resources)
            put(output / (role + "-receipt.json"), receipt.model_dump(mode="json"))
            results[role] = {"receipt_id": receipt.receipt_id, "passed": passed, "observation": observation}
            if not passed:
                break
        put(output / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))
    passed = tuple(results) == ROLES and all(row["passed"] for row in results.values())
    put(output / "result.json", {"passed": passed, "review_sha256": exact, "roles": results,
        "model_turns": 0, "cash_usd": 0, "stage_assigned": False})
    if not passed:
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
