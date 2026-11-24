"""Verify the two original VAREX references in a bounded protected operation."""

import argparse
import asyncio
import json
import shutil
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

from check_extractbench_native_grade import image_layers
from check_linux_install import DOCKER, SOCKET, Scope, docker
from prepare_extractbench_recipe import definition
from repository_offline_pair_batch import context
from stage_varex_calibration import (
    CASES,
    EXCLUSIONS,
    FROZEN,
    MANIFEST,
    ROOT,
    SCORER,
    SOURCE,
    WORK,
    digest,
    pinned,
    write,
)
from varex_calibration_guest import ROLES, VERSIONS

import aeep
from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.extensions import grader_results
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    DocumentTaskInput,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutionReceipt, ExecutorSpec, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.benchmarks import BenchmarkPack
from aeep_toolkit.install_runtime import file_digest

NAME = "c13-varex-calibration-20261124"
RUNTIME = ROOT / ".aeep/completion-20261116/extractbench-readonly-runtime-20261117"
PROTECTED = WORK / "grader"
REVIEW = WORK / "operation-review.json"
RUN = WORK / "execution"
GUEST = Path(__file__).with_name("varex_calibration_guest.py")
SECONDS = 100
FLOOR = 50 * 2**30
PROJECTION = "0901a6cd7ec47142134ca171787e6ab58b365f94d3564db44283789d33b96423"
RUNTIME_REVIEW = "51ae1f19fc49eea70d7c429fa054f3701d31278597fcd778ee891b5242f90396"


def read_cases():
    pack = BenchmarkPack.model_validate_json((WORK / "benchmark-pack.json").read_bytes())
    pack_sha = content_digest(pack.model_dump(mode="json"))
    inputs, protected, cases = [], {}, {}
    case_rows = json.loads((WORK / "acquisition-review.json").read_bytes())["cases"]
    for doc_id in CASES:
        name = f"varex-{doc_id.lower().replace('_', '-')}"
        binding = DocumentTaskInput.model_validate_json((WORK / f"{name}-input.json").read_bytes())
        task = pack.task(name)
        if binding.task_id != name or binding.benchmark_pack_sha256 != pack_sha:
            raise ValueError("staged case does not bind to the reviewed pack")
        archive = WORK / "public-verified" / f"{binding.task_archive_sha256}.zip"
        if file_digest(archive) != binding.task_archive_sha256:
            raise ValueError("public archive drift")
        expected = {}
        for asset in task.assets:
            body = pinned(WORK / "pack" / asset.path, asset.sha256)
            if asset.role in {"input", "instruction"}:
                expected[asset.path.removeprefix(f"tasks/{name}/")] = body
            elif asset.role == "oracle":
                protected[f"{name}-reference.json"] = body
        with ZipFile(archive) as zipped:
            if len(zipped.namelist()) != 3 or set(zipped.namelist()) != set(expected) or any(
                zipped.read(path) != body for path, body in expected.items()
            ):
                raise ValueError("public archive body differs from its asset bindings")
        cases[doc_id] = {"reference": f"{name}-reference.json", "split": case_rows[doc_id]["split"]}
        inputs.append(binding)
    return pack_sha, inputs, protected, cases


def pinned_runtime():
    if Path(aeep.__file__).resolve().parents[2] != FROZEN or verification_source_digest(FROZEN) != SOURCE:
        raise ValueError("requires the exact tested source")
    projection = json.loads(pinned(RUNTIME / "dependency-projection.json", PROJECTION))
    deps = RUNTIME / "dependencies"
    inventory = {str(path.relative_to(deps)): path for path in deps.rglob("*") if path.is_file()}
    if set(inventory) != set(projection["files"]) or any(path.is_symlink() for path in deps.rglob("*")):
        raise ValueError("retained dependency inventory changed")
    for name, path in inventory.items():
        pin = projection["files"][name]
        if path.stat().st_size != pin["bytes"] or file_digest(path) != pin["sha256"]:
            raise ValueError("retained dependency bytes changed")
    runtime_review = json.loads(pinned(RUNTIME / "operation-review.json", RUNTIME_REVIEW))
    if image_layers() != runtime_review["layers"]:
        raise ValueError("retained image layers changed")
    return deps, len(inventory), runtime_review


