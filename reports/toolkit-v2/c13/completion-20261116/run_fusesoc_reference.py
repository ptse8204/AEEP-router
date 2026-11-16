"""Run the first protected FuseSoC reference and original-source control."""

import argparse
import asyncio
import shutil
import stat
import time
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

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

NAME = "aeep-c13-fusesoc-scratch-correction-20261116"
ROOT = Path("/private/tmp") / NAME
MOUNT = ROOT / "protected"
REVIEW = WORK / "fusesoc-scratch-correction-review.json"
ROLES = ("reference", "original")
TIMEOUT = 35


def inventory() -> dict[str, str]:
    files = {}
    for path in sorted(MOUNT.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("protected mount contains an unsupported entry")
        if path.is_file():
            files[path.relative_to(MOUNT).as_posix()] = file_digest(path)
    return files


def extract_support(wheel: Path, target: Path) -> None:
    with ZipFile(wheel) as package:
        entries = package.infolist()
        if sum(entry.file_size for entry in entries) > 32_000_000 or len(entries) > 6000:
            raise ValueError("wheel exceeds protected support bounds")
        for entry in entries:
            name = PurePosixPath(entry.filename)
            if (name.is_absolute() or ".." in name.parts or "\\" in entry.filename
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError("unsafe dependency archive member")
            if entry.is_dir() or name.parts[0].endswith(".data"):
                continue
            if name.suffix == ".pth":
                raise ValueError("support archive attempts an automatic Python import")
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(package.read(entry))


def prepare() -> None:
    if REVIEW.exists() or shutil.disk_usage(ROOT.parent).free < 52 * 1024**3:
        raise ValueError("protected reference review exists or host reserve is insufficient")
    layers = verified_image()
    audit = get(HERE / "fusesoc-runtime-intake.json")
    fixture = WORK / "fusesoc-protected-fixture"
    source_plan = fixture / "protected-inputs.json"
    wheel_audit = WORK / "fusesoc-runtime-wheel-audit.json"
    if file_digest(source_plan) != audit["protected_inputs_sha256"] or file_digest(wheel_audit) != audit["wheel_audit_sha256"]:
        raise ValueError("fixture or dependency audit changed")
    source = get(source_plan)
    ROOT.mkdir(mode=0o700)
    MOUNT.mkdir(mode=0o755)
    support = MOUNT / "support"
    support.mkdir(mode=0o755)
    for artifact in source["assets"].values():
        path = fixture / artifact["file"]
        if file_digest(path) != artifact["sha256"]:
            raise ValueError("protected archive changed")
        shutil.copyfile(path, MOUNT / path.name)
    shutil.copyfile(source_plan, MOUNT / source_plan.name)
    shutil.copyfile(HERE / "fusesoc_reference_guest.py", MOUNT / "guest.py")
    for wheel in get(wheel_audit)["rows"]:
        path = WORK / "fusesoc-runtime-wheels" / wheel["filename"]
        if file_digest(path) != wheel["sha256"]:
            raise ValueError("support dependency changed")
        extract_support(path, support)
    pytest_root = WORK.parent / "skillsbench-spring-reference-20261105/wheels"
    pytest_pins = {
        "pytest-8.4.1-py3-none-any.whl": "539c70ba6fcead8e78eebbf1115e8b589e7565830d7d006a8723f19ac8a0afb7",
        "pluggy-1.6.0-py3-none-any.whl": "e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746",
        "iniconfig-2.1.0-py3-none-any.whl": "9deba5723312380e77435581c6bf4935c94cbfab9b1ed33ef8d238ea168eb760",
        "pygments-2.19.1-py3-none-any.whl": "9ea1544ad55cecf4b8242fab6dd35a93bbce657034b0611ee383099054ab6d8c",
        "packaging-25.0-py3-none-any.whl": "29572ef2b1f17581046b3a2227d5c611fb25ec70ca1ba8554b24b0e69331a484",
    }
    for filename, pin in pytest_pins.items():
        path = pytest_root / filename
        if file_digest(path) != pin:
            raise ValueError("retained pytest closure changed")
        extract_support(path, support)
    for path in MOUNT.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    MOUNT.chmod(0o555)
    files = inventory()
    env = AssessmentEnvironment(
        environment_id=NAME, kind="container", identity={"mount_inventory_sha256": content_digest(files)},
        container_image=IMAGE, container_runtime=DOCKER, container_socket=SOCKET, network=False,
        cpu_count=1.0, memory_mb=512, process_limit=96, container_tmpfs_mb=32, read_only_roots=[str(MOUNT)],
    )
    put(REVIEW, {
        "authority_record": "reports/toolkit-v2/c13/pipeline-standing-authority-20261104.json",
        "purpose": "Recheck the protected FuseSoC reference with a disposable application cache and config",
        "source": verification_source_digest(FROZEN), "base_commit": source["source_revision"],
        "docker": file_digest(Path(DOCKER)), "layers": layers, "files": files,
        "driver": file_digest(Path(__file__)), "mount": env.model_dump(mode="json"), "roles": list(ROLES),
        "expires_at": (utc_now() + timedelta(days=1)).isoformat(), "model_turns": 0,
        "max_operations": len(ROLES), "cash_usd": 0,
        "prior_reference_failure": file_digest(HERE / "fusesoc-protected-reference-result.json"),
    })
    print(file_digest(REVIEW))


async def run(exact: str) -> None:
    review = get(REVIEW)
    if (file_digest(REVIEW) != exact or review["files"] != inventory()
            or review["source"] != verification_source_digest(FROZEN) or review["layers"] != verified_image()
            or review["docker"] != file_digest(Path(DOCKER)) or review["roles"] != list(ROLES)
            or review["driver"] != file_digest(Path(__file__))
            or review["prior_reference_failure"] != file_digest(HERE / "fusesoc-protected-reference-result.json")
            or datetime.fromisoformat(review["expires_at"]) <= utc_now()):
        raise ValueError("exact protected reference review changed")
    approval = get(WORK / "fusesoc-scratch-correction-approval.json")
    if approval["approved"] is not True or approval["review_sha256"] != exact:
        raise ValueError("operator approval required before repeating the protected reference")
    out = WORK / "fusesoc-scratch-correction-execution"
    out.mkdir(mode=0o700)
    scope = Scope(review_sha256=exact)
    ref = content_digest(scope)
    grant = AssessmentAuthorization(
        authorization_id=NAME, subject_digests=[ref], recipe_digests=[ref], environment_digests=[ref],
        limits=AssessmentLimits(max_operations=len(ROLES), max_elapsed_seconds=50*len(ROLES), max_model_turns=0),
        expires_at=datetime.fromisoformat(review["expires_at"]), allowed_destinations=["local"], remote_disclosure=False,
    )
    request = RecipeMaterializationRequest(plan_id=NAME, authorization_id=NAME, subject_digest=ref,
        recipe_digest=ref, environment_digest=ref, mapping_digest=ref, definition_digests=[ref], seed=0)
    env = AssessmentEnvironment.model_validate(review["mount"])
    result = {}
    with ReceiptStore(out / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("toolkit_c13_fusesoc_reference_scope", ref, scope)
        repo.approve_bundle(grant, {ref: scope.model_dump(mode="json")})
        for role in ROLES:
            key = NAME + ":" + role
            spec = ExecutorSpec(id="toolkit.fusesoc-reference", capability="toolkit.upstream-engineering@1",
                kind="command", side_effect="read", description="Bound FuseSoC protected reference verifier",
                config={"argv": ["python3", "-I", "-B", str(MOUNT / "guest.py"), role, str(FROZEN / "src")],
                        "argv_literal": True, "timeout_seconds": TIMEOUT, "max_output_bytes": 16384, "output": {"type": "json"}})
            context = ExecutionContext(
                request=ActionRequest(action_id=key, capability=spec.capability, input={}), spec=spec,
                estimate=spec.estimate, attempt=1, attempt_id=key, approved_side_effect=spec.side_effect,
            )
            executor = ContainerExecutor(env)
            args, name = executor.command(context)
            mounts = {arg for arg in args if arg.startswith("type=bind,")}
            if (mounts != {f"type=bind,src={p},dst={p},readonly" for p in (MOUNT, FROZEN / "src")}
                    or "--read-only" not in args or "--pull=never" not in args
                    or args[args.index("--network") + 1] != "none"
                    or docker("ps", "-aq", "--filter", f"name=^/{name}$")
                    or shutil.disk_usage(ROOT).free < 52 * 1024**3):
                raise ValueError("protected invocation is outside its boundary or below its reserve")
            repo.reserve(request, key, AssessmentLimits(max_operations=1, max_elapsed_seconds=50),
                         stage="fusesoc_protected_reference")
            started, clock = utc_now(), time.monotonic()
            raw = await executor.execute(context)
            elapsed = time.monotonic() - clock
            if docker("ps", "-aq", "--filter", f"name=^/{name}$"):
                raise RuntimeError("owned container absence is unverified")
            row = raw.output if raw.status.value == "success" and isinstance(raw.output, dict) else {}
            passed = (row.get("role") == role and row.get("expected_outcome") is True
                      and row.get("collected") == 15 and row.get("exact_test_identities") is True)
            receipt = ExecutionReceipt(decision_id=key, action_id=key, capability=spec.capability,
                executor_id=spec.id, executor_kind=spec.kind, status="success" if passed else "failed",
                started_at=started, ended_at=utc_now(), estimated=spec.estimate, actual_resources=raw.resources,
                execution_success=passed, error_type=raw.error_type,
                metadata={"review_sha256": exact, "role": role, "observation": row, "container_absent": True})
            store.save_receipt(receipt)
            repo.finish_operation(key, elapsed_seconds=elapsed, resources=raw.resources)
            put(out / (role + "-receipt.json"), receipt.model_dump(mode="json"))
            result[role] = {"receipt_id": receipt.receipt_id, "passed": passed, "observation": row}
            if not passed:
                break
        put(out / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))
    passed = tuple(result) == ROLES and all(row["passed"] for row in result.values())
    put(out / "result.json", {"passed": passed, "review_sha256": exact, "roles": result,
                            "model_turns": 0, "cash_usd": 0, "formal_stage_assigned": False})
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--exact-review")
    a = p.parse_args()
    if a.prepare:
        prepare()
    else:
        asyncio.run(run(a.exact_review))
