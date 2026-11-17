"""Reconcile actual ExtractBench scores and their existing recipe response contract."""

import hashlib
import json
from pathlib import Path

from aeep.assessment.extensions import grader_results
from aeep.assessment.models import RecipeDefinition, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.store import ReceiptStore
from aeep_toolkit.workflow_evidence import _settled
from audit_extractbench_audent import TASK
from extractbench_recipe_guest import native_reply

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PRIVATE = ROOT / ".aeep/completion-20261116/extractbench-readonly-runtime-20261117"
REVIEW = "51ae1f19fc49eea70d7c429fa054f3701d31278597fcd778ee891b5242f90396"


def bound(path):
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def audit():
    if bound(PRIVATE / "operation-review.json")["sha256"] != REVIEW:
        raise ValueError("calibrated native review differs")
    raw = json.loads((PRIVATE / "execution/result.json").read_bytes())
    with ReceiptStore(PRIVATE / "execution/receipts.sqlite3", read_only=True) as store:
        repo = AssessmentRepository(store)
        operation, = repo.operation_ledger("c13-extractbench-readonly-native-20261117").operations
        receipt = store.get_receipt(raw["receipt_id"])
        if (
            _settled(repo, operation.operation_id) != operation
            or receipt is None or not receipt.execution_success
            or receipt.action_id != operation.operation_id
            or receipt.metadata.get("container_absent") is not True
            or receipt.metadata.get("review_sha256") != REVIEW
            or raw["calibration_verified"] is not True
        ):
            raise ValueError("calibration did not settle with a matching successful receipt")
        observation = raw["observation"]
        if (
            not all(observation.get(k) is True for k in
                    ("native_probe_passed", "dependencies_readonly", "scratch_noexec"))
            or observation["verified_files"] != 7613 or observation["installed_wheels"] != 70
        ):
            raise ValueError("native origin or mount probe is incomplete")
        recipe_file = ROOT / ".aeep/completion-20261116/extractbench-cfpb-workflow-bound/recipe.json"
        recipe = RecipeDefinition.model_validate_json(recipe_file.read_bytes())
        roles = []
        for name, observed in observation["grader"]["observations"].items():
            if observed["status"] == "infrastructure_error":
                try:
                    native_reply(observed)
                except ValueError:
                    transferred = None
                else:
                    raise ValueError("an infrastructure error became a task score")
            else:
                wire = native_reply(observed)
                score, = grader_results(wire, recipe.extension, 1)
                if score.quality_score != observed["value_f1"] or score.valid is not bool(observed["perfect"]):
                    raise ValueError("native response normalization changed the observed score")
                transferred = score.model_dump(mode="json")
            roles.append({
                "role": name, "upstream_status": observed["status"],
                "upstream_value_f1": observed["value_f1"], "upstream_perfect": observed["perfect"],
                "counts": observed.get("counts"), "existing_recipe_reply": transferred,
                "observation_ref": content_digest(observed),
            })
        if len(roles) != 7 or {row["role"] for row in roles} != {
            "reference", "changed_value", "missing_row", "repeated_row", "malformed", "no_output", "no_reference"
        }:
            raise ValueError("protected calibration roles differ")
        return {
            "schema_version": "aeep.c13.extractbench-native-calibration-result.v1",
            "review": bound(PRIVATE / "operation-review.json"),
            "execution_source": json.loads((PRIVATE / "operation-review.json").read_bytes())["source"],
            "response_reader_workspace_source": verification_source_digest(ROOT),
            "original_operator_approval": bound(PRIVATE / "operator-approval-ae50eaa7.json"),
            "pre_dispatch_test_refinement": bound(PRIVATE / "pre-dispatch-refinement.json"),
            "execution_result": bound(PRIVATE / "execution/result.json"),
            "ledger": bound(PRIVATE / "execution/ledger.json"),
            "receipt_id": receipt.receipt_id, "receipt_ref": content_digest(receipt),
            "measurement_ref": content_digest(operation),
            "reserved_seconds": operation.reserved.max_elapsed_seconds,
            "settled_seconds": operation.elapsed_seconds, "settled_operations": 1,
            "outstanding_reservations": 0, "container_absent": True, "task_id": TASK,
            "roles": roles, "native_import_origins": observation["native_origins"],
            "dependencies_readonly_observed": True, "scratch_noexec_observed": True,
            "dependency_files_verified": 7613, "locked_distributions_verified": 70,
            "existing_recipe_reply_contract": recipe.extension.schema_version,
            "recipe_contract_source": bound(recipe_file),
            "recipe_contract_transfer_scope": "Normalize retained real observations from this one Audent calibration task using the existing v7 response handler. CFPB native task execution remains separate.",
            "prepared_dependency_bytes": 329240739, "preparation_elapsed_seconds": None,
            "model_turns": 0, "cash_authority_usd": 0, "independent_tasks_observed": 1,
            "conditions": 7, "formal_cases_adopted": 0, "waza_excluded": True,
            "comparisons_paused": True,
        }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True, allow_nan=False))