def fields(*, prepare=False):
    deps, dependency_count, runtime_review = pinned_runtime()
    pack, inputs, assets, cases = read_cases()
    assets.update({
        "guest.py": GUEST.read_bytes(),
        "score.py": pinned(MANIFEST.parent / "score.py", SCORER),
        "field_exclusions.json": pinned(MANIFEST.parent / "field_exclusions.json", EXCLUSIONS),
    })
    if prepare:
        PROTECTED.mkdir(mode=0o755)
        for name, body in assets.items():
            path = PROTECTED / name
            with path.open("xb") as output:
                output.write(body)
            path.chmod(0o444)
    pins = {name: digest(body) for name, body in assets.items()}
    if {path.name for path in PROTECTED.iterdir()} != set(pins):
        raise ValueError("protected calibration inventory differs")
    for name, sha in pins.items():
        path = PROTECTED / name
        if path.is_symlink() or file_digest(path) != sha:
            raise ValueError("protected calibration source differs")
    environment = AssessmentEnvironment(
        environment_id=NAME, kind="container", identity={"source": SOURCE},
        container_image=runtime_review["image"], container_runtime=DOCKER, container_socket=SOCKET,
        memory_mb=1024, process_limit=96, container_tmpfs_mb=64,
        read_only_roots=[str(deps), str(PROTECTED)],
    )
    spec = ExecutorSpec(
        id=NAME, capability="toolkit.upstream-engineering@1", kind="command", side_effect="read",
        description="Calibrate two VAREX native exact-match graders offline",
        config={
            "argv": ["python3", "-I", "-S", "-B", str(PROTECTED / "guest.py"), str(deps), str(PROTECTED)],
            "argv_literal": True, "stdin_json": True, "timeout_seconds": 85, "max_output_bytes": 8192,
            "output": {"type": "json"},
        },
    )
    trial = context(spec, NAME + ":protected-grading", {"cases": cases})
    executor = ContainerExecutor(environment)
    argv, name = executor.command(trial)
    if (
        {arg for arg in argv if arg.startswith("type=bind,")}
        != {f"type=bind,src={path},dst={path},readonly" for path in (FROZEN / "src", deps, PROTECTED)}
        or argv[argv.index("--network") + 1] != "none" or argv[argv.index("--user") + 1] != "65534:65534"
        or not {"--pull=never", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--read-only", "-i"} <= set(argv)
    ):
        raise ValueError("protected executor containment changed")
    record = {
        "schema_version": "aeep.c13.varex-native-calibration.v1",
        "source": SOURCE, "driver_sha256": file_digest(Path(__file__)),
        "image": runtime_review["image"], "layers": runtime_review["layers"],
        "docker_sha256": file_digest(Path(DOCKER)), "dependency_projection_sha256": PROJECTION,
        "dependency_versions": VERSIONS, "dependency_files": dependency_count, "protected_files": pins,
        "benchmark_pack": pack, "input_digests": {item.task_id: content_digest(item) for item in inputs},
        "roles": list(ROLES), "native_metric": "exact_match_normalized",
        "argv_sha256": content_digest({"argv": argv}), "container": name,
        "stdin_sha256": content_digest(trial.request.input), "maximum_operations": 1,
        "maximum_reserved_seconds": SECONDS, "minimum_host_free_bytes": FLOOR,
        "authority": "C13 bounded offline first-check delegation. Preserve old ledgers and source evidence.",
        "model_turns": 0, "cash_usd": 0, "network": False, "image_changes": 0,
        "existing_resource_deletion": False, "must_not_retry": True, "formal_assignments": 0,
    }
    return record, executor, trial, inputs


def verify(value, extension, *, ordered_arrays=()):
    if not isinstance(value, dict) or set(value) != {"versions", "scores"} or value["versions"] != VERSIONS:
        raise ValueError("scorer did not return the native calibration envelope")
    if set(value["scores"]) != set(CASES):
        raise ValueError("scorer did not cover both cases")
    canonical = {}
    for doc_id, observations in value["scores"].items():
        if set(observations) != set(ROLES):
            raise ValueError("scorer did not cover each reviewed control")
        canonical[doc_id] = {}
        fields = observations["reference"]["fields"]
        for role, row in observations.items():
            complete = role == "reference" or (role == "reordered" and doc_id not in ordered_arrays)
            score = row["exact_match_normalized"]
            if (
                set(row) != {"fields", "docs", "exact_match_normalized", "perfect_docs"}
                or not isinstance(fields, int) or fields < 2 or row["fields"] != fields or row["docs"] != 1
                or row["perfect_docs"] != int(complete)
                or (complete and score != 1)
                or (role in ("missing_row", "reordered") and not complete and not 0 < score < 1)
                or (role in ("missing_output", "malformed") and score != 0)
            ):
                raise ValueError("native score does not match the predeclared control")
            if complete:
                failure = None
            else:
                failure = "inexact_extraction" if role in ("reordered", "missing_row") else "invalid_submission"
            grade = grader_results({
                "valid": [complete], "quality_scores": [score], "failure_codes": [failure],
            }, extension, 1)[0]
            canonical[doc_id][role] = grade.model_dump(mode="json")
    return canonical


def replay():
    """Read the completed receipt and preserve the original failed expectation."""
    review = json.loads(REVIEW.read_bytes())
    pinned(WORK / "execution-driver.py", review["driver_sha256"])
    pack, inputs, _, _ = read_cases()
    review_sha = file_digest(REVIEW)
    receipt = ExecutionReceipt.model_validate_json((RUN / "receipt.json").read_bytes())
    ledger = json.loads((RUN / "ledger.json").read_bytes())
    value = json.loads((RUN / "observation.json").read_bytes())
    if (
        review["benchmark_pack"] != pack
        or review["input_digests"] != {item.task_id: content_digest(item) for item in inputs}
        or receipt.metadata != {"review_sha256": review_sha, "container_absent": True}
        or not receipt.execution_success or len(ledger["operations"]) != 1
    ):
        raise ValueError("retained grade evidence does not match the original review")
    with tempfile.TemporaryDirectory(dir=WORK) as root:
        copy = Path(root) / "readonly-receipts-copy.sqlite3"
        shutil.copyfile(RUN / "receipts.sqlite3", copy)
        with ReceiptStore(copy) as store:
            if (
                store.get_receipt(receipt.receipt_id) != receipt
                or AssessmentRepository(store).operation_ledger(NAME).model_dump(mode="json") != ledger
            ):
                raise ValueError("receipt or ledger differs from its exported record")
    extension = definition(pack, inputs, review["protected_files"]["guest.py"]).extension
    assert extension is not None
    # The original guest selected the largest non-palindromic collection.
    # VAREX aligns object rows, while string arrays remain in their submitted order.
    # Keep the observed GSA miss. This is a readback classification, with no replay.
    grades = verify(value, extension, ordered_arrays=("GSA_3418",))
    return {
        "schema_version": "aeep.c13.varex-native-calibration-readback.v1",
        "review_sha256": review_sha, "receipt_id": receipt.receipt_id,
        "source": review["source"], "image": review["image"], "layers": review["layers"],
        "dependency_projection_sha256": review["dependency_projection_sha256"],
        "protected_files": review["protected_files"], "benchmark_pack": pack,
        "inputs": review["input_digests"], "metric": review["native_metric"],
        "operator_note": "The grader settled. The original expectation failed for GSA's ordered string array.",
        "staged_cases": {
            item.task_id: {"archive_sha256": item.task_archive_sha256, "pdf_sha256": item.document_sha256}
            for item in inputs
        },
        "observation": value, "grades": grades, "ledger": ledger,
        "model_turns": 0, "cash_usd": 0, "formal_assignments": 0, "replayed_container_calls": 0,
    }


async def execute(exact):
    review = json.loads(pinned(REVIEW, exact))
    record, executor, trial, inputs = fields()
    expiry = datetime.fromisoformat(review["expiry"])
    if (
        review != record | {"expiry": review["expiry"]}
        or utc_now() >= expiry or shutil.disk_usage(ROOT).free < FLOOR or RUN.exists()
    ):
        raise ValueError("review drift, expired scope, storage reserve or terminal attempt")
    comparison_filter = f"name=^/{review['container']}$"
    if docker("ps", "-aq", "--filter", comparison_filter):
        raise ValueError("owned container name already exists")
    # Only reuse AEEP's native reward result contract here. The ExtractBench transport,
    # generator and scorer are never selected for this local calibration.
    extension = definition(review["benchmark_pack"], inputs, review["protected_files"]["guest.py"]).extension
    assert extension is not None
    limits = AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=SECONDS)
    scope = Scope(review_sha256=exact)
    ref = content_digest(scope)
    request = RecipeMaterializationRequest(
        plan_id=NAME, authorization_id=NAME, subject_digest=ref, recipe_digest=ref,
        mapping_digest=ref, environment_digest=ref, definition_digests=[ref], seed=0,
    )
    grant = AssessmentAuthorization(
        authorization_id=NAME, subject_digests=[ref], recipe_digests=[ref], environment_digests=[ref],
        limits=limits, expires_at=expiry, allowed_destinations=["local"], remote_disclosure=False,
    )
    RUN.mkdir(mode=0o700)
    with ReceiptStore(RUN / "receipts.sqlite3") as store:
        repository = AssessmentRepository(store)
        repository.put("c13_varex_native_calibration_scope", ref, scope)
        repository.approve_bundle(grant, {ref: scope.model_dump(mode="json")})
        identity = trial.attempt_id
        repository.reserve(request, identity, limits, stage="protected_varex_calibration", require_settled_plan=True)
        start, clock = utc_now(), time.monotonic()
        try:
            raw = await executor.execute(trial)
            if docker("ps", "-aq", "--filter", comparison_filter):
                raise RuntimeError("protected container cleanup uncertain")
            receipt = ExecutionReceipt(
                decision_id=identity, action_id=identity, capability=trial.spec.capability,
                executor_id=trial.spec.id, executor_kind=trial.spec.kind, status=raw.status,
                started_at=start, ended_at=utc_now(), estimated=trial.estimate,
                actual_resources=raw.resources, execution_success=raw.status.value == "success",
                error_type=raw.error_type, metadata={"review_sha256": exact, "container_absent": True},
            )
            store.save_receipt(receipt)
            repository.finish_operation(identity, elapsed_seconds=time.monotonic() - clock, resources=raw.resources)
            write(RUN / "receipt.json", receipt.model_dump(mode="json"))
            if raw.status.value != "success":
                raise ValueError("protected executor failed before a grade")
            write(RUN / "observation.json", raw.output)
            grades = verify(raw.output, extension)
            result = {
                "review_sha256": exact, "receipt_id": receipt.receipt_id,
                "metric": review["native_metric"], "case_inputs": review["input_digests"],
                "observations": raw.output, "grades": grades, "model_turns": 0, "cash_usd": 0,
                "formal_assignments": 0,
            }
            write(RUN / "result.json", result)
        finally:
            write(RUN / "ledger.json", repository.operation_ledger(NAME).model_dump(mode="json"))
            await executor.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute")
    mode.add_argument("--reconcile", type=Path)
    args = parser.parse_args()
    if args.prepare:
        scope_fields, _, _, _ = fields(prepare=True)
        write(REVIEW, scope_fields | {"expiry": (utc_now() + timedelta(hours=4)).isoformat()})
        print(file_digest(REVIEW))
    elif args.reconcile:
        write(args.reconcile, replay())
    else:
        asyncio.run(execute(args.execute))
