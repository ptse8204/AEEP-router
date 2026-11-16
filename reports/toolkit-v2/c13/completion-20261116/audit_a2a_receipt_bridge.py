"""Verify retained A2A observations against the ordinary grading callback offline."""

import asyncio
import json
import sqlite3
import tomllib
from collections import Counter
from contextlib import closing
from pathlib import Path

from stage_repository_transport import HERE, ROOT, WORK, read

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import (
    MAX_ARCHIVE,
    SuiteAsset,
    SuiteInput,
    SuiteTruthV6,
    archive_files,
    compressed_patch_artifact,
    grade_suite_output,
)
from aeep.assessment.repository_tasks import RepositoryPatch
from aeep.errors import ConfigurationError

PRIVATE = WORK / "staged-worker-transport-rebound"
SETTLED = WORK / "a2a-batch-reference-execution"
FIXTURES = Path("/private/tmp/aeep-c13-a2a-batch-20261116")
CASES = {"a2aproject__a2a-python-576", "a2aproject__a2a-python-682_interface"}
ROLES = ("reference", "original")


def load(path):
    return json.loads(path.read_bytes())


def settled_receipt(db, case, role, report, review, operations):
    published = report["roles"][case][role]
    path = SETTLED / f"{case}-{role}-receipt.json"
    receipt = json.loads(read(path, published["receipt_sha256"]))
    meta = receipt["metadata"]
    identity = f"aeep-c13-a2a-batch-20261116:{case}:{role}"
    operation = operations[identity]
    stored = db.execute(
        "SELECT payload_json FROM receipts WHERE receipt_id = ?", (published["receipt_id"],)
    ).fetchone()
    state = db.execute(
        "SELECT state FROM assessment_operations WHERE id = ?", (identity,)
    ).fetchone()
    projection = meta["observation"]
    counts = published["observed_result_counts"]
    binding_rel = f"{case}/{role}/binding.json"
    binding = json.loads(read(FIXTURES / binding_rel, review["files"][binding_rel]))
    if not (
        state == ("complete",)
        and stored is not None
        and json.loads(stored[0]) == receipt
        and operation["elapsed_seconds"] > 0
        and operation["resources"] == receipt["actual_resources"]
        and operation["reserved"]["max_model_turns"] == 0
        and operation["reserved"]["max_cash_usd"] == "0"
        and receipt["decision_id"] == receipt["action_id"] == identity
        and receipt["receipt_id"] == published["receipt_id"]
        and receipt["status"] == projection["worker_status"] == "success"
        and meta["review_sha256"] == report["review_sha256"]
        and (meta["case_id"], meta["role"]) == (case, role)
        and published["verified"] is meta["container_absent"] is True
        and projection["source_verified"] is projection["input_verified"] is True
        and projection["exit_code"] == published["upstream_exit_code"] == binding["exit_code"]
        and projection["statuses"] == binding["outcomes"]
        and projection["collected"] == published["collected"] == sum(counts.values())
        and Counter(projection["statuses"].values()) == counts
        and binding["archive_sha256"] == review["files"][f"{case}/{role}/fixture.tar.gz"]
    ):
        raise ValueError("retained receipt, settlement or fixture binding differs")
    return published["receipt_id"], binding["archive_sha256"], projection


def reviewed_wheels(review):
    standalone = load(WORK / "a2a-protected-reference-review.json")
    lock = json.loads(
        read(WORK / "a2a-offline-assets/wheel-lock.json", standalone["wheel_lock_sha256"])
    )
    extra = load(HERE / "a2a-batch-intake.json")["additional_wheel"]
    starlette = (
        ROOT / ".aeep/repository-supported-suite-wheels-20261027/starlette-0.48.0-py3-none-any.whl"
    )
    paths = [(ROOT / wheel["path"], wheel["sha256"]) for wheel in lock["wheels"].values()]
    paths.append((starlette, extra["sha256"]))
    portable, unsupported = [], []
    for path, sha in paths:
        size = len(read(path, sha))
        reasons = []
        if not path.name.endswith("-none-any.whl"):
            reasons.append("native_wheel")
        if size > MAX_ARCHIVE:
            reasons.append("wheel_exceeds_asset_limit")
        if reasons:
            unsupported.append(
                {"filename": path.name, "sha256": sha, "bytes": size, "reasons": reasons}
            )
        else:
            portable.append(SuiteAsset(path=str(path), sha256=sha, size_bytes=size))
    if (
        len(portable) != 22
        or len(unsupported) != 3
        or "shared/support/pytest_asyncio/plugin.py" not in review["files"]
    ):
        raise ValueError("reviewed runtime closure differs")
    return portable, unsupported


def case_assets(row, wheels):
    task = SuiteInput.model_validate(row["input"])
    private = PRIVATE / "protected" / task.task_id
    required = json.loads(read(private / "required.json", row["required_identities"]["sha256"]))
    public = PRIVATE / "public" / row["public_source"]["name"]
    oracle = SuiteTruthV6(
        input_sha256=content_digest(task),
        source={
            "path": str(public),
            "sha256": task.source_sha256,
            "size_bytes": row["public_source"]["bytes"],
        },
        tests={
            "path": str(private / "tests.tar.gz"),
            "sha256": row["protected_tests"]["sha256"],
            "size_bytes": row["protected_tests"]["bytes"],
        },
        wheels=wheels,
        python="3.13",
        pytest="8.4.1",
        test_paths=row["test_modules"],
        pytest_plugins=["pytest_asyncio.plugin"],
        test_roots=row["test_roots"],
        patch_encoding="gzip-json",
        archive_profile="repository-v1",
        identity_format="pytest-native-v1",
        **required,
    )
    reference = json.loads(read(private / "reference.json", row["reference"]["sha256"]))
    source = archive_files(oracle.source.read(), large=True)
    # Writing the existing source bytes is a nonempty, in-scope patch that preserves the original tree.
    original_patch = RepositoryPatch(
        base_sha256=oracle.input_sha256,
        files={path: source[path].decode("utf-8") for path in task.editable_paths},
    )
    return task, oracle, reference, original_patch, source


