"""Revalidate all current component records and add the verified ASE boundary."""

import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path

import aeep_toolkit
from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.cli import app as aeep_app
from aeep.store import ReceiptStore
from aeep_toolkit.stack_readiness import require_integration, source_revisions
from aeep_toolkit.stack_receipts import StackReceiptEvidence

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "canonical-stack-receipts-20261114"
SCANNER = HERE.parent / "canonical-stack-boundaries-20261114"
SCHEDULED = "agent-skill-eval"
SPEC = importlib.util.spec_from_file_location(
    "readiness_registration", PREVIOUS / "register-receipt-records.py"
)
assert SPEC and SPEC.loader
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)


def prepare(database, output, source):
    files = sorted((PREVIOUS / "records").glob("*-record.json"))
    files += [SCANNER / "skill-scanner-record.json", HERE / f"{SCHEDULED}-record.json"]
    revisions = source_revisions(source)
    prepared = {}
    for file in files:
        record = DRIVER.read(file)
        component = record["component"]
        if component.startswith("workflow-"):
            request = DRIVER.WORKFLOW_REVIEWS / file.name.replace("-record.json", "-request.json")
            result = DRIVER.cli("workflow", "evidence", "--store", database, "--file", request)
            record = result["record"]
            assert all(record["observations"]["checks"].values())
        else:
            record["implementation_source"] = source
            record["source_revision"] = revisions[component]
            if component != SCHEDULED:
                record["compatibility_basis"] += (
                    " Current source adds retained ASE launcher proof validation only. "
                    "This component's original execution path and bindings are unchanged."
                )
            record = StackReceiptEvidence.model_validate(record).model_dump(mode="json")
        prepared[component] = (
            DRIVER.save(output / f"{component}-record.json", record),
            content_digest(record),
        )
    assert len(prepared) == 18
    return prepared


def controls(database, output, scheduled, manifest):
    file, ref = scheduled
    original = DRIVER.read(file)
    no_proof = DRIVER.read(file)
    del no_proof["proof"]["native_boundary"]
    swapped = DRIVER.read(file)
    old = DRIVER.read(SCANNER / "boundary-result.json")["agent_skill_eval"]
    swapped["proof"]["native_boundary"]["receipt"] = {
        key: old[key] for key in ("operation_id", "receipt_ref")
    }
    corrupt = DRIVER.read(file)
    corrupt["proof"]["native_boundary"]["receipt"]["receipt_ref"] = "0" * 64
    faults = {}
    for key, case in (
        ("missing_boundary", no_proof),
        ("swapped_failed_operation", swapped),
        ("unbound_receipt", corrupt),
    ):
        faults[key] = DRIVER.cli(
            "stack-verify",
            "record",
            "--store",
            database,
            "--component",
            SCHEDULED,
            "--file",
            DRIVER.save(output / f"{key}.json", case),
            blocked=True,
        )
    with contextlib.redirect_stdout(io.StringIO()):
        aeep_app(
            ["assess", "--manifest", str(manifest), "review", ref, "--revoke"],
            standalone_mode=False,
        )
    current = DRIVER.cli("stack-status", "--store", database)
    assert DRIVER.count_checks(current) == 35
    assert {
        row["component"] for row in current["components"] if row["functional_status"] == "BLOCKED"
    } == {
        SCHEDULED,
        "waza",
    }
    faults["revoked_evidence_review"] = "The two ASE checks became blocked in the copied ledger."
    assert original["proof"]["native_boundary"]
    return faults


def run(original, output, review_file):
    output.mkdir(mode=0o700)
    database = original
    if review_file is None:
        database = output / "canonical-copy.sqlite3"
        with ReceiptStore(original, read_only=True) as source, ReceiptStore(database) as copy:
            source._connection.backup(copy._connection)
    source = verification_source_digest(Path(aeep_toolkit.__file__).resolve().parents[2])
    before = DRIVER.snapshot(database)
    prepared = prepare(database, output, source)
    refs = {component: ref for component, (_, ref) in prepared.items()}
    if review_file:
        copied = DRIVER.read(review_file)
        if (
            copied["mode"] != "copied"
            or copied["implementation_source"] != source
            or copied["records"] != refs
            or copied["verified_checks"] != 37
            or not copied["negative_controls"]
        ):
            raise RuntimeError("exact copied-ledger validation differs")
    with ReceiptStore(database, read_only=True) as store:
        connection = store._connection
        reviews = dict(connection.execute("SELECT digest, revoked FROM assessment_reviews"))
        present = {row[0] for row in connection.execute("SELECT digest FROM assessment_records")}
    if any(reviews.get(ref) for ref in refs.values()):
        raise RuntimeError("an exact canonical evidence review was revoked")
    for component, (file, ref) in prepared.items():
        result = DRIVER.cli(
            "stack-verify",
            "record",
            "--store",
            database,
            "--component",
            component,
            "--file",
            file,
        )
        assert ref in (result.get("workflow_evidence_ref"), result.get("integration_evidence_ref"))
    manifest = DRIVER.save(output / "operational-manifest.json", {"database": str(database)})
    for ref in refs.values():
        if ref not in reviews:
            with contextlib.redirect_stdout(io.StringIO()):
                aeep_app(
                    ["assess", "--manifest", str(manifest), "review", ref], standalone_mode=False
                )
    with ReceiptStore(database, read_only=True) as store:
        repo = AssessmentRepository(store)
        for component, ref in refs.items():
            require_integration(repo, ref, component=component, source_digest=source)
    status = DRIVER.cli("stack-status", "--store", database)
    assert DRIVER.count_checks(status) == 37 and status["comparison_dispatch"].startswith("BLOCKED")
    assert {
        row["component"] for row in status["components"] if row["functional_status"] == "BLOCKED"
    } == {"waza"}
    assert DRIVER.snapshot(database, set(refs.values()) - present) == before
    DRIVER.save(output / "stack-status.json", status)
    result = {
        "mode": "managed" if review_file else "copied",
        "implementation_source": source,
        "records": refs,
        "verified_checks": 37,
        "comparison_dispatch": status["comparison_dispatch"],
        "prior_ledger_rows_preserved": True,
        "runtime_dispatches": 0,
    }
    if review_file is None:
        result["negative_controls"] = controls(database, output, prepared[SCHEDULED], manifest)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--apply-copied-result", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.store.resolve(), args.output.resolve(), args.apply_copied_result), indent=2
        )
    )
