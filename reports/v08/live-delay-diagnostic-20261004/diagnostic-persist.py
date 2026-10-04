"""Apply one exact reviewed inert diagnostic bundle; never execute or reset counters."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE = "e6b71acba487280dfe50057d17379e5994c9113bc651a262935474f656a5dba6"
DB = ROOT / ".aeep/live-review-v3/aeep.sqlite3"
MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
REVIEW = OUT / "diagnostic-persistence-review.json"
BUNDLE = OUT / "diagnostic-preparation.json"
RESULT = OUT / "diagnostic-persistence-result.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    from aeep.assessment.identity import verify_dependencies
    from aeep.assessment.models import ConformanceProbeRequest, content_digest
    from aeep.assessment.repository import AssessmentRepository
    from aeep.assessment.verification import verification_source_digest

    parser = argparse.ArgumentParser()
    parser.add_argument("--persist-reviewed-sha256", required=True)
    args = parser.parse_args()
    require(sha(REVIEW) == args.persist_reviewed_sha256, "persistence review changed")
    review = json.loads(REVIEW.read_text())
    require(review.get("persistence_authorized") is True and review.get("execution_authorized") is False,
            "separate inert persistence authority required")
    require(review.get("runner_sha256") == sha(Path(__file__)) and review.get("source_digest") == SOURCE
            and verification_source_digest(ROOT) == SOURCE, "reviewed helper or source changed")
    require(not DB.is_symlink() and (DB.stat().st_dev, DB.stat().st_ino) == (16777231, 166293865),
            "canonical store identity changed")
    require(sha(MANIFEST) == review.get("manifest_sha256") ==
            "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb", "manifest pin changed")
    require(not RESULT.exists(), "preserve one-shot persistence result")
    require(review.get("bundles") == {BUNDLE.name: sha(BUNDLE)}, "review must pin this one inert bundle")
    bundle = json.loads(BUNDLE.read_text())
    require(bundle.get("source_digest") == SOURCE and bundle.get("diagnostic_only") is True
            and bundle.get("execution_authorized") is False and bundle.get("holdout") is False,
            "bundle must remain an inert diagnostic")
    require(bundle.get("limits") == {"operations": 1, "model_turns": 1, "elapsed_seconds": 208.0,
            "cash_usd": 0, "task_calls": 1, "task_call_timeout_seconds": 10.0, "task_scope_attempts": 1},
            "diagnostic limits changed")
    request = ConformanceProbeRequest.model_validate(bundle["request"])
    require(content_digest(request) == bundle["request_digest"] and request.authorization_id == "onboarding"
            and request.composed_model_turns == 1, "existing grant and exact request required")
    verify_dependencies(request.executable_dependencies)
    connection = sqlite3.connect(f"file:{DB}?mode=rw", uri=True)
    repository = AssessmentRepository(SimpleNamespace(_connection=connection, _lock=threading.RLock()))
    inserted, reused = [], []
    try:
        connection.execute("BEGIN IMMEDIATE")
        before = connection.execute("SELECT * FROM assessment_grants ORDER BY id").fetchall()
        repository.current_grant("onboarding")
        for item in bundle["records_to_store_and_review"]:
            kind, identity, digest, value = (item[key] for key in ("kind", "identity", "digest", "value"))
            require(kind in {"boundary_probe_definition", "composed_callback_action", "c_callback_fixture_binding",
                    "c_callback_capacity_binding", "c_treatment_task_scope_binding", "conformance_request"},
                    "unexpected diagnostic record kind")
            require(content_digest(value) == digest, "record digest changed")
            old = connection.execute("SELECT digest,payload_json FROM assessment_records WHERE kind=? AND id=?",
                                     (kind, identity)).fetchone()
            previous_review = connection.execute("SELECT revoked FROM assessment_reviews WHERE digest=?", (digest,)).fetchone()
            if old is not None:
                require(kind == "boundary_probe_definition" and old[0] == digest
                        and content_digest(json.loads(old[1])) == digest
                        and previous_review is not None and previous_review[0] == 0,
                        "one-shot diagnostic record exists or prior review changed")
                reused.append([kind, digest])
                continue
            require(previous_review is None, "existing review cannot be replaced")
            connection.execute("INSERT INTO assessment_records VALUES (?,?,?,?)",
                               (kind, identity, digest, json.dumps(value)))
            connection.execute("INSERT INTO assessment_reviews VALUES (?,?,0)",
                               (digest, datetime.now(UTC).isoformat()))
            inserted.append([kind, digest])
        repository.authorize(request)
        require(connection.execute("SELECT * FROM assessment_grants ORDER BY id").fetchall() == before,
                "grant counters changed during inert persistence")
        require(verification_source_digest(ROOT) == SOURCE, "source changed during persistence")
        connection.commit()
        result = dict(status="persisted_reviewed_inert", review_sha256=args.persist_reviewed_sha256,
                      source_digest=SOURCE, inserted=inserted, reused_exact_reviewed=reused,
                      grant_counters_unchanged=True, model_turns=0, operations_reserved=0,
                      atomic_commit=True, execution_authorized=False, diagnostic_only=True)
        with RESULT.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(json.dumps(result))
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


if __name__ == "__main__":
    main()
