"""Bind the published RETURNN repair to one reviewed offline grading pair."""

import argparse
import asyncio
import json
from datetime import timedelta
from pathlib import Path

import repository_offline_pair_batch as runner
from audit_staged_repository_graders import bind, wheel_probe_assets
from stage_repository_transport import digest, read

import aeep
from aeep.assessment.models import AssessmentEnvironment, content_digest
from aeep.assessment.repository_suites import LARGE_PAYLOAD
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec, utc_now
from aeep_toolkit.install_runtime import file_digest

HERE, ROOT, WORK = runner.HERE, runner.ROOT, runner.WORK
NAME = "c13-returnn-protected-pair-20261117"
TARGET = WORK / NAME
RUN = TARGET / "execution"
APPROVAL = TARGET / "approval.json"
REVIEW = HERE / "returnn-protected-pair-review-20261117.json"
FROZEN = WORK / "formal-document-native-20261117/committable-source"
SOURCE = "03c615b31e1c84f7225f20f8b9b8538e3dc618c223052b6232a02ce68864f6ab"
CASE = "rwth-i6__returnn-1764"
REVISION = "58aca86de83f85cf513878d3c48f03c23280181b"
CARRIER = "sha256:2386ef223e39b5dc12e6d8cdbaa6ac9779753f13ee74dc51e8d207279edae91f"
PROJECTION = HERE / "retained-link-projection-result.json"
PUBLISHER = HERE / "verified-publisher-projection-bindings.json"
PREREQUISITES = HERE / "retained-runtime-prerequisites.json"
PINNED_OBSERVER = "1f099dfb9eee49db52c631a2c59f56c45f933e15bb6b4f1be35b86f5b8a84ba2"
BASE_REVIEW_FIELDS = runner.review_fields


def definitions():
    if Path(aeep.__file__).resolve().parents[2] != FROZEN or verification_source_digest(FROZEN) != SOURCE:
        raise ValueError("load the exact frozen source using PYTHONPATH")
    projection = json.loads(read(PROJECTION, "d8a8849a2465e19a74a63b26026988f25f0a1f91c9e54cd083885d04bd5e47f3"))
    publisher = json.loads(read(PUBLISHER, "412a3a81f9626bc205d61e8da6f8bd9b18c07adaff57b77ebe4530f541c1f207"))
    preflight = json.loads(read(PREREQUISITES, "186eb0fc1815dc4d4c772508c5907f5266e0c8a46b718d31883f10c836a86ba5"))
    bound = next(item for item in publisher["bindings"] if item["case"] == CASE)
    index = projection["verification"]["private_index"]
    index_path = ROOT / index["path"]
    row = next(item for item in json.loads(read(index_path, index["sha256"])) if item["input"]["task_id"] == CASE)
    _, wheels = wheel_probe_assets()
    task, truth, reference, original, _ = bind(row, index_path.parent, wheels)
    if (not bound["publisher_binding_verified"] or bound["source_revision"] != REVISION
            or bound["input_digest"] != content_digest(task) or bound["public_archive_sha256"] != task.source_sha256
            or bound["protected_tests_sha256"] != truth.tests.sha256 or bound["editable_paths"] != list(task.editable_paths)
            or (len(truth.fail_to_pass), len(truth.pass_to_pass)) != (3, 10)
            or bound["protected_identity_digest"] != content_digest(truth.fail_to_pass + truth.pass_to_pass)):
        raise ValueError("publisher or test identity binding changed")
    carrier = preflight["returnn_pair_preflight"]["carrier"]
    carrier_history = HERE.parent / "repository-large-archives-20261027"
    build = json.loads(read(carrier_history / "build-result.json", carrier["build_result_sha256"]))
    old_review = json.loads(read(carrier_history / "runtime-review.json", carrier["runtime_review_sha256"]))
    if (not build["passed"] or build["image_id"] != CARRIER or carrier["image"] != CARRIER
            or not build["parent_layers_verified"]
            or old_review["pending_wheel_fetch"]["inherited_numpy_version"] != "2.2.6"):
        raise ValueError("retained NumPy carrier provenance differs")

    runtime = FROZEN / "integrations/assessment-runtime"
    template = (runtime / "repository_suite_native_program.py").read_text()
    program = template.replace(
        "'__AEEP_NATIVE_CAPTURE_SOURCE__'",
        repr((runtime / "repository_suite_native_capture.py").read_text()),
    )
    if digest(program.encode()) != PINNED_OBSERVER:
        raise ValueError("ordinary protected observer differs")
    compile(program, "<ordinary protected grader>", "exec")
    spec = ExecutorSpec(
        id="repository.suite.observe",
        capability="assessment.repository_suite@1",
        kind="command",
        description="Contained RETURNN native pytest grader",
        config={
            "argv": ["python3", "-B", "-c", program],
            "argv_literal": True,
            "stdin_json": True,
            "output": {"type": "json"},
            "timeout_seconds": 30,
            "max_stdin_bytes": LARGE_PAYLOAD,
            "max_output_bytes": 500_000,
        },
    )
    environment = AssessmentEnvironment(
        environment_id=NAME,
        kind="container",
        container_image=CARRIER,
        identity={"source": SOURCE},
        container_runtime=runner.DOCKER,
        container_socket=runner.SOCKET,
        memory_mb=512,
        process_limit=96,
        container_tmpfs_mb=64,
    )
    entry = {
        "case_id": CASE,
        "source_revision": REVISION,
        "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"),
        "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": bound["reference_archive_sha256"],
        "existing_image_dependencies": ["numpy==2.2.6"],
    }
    return spec, environment, [entry]


async def review_fields():
    fields, spec, environment, cases = await BASE_REVIEW_FIELDS()
    expected = runner.get(PREREQUISITES)["returnn_pair_preflight"]["fixtures"]
    for staged, prior in zip(fields["launches"], expected, strict=True):
        if (staged["operation"] != f"{NAME}:{CASE}:{prior['role']}"
                or staged["archive_sha256"] != prior["protected_archive_sha256"]
                or staged["payload_sha256"] != prior["payload_sha256"]
                or staged["required_tests"] != prior["test_identities"]):
            raise ValueError("previously audited pair has drifted")
    return fields | {
        "schema_version": "aeep.c13.returnn-protected-pair.v1",
        "wrapper_sha256": file_digest(Path(__file__)),
        "publisher_binding_sha256": file_digest(PUBLISHER),
        "source_projection_sha256": file_digest(PROJECTION),
        "retained_prerequisites_sha256": file_digest(PREREQUISITES),
        "minimum_host_free_bytes": 52 * 1024**3,
        "purpose": "Check the published tensor serialization repair and unchanged original bytes against 13 protected upstream tests",
    }, spec, environment, cases


def select_attempt():
    runner.NAME, runner.FROZEN, runner.CARRIER = NAME, FROZEN, CARRIER
    runner.RUN, runner.REVIEW, runner.APPROVAL = RUN, REVIEW, APPROVAL
    runner.MAX_CALLS = 2
    runner.definitions, runner.review_fields = definitions, review_fields


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
        reference = runner.get(REVIEW)
        if file_digest(REVIEW) != args.verify or fields != {
            key: value for key, value in reference.items() if key != "expires_at"
        }:
            raise ValueError("exact review or staged inputs changed")
    print(file_digest(REVIEW))


if __name__ == "__main__":
    asyncio.run(main())
