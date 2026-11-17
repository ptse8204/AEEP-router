"""Recheck retained C13 observations on the pinned committed source in a ledger copy."""

import argparse
import contextlib
import hashlib
import io
import json
import shutil
import socket
import sqlite3
from email import policy
from email.parser import BytesParser
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from check_linux_install import FROZEN, HERE, WORK, get, put

from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.errors import ConfigurationError
from aeep.store import ReceiptStore
from aeep_toolkit.cli import main as toolkit
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.stack_readiness import (
    REQUIRED_CHECKS,
    StackCompletion,
    require_stack_complete,
    source_revisions,
)
from aeep_toolkit.stack_receipts import KIND, StackReceiptEvidence, verify_receipt_evidence
from aeep_toolkit.stack_verification import COMPLETION, ROOT
from aeep_toolkit.workflow_evidence import KIND as WORKFLOW_KIND
from aeep_toolkit.workflow_evidence import EvidenceRequest, WorkflowEvidence, inspect_workflow

BASE = HERE.parent / "managed-comparison-20261115/offline-evidence/source-stack-rebinding.json"
COMMIT = "022c0060"
SELECTION_PATH = "src/aeep_toolkit/selection.py"
WHEEL = "aeep_agent_router-0.8.2-py3-none-any.whl"
SOURCE_SCOPE = (
    "pyproject.toml",
    "src",
    "tests",
    "integrations/aeep",
    "integrations/assessment-runtime",
    "integrations/managed-worker",
    "scripts",
)
CHANGED = {
    SELECTION_PATH,
    "pyproject.toml",
    "tests/test_ci_checkout.py",
    "tests/test_toolkit_selection.py",
}
BASIS = (
    "Preserve the original execution and review sources. The committed archive changes "
    "only selection-report route conversion at runtime. A route with no executor is now "
    "rejected before scoring. The execution, protected grading, reporting, setup, removal, "
    "telemetry and stack proof verifiers are byte-identical. The development extra and test "
    "deltas do not participate in these observations. Both ordinary workflows were prepared "
    "and every retained observation was independently resolved on the committed source."
)


def sources(root):
    files = {}
    for name in SOURCE_SCOPE:
        path = root / name
        for item in [path] if path.is_file() else path.rglob("*"):
            relative = item.relative_to(root)
            if any(part == "__pycache__" or part.endswith(".egg-info") for part in relative.parts):
                continue
            if item.is_symlink():
                raise ValueError("unexpected link in a frozen implementation")
            if item.is_file():
                files[relative.as_posix()] = file_digest(item)
    return files


def diff(before, after):
    return {
        key: [before.get(key), after.get(key)]
        for key in sorted(before.keys() | after.keys())
        if before.get(key) != after.get(key)
    }


def wheel_entries(path):
    with ZipFile(path) as wheel:
        filenames = [name for name in wheel.namelist() if not name.endswith("/")]
        if len(filenames) != len(set(filenames)):
            raise ValueError("retained wheel has duplicate members")
        (metadata,) = [name for name in filenames if name.endswith(".dist-info/METADATA")]
        entries = {name: hashlib.sha256(wheel.read(name)).hexdigest() for name in filenames}
        message = BytesParser(policy=policy.default).parsebytes(wheel.read(metadata))
        requirements = sorted(
            item for item in message.get_all("Requires-Dist", []) if 'extra == "dev"' not in item
        )
    return entries, requirements


def verify_delta():
    verified = get(HERE / "selection-guard-verification.json")["exact_committed_archive"]
    beta = get(HERE / "beta-package-audit.json")
    old = verification_source_digest(FROZEN)
    current = verification_source_digest(ROOT)
    if old != beta["implementation_source"] or current != verified["source_digest"]:
        raise ValueError("load the exact committed source and retain the original snapshot")
    changed = diff(sources(FROZEN), sources(ROOT))
    if changed.keys() != CHANGED or changed[SELECTION_PATH][1] != verified["selection_file_sha256"]:
        raise ValueError("source changed outside the reviewed selection fix")
    original_wheel = WORK / "beta-wheels" / WHEEL
    current_wheel = WORK / "selection-final-check.vuYku6/committed-dist" / WHEEL
    wheel_hashes = [file_digest(path) for path in (original_wheel, current_wheel)]
    if wheel_hashes != [beta["wheel_sha256"], verified["wheel_sha256"]]:
        raise ValueError("archived wheel bytes changed")
    (before, old_requirements), (after, new_requirements) = map(
        wheel_entries, (original_wheel, current_wheel)
    )
    member_changes = diff(before, after)
    runtime_changes = {
        key
        for key in member_changes
        if "/docs/" not in key and not key.endswith((".dist-info/METADATA", ".dist-info/RECORD"))
    }
    if (
        runtime_changes != {SELECTION_PATH.removeprefix("src/")}
        or old_requirements != new_requirements
    ):
        raise ValueError("runtime wheel changes exceed the selection fix")
    return old, current, changed, member_changes, wheel_hashes


def denied(repo, ref, source, reason, *, waza=False):
    try:
        require_stack_complete(repo, ref, source_digest=source, waza_selected=waza)
    except ConfigurationError as error:
        if reason not in str(error):
            raise
    else:
        raise ValueError("stack acceptance control failed")