async def grade_retained(row, wheels, observations):
    task, oracle, reference, original_patch, source = case_assets(row, wheels)
    if observations["reference"][1] != row["reference_archive_sha256"]:
        raise ValueError("reviewed fixture and staged reference differ")

    async def grade(role, artifact, *, drop=None, corrupt=False, expected_calls=1):
        receipt_id, archive_sha256, observation = observations[role]
        calls = []

        async def replay(payload):
            calls.append(payload["archive_sha256"])
            if payload["archive_sha256"] != archive_sha256:
                raise ValueError("ordinary grader built a different protected fixture")
            statuses = dict(observation["statuses"])
            if drop:
                statuses.pop(drop)
            return {
                "archive_sha256": "0" * 64 if corrupt else archive_sha256,
                "python": oracle.python,
                "pytest": oracle.pytest,
                "statuses": statuses,
                "exit_code": observation["exit_code"],
            }

        try:
            grade = await grade_suite_output(
                task.model_dump(mode="json"), oracle.model_dump(mode="json"), artifact, replay
            )
            result = {"score": grade.quality_score, "detail": grade.detail}
        except ConfigurationError:
            if not corrupt:
                raise
            result = {"score": None, "detail": "protocol_error"}
        if len(calls) != expected_calls:
            raise ValueError("unexpected ordinary callback consultation")
        return {"source_receipt_id": receipt_id if calls else None, **result}

    grades = {
        "reference": await grade("reference", reference),
        "original": await grade("original", compressed_patch_artifact(original_patch)),
        "missing_assertion_control": await grade(
            "reference", reference, drop=oracle.fail_to_pass[0]
        ),
        "mismatched_archive_control": await grade("reference", reference, corrupt=True),
        "wrong_patch_base_control": await grade(
            "original",
            compressed_patch_artifact(original_patch.model_copy(update={"base_sha256": "0" * 64})),
            expected_calls=0,
        ),
    }
    expected = [
        (1.0, ""),
        (0.0, "test_failure"),
        (0.0, "missing_test"),
        (None, "protocol_error"),
        (0.0, "input_binding"),
    ]
    if [(item["score"], item["detail"]) for item in grades.values()] != expected:
        raise ValueError("ordinary grading decision differs")
    config = tomllib.loads(source["pyproject.toml"].decode())["tool"]["pytest"]["ini_options"]
    return {
        "source_revision": row["source_revision"],
        "protected_test_archive_sha256": oracle.tests.sha256,
        "required_assertions": len(oracle.fail_to_pass) + len(oracle.pass_to_pass),
        "published_addopts": config["addopts"],
        "required_selector_scope": "exact nodes used in protected run; ordinary observer selects modules",
        "read_only_grade_projection": grades,
    }


async def main():
    report = load(HERE / "approved-a2a-batch-results.json")
    review = json.loads(read(WORK / "a2a-batch-reference-review.json", report["review_sha256"]))
    transport = load(HERE / "rebound-worker-transport.json")
    rows = json.loads(read(PRIVATE / "private-index.json", transport["private_index_sha256"]))
    ledger = json.loads(read(SETTLED / "ledger.json", report["operation_ledger_sha256"]))
    operations = {item["operation_id"]: item for item in ledger["operations"]}
    if set(report["reproduced"]) != CASES or len(operations) != report["settled_operations"]:
        raise ValueError("reproduced case or operation inventory differs")
    wheels, unsupported_wheels = reviewed_wheels(review)
    wal = SETTLED / "receipts.sqlite3-wal"
    if wal.exists() and wal.stat().st_size:
        raise ValueError("receipt database has an unreconciled WAL")
    uri = (SETTLED / "receipts.sqlite3").as_uri() + "?mode=ro&immutable=1"
    results = {}
    with closing(sqlite3.connect(uri, uri=True)) as db:
        for row in rows:
            case = row["input"]["task_id"]
            if case not in CASES:
                continue
            observed = {
                role: settled_receipt(db, case, role, report, review, operations) for role in ROLES
            }
            results[case] = await grade_retained(row, wheels, observed)
    if set(results) != CASES:
        raise ValueError("ordinary archive inventory differs")
    print(
        json.dumps(
            {
                "schema_version": "aeep.c13.a2a-receipt-bridge-audit.v1",
                "historical_review_sha256": report["review_sha256"],
                "historical_source": review["source"],
                "historical_operation_ledger_sha256": report["operation_ledger_sha256"],
                "cases": results,
                "ordinary_tests_executed": 0,
                "prior_receipts_verified": 4,
                "transport_wheels_in_read_only_payload": len(wheels),
                "model_turns": 0,
                "formal_cases_adopted": 0,
                "ordinary_runtime_blockers": {
                    "wheels_outside_v6_transport": unsupported_wheels,
                    "unadapted_addopts": {
                        "a2aproject__a2a-python-682_interface": "--dist loadgroup"
                    },
                    "selector_equivalence": "Protected runs use required node IDs. Module-wide collection and exit status remain unverified.",
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
