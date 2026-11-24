"""Measure protection and native grader behavior for the 131 retained VAREX references."""

import argparse
import asyncio
import json
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

import check_varex_calibration as calibration
from check_linux_install import DOCKER, SOCKET, Scope, docker
from repository_offline_pair_batch import context
from stage_varex_calibration import (
    EXCLUSIONS,
    FROZEN,
    MANIFEST,
    ROOT,
    SCORER,
    SOURCE,
    digest,
    pinned,
    write,
)
from stage_varex_references import BATCH, COMPLEMENT, FLOOR
from varex_cohort_guest import ROLES

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.models import ExecutionReceipt, ExecutorSpec, utc_now
from aeep.store import ReceiptStore

NAME = "c13-varex-cohort-native-20261124"
INTAKE = "e3e832f79a86550ead32bb4fc06854d6ec5333381babc13fb4100661b53644a0"
SCREEN = ROOT / "reports/toolkit-v2/c13/completion-20261116/varex-source-family-screen-20261124.json"
PROTECTED = BATCH / "native-inputs"
REVIEW = BATCH / "native-review.json"
RUN = BATCH / "native-execution"
GUEST = Path(__file__).with_name("varex_cohort_guest.py")
SECONDS = 135
IS_COMPLEMENT = False


def launch(*, prepare=False):
    deps, dependency_count, runtime_review = calibration.pinned_runtime()
    intake = json.loads(pinned(BATCH / "reference-intake.json", INTAKE))
    screen_bytes = SCREEN.read_bytes()
    screen = json.loads(screen_bytes)
    if (
        (not IS_COMPLEMENT and intake["reference_rows"] != 131)
        or intake["reference_rows"] != len(intake["cases"]) or set(intake["cases"]) != set(screen["files"])
    ):
        raise ValueError("reference and verified PDF inventories differ")
    files = {
        "guest.py": GUEST.read_bytes(), "guest_boundary.py": calibration.GUEST.read_bytes(),
        "score.py": pinned(MANIFEST.parent / "score.py", SCORER),
        "field_exclusions.json": pinned(MANIFEST.parent / "field_exclusions.json", EXCLUSIONS),
    }
    cases = {}
    for name, binding in intake["cases"].items():
        identity = digest(name.encode())
        if binding["protected_case"] != identity:
            raise ValueError("source row archive path changed")
        source = BATCH / "protected" / identity
        schema, ref = identity + "-schema.json", identity + "-reference.json"
        files[ref] = pinned(source / "reference.json", binding["reference_sha256"])
        files[schema] = pinned(source / "schema.json", binding["schema_sha256"])
        cases[name] = {"reference": ref, "schema": schema, "split": binding["split"]}
    pins = {name: digest(data) for name, data in files.items()}
    if prepare:
        if shutil.disk_usage(ROOT).free < FLOOR + sum(len(data) for data in files.values()):
            raise ValueError("protected input staging would cross the host reserve")
        PROTECTED.mkdir(mode=0o755)
        for name, data in files.items():
            path = PROTECTED / name
            with path.open("xb") as stream:
                stream.write(data)
            path.chmod(0o444)
    if {path.name for path in PROTECTED.iterdir()} != set(pins):
        raise ValueError("protection inventory differs")
    for name, sha in pins.items():
        path = PROTECTED / name
        if path.is_symlink():
            raise ValueError("protected case requires a regular file")
        pinned(path, sha)
    env = AssessmentEnvironment(
        environment_id=NAME, kind="container", identity={"source": SOURCE},
        container_image=runtime_review["image"], container_runtime=DOCKER, container_socket=SOCKET,
        memory_mb=1024, process_limit=96, container_tmpfs_mb=64, read_only_roots=[str(deps), str(PROTECTED)],
    )
    spec = ExecutorSpec(
        id=NAME, capability="toolkit.upstream-engineering@1", kind="command", side_effect="read",
        description="Read-only protected VAREX cohort grader verification",
        config={
            "argv": ["python3", "-I", "-S", "-B", str(PROTECTED / "guest.py"), str(deps), str(PROTECTED)],
            "argv_literal": True, "stdin_json": True, "timeout_seconds": 120, "max_output_bytes": 100_000,
            "output": {"type": "json"},
        },
    )
    trial = context(spec, NAME + ":grade", {"cases": cases})
    executor = ContainerExecutor(env)
    argv, container = executor.command(trial)
    if (
        {arg for arg in argv if arg.startswith("type=bind,")}
        != {f"type=bind,src={root},dst={root},readonly" for root in (FROZEN / "src", deps, PROTECTED)}
        or argv[argv.index("--network") + 1] != "none" or argv[argv.index("--user") + 1] != "65534:65534"
        or not {"--pull=never", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--read-only", "-i"} <= set(argv)
    ):
        raise ValueError("protected executor boundary changed")
    record = {
        "schema_version": "aeep.c13.varex-cohort-native-review.v1",
        "source": SOURCE, "driver": digest(Path(__file__).read_bytes()), "reference_intake": INTAKE,
        "pdf_inventory": digest(screen_bytes), "protected_files": pins, "image": env.container_image,
        "image_layers": runtime_review["layers"], "docker_sha256": digest(Path(DOCKER).read_bytes()),
        "dependencies": calibration.PROJECTION, "dependency_files": dependency_count,
        "container": container, "argv_digest": content_digest(argv), "input_digest": content_digest(trial.request.input),
        "maximum_operations": 1, "maximum_reserved_seconds": SECONDS, "host_free_floor_bytes": FLOOR,
        "roles": list(ROLES), "authority": "C13 bounded first protected cohort verification",
        "network": False, "model_turns": 0, "cash_usd": 0, "formal_assignments": 0, "retries": 0,
    }
    return record, executor, trial


def classify(output, case_ids):
    if (
        not isinstance(output, dict) or set(output) != {"versions", "cases"}
        or output["versions"] != calibration.VERSIONS or set(output["cases"]) != set(case_ids)
    ):
        raise ValueError("native score envelope does not bind all reviewed cases")
    results = {}
    reasons = {
        "case_error", "no_scoreable_fields", "missing_scorer_result", "scorer_population_changed",
        "observed",
    }
    for case_id, row in output["cases"].items():
        if not isinstance(row, dict) or row.get("status") not in reasons:
            raise ValueError("invalid protected scorer case")
        if row["status"] == "case_error":
            if set(row) != {"status", "category"} or row["category"] not in {
                "OSError", "ValueError", "JSONDecodeError", "KeyError", "TypeError", "OverflowError", "RecursionError",
            }:
                raise ValueError("unexpected error category")
            results[case_id] = row | {"reference_check_passed": False}
            continue
        base = {"schema_valid", "scoreable_fields", "status"}
        observed = row["status"] == "observed"
        if (
            set(row) != (base | {"scores"} if observed else base) or type(row["schema_valid"]) is not bool
            or type(row["scoreable_fields"]) is not int or row["scoreable_fields"] < 0
        ):
            raise ValueError("invalid scorer case metadata")
        if not observed:
            results[case_id] = row | {"reference_check_passed": False}
            continue
        scores = row["scores"]
        if (
            set(scores) != set(ROLES) or row["scoreable_fields"] <= 0
            or any(type(score) not in {int, float} or not 0 <= score <= 1 for score in scores.values())
        ):
            raise ValueError("invalid native score vectors")
        passed = (
            row["schema_valid"] and scores["reference"] == 1 and scores["missing_field"] < 1
            and scores["missing_output"] == scores["malformed"] == 0
        )
        results[case_id] = row | {"reference_check_passed": passed}
    return results


def choose_complement(intake_hash):
    global BATCH, INTAKE, IS_COMPLEMENT, NAME, PROTECTED, REVIEW, RUN, SCREEN
    BATCH = COMPLEMENT / "protected-references"
    IS_COMPLEMENT = True
    NAME = "c13-varex-complement-native-20261124"
    SCREEN = COMPLEMENT / "pdf-intake.json"
    INTAKE = intake_hash
    PROTECTED = BATCH / "native-inputs"
    REVIEW = BATCH / "native-review.json"
    RUN = BATCH / "native-execution"


async def execute(exact):
    review = json.loads(pinned(REVIEW, exact))
    record, executor, trial = launch()
    expiry = datetime.fromisoformat(review["expiry"])
    if (
        review != record | {"expiry": review["expiry"]} or utc_now() >= expiry
        or shutil.disk_usage(ROOT).free < FLOOR or RUN.exists()
    ):
        raise ValueError("unavailable scope, capacity or fresh operation")
    ownership_filter = f"name=^/{review['container']}$"
    if docker("ps", "-aq", "--filter", ownership_filter):
        raise ValueError("owned worker name already exists")
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
        repository.put("c13_varex_cohort_native_scope", ref, scope)
        repository.approve_bundle(grant, {ref: scope.model_dump(mode="json")})
        identity = trial.attempt_id
        repository.reserve(request, identity, limits, stage="protected_reference_verification", require_settled_plan=True)
        start, clock = utc_now(), time.monotonic()
        try:
            raw = await executor.execute(trial)
            if docker("ps", "-aq", "--filter", ownership_filter):
                raise RuntimeError("protected container cleanup uncertain")
            results = None
            error_type = raw.error_type
            if raw.status.value == "success":
                try:
                    results = classify(raw.output, trial.request.input["cases"])
                except (ValueError, TypeError, KeyError):
                    error_type = "PROTECTED_GRADE_PROTOCOL"
            receipt = ExecutionReceipt(
                decision_id=identity, action_id=identity, capability=trial.spec.capability,
                executor_id=trial.spec.id, executor_kind=trial.spec.kind,
                status=raw.status if error_type != "PROTECTED_GRADE_PROTOCOL" else "failed",
                started_at=start, ended_at=utc_now(), estimated=trial.estimate,
                actual_resources=raw.resources, execution_success=results is not None, error_type=error_type,
                metadata={
                    "review_sha256": exact, "container_absent": True,
                    "grade_observation_digest": content_digest(results) if results is not None else None,
                },
            )
            store.save_receipt(receipt)
            repository.finish_operation(identity, elapsed_seconds=time.monotonic() - clock, resources=raw.resources)
            write(RUN / "receipt.json", receipt.model_dump(mode="json"))
            if results is None:
                raise ValueError("protected execution did not return grades")
            write(RUN / "result.json", {
                "review_sha256": exact, "receipt_id": receipt.receipt_id, "cases": results,
                "protected_reference_checks_passed": sum(row["reference_check_passed"] for row in results.values()),
                "formal_assignments": 0, "model_turns": 0, "cash_usd": 0,
            })
        finally:
            write(RUN / "ledger.json", repository.operation_ledger(NAME).model_dump(mode="json"))
            await executor.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--execute")
    parser.add_argument("--complement-intake-sha256")
    args = parser.parse_args()
    if args.complement_intake_sha256:
        choose_complement(args.complement_intake_sha256)
    if args.prepare:
        record, _, _ = launch(prepare=True)
        write(REVIEW, record | {"expiry": (utc_now() + timedelta(hours=4)).isoformat()})
        print(digest(REVIEW.read_bytes()))
    else:
        asyncio.run(execute(args.execute))
