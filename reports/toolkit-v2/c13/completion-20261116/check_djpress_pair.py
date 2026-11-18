"""Review the first DJPress protected pair on the retained Django carrier."""

import argparse
import asyncio
import json
from collections import Counter
from datetime import timedelta
from pathlib import Path

import repository_offline_pair_batch as runner
from acquire_larger_multifile_source import AUTHORITY, binding
from audit_staged_repository_graders import bind, wheel_probe_assets
from check_advanced_alchemy_pair import FROZEN, SOURCE, verify_source
from stage_repository_transport import ROOT, WORK, digest, read

from aeep.assessment.models import AssessmentEnvironment
from aeep.assessment.repository_suites import LARGE_PAYLOAD, archive_files
from aeep.models import ExecutorSpec, utc_now

CASE = "stuartmaxwell__djpress-117"
NAME = "c13-djpress-protected-pair-20261118"
TARGET = WORK / "djpress-protected-pair-20261118"
INDEX = WORK / "staged-worker-transport-rebound/private-index.json"
INDEX_PIN = "378a7a9cf4dc2184f5af65b063547cbc27fc253d6f51d1e74cb3278280d5d4bc"
PROOF = TARGET / "source-and-runtime-proof.json"
PROOF_PIN = "e9d30b1e81457984642ca37f3f20b3f13ce07dd8d6372a987027dee863d3ab3f"
BASE_REVIEW, BASE_PROBE = runner.review_fields, runner.verify_probe


