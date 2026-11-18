"""Run the first ordinary protected Pyfakefs file-open reproduction."""

import argparse
import asyncio
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import repository_offline_pair_batch as runner
from audit_staged_repository_graders import bind, wheel_probe_assets
from stage_repository_transport import HERE, WORK, digest, read

import aeep
from aeep.assessment.models import AssessmentEnvironment
from aeep.assessment.repository_suites import LARGE_PAYLOAD, archive_files
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec, utc_now

CASE = "pytest-dev__pyfakefs-1269"
REVISION = "a3685da29db2f185d4793f185ca07dfe36f3d9a9"
NAME = "c13-pyfakefs-protected-pair-20261118"
TARGET = WORK / NAME
REVIEW = HERE / "pyfakefs-protected-pair-review-20261118.json"
INDEX = WORK / "staged-worker-transport-rebound/private-index.json"
INDEX_PIN = "378a7a9cf4dc2184f5af65b063547cbc27fc253d6f51d1e74cb3278280d5d4bc"
PUBLISHER_PIN = "e9423a1c04f2c82d05ef8ae2c1e7a7144f217acd4525070fd2b86131206e8eda"
FROZEN = WORK.parent / "c13-document-archive-verification.wvK9pP/source"
SOURCE = "e060413cc2af11fd3c967384ad908026d8e8d467aaa430729ae28462b4f5afc7"
OBSERVER = "1f099dfb9eee49db52c631a2c59f56c45f933e15bb6b4f1be35b86f5b8a84ba2"
ROLE_ARCHIVES = (
    "7f3da018098c0b126e187868d11785b9e6a07b4450cc77956e6cbf4fb8ba8a3d",
    "4e759e7f869c4a0c1227a643d2969b34a8827959bc9ab047604a7774ad0011b5",
)
BASE_REVIEW, BASE_PROBE = runner.review_fields, runner.verify_probe


