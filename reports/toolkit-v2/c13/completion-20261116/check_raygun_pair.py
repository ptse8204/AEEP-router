"""Verify the retained Raygun wildcard-key contract through the ordinary grader."""

import argparse
import asyncio
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import repository_offline_pair_batch as runner
from audit_staged_repository_graders import bind, wheel_probe_assets
from check_returnn_pair import FROZEN, PINNED_OBSERVER, SOURCE
from stage_repository_transport import HERE, WORK, digest, read

import aeep
from aeep.assessment.models import AssessmentEnvironment
from aeep.assessment.repository_suites import LARGE_PAYLOAD, archive_files
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec, utc_now

CASE = "MindscapeHQ__raygun4py-119-aeep-contract-audit"
REVISION = "4c0ab4f645d9af29c91370667878fb29303ac972"
NAME = "c13-raygun-protected-pair-20261118"
TARGET = WORK / NAME
REVIEW = HERE / "raygun-protected-pair-review-20261118.json"
INDEX = WORK / "ancillary-contract-audits/index.json"
INDEX_PIN = "668b21cc6493bbffc4a54fd622c63ef304f9953fd7853ba8b7651f536f556d3a"
BASE_REVIEW, BASE_PROBE = runner.review_fields, runner.verify_probe


def select_attempt(diagnostics):
    if (
        Path(aeep.__file__).resolve().parents[2] != FROZEN
        or verification_source_digest(FROZEN) != SOURCE
    ):
        raise ValueError("load the frozen coordinator")
    (row,) = (
        item for item in json.loads(read(INDEX, INDEX_PIN)) if item["input"]["task_id"] == CASE
    )
    core_review, wheels = wheel_probe_assets()
    task, truth, reference, original, checks = bind(row, INDEX.parent, wheels)
    required_path = INDEX.parent / "protected" / CASE / "required.json"
    required = json.loads(read(required_path, row["protected_assets"]["required.json"]["sha256"]))
    original_failures = {*required["published_fail_to_pass"], row["protected_guard"]}
    public = archive_files(truth.source.read(), large=True)
    if (
        row["source_revision"] != REVISION
        or (len(truth.pass_to_pass), len(original_failures)) != (7, 3)
        or checks["names_not_declared_in_selected_module"]
        or "python3/tests/__init__.py" not in public
        or "python3/__init__.py" in public
    ):
        raise ValueError("pinned test identities or package layout differ")
    entry = {
        "case_id": CASE,
        "source_revision": REVISION,
        "input": task.model_dump(mode="json"),
        "truth": truth.model_dump(mode="json"),
        "roles": {"reference": reference, "original": original},
        "reference_archive_sha256": row["reference_archive_sha256"],
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
    if digest(program.encode()) != PINNED_OBSERVER:
        raise ValueError("protected native observer differs")
    spec = ExecutorSpec(
        id="repository.suite.observe",
        capability="assessment.repository_suite@1",
        kind="command",
        description="Contained Raygun wildcard-key audit grader",
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
        container_image=runner.CARRIER,
        identity={"source": SOURCE},
        container_runtime=runner.DOCKER,
        container_socket=runner.SOCKET,
        memory_mb=512,
        process_limit=96,
        container_tmpfs_mb=64,
    )

    def expected_statuses(truth, role):
        outcomes = dict.fromkeys(truth["pass_to_pass"], "PASSED")
        if role == "original":
            outcomes.update(dict.fromkeys(original_failures, "FAILED"))
        return outcomes

    def verify(reply, payload, statuses, code):
        valid = BASE_PROBE(reply, payload, statuses, code)
        if isinstance(reply, dict) and type(reply.get("exit_code")) is int:
            values = reply.get("statuses")
            allowed = {"PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL"}
            if (
                isinstance(values, dict)
                and len(values) <= 10_000
                and all(type(value) is str and value in allowed for value in values.values())
            ):
                diagnostics.append(
                    {
                        "role": "original" if code else "reference",
                        "exit_code": reply["exit_code"],
                        "required_status_counts": dict(
                            Counter(values.get(name, "MISSING") for name in statuses)
                        ),
                        "contract_matched": valid,
                    }
                )
        return valid

    async def review_fields():
        fields, *_ = await BASE_REVIEW()
        for launch, expected in zip(
            fields["launches"],
            (row["reference_archive_sha256"], row["fault_archive_sha256"]),
            strict=True,
        ):
            if launch["archive_sha256"] != expected or launch["required_tests"] != 7:
                raise ValueError("ordinary role differs from the previously staged test artifact")
        return (
            {
                **fields,
                "schema_version": "aeep.c13.raygun-protected-pair.v1",
                "source_index_sha256": INDEX_PIN,
                "core_wheels_review_sha256": core_review,
                "wrapper_sha256": runner.file_digest(Path(__file__)),
                "minimum_host_free_bytes": 52 * 1024**3,
                "raw_protected_output_retained": False,
                "comparisons_paused": True,
                "waza_excluded": True,
            },
            spec,
            environment,
            [entry],
        )

    runner.NAME, runner.FROZEN = NAME, FROZEN
    runner.RUN, runner.APPROVAL = TARGET / "execution", TARGET / "approval.json"
    runner.REVIEW, runner.MAX_CALLS = REVIEW, 2
    runner.definitions = lambda: (spec, environment, [entry])
    runner.review_fields, runner.expected_statuses, runner.verify_probe = (
        review_fields,
        expected_statuses,
        verify,
    )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--verify")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    summaries = []
    select_attempt(summaries)
    if args.exact_review:
        try:
            passed = await runner.run(args.exact_review)
        finally:
            if runner.RUN.exists() and summaries:
                runner.put(runner.RUN / "status-counts.json", summaries)
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
