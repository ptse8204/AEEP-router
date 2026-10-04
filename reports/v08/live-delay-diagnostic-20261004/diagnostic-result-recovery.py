"""Persist the exact failed diagnostic result after separate review; never replay work."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = "e6b71acba487280dfe50057d17379e5994c9113bc651a262935474f656a5dba6"
RUNNER = OUT / "diagnostic-run.py"
RUNNER_SHA = "2c02948928087ae2de43a8c313b71f273a986c9dea797a387c11e56921bd1f4c"
RESULT = OUT / "diagnostic-result.json"
RESULT_SHA = "249c2c86f14a2f21596fa9154d983e8d39c575a49b39c9f9526b64bfe534ee07"
RESULT_DIGEST = "46f33e2c35dc4b669f0b0975eb7b211af886be4e18e7196c360ee61e218e7855"
OPERATION = "composed:conformance_probe_17ffbc14f98146619659c1cdec1660b2"
MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
MANIFEST_SHA = "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb"
DB = ROOT / ".aeep/live-review-v3/aeep.sqlite3"
PROPOSAL = OUT / "diagnostic-result-recovery-proposed-review.json"
REVIEW = OUT / "diagnostic-result-recovery-review.json"
RECOVERY_RESULT = OUT / "diagnostic-result-recovery-result.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 2_000_000,
            "recovery input is unavailable, oversized or a symlink")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_result() -> tuple[dict, str]:
    """Validate with the original model and an explicit module namespace; no DB."""
    from aeep.assessment.models import content_digest
    from aeep.assessment.verification import verification_source_digest

    require(verification_source_digest(ROOT) == SOURCE, "source changed")
    require(sha(RUNNER) == RUNNER_SHA and sha(RESULT) == RESULT_SHA, "frozen runner/result changed")
    payload = RESULT.read_text()
    value = json.loads(payload)
    require(value.get("operation_id") == OPERATION and value.get("source_digest") == SOURCE
            and value.get("result_status") == "failed" and value.get("host_receipt_status") == "timeout"
            and value.get("canonical_result_error_type") == "PydanticUserError"
            and value.get("probe_digest") is None and value.get("operation_settled") is True
            and value.get("cleanup_confirmed") is True
            and all(value.get(key) is False for key in ("full_conformance", "qualification", "admission", "holdout", "value_trial")),
            "recovery must preserve the original negative diagnostic")
    name = "aeep_frozen_delay_result_recovery"
    require(name not in sys.modules, "recovery module namespace is already occupied")
    spec = importlib.util.spec_from_file_location(name, RUNNER)
    require(spec is not None and spec.loader is not None, "frozen runner loader is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        model = module._load_result_model(value)
        require(model.model_dump(mode="json") == value and content_digest(model) == RESULT_DIGEST
                and content_digest(value) == RESULT_DIGEST, "result content changed during validation")
    finally:
        sys.modules.pop(name, None)
    return value, payload


def proposed_review() -> dict:
    value, _ = checked_result()
    return dict(schema_version="assessment.live-delay-result-recovery-review.v1",
        status="proposed_not_authorized", recovery_authorized=False, execution_authorized=False,
        source_digest=SOURCE, helper_sha256=sha(Path(__file__)), runner_sha256=RUNNER_SHA,
        original_result_sha256=RESULT_SHA, original_result_digest=RESULT_DIGEST,
        operation_id=OPERATION, record_kind="composed_runner_result", only_if_absent=True,
        manifest_sha256=MANIFEST_SHA, database_path=str(DB), database_device=16777231,
        database_inode=166293865, operation_start_digest=value["operation_start_digest"],
        operation_measurement_digest=value["operation_measurement_digest"],
        preserve_negative_status=True, reset_counters=False, reserve_operations=0, model_turns=0,
        authority="Pending root exact review for one missing canonical failed-result record only.")


def recover(review_sha256: str) -> dict:
    from aeep.assessment.models import content_digest

    require(sha(REVIEW) == review_sha256, "exact recovery review required")
    review = json.loads(REVIEW.read_text())
    expected = proposed_review()
    for key, value in expected.items():
        if key not in {"status", "authority", "recovery_authorized"}:
            require(review.get(key) == value, "recovery review differs from the frozen proposal")
    require(review.get("recovery_authorized") is True and review.get("status") == "reviewed",
            "separate exact persistence recovery authority required")
    require(not RECOVERY_RESULT.exists(), "preserve existing recovery record; no replay")
    value, payload = checked_result()
    require(sha(MANIFEST) == MANIFEST_SHA and not DB.is_symlink()
            and (DB.stat().st_dev, DB.stat().st_ino) == (16777231, 166293865), "canonical store changed")
    require(Path(json.loads(MANIFEST.read_text())["database"]).resolve() == DB.resolve(), "manifest store target changed")
    connection = sqlite3.connect(f"file:{DB}?mode=rw", uri=True)
    try:
        connection.execute("BEGIN IMMEDIATE")
        require(connection.execute("SELECT 1 FROM assessment_records WHERE kind='composed_runner_result' AND id=?",
                                   (OPERATION,)).fetchone() is None, "canonical result already exists; preserve it")
        grants = connection.execute("SELECT * FROM assessment_grants ORDER BY id").fetchall()
        operation = connection.execute("SELECT * FROM assessment_operations WHERE id=?", (OPERATION,)).fetchone()
        require(operation is not None and operation[1] == "onboarding" and operation[2] == "complete",
                "existing operation must already be terminal on the original grant")

        def record(kind: str, identity: str, digest: str) -> dict:
            row = connection.execute("SELECT digest,payload_json FROM assessment_records WHERE kind=? AND (id=? OR digest=?)",
                                     (kind, identity, identity)).fetchone()
            require(row is not None and row[0] == digest, "original canonical evidence is missing or changed")
            result = json.loads(row[1])
            require(content_digest(result) == digest, "original canonical evidence digest differs")
            return result

        record("operation_start", OPERATION, value["operation_start_digest"])
        measurement = record("operation_measurement", OPERATION, value["operation_measurement_digest"])
        require(value["charged_operation_digest"] == value["operation_start_digest"]
                and measurement.get("elapsed_seconds") == value["elapsed_seconds"], "original settled charge differs")
        for digest in set([value["host_receipt_digest"], *value["outer_receipt_digests"]]):
            record("conformance_host_receipt", digest, digest)
        for digest in value["outer_attempt_digests"]:
            record("conformance_outer_attempt", digest, digest)
        if value["partial_execution_evidence_digest"]:
            digest = value["partial_execution_evidence_digest"]
            record("execution_evidence", digest, digest)
        probe_count = connection.execute("SELECT COUNT(*) FROM assessment_records WHERE kind='boundary_probe'").fetchone()[0]
        review_count = connection.execute("SELECT COUNT(*) FROM assessment_reviews").fetchone()[0]
        connection.execute("INSERT INTO assessment_records VALUES ('composed_runner_result',?,?,?)",
                           (OPERATION, RESULT_DIGEST, payload))
        require(connection.execute("SELECT * FROM assessment_grants ORDER BY id").fetchall() == grants
                and connection.execute("SELECT * FROM assessment_operations WHERE id=?", (OPERATION,)).fetchone() == operation
                and connection.execute("SELECT COUNT(*) FROM assessment_records WHERE kind='boundary_probe'").fetchone()[0] == probe_count
                and connection.execute("SELECT COUNT(*) FROM assessment_reviews").fetchone()[0] == review_count,
                "recovery changed unrelated authority or measurements")
        checked_result()  # Recheck frozen source/result before committing the single insert.
        connection.commit()
        return dict(schema_version="assessment.live-delay-result-recovery.v1", status="failed_result_persisted",
            review_sha256=review_sha256, helper_sha256=sha(Path(__file__)), operation_id=OPERATION,
            original_result_sha256=RESULT_SHA, canonical_result_digest=RESULT_DIGEST,
            original_failed_result_unchanged=True, original_canonical_error_retained=True,
            grant_counters_unchanged=True, operation_measurement_unchanged=True, probe_count_unchanged=True,
            reviews_unchanged=True, new_model_turns=0, new_operations_reserved=0,
            full_conformance=False, qualification=False, admission=False, holdout=False)
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-inert", action="store_true")
    mode.add_argument("--recover-reviewed-sha256")
    args = parser.parse_args()
    if args.prepare_inert:
        target, result = PROPOSAL, proposed_review()
    else:
        target, result = RECOVERY_RESULT, recover(args.recover_reviewed_sha256)
    with target.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({"result_path": str(target), "sha256": sha(target), "status": result["status"]}))


if __name__ == "__main__":
    main()