def accounting(store):
    conn = store._connection
    return content_digest(
        {
            table: [list(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
            for table in ("assessment_grants", "assessment_operations", "assessment_jobs")
        }
    )


def register_copy(database, old, current):
    frozen = get(BASE)
    original_ref = frozen["stack_completion_ref"]
    receipt_map, packet = {}, {}
    with ReceiptStore(database) as store:
        repo = AssessmentRepository(store)
        root = repo.get(COMPLETION, original_ref)
        if content_digest(root) != original_ref or root["implementation_source"] != old:
            raise ValueError("the ledger is missing the retained stack completion")
        denied(repo, original_ref, current, "another implementation source")
        before = accounting(store)
        revisions = source_revisions(current)
        refs = {}
        for component, item in frozen["records"].items():
            value, kind = item["value"], item["kind"]
            previous = root["components"][component]
            if content_digest(value) != previous or repo.get(kind, previous) != value:
                raise ValueError("historical evidence bytes or references differ")
            if kind == WORKFLOW_KIND:
                old_record = WorkflowEvidence.model_validate(value)
                request = EvidenceRequest.model_validate(
                    {
                        **value["request"],
                        "compatibility_basis": BASIS,
                    }
                )
                record = inspect_workflow(repo, request, current)
                observed = diff(old_record.observations, record.observations)
                if (
                    observed.keys() != {"prepared_workflow_ref"}
                    or record.original_source != old_record.original_source
                ):
                    raise ValueError("a historical workflow observation changed")
                checks = old_record.observations["checks"]
                if set(checks) != set(REQUIRED_CHECKS[component]) or not all(checks.values()):
                    raise ValueError("workflow evidence omits a required observation")
                receipt_map[component] = {"changed_observations": observed}
            elif kind == KIND:
                record = StackReceiptEvidence.model_validate(
                    {
                        **value,
                        "source_revision": revisions[component],
                        "implementation_source": current,
                        "compatibility_basis": BASIS,
                    }
                )
                checks = verify_receipt_evidence(repo, record, component=component, source=current)
                if set(checks) != set(REQUIRED_CHECKS[component]):
                    raise ValueError("receipt evidence omits a required check")
                receipt_map[component] = {"observed_references": checks}
            else:
                raise ValueError("unrecognized retained evidence kind")
            ref = repo.put(kind, content_digest(record), record)
            repo.review(ref)
            refs[component] = ref
            packet[component] = {"kind": kind, "ref": ref, "value": record.model_dump(mode="json")}
        completion = StackCompletion.model_validate(
            {
                **root,
                "implementation_source": current,
                "components": refs,
            }
        )
        ref = repo.put(COMPLETION, content_digest(completion), completion)
        denied(repo, ref, current, "unreviewed")
        repo.review(ref)
        accepted = require_stack_complete(repo, ref, source_digest=current)
        denied(repo, ref, current, "requires both Waza readiness checks", waza=True)
        if (
            accepted != completion
            or accounting(store) != before
            or repo.get(COMPLETION, original_ref) != root
        ):
            raise ValueError("ledger copy changed authority, accounting or history")
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        if toolkit(["stack-verify", "status", "--store", str(database)]) != 0:
            raise ValueError("ordinary stack status failed")
    status = json.loads(stdout.getvalue())
    components = {row["component"]: row for row in status["components"]}
    checks = sum(
        check["status"] == "VERIFIED"
        for row in components.values()
        for check in row["checks"].values()
    )
    if (
        status["stack_completion_ref"] != ref
        or checks != 37
        or status["waza_in_stack_completion"]
        or status["implementation_source"] != current
        or not all(components[name]["integration_evidence_ref"] == refs[name] for name in refs)
    ):
        raise ValueError("ordinary CLI did not accept all exact rebound evidence")
    return accepted, ref, packet, receipt_map, status, checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    ledger = args.ledger.resolve(strict=True)
    if (
        args.output.exists()
        or shutil.disk_usage(args.output.parent).free < 52 * 1024**3 + ledger.stat().st_size
    ):
        raise ValueError("provide a new private output with space for a ledger copy")
    old, current, changed, members, wheel_hashes = verify_delta()
    with TemporaryDirectory(prefix="aeep-c13-readiness-ledger-") as tmp:
        database = Path(tmp).resolve() / "audit.sqlite3"
        if shutil.disk_usage(database.parent).free < 52 * 1024**3 + ledger.stat().st_size:
            raise ValueError("temporary volume cannot retain the audit copy")
        with (
            contextlib.closing(sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True)) as source,
            contextlib.closing(sqlite3.connect(database)) as copy,
        ):
            source.backup(copy)
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network denied")):
            completion, ref, records, evidence, status, checks = register_copy(
                database, old, current
            )
    if verification_source_digest(ROOT) != current:
        raise ValueError("committed source snapshot drifted during verification")
    args.output.mkdir(mode=0o700)
    put(
        args.output / "source-stack-binding.json",
        {
            "completion": completion.model_dump(mode="json"),
            "stack_completion_ref": ref,
            "records": records,
        },
    )
    put(args.output / "status.json", status)
    print(
        json.dumps(
            {
                "tested_commit": COMMIT,
                "original_source": old,
                "implementation_source": current,
                "changed_source_files": changed,
                "wheel_member_changes": members,
                "wheel_sha256": wheel_hashes,
                "runtime_dependencies_equal": True,
                "retained_observations": evidence,
                "original_completion_ref": get(BASE)["stack_completion_ref"],
                "copied_completion_ref": ref,
                "private_packet_sha256": file_digest(args.output / "source-stack-binding.json"),
                "ordinary_cli_status_sha256": file_digest(args.output / "status.json"),
                "accepted_components": len(records),
                "accepted_checks": checks,
                "waza_selected": False,
                "old_source_binding_refused_on_new_source": True,
                "unreviewed_completion_refused": True,
                "explicit_waza_selection_refused": True,
                "operational_ledger_mode": "read-only",
                "assessment_counters_and_jobs_unchanged_in_copy": True,
                "wheel_installed": False,
                "new_model_calls": 0,
                "release": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