def configure(diagnostics):
    if (
        Path(aeep.__file__).resolve().parents[2] != FROZEN
        or verification_source_digest(FROZEN) != SOURCE
    ):
        raise ValueError("load the frozen coordinator")
    (row,) = (
        item for item in json.loads(read(INDEX, INDEX_PIN)) if item["input"]["task_id"] == CASE
    )
    publisher_path = WORK / "cached-source-tree-rebinding/source-results.json"
    (publisher,) = (
        item for item in json.loads(read(publisher_path, PUBLISHER_PIN)) if item["case_id"] == CASE
    )
    wheel_review, wheels = wheel_probe_assets()
    task, truth, reference, original, checks = bind(row, INDEX.parent, wheels)
    files = archive_files(truth.source.read(), large=True)
    if (
        row["source_revision"] != publisher["source_revision"]
        or row["source_revision"] != REVISION
        or publisher["status"] != "archive_tree_and_notice_bound"
        or publisher["reconstructed_tree"] != publisher["published_tree"]
        or [(item["file"], item["sha256"]) for item in publisher["license_notices"]]
        != [("COPYING", digest(files["COPYING"]))]
        or len(truth.fail_to_pass) != 1
        or len(truth.pass_to_pass) != 431
        or checks["names_not_declared_in_selected_module"]
        or not checks["admits_python_3_13_0"]
        or "pyfakefs/_version.py" not in files
    ):
        raise ValueError("source, licence, Python or test identities differ")
    entry = {
        "case_id": CASE,
        "source_revision": REVISION,
        "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"),
        "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": ROLE_ARCHIVES[0],
        "existing_image_dependencies": [],
    }
    runtime = FROZEN / "integrations/assessment-runtime"
    program = (
        (runtime / "repository_suite_native_program.py")
        .read_text()
        .replace(
            "'__AEEP_NATIVE_CAPTURE_SOURCE__'",
            repr((runtime / "repository_suite_native_capture.py").read_text()),
        )
    )
    if digest(program.encode()) != OBSERVER:
        raise ValueError("protected native observer differs")
    spec = ExecutorSpec(
        id="repository.suite.observe",
        capability="assessment.repository_suite@1",
        kind="command",
        description="Contained Pyfakefs file-open grader",
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
    env = AssessmentEnvironment(
        environment_id=NAME,
        kind="container",
        container_image=runner.CARRIER,
        identity={"source": SOURCE},
        container_runtime=runner.DOCKER,
        container_socket=runner.SOCKET,
        memory_mb=512,
        process_limit=96,
        container_tmpfs_mb=64,
    )

    def verify(reply, payload, expected, code):
        valid = BASE_PROBE(reply, payload, expected, code)
        if isinstance(reply, dict) and type(reply.get("exit_code")) is int:
            actual = reply.get("statuses")
            allowed = {"PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL"}
            if (
                isinstance(actual, dict)
                and len(actual) <= 10_000
                and all(type(value) is str and value in allowed for value in actual.values())
            ):
                diagnostics.append(
                    {
                        "role": "original" if code else "reference",
                        "exit_code": reply["exit_code"],
                        "all_status_counts": dict(Counter(actual.values())),
                        "required_status_counts": dict(
                            Counter(actual.get(node, "MISSING") for node in expected)
                        ),
                        "unexpected_required_status_counts": dict(
                            Counter(
                                actual.get(node, "MISSING")
                                for node, want in expected.items()
                                if actual.get(node) != want
                            )
                        ),
                        "contract_matched": valid,
                    }
                )
        return valid

    async def review_fields():
        fields, *_ = await BASE_REVIEW()
        if any(
            launch["archive_sha256"] != sha or launch["required_tests"] != 432
            for launch, sha in zip(fields["launches"], ROLE_ARCHIVES, strict=True)
        ):
            raise ValueError("ordinary role differs from the retained test artifact")
        return (
            {
                **fields,
                "schema_version": "aeep.c13.pyfakefs-protected-pair.v1",
                "source_index_sha256": INDEX_PIN,
                "publisher_inventory_sha256": PUBLISHER_PIN,
                "publisher_tree": publisher["published_tree"],
                "core_wheels_review_sha256": wheel_review,
                "wrapper_sha256": runner.file_digest(Path(__file__)),
                "minimum_host_free_bytes": 52 * 1024**3,
                "raw_protected_output_retained": False,
                "comparisons_paused": True,
                "waza_excluded": True,
            },
            spec,
            env,
            [entry],
        )

    runner.NAME, runner.FROZEN = NAME, FROZEN
    runner.RUN, runner.APPROVAL = TARGET / "execution", TARGET / "approval.json"
    runner.REVIEW, runner.MAX_CALLS = REVIEW, 2
    runner.definitions = lambda: (spec, env, [entry])
    runner.review_fields, runner.verify_probe = review_fields, verify


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--verify")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    diagnostics = []
    configure(diagnostics)
    if args.exact_review:
        try:
            passed = await runner.run(args.exact_review)
        finally:
            if runner.RUN.exists() and diagnostics:
                runner.put(runner.RUN / "status-counts.json", diagnostics)
        raise SystemExit(0 if passed else 1)
    fields, *_ = await runner.review_fields()
    if args.prepare:
        if REVIEW.exists() or TARGET.exists():
            raise ValueError("existing review and attempt must be preserved")
        TARGET.mkdir(mode=0o700)
        runner.put(REVIEW, fields | {"expires_at": (utc_now() + timedelta(days=7)).isoformat()})
    else:
        saved = runner.get(REVIEW)
        expiry = saved["expires_at"]
        if (
            runner.file_digest(REVIEW) != args.verify
            or fields | {"expires_at": expiry} != saved
            or datetime.fromisoformat(expiry) <= utc_now()
        ):
            raise ValueError("exact review changed or expired")
    print(runner.file_digest(REVIEW))


if __name__ == "__main__":
    asyncio.run(main())