def configure(observations):
    verify_source()
    proof = json.loads(read(PROOF, PROOF_PIN))
    (row,) = [
        item for item in json.loads(read(INDEX, INDEX_PIN)) if item["input"]["task_id"] == CASE
    ]
    archive = proof["archive"]
    root = ROOT / proof["publisher_source_and_notices"]["path"]
    read(root, proof["publisher_source_and_notices"]["sha256"])
    read(ROOT / archive["path"], archive["sha256"])
    base_pin, wheels = wheel_probe_assets()
    for name in proof["portable_projects"]:
        pin = proof["selected_runtime"][name]
        wheels.append(runner.asset(ROOT / pin["path"], pin["sha256"]))
    task, original_truth, reference, original, _ = bind(row, INDEX.parent, wheels)
    if (
        row["source_revision"] != proof["source_revision"]
        or task.family != "multi-file-repair"
        or len(task.editable_paths) != 2
        or len(original_truth.fail_to_pass) != 3
        or len(original_truth.pass_to_pass) != 65
    ):
        raise ValueError("DJPress source or test contract changed")
    source = archive_files(original_truth.source.read(), large=True)
    for notice in proof["license_notices"]:
        if digest(source[notice["file"]]) != notice["sha256"]:
            raise ValueError("retained authorization notice changed")
    config_path = "example/config/settings_testing.py"
    settings = source[config_path].decode()
    if (
        '"ENGINE": "django.db.backends.sqlite3"' not in settings
        or '"NAME": ":memory:"' not in settings
    ):
        raise ValueError("reviewed test database configuration changed")
    truth = original_truth.model_copy(update={"pytest_plugins": ["pytest_django.plugin"]})
    versions = {key: item["version"] for key, item in proof["selected_runtime"].items()}
    runtime = FROZEN / "integrations/assessment-runtime"
    program = (
        (runtime / "repository_suite_native_program.py")
        .read_text()
        .replace(
            "'__AEEP_NATIVE_CAPTURE_SOURCE__'",
            repr((runtime / "repository_suite_native_capture.py").read_text()),
        )
    )
    anchor = "+ ';import pytest;"
    dependency_probe = (
        ";from importlib.metadata import version;assert all("
        f"version(name)==expected for name,expected in {versions!r}.items())"
    )
    if program.count(anchor) != 1:
        raise ValueError("reviewed observer bootstrap changed")
    program = program.replace(anchor, "+ " + repr(dependency_probe) + "\n            " + anchor)
    compile(program, "<DJPress protected observer>", "exec")
    spec = ExecutorSpec(
        id="repository.suite.observe",
        capability="assessment.repository_suite@1",
        kind="command",
        description="Contained DJPress native unit grader",
        config={
            "argv": ["python3", "-B", "-c", program],
            "argv_literal": True,
            "stdin_json": True,
            "timeout_seconds": 32,
            "max_stdin_bytes": LARGE_PAYLOAD,
            "max_output_bytes": 500_000,
            "output": {"type": "json"},
        },
    )
    environment = AssessmentEnvironment(
        environment_id=NAME,
        kind="container",
        network=False,
        container_image=proof["carrier"],
        identity={"source": SOURCE, "djpress_source_runtime": PROOF_PIN},
        container_runtime=runner.DOCKER,
        container_socket=runner.SOCKET,
        memory_mb=512,
        process_limit=96,
        container_tmpfs_mb=64,
    )
    subject = {
        "case_id": CASE,
        "source_revision": row["source_revision"],
        "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"),
        "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": row["reference_archive_sha256"],
        "existing_image_dependencies": [
            f"{name}=={versions[name]}" for name in proof["inherited_projects"]
        ],
    }

    def observe(reply, payload, expected, code):
        accepted = BASE_PROBE(reply, payload, expected, code)
        row = {"role": "original" if code else "reference", "verified_contract": accepted}
        if isinstance(reply, dict) and isinstance(reply.get("statuses"), dict):
            statuses = reply["statuses"]
            allowed = {"PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL"}
            if len(statuses) <= 10000 and all(
                isinstance(v, str) and v in allowed for v in statuses.values()
            ):
                row.update(
                    pytest_exit=reply.get("exit_code"),
                    required_status_counts=dict(
                        Counter(statuses.get(node, "MISSING") for node in expected)
                    ),
                    mismatch_identities=[
                        {
                            "node_id": node,
                            "observed": statuses.get(node, "MISSING"),
                            "expected": want,
                            "kind": "issue" if node in truth.fail_to_pass else "preservation",
                        }
                        for node, want in expected.items()
                        if statuses.get(node) != want
                    ],
                )
        observations.append(row)
        return accepted

    async def review_fields():
        fields, *_ = await BASE_REVIEW()
        if fields["carrier_layers"] != proof["carrier_layers"] or [
            row["required_tests"] for row in fields["launches"]
        ] != [68, 68]:
            raise ValueError("retained carrier or required test inventory differs")
        return (
            fields
            | {
                "schema_version": "aeep.c13.djpress-protected-pair.v1",
                "driver": binding(Path(__file__)),
                "delegated_authority": binding(AUTHORITY),
                "source_runtime_proof": binding(PROOF),
                "baseline_wheel_review_sha256": base_pin,
                "test_database": ":memory:",
                "test_settings_sha256": digest(source[config_path]),
                "runtime_scope": "Retained compatible Python 3.13 and dependency versions differ from the publisher lock. Source, test assertions and SQLite settings are unchanged.",
                "retain_private_oracle_mismatches": True,
                "retry": False,
                "waza_excluded": True,
                "comparisons_paused": True,
            },
            spec,
            environment,
            [subject],
        )

    runner.NAME, runner.FROZEN, runner.CARRIER = NAME, FROZEN, proof["carrier"]
    runner.MAX_CALLS = 2
    runner.REVIEW, runner.APPROVAL = TARGET / "operation-review.json", TARGET / "approval.json"
    runner.RUN = TARGET / "execution"
    runner.definitions, runner.review_fields, runner.verify_probe = (
        lambda: (spec, environment, [subject]),
        review_fields,
        observe,
    )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    observations = []
    configure(observations)
    if args.prepare:
        review, *_ = await runner.review_fields()
        runner.put(
            runner.REVIEW, review | {"expires_at": (utc_now() + timedelta(days=7)).isoformat()}
        )
        print(runner.file_digest(runner.REVIEW))
    else:
        try:
            passed = await runner.run(args.exact_review)
        finally:
            if observations and runner.RUN.exists():
                runner.put(runner.RUN / "required-test-observations.json", observations)
        raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
