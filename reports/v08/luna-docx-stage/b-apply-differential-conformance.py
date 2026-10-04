"""Store exact paired evidence; the validator projection creates no campaign."""
import argparse
import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from aeep.assessment.boundary import DifferentialConformance, require_differential
from aeep.assessment.models import AssessmentEnvironment, ReviewedMapping, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
PROPOSAL = OUT / "b-control-differential-conformance-proposal.json"
PROPOSAL_SHA = "bf01e27657805e05f856640040ee35ed4bd0aad7b767464b4455ef53cfd7d52e"
REVIEW = OUT / "b-differential-parent-review.json"
RESULT = OUT / "b-differential-apply-result.json"
DB = ROOT / ".aeep/live-review-v3/aeep.sqlite3"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MappingProjection:
    def __init__(self, repository, mapping):
        self.repository, self.mapping = repository, mapping

    def __getattr__(self, name):
        return getattr(self.repository, name)

    def get(self, kind, key):
        if (kind, key) == ("mapping", content_digest(self.mapping)):
            return self.mapping.model_dump(mode="json")
        return self.repository.get(kind, key)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("review_sha256")
    args = parser.parse_args()
    if RESULT.exists() or sha(REVIEW) != args.review_sha256:
        raise ValueError("fresh exact review required")
    review = json.loads(REVIEW.read_text())
    if (review.get("execution_authorized") is not True
            or review.get("runner_sha256") != sha(Path(__file__).resolve())
            or review.get("proposal_sha256") != PROPOSAL_SHA or sha(PROPOSAL) != PROPOSAL_SHA
            or verification_source_digest(ROOT) != SOURCE
            or sha(ROOT / ".aeep/live-review-v3/aeep.json") != "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb"
            or DB.is_symlink() or (DB.stat().st_dev, DB.stat().st_ino) != (16777231, 166293865)):
        raise ValueError("source, store or exact review changed")
    proposal = json.loads(PROPOSAL.read_text())
    for path, expected in proposal["input_pins"].items():
        if sha(ROOT / path) != expected:
            raise ValueError("proposal input changed")
    record = DifferentialConformance.model_validate(proposal["differential_conformance"]["document"])
    digest = content_digest(record)
    if digest != proposal["differential_conformance"]["digest"] or digest != review.get("digest"):
        raise ValueError("exact differential changed")
    projection = proposal["validation_projection"]
    mapping = ReviewedMapping.model_validate(projection["mapping_projection"]["document"])
    mapping_digest = content_digest(mapping)
    environment = AssessmentEnvironment.model_validate(projection["environment_projection"])
    fields = projection["plan_projection"]["fields_consumed"]
    if (mapping_digest != projection["mapping_projection"]["digest"]
            or fields["mapping_digest"] != mapping_digest
            or fields["candidate_id"] != mapping.candidate.id
            or fields["baseline_id"] != mapping.baseline.id
            or fields["comparison.experiment.environment"] != record.definition.model_dump(mode="json")
            or fields["comparison.experiment.stage"] != "qualification"):
        raise ValueError("validator projection differs")
    plan_view = SimpleNamespace(candidate_id=mapping.candidate.id, baseline_id=mapping.baseline.id,
        mapping_digest=mapping_digest,
        comparison=SimpleNamespace(experiment=SimpleNamespace(environment=record.definition, stage="qualification")))
    conn = sqlite3.connect(f"file:{DB}?mode=rw", uri=True)
    repo = AssessmentRepository(SimpleNamespace(_connection=conn, _lock=threading.RLock()))
    try:
        conn.execute("BEGIN IMMEDIATE")
        before = conn.execute("SELECT * FROM assessment_grants ORDER BY id").fetchall()
        repo.current_grant("onboarding")
        pair = repo.get("composed_pair_definition", "5124b0de3c686a20290443f0580137add30f07070311ab3786a044bed47d0202")
        if (content_digest(mapping.candidate) != content_digest(pair["treatment"])
                or content_digest(mapping.baseline) != content_digest(pair["control"])
                or record.definition.model_dump(mode="json") != pair["differential"]):
            raise ValueError("projection differs from canonical reviewed pair")
        if conn.execute("SELECT 1 FROM assessment_records WHERE kind='differential_conformance' AND (id=? OR digest=?)", (digest, digest)).fetchone():
            raise ValueError("differential exists; inspect instead of replaying")
        conn.execute("INSERT INTO assessment_records VALUES (?,?,?,?)", ("differential_conformance", digest, digest, record.model_dump_json()))
        conn.execute("INSERT INTO assessment_reviews VALUES (?,?,0)", (digest, datetime.now(UTC).isoformat()))
        # Only the explicitly labelled mapping projection is ephemeral. All
        # enforcement, probe, scope, receipt and review lookups remain canonical.
        view = MappingProjection(repo, mapping)
        require_differential(view, environment, plan_view)
        if (before != conn.execute("SELECT * FROM assessment_grants ORDER BY id").fetchall()
                or verification_source_digest(ROOT) != SOURCE):
            raise ValueError("grant or source changed")
        conn.commit()
        result = {"status": "passed", "recorded_at": datetime.now(UTC).isoformat(), "source_digest": SOURCE,
                  "digest": digest, "review_sha256": args.review_sha256,
                  "control_conformance_digest": record.control_conformance_digest,
                  "treatment_conformance_digest": record.treatment_conformance_digest,
                  "require_differential": "passed_with_explicit_validator_projection",
                  "mapping_plan_environment_persisted": False, "campaign_authorized": False,
                  "qualification": False, "value_trial": False, "grant_counters_unchanged": True, "model_turns": 0}
        with RESULT.open("x") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
    finally:
        if conn.in_transaction:
            conn.rollback()
        conn.close()


if __name__ == "__main__":
    main()
