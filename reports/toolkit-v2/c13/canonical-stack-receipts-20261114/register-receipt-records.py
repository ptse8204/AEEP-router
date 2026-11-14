"""Register exact readiness records or test their registration on a copied ledger."""

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.cli import app as aeep_app
from aeep.store import ReceiptStore
from aeep_toolkit.cli import main

ROOT = Path(__file__).resolve().parent
WORKFLOW_REVIEWS = ROOT.parent / "canonical-stack-verification-20261114"
RETENTION_KINDS = ("toolkit_stack_receipt_evidence", "toolkit_workflow_completion_evidence")
WORKFLOWS = ("document-data", "software-engineering")


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    return path


def cli(*arguments, blocked=False):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            assert main(list(map(str, arguments))) == 0
        except SystemExit as error:
            assert blocked and error.code == 2, stderr.getvalue()
            return stderr.getvalue().strip()
    assert not blocked
    return json.loads(stdout.getvalue())


def snapshot(database, new_refs=()):
    """Fingerprint all prior ledger contents and retain references to additive evidence."""
    with ReceiptStore(database, read_only=True) as store:
        connection = store._connection
        tables = connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
        ).fetchall()
        state = {}
        for (table,) in tables:
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
            order = ", ".join(str(index) for index in range(1, len(columns) + 1))
            digest = hashlib.sha256()
            count = 0
            for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY {order}'):
                if (
                    table == "assessment_records"
                    and row[0] in RETENTION_KINDS
                    and row[2] in new_refs
                ) or (table == "assessment_reviews" and row[0] in new_refs):
                    continue
                digest.update(repr(tuple(row)).encode() + b"\n")
                count += 1
            state[table] = {"rows": count, "sha256": digest.hexdigest()}
        return state


def count_checks(status):
    return sum(
        check["status"] == "VERIFIED"
        for component in status["components"]
        for check in component["checks"].values()
    )


def registration(database, evidence, output, *, copied):
    prepared = []
    for domain in WORKFLOWS:
        request = WORKFLOW_REVIEWS / f"{domain}-request.json"
        result = cli("workflow", "evidence", "--store", database, "--file", request)
        record = result["record"]
        assert record["observations"]["checks"] == {"ordinary_cli": True, "canonical_report": True}
        file = save(output / f"{domain}-record.json", record)
        assert content_digest(record) == result["review_sha256"]
        prepared.append((record["component"], result["review_sha256"], file))
    for file in sorted(evidence.glob("*-record.json")):
        record = read(file)
        prepared.append((record["component"], content_digest(record), file))
    assert len(prepared) == 16 and len({row[0] for row in prepared}) == 16

    before = cli("stack-status", "--store", database)
    ledger_before = snapshot(database)
    with ReceiptStore(database, read_only=True) as store:
        reviews = dict(store._connection.execute("SELECT digest, revoked FROM assessment_reviews"))
        present = {
            row[0] for row in store._connection.execute("SELECT digest FROM assessment_records")
        }
    if any(reviews.get(ref) for _, ref, _ in prepared):
        raise RuntimeError("an exact evidence review was revoked")
    bindings = {}
    for component, ref, file in prepared:
        result = cli(
            "stack-verify", "record", "--store", database, "--component", component, "--file", file
        )
        assert ref in (result.get("workflow_evidence_ref"), result.get("integration_evidence_ref"))
        assert result["operator_review_required"] is True
        bindings[component] = ref

    pending = cli("stack-status", "--store", database)
    assert count_checks(pending) == count_checks(before)
    manifest = save(output / "manifest.json", {"database": str(database)})
    for ref in bindings.values():
        if ref not in reviews:
            with contextlib.redirect_stdout(io.StringIO()):
                aeep_app(
                    ["assess", "--manifest", str(manifest), "review", ref], standalone_mode=False
                )
    after = cli("stack-status", "--store", database)
    assert count_checks(after) == 33
    assert after["comparison_dispatch"].startswith("BLOCKED")
    assert {
        row["component"] for row in after["components"] if row["functional_status"] == "BLOCKED"
    } == {"agent-skill-eval", "skill-scanner", "waza"}
    assert (
        snapshot(database, {ref for ref in bindings.values() if ref not in present})
        == ledger_before
    )
    save(output / "stack-status.json", after)
    result = {
        "ledger": "copy" if copied else "managed",
        "implementation_source": after["implementation_source"],
        "checks_before": count_checks(before),
        "checks_pending_exact_review": count_checks(pending),
        "checks_after": count_checks(after),
        "checks_required": 39,
        "records": bindings,
        "comparison_dispatch": after["comparison_dispatch"],
        "existing_ledger_rows_preserved": True,
        "dispatches": 0,
    }
    if copied:
        result["controls"] = exercise_controls(database, evidence, output, manifest, bindings)
    return result


def exercise_controls(database, evidence, output, manifest, bindings):
    original = read(evidence / "langfuse-record.json")
    bogus = "0" * 64
    fault_file = output / "fault.json"
    controls = {}
    for name, component, mutation in (
        ("wrong_component", "mcpmark", lambda _record: None),
        ("source_drift", "langfuse", lambda record: record.update(implementation_source=bogus)),
        (
            "historical_source_drift",
            "langfuse",
            lambda record: record.update(original_source=bogus),
        ),
        (
            "unknown_export",
            "langfuse",
            lambda record: record["proof"].update(export_record_ref=bogus),
        ),
        (
            "forged_transport",
            "langfuse",
            lambda record: record["proof"]["receipts"]["transport"].update(receipt_ref=bogus),
        ),
        (
            "forged_readback",
            "langfuse",
            lambda record: record["proof"]["receipts"]["readback"].update(receipt_ref=bogus),
        ),
        (
            "forged_disablement",
            "langfuse",
            lambda record: record["proof"]["receipts"]["disabled"].update(receipt_ref=bogus),
        ),
        (
            "changed_observation",
            "langfuse",
            lambda record: record["proof"]["receipts"]["observed_result"].update(sha256=bogus),
        ),
        ("changed_version", "langfuse", lambda record: record.update(schema_version="unknown")),
    ):
        changed = json.loads(json.dumps(original))
        mutation(changed)
        controls[name] = cli(
            "stack-verify",
            "record",
            "--store",
            database,
            "--component",
            component,
            "--file",
            save(fault_file, changed),
            blocked=True,
        )
    ref = bindings["langfuse"]
    with contextlib.redirect_stdout(io.StringIO()):
        aeep_app(
            ["assess", "--manifest", str(manifest), "review", ref, "--revoke"],
            standalone_mode=False,
        )
    assert count_checks(cli("stack-status", "--store", database)) == 31
    controls["revoked_review"] = "Langfuse blocked and OpenTelemetry remains verified."
    return controls


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument(
        "--apply", action="store_true", help="Use only with exact reviewed evidence"
    )
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(mode=0o700)
    database = args.store.resolve()
    if not args.apply:
        database = output / "copied-ledger.sqlite3"
        with ReceiptStore(args.store, read_only=True) as source, ReceiptStore(database) as target:
            source._connection.backup(target._connection)
    print(
        json.dumps(registration(database, args.evidence, output, copied=not args.apply), indent=2)
    )
