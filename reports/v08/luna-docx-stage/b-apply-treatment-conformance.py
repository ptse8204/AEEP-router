"""Persist only the exact reviewed treatment evidence; no worker or model work."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from aeep.assessment.boundary import (
    BoundaryConformance,
    require_candidate_access,
    require_conformance,
)
from aeep.assessment.models import DifferentialEnvironment, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
PROPOSAL = OUT / "b-treatment-boundary-conformance-proposal.json"
PROPOSAL_SHA = "0c1ebcd30ff2472bb9205f17d8714daabc09671734edcddfc1e39a7b9ea72881"
SOURCE = "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
DATABASE = ROOT / ".aeep/live-review-v3/aeep.sqlite3"
REVIEW = OUT / "b-treatment-boundary-parent-review.json"
RESULT = OUT / "b-treatment-boundary-apply-result.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(repo, record, digest):
    actual = require_conformance(repo, digest, source_digest=SOURCE,
        worker_digest=record.worker_digest, identity_digest=record.identity_digest)
    pair = repo.get("composed_pair_definition", record.composed_definition_digest)
    require_candidate_access(repo, actual,
        DifferentialEnvironment.model_validate(pair["differential"]), available=True)
    return actual


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("review_sha256")
    args = parser.parse_args()
    if RESULT.exists() or sha(REVIEW) != args.review_sha256:
        raise ValueError("exact fresh parent review required")
    review = json.loads(REVIEW.read_text())
    if (review.get("execution_authorized") is not True
            or review.get("proposal_sha256") != PROPOSAL_SHA
            or review.get("runner_sha256") != sha(Path(__file__).resolve())
            or sha(PROPOSAL) != PROPOSAL_SHA or verification_source_digest(ROOT) != SOURCE
            or sha(MANIFEST) != "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb"
            or DATABASE.is_symlink()
            or (DATABASE.stat().st_dev, DATABASE.stat().st_ino) != (16777231, 166293865)):
        raise ValueError("review, source, or canonical store changed")
    proposal = json.loads(PROPOSAL.read_text())
    for name, expected in proposal["input_pins"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("proposal input changed")
    record = BoundaryConformance.model_validate(proposal["conformance_record"]["document"])
    digest = content_digest(record)
    if digest != proposal["conformance_record"]["digest"]:
        raise ValueError("conformance record changed")
    documents = proposal["review_documents"]
    if set(documents) != {digest, record.enforcement_definition_digest,
            record.effective_policy_digest, record.reviewed_inventory_digest}:
        raise ValueError("only four exact conformance documents may be added")
    enforcement = documents[record.enforcement_definition_digest]["document"]["definition"]
    for name, expected in enforcement["implementation_sha256"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("enforcement implementation changed")
    canonical = sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True)
    memory = sqlite3.connect(":memory:")
    try:
        canonical.backup(memory)
        for key, item in documents.items():
            if content_digest(item["document"]) != key:
                raise ValueError("document hash differs")
            old_review = memory.execute("SELECT revoked FROM assessment_reviews WHERE digest=?", (key,)).fetchone()
            if old_review is not None and old_review[0]:
                raise ValueError("revoked evidence must not be revived")
            identity = item["document"].get("conformance_id", key)
            memory.execute("INSERT OR IGNORE INTO assessment_records VALUES (?,?,?,?)",
                (item["kind"], identity, key, json.dumps(item["document"])))
            memory.execute("INSERT OR IGNORE INTO assessment_reviews VALUES (?,?,0)",
                (key, datetime.now(UTC).isoformat()))
        simulated = AssessmentRepository(SimpleNamespace(_connection=memory, _lock=threading.RLock()))
        validate(simulated, record, digest)
    finally:
        memory.close()
        canonical.close()
    connection = sqlite3.connect(f"file:{DATABASE}?mode=rw", uri=True)
    repo = AssessmentRepository(SimpleNamespace(_connection=connection, _lock=threading.RLock()))
    try:
        connection.execute("BEGIN IMMEDIATE")
        before = connection.execute("SELECT * FROM assessment_grants ORDER BY id").fetchall()
        repo.current_grant("onboarding")
        for key, item in documents.items():
            old = connection.execute("SELECT revoked FROM assessment_reviews WHERE digest=?", (key,)).fetchone()
            if old is not None and old[0]:
                raise ValueError("review revoked since preflight")
            identity = item["document"].get("conformance_id", key)
            if connection.execute("SELECT 1 FROM assessment_records WHERE kind=? AND (id=? OR digest=?)",
                    (item["kind"], identity, key)).fetchone() is not None:
                raise ValueError("proposed document already exists; inspect instead of reapplying")
            connection.execute("INSERT INTO assessment_records VALUES (?,?,?,?)",
                (item["kind"], identity, key, json.dumps(item["document"])))
            connection.execute("INSERT INTO assessment_reviews VALUES (?,?,0)",
                (key, datetime.now(UTC).isoformat()))
        actual = validate(repo, record, digest)
        after = connection.execute("SELECT * FROM assessment_grants ORDER BY id").fetchall()
        assert before == after and verification_source_digest(ROOT) == SOURCE
        connection.commit()
        result = {"status": "passed", "recorded_at": datetime.now(UTC).isoformat(),
            "source_digest": SOURCE, "review_sha256": args.review_sha256,
            "proposal_sha256": PROPOSAL_SHA, "conformance_digest": digest,
            "worker_digest": actual.worker_digest, "verified_probe_count": len(actual.probe_digests),
            "candidate_access_verified": True, "persisted_documents": list(documents),
            "atomic_commit": True, "router_initialized": False, "schema_initialization": False,
            "grant_counters_unchanged": True, "model_turns": 0,
            "treatment_conformance": True, "paired_conformance": False,
            "qualification": False, "admission": False, "value_trial": False}
        with RESULT.open("x") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


if __name__ == "__main__":
    main()
