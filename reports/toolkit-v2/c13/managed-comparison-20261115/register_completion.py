"""Register the operator-approved stack evidence without executing a benchmark."""

import argparse
import importlib.util
import json
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.errors import ConfigurationError
from aeep.store import ReceiptStore
from aeep_toolkit.stack_readiness import StackCompletion, require_stack_complete
from aeep_toolkit.stack_receipts import StackReceiptEvidence, verify_receipt_evidence
from aeep_toolkit.workflow_evidence import WorkflowEvidence, verify_workflow

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
COMPLETION = "81e3ebd64ad53518026bf7e8b1374cc564fbc4f768c0e255646fb38bbc117031"
SPEC = importlib.util.spec_from_file_location(
    "receipt_registration",
    HERE.parent / "canonical-stack-receipts-20261114/register-receipt-records.py",
)
assert SPEC and SPEC.loader
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)
driver.RETENTION_KINDS += ("toolkit_stack_completion",)


def register(bundle, database):
    source = verification_source_digest(ROOT)
    summary = driver.read(bundle / "verification-summary.json")
    completion_file = bundle / "stack-completion-v2.json"
    completion = StackCompletion.model_validate_json(completion_file.read_bytes())
    if (
        content_digest(completion) != COMPLETION
        or completion.implementation_source != source
        or summary["stack_completion_ref"] != COMPLETION
        or summary["verified_checks"] != 37
        or "waza" in completion.components
    ):
        raise ConfigurationError("approved completion or implementation source differs")
    with ReceiptStore(bundle / "verification-copy.sqlite3", read_only=True) as copied:
        require_stack_complete(AssessmentRepository(copied), COMPLETION, source_digest=source)

    records = {}
    with ReceiptStore(database, read_only=True) as operative:
        repo = AssessmentRepository(operative)
        connection = operative._connection
        reviews = dict(connection.execute("SELECT digest, revoked FROM assessment_reviews"))
        references = {*completion.components.values(), COMPLETION}
        if any(reviews.get(ref) for ref in references):
            raise ConfigurationError("an exact prior review has been revoked")
        new_refs = references - {
            row[0] for row in connection.execute("SELECT digest FROM assessment_records")
        }
        for component, ref in completion.components.items():
            file = bundle / f"{component}.json"
            if component.startswith("workflow-"):
                evidence = WorkflowEvidence.model_validate_json(file.read_bytes())
                verify_workflow(repo, evidence, component=component, source=source)
            else:
                evidence = StackReceiptEvidence.model_validate_json(file.read_bytes())
                verify_receipt_evidence(repo, evidence, component=component, source=source)
            if content_digest(evidence) != ref:
                raise ConfigurationError(f"reviewed evidence differs for {component}")
            records[component] = file

    before = driver.snapshot(database)
    for component, file in records.items():
        result = driver.cli(
            "stack-verify", "record", "--store", database, "--component", component, "--file", file
        )
        assert completion.components[component] in (
            result.get("workflow_evidence_ref"),
            result.get("integration_evidence_ref"),
        )
    with ReceiptStore(database) as store:
        repo = AssessmentRepository(store)
        for ref in completion.components.values():
            if ref not in reviews:
                repo.review(ref)
    result = driver.cli("stack-verify", "assemble", "--store", database, "--file", completion_file)
    assert result == {"stack_completion_ref": COMPLETION, "comparisons_authorized": False}
    with ReceiptStore(database) as store:
        repo = AssessmentRepository(store)
        if COMPLETION not in reviews:
            repo.review(COMPLETION)
    with ReceiptStore(database, read_only=True) as store:
        repo = AssessmentRepository(store)
        require_stack_complete(repo, COMPLETION, source_digest=source)
        try:
            require_stack_complete(repo, COMPLETION, source_digest=source, waza_selected=True)
        except ConfigurationError as error:
            assert str(error) == "selected Waza requires both Waza readiness checks"
        else:
            raise AssertionError("a Waza workflow passed without Waza evidence")
    status = driver.cli("stack-status", "--store", database)
    assert driver.count_checks(status) == 37 and status["stack_completion_ref"] == COMPLETION
    assert driver.snapshot(database, new_refs) == before
    return {
        "implementation_source": source,
        "stack_completion_ref": COMPLETION,
        "verified_checks": 37,
        "required_checks": 37,
        "total_checks_including_optional_waza": 39,
        "reviewed_components": completion.components,
        "operational_ledger": str(database),
        "prior_ledger_rows_preserved": True,
        "waza_selection_blocked": True,
        "comparison_dispatch": status["comparison_dispatch"],
        "comparisons_authorized": False,
        "model_runs": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    print(json.dumps(register(args.bundle.resolve(), args.database.resolve()), indent=2))
