"""Bind three retained document grades to their exact ordinary public archives."""

import json
from pathlib import Path

from aeep.assessment.models import AssessmentEnvironment, IntegrationCaseSet, RecipeDefinition, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.store import ReceiptStore
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from reconcile_c13_offline_completion import operations, reference, retained

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / ".aeep/completion-20261116"
PACK = WORK / "independent-document-pack"
GROUP = HERE / "offline-group-9ee3ca0f-result-20261117.json"
CORRECTIONS = HERE / "offline-correction-results-20261117.json"
PRIOR = HERE / "document-grader-evidence-20261117.json"


def load(path):
    return json.loads(path.read_bytes())


def verify_task(pack, task_id, definitions, recipe_path, db, record, source):
    casefile = definitions / "case-set.json"
    environment_path = definitions / "environment.json"
    cases = IntegrationCaseSet.model_validate(load(casefile))
    environment = AssessmentEnvironment.model_validate(load(environment_path))
    recipe = RecipeDefinition.model_validate(load(recipe_path))
    trial, = cases.cases
    generated = task_input(pack, PACK / "pack-assets", task_id)
    if (cases.purpose != "stack_integration_only" or trial.action.input != generated
            or cases.recipe_digest != content_digest(recipe)
            or cases.environment_digest != content_digest(environment)
            or cases.benchmark_pack_digest != content_digest(pack.model_dump(mode="json"))
            or generated["task_archive_sha256"] != source["public_archive_sha256"]):
        raise ValueError("ordinary input, recipe, environment or verification purpose drift")
    ledger = retained(record["ledger"])
    result = retained(record["result"])
    by_id = operations(ledger)
    observations = result.get("observations", result.get("operations"))
    if not result.get("verified", result.get("passed")) or not observations:
        raise ValueError("ordinary contained grade lacks a verified result")
    with ReceiptStore(db, read_only=True) as store:
        repo = AssessmentRepository(store)
        if repo.operation_ledger(ledger["plan_id"]).model_dump(mode="json") != ledger:
            raise ValueError("ordinary ledger no longer matches its sealed result")
        receipts = set()
        for observed in observations:
            identifier = observed["receipt_id"]
            receipt = store.get_receipt(identifier)
            if (receipt is None or identifier in receipts or not receipt.execution_success
                    or receipt.metadata["review_sha256"] != result["review_sha256"]
                    or receipt.action_id not in by_id or not observed["contract_matched"]):
                raise ValueError("role did not retain an accepted canonical receipt")
            if observed.get("role") not in ("build", "import") and not (
                receipt.metadata.get("container_absent") or receipt.metadata.get("guest_container_absent")
            ):
                raise ValueError("contained grader cleanup was never confirmed")
            receipts.add(identifier)
    task = pack.task(task_id)
    if task.rights_review_ref is not None:
        raise ValueError("expected original integration-only pack with pending rights")
    source_review = source.get("source_and_adaptation_record", source.get("local_only_asset_review"))
    retained(source_review)
    return {
        "task": task_id, "source_revision": pack.source.revision,
        "pack_sha256": cases.benchmark_pack_digest, "recipe_sha256": cases.recipe_digest,
        "environment_sha256": cases.environment_digest, "carrier": environment.container_image,
        "ordinary_case_set": reference(casefile), "settled_ledger": record["ledger"], "ordinary_result": record["result"],
        "canonical_receipts_verified": len(receipts), "source_review": source_review,
        "public_archive_sha256": generated["task_archive_sha256"],
        "public_asset_pins": {item.path: item.sha256 for item in task.assets if item.role in {"instruction", "input"}},
        "protected_asset_pins": {item.path: item.sha256 for item in task.assets if item.role not in {"instruction", "input"}},
        "evidence_purpose": cases.purpose, "use_rights_review_registered": False,
        "formal_assignment": None, "provider_dispatch_authorized_by_this_evidence": False,
    }


def main():
    prior = load(PRIOR)
    pack = BenchmarkPack.model_validate(retained(prior["pack"]))
    group = load(GROUP)["results"]
    recovered = load(CORRECTIONS)["formula_extraction"]
    original = load(HERE / "workbook-reference-result.json")
    workbook = WORK / "workbook-ordinary-recipe"
    formula = WORK / "formula-ordinary-recipe"
    economic = WORK / "economic-ordinary-recipe-inline"
    workbook_db = (WORK / "xlsx-recover-preparation"
                   / f"reference-execution-{original['operation_review_sha256'][:12]}" / "receipts.sqlite3")
    scopes = [
        ("xlsx-recover-data", workbook / "execution", workbook / "recipe.json", workbook_db,
         group["workbook-ordinary-grading"]),
        ("latex-formula-extraction", WORK / "formula-local-import-20261117", formula / "recipe.json",
         formula / "execution/receipts.sqlite3", recovered),
        ("econ-detrending-correlation", economic, economic / "recipe.json",
         WORK / "economic-ordinary-execution/receipts.sqlite3", group["economic-ordinary-grading"]),
    ]
    joined = [verify_task(pack, task, definitions, recipe, db, record, prior["tasks"][task])
              for task, definitions, recipe, db, record in scopes]
    print(json.dumps({
        "schema_version": "aeep.c13.document-dispatch-boundary.v1",
        "original_pack": prior["pack"], "upstream_and_adaptation_sources": reference(PRIOR),
        "tasks": joined, "ordinary_runtime_complete": len(joined),
        "actual_new_upstream_tests": 0, "model_turns": 0, "formal_assignments": 0,
        "remaining": [
            "Operator asset-use determination for each task and any exact provider disclosure.",
            "A reviewed formal recipe that supports the retained output types and the unchanged cohort floors.",
        ],
    }, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
