"""Register the approved VAREX local preparation records in a private definition ledger."""

import argparse
import json
from contextlib import closing

from audit_varex_archive_lineage import STAGED, STAGED_SHA
from stage_repository_transport import HERE, ROOT, digest, encode, read, write

from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.errors import ConfigurationError
from aeep.store import ReceiptStore
from aeep_toolkit.benchmarks import BenchmarkPack, inspect_pack
from aeep_toolkit.workflow_preparation import TaskRightsReview, require_rights

WORK = ROOT / ".aeep/c13-cohort-runtime-20261124"
REVIEW = HERE / "varex-local-use-review-20261124.json"
REVIEW_SHA = "1fbac221fe8a252acc01caffec738f144fe69940b636f926358e74fc887092a4"
APPROVAL = WORK / "varex-local-use-operator-approval-20261124.json"
OUTPUT = WORK / "varex-local-rights-approved-20261124"
KIND = "toolkit_task_rights"


def load_scope():
    scope = json.loads(read(REVIEW, REVIEW_SHA))
    staging = json.loads(read(STAGED / "staged.json", STAGED_SHA))
    pack = BenchmarkPack.model_validate_json(
        read(STAGED / "benchmark-pack.json", staging["manifest_file_sha256"])
    )
    proposed = scope["proposed_records"]
    raw_records = json.loads(read(ROOT / proposed["path"], proposed["sha256"]))
    if (
        scope["schema_version"] != "aeep.c13.varex-local-rights-proposal.v1"
        or scope["operator_approved"]
        or scope["provider_disclosure_authorized"]
        or scope["trial_dispatch_authorized"]
        or scope["formal_assignments"]
        or scope["pack_sha256"] != content_digest(pack.model_dump(mode="json"))
        or len(raw_records) != scope["as_reviewed_cases"]
        or len(pack.tasks) != len(raw_records)
        or scope["source_revision"] != pack.source.revision
    ):
        raise ValueError("VAREX rights scope or original pack changed")
    records = {}
    for ref, raw in raw_records.items():
        entry = TaskRightsReview.model_validate(raw)
        task = pack.task(entry.task_id)
        source = pack.source_for_task(task.task_id)
        if (
            ref != content_digest(entry)
            or task.task_id in records
            or task.rights_review_ref is not None
            or not entry.local_execution_allowed
            or entry.provider_disclosure_allowed
            or entry.assets != {asset.path: asset.sha256 for asset in task.assets}
            or entry.source_revision != source.revision
            or entry.source_pin_sha256 != content_digest(source.model_dump(mode="json"))
        ):
            raise ValueError("VAREX local-use record differs from its task")
        records[task.task_id] = entry
    if sum(len(record.assets) for record in records.values()) != scope["asset_hashes"]:
        raise ValueError("VAREX asset inventory count changed")
    inspect_pack(pack, STAGED / "pack", tuple(records))
    return pack, records


def register_local_rights(store, pack, records):
    if {task.task_id for task in pack.tasks} != records.keys() or any(
        not row.local_execution_allowed or row.provider_disclosure_allowed
        for row in records.values()
    ):
        raise ValueError("registration requires every case with local-only rights")
    repo = AssessmentRepository(store)
    references = {}
    for case, record in records.items():
        ref = content_digest(record)
        if repo.put(KIND, ref, record) != ref:
            raise ValueError("definition ledger returned a different rights reference")
        repo.review(ref)
        references[case] = ref
    bound = pack.model_copy(
        update={
            "tasks": tuple(
                task.model_copy(update={"rights_review_ref": references[task.task_id]})
                for task in pack.tasks
            )
        }
    )
    for case, ref in references.items():
        if TaskRightsReview.model_validate(repo.get(KIND, ref)) != records[case]:
            raise ValueError("registered local-use definition changed")
        try:
            require_rights(repo, bound, (case,))
        except ConfigurationError as error:
            if (
                str(error)
                != "task asset-use review is missing, revoked, mismatched or insufficient"
            ):
                raise
        else:
            raise ValueError("a local-only record passed the managed plan rights gate")
    with store._lock:
        reviewed = {
            row[0]
            for row in store._connection.execute(
                "SELECT digest FROM assessment_reviews WHERE revoked=0"
            )
        }
        if reviewed != set(references.values()):
            raise ValueError("registration did not retain each exact review")
        for table in ("assessment_grants", "assessment_operations", "receipts"):
            if store._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] != 0:
                raise ValueError(
                    "the private definition ledger has execution authority or activity"
                )
    return bound


def apply(exact):
    if (
        exact != REVIEW_SHA
        or digest(REVIEW.read_bytes()) != REVIEW_SHA
        or not APPROVAL.is_file()
        or APPROVAL.resolve() != APPROVAL
        or json.loads(APPROVAL.read_bytes()) != {"approved": True, "review_sha256": exact}
    ):
        raise ValueError("VAREX local-use registration needs its exact operator decision")
    pack, records = load_scope()
    OUTPUT.mkdir(mode=0o700)
    database = OUTPUT / "definitions.sqlite3"
    with closing(ReceiptStore(database)) as store:
        bound = register_local_rights(store, pack, records)
    pack_file = write(OUTPUT / "local-rights-pack.json", encode(bound.model_dump(mode="json")))
    return write(
        OUTPUT / "result.json",
        encode(
            {
                "review_sha256": REVIEW_SHA,
                "registered_local_rights_records": len(records),
                "pack_file": pack_file,
                "model_turns": 0,
                "provider_disclosure": False,
                "formal_assignments": 0,
            }
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply-approved", required=True)
    args = parser.parse_args()
    print(apply(args.apply_approved))
