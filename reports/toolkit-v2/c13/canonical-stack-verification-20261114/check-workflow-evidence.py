"""Exercise the operator CLI on copies of the two completed SkillsBench runs."""

import contextlib
import io
import json
import shutil
from pathlib import Path
from unittest.mock import patch

from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.cli import app as aeep_app
from aeep.errors import ConfigurationError
from aeep.router import Router
from aeep.store import ReceiptStore
from aeep_toolkit.cli import main
from aeep_toolkit.stack_readiness import require_integration

ROOT = Path(__file__).resolve().parents[4]
SOURCE = Path(__file__).resolve().parent
DOMAINS = ("document-data", "software-engineering")


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")
    return path


def cli(*argv, blocked=False, reason=None):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            assert main(list(map(str, argv))) == 0
        except SystemExit as error:
            assert blocked and error.code == 2, stderr.getvalue()
            assert reason is None or reason in stderr.getvalue(), stderr.getvalue()
            return None
    assert not blocked
    return json.loads(stdout.getvalue())


def verify(work, original_store):
    work.mkdir(mode=0o700)
    store_path = work / "copied-ledger.sqlite3"
    with ReceiptStore(original_store, read_only=True) as original, ReceiptStore(store_path) as copy:
        original._connection.backup(copy._connection)
    manifest = save(work / "manifest.json", {"database": str(store_path)})
    source = verification_source_digest(ROOT)
    observed, requests = {}, {}
    for name in DOMAINS:
        request = read(SOURCE / f"{name}-request.json")
        report = work / name / "report"
        shutil.copytree(request["report_directory"], report)
        request["report_directory"] = str(report)
        requests[name] = request
        with patch.object(
            Router, "from_manifest", side_effect=AssertionError("unexpected Router initialization")
        ):
            result = cli(
                "workflow",
                "evidence",
                "--store",
                store_path,
                "--file",
                save(work / f"{name}-request.json", request),
            )
        record, ref = result["record"], result["review_sha256"]
        assert record["implementation_source"] == source
        assert record["observations"]["checks"] == {"ordinary_cli": True, "canonical_report": True}
        registered = cli(
            "stack-verify",
            "record",
            "--store",
            store_path,
            "--component",
            record["component"],
            "--file",
            save(work / f"{name}-record.json", record),
        )
        assert registered["workflow_evidence_ref"] == ref
        unreviewed = cli("stack-status", "--store", store_path)
        (entry,) = (c for c in unreviewed["components"] if c["component"] == record["component"])
        assert entry["functional_status"] == "BLOCKED"
        with contextlib.redirect_stdout(io.StringIO()):
            aeep_app(["assess", "--manifest", str(manifest), "review", ref], standalone_mode=False)
        (tele,) = record["observations"]["telemetry"]
        assert (
            tele["transport_status"] == "failed"
            and tele["ingestion_verified"]
            and tele["disabled_export_verified"]
        )
        observed[name] = {
            "component": record["component"],
            "ref": ref,
            "original_source": record["original_source"],
            "report_ref": record["observations"]["report_ref"],
            "report_files": record["observations"]["report_files"],
            "task_scores": [
                trial["binary_task_score"] for trial in record["observations"]["trials"]
            ],
            "telemetry": tele,
            "lifecycle": record["observations"]["lifecycle"],
        }
    good = cli("stack-status", "--store", store_path)
    assert good["comparison_dispatch"].startswith("BLOCKED")
    assert (
        sum(
            check["status"] == "VERIFIED"
            for c in good["components"]
            for check in c["checks"].values()
        )
        == 4
    )
    save(work / "stack-status.json", good)

    document, software = (requests[name] for name in DOMAINS)
    fault = work / "fault.json"
    checks = {}
    for name, changed, reason in (
        (
            "mismatched_transport",
            document | {"telemetry": software["telemetry"]},
            "different trial receipt",
        ),
        (
            "mismatched_report_id",
            document | {"report_id": software["report_id"]},
            "completed canonical job",
        ),
        ("missing_readback", document | {"telemetry": []}, None),
    ):
        saved = save(fault, changed)
        if name == "missing_readback":
            draft = cli("workflow", "evidence", "--store", store_path, "--file", saved)["record"]
            assert draft["observations"]["checks"] == {
                "ordinary_cli": False,
                "canonical_report": True,
            }
            cli(
                "stack-verify",
                "record",
                "--store",
                store_path,
                "--component",
                draft["component"],
                "--file",
                save(fault, draft),
                blocked=True,
                reason="required observations are missing",
            )
        else:
            cli(
                "workflow",
                "evidence",
                "--store",
                store_path,
                "--file",
                saved,
                blocked=True,
                reason=reason,
            )
        checks[name] = True

    saved = save(fault, document)
    report_directory = Path(document["report_directory"])
    html = report_directory / "report.html"
    retained = html.read_bytes()
    html.write_bytes(retained + b"\n")
    cli(
        "workflow",
        "evidence",
        "--store",
        store_path,
        "--file",
        saved,
        blocked=True,
        reason="report rendering differs",
    )
    bad = cli("stack-status", "--store", store_path)
    assert [
        c["functional_status"] for c in bad["components"] if c["component"].startswith("workflow-")
    ] == ["BLOCKED", "VERIFIED"]
    html.write_bytes(retained)
    checks["changed_rendering"] = True

    with ReceiptStore(store_path) as store, store._immediate_transaction() as transaction:
        count = transaction.execute(
            "UPDATE assessment_jobs SET state='indeterminate' WHERE report_id=?",
            (document["report_id"],),
        ).rowcount
        assert count == 1
    cli(
        "workflow",
        "evidence",
        "--store",
        store_path,
        "--file",
        saved,
        blocked=True,
        reason="completed canonical job",
    )
    with ReceiptStore(store_path) as store:
        with store._immediate_transaction() as transaction:
            transaction.execute(
                "UPDATE assessment_jobs SET state='complete' WHERE report_id=?",
                (document["report_id"],),
            )
        repo = AssessmentRepository(store)
        ref = observed["document-data"]["ref"]
        try:
            require_integration(
                repo, ref, component="workflow-document-data", source_digest="f" * 64
            )
        except ConfigurationError as error:
            assert "another component or source" in str(error)
        else:
            raise AssertionError("source drift passed")
        repo.review(ref, revoke=True)
    denied = cli("stack-status", "--store", store_path)
    assert [
        c["functional_status"]
        for c in denied["components"]
        if c["component"].startswith("workflow-")
    ] == ["BLOCKED", "VERIFIED"]
    checks.update(interrupted_run=True, source_drift=True, revoked_review=True)
    with ReceiptStore(store_path) as store:
        AssessmentRepository(store).review(ref)

    return {
        "scope": "retained real workflow records validated in a copied ledger",
        "implementation_source": source,
        "checks_accepted": 4,
        "checks_required": 39,
        "workflows": observed,
        "controls": checks,
        "live_dispatches": 0,
        "comparison_dispatch": good["comparison_dispatch"],
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--store", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(verify(args.output.resolve(), args.store.resolve()), indent=2, allow_nan=False)
    )
