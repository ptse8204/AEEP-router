"""Check a new protected document/data workload using the existing contained executor."""

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

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
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, StrictModel, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / ".aeep/completion-20261116/xlsx-recover-preparation"
PHASES = ("reference", "missing", "incomplete", "invalid")


class Scope(StrictModel):
    review_sha256: str


def write(path, value) -> None:
    with path.open("x") as output:
        output.write(json.dumps(value, indent=2) + "\n")


def verify_phase(phase: str, output: dict | None, expected: int) -> bool:
    keys = {"phase", "exit_code", "collected", "distinct", "identity_sha256",
            "passed", "failed", "skipped", "xfail", "errors"}
    if (not isinstance(output, dict) or output.keys() != keys or output["phase"] != phase
            or any(type(output[name]) is not int or output[name] < 0
                   for name in keys - {"phase", "identity_sha256"})
            or not isinstance(output["identity_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", output["identity_sha256"]) is None
            or output["collected"] != expected or output["distinct"] != expected
            or output["xfail"] or sum(output[name] for name in ("passed", "failed", "skipped", "errors")) != expected):
        return False
    if phase == "reference":
        return output["exit_code"] == 0 and output["passed"] == expected
    if phase == "missing":
        return output["exit_code"] == 1 and output["failed"] == 1 and output["skipped"] == expected - 1
    if phase == "incomplete":
        return output["exit_code"] == 1 and output["failed"] > 0 and not output["errors"] and not output["skipped"]
    return output["exit_code"] == 1 and output["errors"] == expected - 1 and output["passed"] == 1


def preflight(review_path: Path, required_digest: str):
    if file_digest(review_path) != required_digest:
        raise ValueError("review digest does not match")
    data = json.loads(review_path.read_bytes())
    env = AssessmentEnvironment.model_validate(data["environment"])
    source = Path(data["source_snapshot"])
    if verification_source_digest(source) != data["source_digest"]:
        raise ValueError("implementation source drift")
    phases = tuple(data["phases"])
    if phases not in (PHASES, PHASES[:3]) or data["expected_test_identities"] != 19:
        raise ValueError("unexpected execution scope")
    if shutil.disk_usage(WORK).free < 52 * 1024**3:
        raise ValueError("stop below the local operation storage reserve")
    guest = Path(env.read_only_roots[0])
    expect = {path: sha for path, sha in data["pins"].items() if Path(path).is_relative_to(guest)}
    if {str(path) for path in guest.rglob("*") if not path.is_dir()} != expect.keys():
        raise ValueError("protected mount inventory differs")
    if any(file_digest(Path(path)) != hash_value for path, hash_value in data["pins"].items()):
        raise ValueError("reviewed file changed")

    docker = [str(env.container_runtime), "--host", "unix://" + str(env.container_socket)]
    parent = subprocess.check_output([*docker, "image", "inspect", "--format", "{{json .}}",
                                      str(env.container_image)], env={}, timeout=10)
    image = json.loads(parent)
    if (image["Id"] != env.container_image or image["RootFS"]["Layers"] != data["layers"]
            or image["Os"] != "linux" or image["Architecture"] != "arm64"
            or image["Config"].get("Volumes") or image["Config"].get("Healthcheck")):
        raise ValueError("protected runtime fingerprint differs")
    return data, env, source, guest, docker


async def run(review_path: Path, required_digest: str) -> bool:
    data, env, source, guest, docker = await asyncio.to_thread(preflight, review_path, required_digest)
    phases = tuple(data["phases"])
    scope = Scope(review_sha256=required_digest)
    scope_ref = content_digest(scope)
    grant = AssessmentAuthorization(
        authorization_id=data["scope_id"],
        subject_digests=[scope_ref], recipe_digests=[scope_ref], environment_digests=[scope_ref],
        limits=AssessmentLimits(max_operations=len(phases), max_model_turns=0, max_elapsed_seconds=50*len(phases)),
        expires_at=datetime.fromisoformat(data["expires_at"]), allowed_destinations=["local"],
        remote_disclosure=False,
    )
    request = RecipeMaterializationRequest(
        plan_id=grant.authorization_id, authorization_id=grant.authorization_id,
        subject_digest=scope_ref, recipe_digest=scope_ref, mapping_digest=scope_ref,
        environment_digest=scope_ref, definition_digests=[scope_ref], seed=0,
    )
    output = WORK / ("reference-execution-" + required_digest[:12])
    output.mkdir(mode=0o700)
    write(output / "started.json", {"review_sha256": required_digest, "source": data["source_digest"]})
    results = {}
    with ReceiptStore(output / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("toolkit_skillsbench_reference_scope", scope_ref, scope)
        repo.approve_bundle(grant, {scope_ref: scope.model_dump(mode="json")})
        for phase in phases:
            operation = grant.authorization_id + ":" + phase
            spec = ExecutorSpec(id="skillsbench.xlsx-recovery-reference", capability="toolkit.upstream-engineering@1",
                kind="command", side_effect="read", description="Pinned protected reference or failure control",
                config={"argv": ["python3", "-I", "-B", str(guest / "observe.py"), phase],
                        "argv_literal": True, "timeout_seconds": 35, "max_output_bytes": 16384,
                        "output": {"type": "json"}})
            context = ExecutionContext(
                request=ActionRequest(action_id=operation, capability=spec.capability, input={}),
                spec=spec, estimate=spec.estimate, attempt=1, attempt_id=operation, approved_side_effect=spec.side_effect,
            )
            executor = ContainerExecutor(env)
            argv, name = executor.command(context)
            mounts = {arg for arg in argv if arg.startswith("type=bind,")}
            if ("--pull=never" not in argv or argv[argv.index("--network") + 1] != "none"
                    or "--read-only" not in argv or argv[argv.index("--user") + 1] != "65534:65534"
                    or mounts != {f"type=bind,src={path},dst={path},readonly" for path in (guest, source / "src")}):
                raise ValueError("unexpected protected launch")
            matches = [*docker, "ps", "-aq", "--filter", "name=^/" + name + "$"]
            if (await asyncio.to_thread(subprocess.check_output, matches, env={}, timeout=10)).strip():
                raise ValueError("container name is in use")
            if file_digest(review_path) != required_digest or shutil.disk_usage(WORK).free < 52 * 1024**3:
                raise ValueError("review or reserve changed before dispatch")
            repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=50),
                         stage="skillsbench_protected_reference")
            start = time.monotonic()
            started = utc_now()
            raw = await executor.execute(context)
            if (await asyncio.to_thread(subprocess.check_output, matches, env={}, timeout=10)).strip():
                raise RuntimeError("owned cleanup is uncertain; reservation stays unresolved")
            elapsed = time.monotonic() - start
            observation = raw.output if raw.status.value == "success" else None
            passed = verify_phase(phase, observation, data["expected_test_identities"])
            if results and observation is not None:
                passed &= results["reference"]["observation"]["identity_sha256"] == observation["identity_sha256"]
            receipt = ExecutionReceipt(
                decision_id=operation, action_id=operation, capability=spec.capability,
                executor_id=spec.id, executor_kind=spec.kind, status="success" if passed else "failed",
                started_at=started, ended_at=utc_now(), estimated=spec.estimate,
                actual_resources=raw.resources, execution_success=passed, error_type=raw.error_type,
                metadata={"review_sha256": required_digest, "phase": phase,
                          "observation": observation, "container_absent": True},
            )
            store.save_receipt(receipt)
            repo.finish_operation(operation, elapsed_seconds=elapsed, resources=raw.resources)
            results[phase] = {"passed": passed, "observation": observation, "receipt_id": receipt.receipt_id}
            write(output / (phase + "-receipt.json"), receipt.model_dump(mode="json"))
            if not passed:
                break
        write(output / "ledger.json", repo.operation_ledger(request.plan_id).model_dump(mode="json"))
    complete = len(results) == len(phases) and all(item["passed"] for item in results.values())
    write(output / "result.json", {"passed": complete, "phases": results, "model_turns": 0, "cash_usd": 0})
    return complete


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-path", type=Path, required=True)
    parser.add_argument("--exact-review", required=True)
    args = parser.parse_args()
    raise SystemExit(not asyncio.run(run(args.review_path, args.exact_review)))


if __name__ == "__main__":
    main()
