"""Atomically apply one exactly reviewed, source-pinned C conformance proposal."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from aeep.assessment.boundary import (
    BoundaryConformance,
    DifferentialConformance,
    require_candidate_access,
    require_conformance,
    require_differential,
)
from aeep.assessment.models import (
    AssessmentEnvironment,
    ReviewedMapping,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import ComposedPairDefinition
from aeep.hosts.workers import binding_from_config

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE = "50de999eb8fcd15ffef056c6b67db9f1dc0e491a3b32a3f236bbd81cd52651f7"
PROFILE = OUT / "c-current-profile-v1.json"
PROFILE_SHA256 = "8d3f49299452a7b4ea1e8cbc46abcd6ef8b81989ca24e131b35fbc8ed6bcd449"
MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
MANIFEST_SHA256 = "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb"
DATABASE = ROOT / ".aeep/live-review-v3/aeep.sqlite3"
DATABASE_DEVICE = 16777231
DATABASE_INODE = 166293865
PROPOSAL = OUT / "c-boundary-conformance-proposal-v1.json"
REVIEW = OUT / "c-boundary-conformance-parent-review-v1.json"
RESULT = OUT / "c-boundary-conformance-apply-result-v1.json"
ROLE_IDS = {"control": "b.luna.discovery", "treatment": "b.luna.aeep"}


def sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"expected regular non-symlink input: {path.name}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"invalid JSON object: {path.name}")
    return value


class MappingProjection:
    """Expose only the exact profile mapping projection to the differential verifier."""

    def __init__(self, repository: AssessmentRepository, mapping: ReviewedMapping):
        self.repository, self.mapping = repository, mapping

    def __getattr__(self, name: str) -> Any:
        return getattr(self.repository, name)

    def get(self, kind: str, key: str) -> Any:
        if kind == "mapping" and key == content_digest(self.mapping):
            return self.mapping.model_dump(mode="json")
        return self.repository.get(kind, key)


def require_canonical_pins() -> None:
    require(verification_source_digest(ROOT) == SOURCE, "frozen source digest changed")
    require(sha(PROFILE) == PROFILE_SHA256, "C profile bytes changed")
    require(sha(MANIFEST) == MANIFEST_SHA256, "canonical manifest bytes changed")
    require(not DATABASE.is_symlink() and DATABASE.is_file(), "canonical database target changed")
    stat = DATABASE.stat()
    require(
        (stat.st_dev, stat.st_ino) == (DATABASE_DEVICE, DATABASE_INODE),
        "canonical database identity changed",
    )


def insert_documents(
    connection: sqlite3.Connection,
    documents: dict[str, Any],
    seen_digests: set[str],
    reused_inventory_digests: set[str],
) -> tuple[int, int, int]:
    inserted_count = 0
    reused_inventory_count = 0
    shared_reference_count = 0
    for digest, item in documents.items():
        document = item["document"]
        require(content_digest(document) == digest, "proposal document digest differs")
        kind = item["kind"]
        identity = document.get("conformance_id", digest)
        rows = connection.execute(
            "SELECT kind,id,digest,payload_json FROM assessment_records "
            "WHERE digest=? OR (kind=? AND id=?)",
            (digest, kind, identity),
        ).fetchall()
        review = connection.execute(
            "SELECT revoked FROM assessment_reviews WHERE digest=?", (digest,)
        ).fetchone()
        if rows:
            exact_row = (
                len(rows) == 1
                and rows[0][0] == kind
                and rows[0][1] == identity
                and rows[0][2] == digest
                and json.loads(rows[0][3]) == document
            )
            active_review = review is not None and review[0] == 0
            if digest in seen_digests:
                require(
                    exact_row and active_review,
                    "shared proposal document changed during apply",
                )
                shared_reference_count += 1
                continue
            require(
                kind == "reviewed_inventory" and exact_row and active_review,
                "only an exact active-reviewed inventory may be reused",
            )
            seen_digests.add(digest)
            if digest not in reused_inventory_digests:
                reused_inventory_digests.add(digest)
                reused_inventory_count += 1
            continue
        require(review is None, "review exists without its exact active document")
        connection.execute(
            "INSERT INTO assessment_records VALUES (?,?,?,?)",
            (kind, identity, digest, json.dumps(document, sort_keys=True)),
        )
        connection.execute(
            "INSERT INTO assessment_reviews VALUES (?,?,0)",
            (digest, datetime.now(UTC).isoformat()),
        )
        seen_digests.add(digest)
        inserted_count += 1
    return inserted_count, reused_inventory_count, shared_reference_count


def differential_documents(proposal: dict[str, Any]) -> dict[str, Any]:
    item = {
        "kind": "differential_conformance",
        "document": proposal["differential_conformance"]["document"],
    }
    digest = proposal["differential_conformance"]["digest"]
    require(content_digest(item["document"]) == digest, "C differential document digest differs")
    return {digest: item}


def validate_role(
    repository: AssessmentRepository,
    profile: dict[str, Any],
    role: str,
    role_proposal: dict[str, Any],
    differential,
) -> BoundaryConformance:
    record = BoundaryConformance.model_validate(role_proposal["conformance_record"]["document"])
    digest = content_digest(record)
    require(
        digest == role_proposal["conformance_record"]["digest"], f"C {role} record digest differs"
    )
    spec = ComposedPairDefinition.model_validate(profile["component"]["composed"])
    selected = getattr(spec, role)
    config = selected.managed_host_config()
    worker = binding_from_config(config.managed_worker)
    require(
        worker is not None and selected.id == ROLE_IDS[role], f"C {role} profile identity differs"
    )
    require(
        record.source_digest == SOURCE
        and record.worker_digest == worker.digest()
        and record.adapter == config.adapter_id
        and record.callback_binding_digest == spec.callback_bindings[worker.digest()]
        and record.native_backend_digest == spec.native_backends[worker.digest()]
        and record.composed_definition_digest == content_digest(spec)
        and record.effective_inventory
        == (
            differential.control_inventory
            if role == "control"
            else differential.treatment_inventory
        ),
        f"C {role} conformance does not match the exact composed profile",
    )
    docs = role_proposal.get("review_documents")
    expected = {
        digest,
        record.enforcement_definition_digest,
        record.effective_policy_digest,
        record.reviewed_inventory_digest,
    }
    require(
        isinstance(docs, dict) and set(docs) == expected,
        f"C {role} must add exactly four documents",
    )
    for key, item in docs.items():
        require(
            content_digest(item.get("document")) == key, f"C {role} review document digest differs"
        )
    enforcement = docs[record.enforcement_definition_digest]["document"]["definition"]
    for relative, expected_sha in enforcement["implementation_sha256"].items():
        require(
            sha(ROOT / relative) == expected_sha, f"C {role} enforcement implementation changed"
        )
    actual = require_conformance(
        repository,
        digest,
        source_digest=SOURCE,
        worker_digest=record.worker_digest,
        identity_digest=record.identity_digest,
    )
    require_candidate_access(repository, actual, differential, available=role == "treatment")
    return actual


def validate_all(
    repository: AssessmentRepository, proposal: dict[str, Any], profile: dict[str, Any]
) -> tuple[BoundaryConformance, BoundaryConformance, DifferentialConformance]:
    require(
        proposal.get("schema_version") == "assessment.c-boundary-conformance-proposal.v1"
        and proposal.get("status") == "inert_proposal_unreviewed"
        and proposal.get("source_digest") == SOURCE
        and proposal.get("profile_sha256") == PROFILE_SHA256
        and proposal.get("simulation_preflight", {}).get("status") == "passed"
        and proposal.get("simulation_preflight", {}).get("canonical_database_writes") == 0,
        "proposal is not the exact inert C proposal shape",
    )
    composed = ComposedPairDefinition.model_validate(profile["component"]["composed"])
    from aeep.assessment.models import DifferentialEnvironment

    differential = DifferentialEnvironment.model_validate(profile["differential"])
    composed_digest = content_digest(composed)
    require(
        content_digest(repository.get("composed_pair_definition", composed_digest))
        == composed_digest,
        "profile composed definition is not the exact canonical definition",
    )
    control = validate_role(repository, profile, "control", proposal["control"], differential)
    treatment = validate_role(repository, profile, "treatment", proposal["treatment"], differential)
    differential_record = DifferentialConformance.model_validate(
        proposal["differential_conformance"]["document"]
    )
    differential_digest = content_digest(differential_record)
    require(
        differential_digest == proposal["differential_conformance"]["digest"]
        and differential_record.control_conformance_digest == content_digest(control)
        and differential_record.treatment_conformance_digest == content_digest(treatment)
        and differential_record.definition == differential,
        "C differential does not bind the exact two role conformance records",
    )
    mapping = ReviewedMapping(candidate=composed.treatment, baseline=composed.control)
    environment = AssessmentEnvironment(
        environment_id="c-conformance-apply-validator-projection",
        kind="trusted_local",
        identity={"purpose": "exact C differential validation projection"},
        conformance_digests={
            composed.control.id: content_digest(control),
            composed.treatment.id: content_digest(treatment),
        },
        differential_conformance_digest=differential_digest,
    )
    plan = SimpleNamespace(
        candidate_id=composed.treatment.id,
        baseline_id=composed.control.id,
        mapping_digest=content_digest(mapping),
        comparison=SimpleNamespace(
            experiment=SimpleNamespace(environment=differential, stage="qualification")
        ),
    )
    require_differential(MappingProjection(repository, mapping), environment, plan)
    return control, treatment, differential_record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_sha256", help="exact SHA-256 of the one-use parent review")
    args = parser.parse_args()
    require(
        not RESULT.exists() and not RESULT.is_symlink(), "apply result exists; preserve and inspect"
    )
    require(sha(REVIEW) == args.review_sha256, "exact fresh parent review required")
    review = read_json(REVIEW)
    require_canonical_pins()
    require(
        review.get("execution_authorized") is True
        and review.get("source_digest") == SOURCE
        and review.get("proposal_sha256") == sha(PROPOSAL)
        and review.get("runner_sha256") == sha(Path(__file__).resolve())
        and review.get("manifest_sha256") == MANIFEST_SHA256
        and review.get("database_device") == DATABASE_DEVICE
        and review.get("database_inode") == DATABASE_INODE,
        "parent review does not authorize the exact proposal/helper/source/store pins",
    )
    proposal = read_json(PROPOSAL)
    require(proposal.get("source_digest") == SOURCE, "proposal source differs")
    for relative, expected_sha in proposal["input_pins"].items():
        require(
            sha(ROOT / relative) == expected_sha, f"proposal input changed: {Path(relative).name}"
        )
    profile = read_json(PROFILE)
    require(profile.get("source_digest") == SOURCE, "profile source differs")

    canonical = sqlite3.connect(f"file:{DATABASE.as_posix()}?mode=ro", uri=True)
    memory = sqlite3.connect(":memory:")
    simulated_seen: set[str] = set()
    simulated_reused: set[str] = set()
    try:
        canonical.backup(memory)
        simulated = AssessmentRepository(
            SimpleNamespace(_connection=memory, _lock=threading.RLock())
        )
        for role in ("control", "treatment"):
            insert_documents(
                memory,
                proposal[role]["review_documents"],
                simulated_seen,
                simulated_reused,
            )
        insert_documents(
            memory,
            differential_documents(proposal),
            simulated_seen,
            simulated_reused,
        )
        validate_all(simulated, proposal, profile)
    finally:
        memory.close()
        canonical.close()

    require_canonical_pins()
    connection = sqlite3.connect(f"file:{DATABASE.as_posix()}?mode=rw", uri=True)
    repository = AssessmentRepository(
        SimpleNamespace(_connection=connection, _lock=threading.RLock())
    )
    seen_digests: set[str] = set()
    reused_inventory_digests: set[str] = set()
    inserted_count = 0
    reused_inventory_count = 0
    shared_reference_count = 0
    try:
        connection.execute("BEGIN IMMEDIATE")
        grant_before = connection.execute("SELECT * FROM assessment_grants ORDER BY id").fetchall()
        repository.current_grant("onboarding")
        for role in ("control", "treatment"):
            inserted, reused, shared = insert_documents(
                connection,
                proposal[role]["review_documents"],
                seen_digests,
                reused_inventory_digests,
            )
            inserted_count += inserted
            reused_inventory_count += reused
            shared_reference_count += shared
        inserted, reused, shared = insert_documents(
            connection,
            differential_documents(proposal),
            seen_digests,
            reused_inventory_digests,
        )
        inserted_count += inserted
        reused_inventory_count += reused
        shared_reference_count += shared
        control, treatment, differential = validate_all(repository, proposal, profile)
        grant_after = connection.execute("SELECT * FROM assessment_grants ORDER BY id").fetchall()
        require(grant_before == grant_after, "assessment grant counters changed")
        require_canonical_pins()
        connection.commit()
        document_references = sum(
            len(proposal[role]["review_documents"]) for role in ("control", "treatment")
        ) + len(differential_documents(proposal))
        output = {
            "status": "passed",
            "recorded_at": datetime.now(UTC).isoformat(),
            "source_digest": SOURCE,
            "proposal_sha256": sha(PROPOSAL),
            "review_sha256": args.review_sha256,
            "runner_sha256": sha(Path(__file__).resolve()),
            "control_conformance_digest": content_digest(control),
            "treatment_conformance_digest": content_digest(treatment),
            "differential_conformance_digest": content_digest(differential),
            "document_references": document_references,
            "unique_proposal_documents": len(seen_digests),
            "documents_inserted": inserted_count,
            "existing_inventory_documents_reused": reused_inventory_count,
            "shared_proposal_document_references": shared_reference_count,
            "atomic_commit": True,
            "grant_counters_unchanged": True,
            "model_turns": 0,
            "qualification": False,
            "admission": False,
            "value_trial": False,
        }
        with RESULT.open("x", encoding="utf-8") as stream:
            json.dump(output, stream, indent=2, sort_keys=True)
            stream.write("\n")
        print(json.dumps(output, sort_keys=True))
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


if __name__ == "__main__":
    main()
