"""Apply one reviewed metadata successor without altering earlier evidence."""
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

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
PROPOSAL = OUT / "b-treatment-advertisement-correction-proposal.json"
REVIEW = OUT / "b-treatment-advertisement-correction-review.json"
RESULT = OUT / "b-treatment-advertisement-correction-result.json"
DB = ROOT / ".aeep/live-review-v3/aeep.sqlite3"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("review_sha256")
    args = parser.parse_args()
    if RESULT.exists() or sha(REVIEW) != args.review_sha256:
        raise ValueError("fresh exact review required")
    review = json.loads(REVIEW.read_text())
    if (review.get("execution_authorized") is not True
            or review.get("runner_sha256") != sha(Path(__file__).resolve())
            or review.get("proposal_sha256") != sha(PROPOSAL)
            or verification_source_digest(ROOT) != SOURCE
            or sha(ROOT / ".aeep/live-review-v3/aeep.json") != "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb"
            or DB.is_symlink() or (DB.stat().st_dev, DB.stat().st_ino) != (16777231, 166293865)):
        raise ValueError("source, store or exact review changed")
    proposal = json.loads(PROPOSAL.read_text())
    record = BoundaryConformance.model_validate(proposal["document"])
    digest = content_digest(record)
    annotation = {"conformance_digest": digest, "supersedes_digest": proposal["old_digest"],
                  "advertisement_names_status": "unknown", "empty_list_proves_absence": False,
                  "reason": proposal["reason"]}
    annotation_digest = content_digest(annotation)
    if (review.get("new_digest") != digest or review.get("old_digest") != proposal["old_digest"]
            or review.get("annotation_digest") != annotation_digest):
        raise ValueError("exact successor differs")
    conn = sqlite3.connect(f"file:{DB}?mode=rw", uri=True)
    repo = AssessmentRepository(SimpleNamespace(_connection=conn, _lock=threading.RLock()))
    try:
        conn.execute("BEGIN IMMEDIATE")
        before = conn.execute("SELECT * FROM assessment_grants ORDER BY id").fetchall()
        repo.current_grant("onboarding")
        old = repo.get("boundary_conformance", proposal["old_digest"])
        expected = dict(old, conformance_id=record.conformance_id, advertised_tools=[])
        if content_digest(old) != proposal["old_digest"] or record.model_dump(mode="json") != expected:
            raise ValueError("correction changes fields beyond the reviewed metadata")
        if conn.execute("SELECT 1 FROM assessment_records WHERE kind='boundary_conformance' AND (id=? OR digest=?)", (record.conformance_id, digest)).fetchone():
            raise ValueError("successor exists; inspect instead of replaying")
        conn.execute("INSERT INTO assessment_records VALUES (?,?,?,?)", ("boundary_conformance", record.conformance_id, digest, record.model_dump_json()))
        conn.execute("INSERT INTO assessment_reviews VALUES (?,?,0)", (digest, datetime.now(UTC).isoformat()))
        conn.execute("INSERT INTO assessment_records VALUES (?,?,?,?)", ("conformance_annotation", digest, annotation_digest, json.dumps(annotation)))
        conn.execute("INSERT INTO assessment_reviews VALUES (?,?,0)", (annotation_digest, datetime.now(UTC).isoformat()))
        actual = require_conformance(repo, digest, source_digest=SOURCE, worker_digest=record.worker_digest, identity_digest=record.identity_digest)
        pair = repo.get("composed_pair_definition", record.composed_definition_digest)
        require_candidate_access(repo, actual, DifferentialEnvironment.model_validate(pair["differential"]), available=True)
        if (before != conn.execute("SELECT * FROM assessment_grants ORDER BY id").fetchall()
                or verification_source_digest(ROOT) != SOURCE):
            raise ValueError("grant or source changed")
        conn.commit()
        result = {"status": "passed", "recorded_at": datetime.now(UTC).isoformat(), "source_digest": SOURCE,
                  "old_digest": proposal["old_digest"], "new_digest": digest, "review_sha256": args.review_sha256,
                  "canonical_annotation_digest": annotation_digest,
                  "original_preserved": True, "verified_probe_count": len(actual.probe_digests),
                  "candidate_access_verified": True, "grant_counters_unchanged": True,
                  "model_turns": 0, "advertisement_names": "unavailable; empty list is not proof of absence"}
        with RESULT.open("x") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
    finally:
        if conn.in_transaction:
            conn.rollback()
        conn.close()


if __name__ == "__main__":
    main()
