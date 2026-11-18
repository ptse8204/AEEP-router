"""Run the approved Arta contract audit with the existing protected pair runner."""

import argparse
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

import repository_offline_pair_batch as runner
from audit_staged_repository_graders import bind
from check_returnn_pair import FROZEN, PINNED_OBSERVER, SOURCE
from stage_arta_runtime import CASE, IMAGE, SOURCE_INDEX
from stage_repository_transport import digest, read

import aeep
from aeep.assessment.models import AssessmentEnvironment
from aeep.assessment.repository_suites import LARGE_PAYLOAD
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec, utc_now
from aeep_toolkit.install_runtime import file_digest

HERE, ROOT, WORK = runner.HERE, runner.ROOT, runner.WORK
NAME = "c13-arta-protected-pair-20261117"
TARGET = WORK / NAME
REVIEW = HERE / "arta-protected-pair-review-20261117.json"
INPUTS = HERE / "arta-runtime-inputs-20261117.json"
INPUTS_SHA256 = "ced4fa0f8a9b6b35a25a3c29f26bdf972b3a6979d7aedcd082d80b11da04de3c"
BASE_REVIEW_FIELDS = runner.review_fields


def staged_case():
    prepared = json.loads(read(INPUTS, INPUTS_SHA256))
    for key in ("source_index", "dependency_acquisition_record", "carrier_inventory",
                "metadata_only_distribution", "driver"):
        ref = prepared[key]
        read(ROOT / ref["path"], ref["sha256"])
    catalog = runner.get(SOURCE_INDEX)
    index_path = ROOT / catalog["private_index"]
    row = next(r for r in json.loads(read(index_path, catalog["private_index_sha256"]))
               if r["input"]["task_id"] == CASE)
    for wheel in prepared["portable_grader_inputs"]:
        if len(read(Path(wheel["path"]), wheel["sha256"])) != wheel["size_bytes"]:
            raise ValueError("portable grader wheel size changed")
    task, truth, reference, original, _ = bind(row, index_path.parent, prepared["portable_grader_inputs"])
    oracle = index_path.parent / "protected" / CASE / "required.json"
    declared = json.loads(read(oracle, row["protected_assets"]["required.json"]["sha256"]))
    faults = set(declared["published_fail_to_pass"]) | {row["protected_guard"]}
    if (len(faults) != 3 or len(truth.pass_to_pass) != 17 or truth.fail_to_pass
            or not faults <= set(truth.pass_to_pass) or row["source_revision"] != prepared["revision"]):
        raise ValueError("published case or expected original failures changed")
    return prepared, faults, {
        "case_id": CASE,
        "source_revision": row["source_revision"],
        "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"),
        "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": row["reference_archive_sha256"],
        "existing_image_dependencies": [
            f"{name}=={meta['version']}"
            for name, meta in prepared["carrier"]["installed_metadata"].items()
        ],
    }


def definitions():
    if Path(aeep.__file__).resolve().parents[2] != FROZEN or verification_source_digest(FROZEN) != SOURCE:
        raise ValueError("load the exact frozen source using PYTHONPATH")
    _, _, case = staged_case()
    runtime = FROZEN / "integrations/assessment-runtime"
    program = (runtime / "repository_suite_native_program.py").read_text().replace(
        "'__AEEP_NATIVE_CAPTURE_SOURCE__'",
        repr((runtime / "repository_suite_native_capture.py").read_text()),
    )
    if digest(program.encode()) != PINNED_OBSERVER:
        raise ValueError("ordinary protected observer changed")
    compile(program, "<ordinary protected grader>", "exec")
    spec = ExecutorSpec(
        id="repository.suite.observe", capability="assessment.repository_suite@1", kind="command",
        description="Contained Arta native pytest grader",
        config={
            "argv": ["python3", "-B", "-c", program], "argv_literal": True, "stdin_json": True,
            "output": {"type": "json"}, "timeout_seconds": 30, "max_stdin_bytes": LARGE_PAYLOAD,
            "max_output_bytes": 500_000,
        },
    )
    environment = AssessmentEnvironment(
        environment_id=NAME, kind="container", container_image=IMAGE, identity={"source": SOURCE},
        container_runtime=runner.DOCKER, container_socket=runner.SOCKET, memory_mb=512,
        process_limit=96, container_tmpfs_mb=64,
    )
    return spec, environment, [case]


async def review_fields():
    fields, spec, environment, cases = await BASE_REVIEW_FIELDS()
    prepared, faults, _ = staged_case()
    for launch in fields["launches"]:
        role = launch["operation"].rsplit(":", 1)[-1]
        expected = prepared["ordinary_callback_rehearsals"][role]
        if any(launch[key] != expected[key] for key in ("archive_sha256", "payload_sha256", "required_tests")):
            raise ValueError("exact previously staged Arta payload changed")
    return fields | {
        "schema_version": "aeep.c13.arta-protected-pair.v1",
        "purpose": "Verify the published Arta rules-engine contract and reject the original source with the same 17 protected checks",
        "wrapper_sha256": file_digest(Path(__file__)),
        "staged_inputs_sha256": INPUTS_SHA256,
        "expected_original_failures": sorted(faults),
        "minimum_host_free_bytes": 52 * 1024**3,
        "installations": 0,
    }, spec, environment, cases


def select_attempt():
    _, faults, _ = staged_case()

    def expected_statuses(truth, role):
        outcomes = dict.fromkeys(truth["pass_to_pass"], "PASSED")
        if role == "original":
            outcomes.update(dict.fromkeys(faults, "FAILED"))
        return outcomes

    runner.NAME, runner.FROZEN, runner.CARRIER = NAME, FROZEN, IMAGE
    runner.REVIEW, runner.RUN, runner.APPROVAL = REVIEW, TARGET / "execution", TARGET / "approval.json"
    runner.MAX_CALLS = 2
    runner.definitions, runner.review_fields, runner.expected_statuses = definitions, review_fields, expected_statuses


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--verify")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    select_attempt()
    if args.exact_review:
        raise SystemExit(0 if await runner.run(args.exact_review) else 1)
    fields, *_ = await review_fields()
    if args.prepare:
        if REVIEW.exists() or TARGET.exists():
            raise ValueError("review or attempt already exists")
        TARGET.mkdir(mode=0o700)
        runner.put(REVIEW, fields | {"expires_at": (utc_now() + timedelta(days=7)).isoformat()})
    else:
        record = runner.get(REVIEW)
        expiry = record["expires_at"]
        if (file_digest(REVIEW) != args.verify or record != fields | {"expires_at": expiry}
                or datetime.fromisoformat(expiry) <= utc_now()):
            raise ValueError("review expired or staged input changed")
    print(file_digest(REVIEW))


if __name__ == "__main__":
    asyncio.run(main())
