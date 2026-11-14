"""Prepare the two remaining local readiness checks without starting either check."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from aeep.assessment.identity import file_digest
from aeep.assessment.models import AssessmentAuthorization, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.scheduling import SchedulerDefinition
from aeep.assessment.verification import verification_source_digest
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import snapshot
from aeep_toolkit.workflow_security import ScannerRuntimeDefinition, scan_preview

REPORT = Path(__file__).resolve().parent
ROOT = REPORT.parents[3]
SCANNER = REPORT.parent / "scanner-fixture-continuation-20261103"
ASE = REPORT.parent / "ase-controlled-workflow-20261103"
ASE_DEFINITION = REPORT.parent / "integration-snapshot-correction-20261103" / "scheduler.json"
SANDBOX = Path("/usr/bin/sandbox-exec")
GIB = 1024**3


def load(path):
    return json.loads(path.read_bytes())


def pin(path):
    return {"path": str(path), "sha256": file_digest(path)}


def save(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
    return path


def changed(dependencies):
    return {
        name: {"original": digest, "current": actual}
        for name, digest in dependencies.items()
        if (actual := file_digest(Path(name))) != digest
    }


def debit_baseline(repo, grant_id, *, plan_id=None):
    effective = repo.effective_grant(grant_id)
    root = AssessmentAuthorization.model_validate(repo.get("authorization", grant_id))
    connection = repo.store._connection
    row = connection.execute(
        "SELECT revoked, operations, model_turns, elapsed_seconds, cash_usd "
        "FROM assessment_grants WHERE id=?",
        (grant_id,),
    ).fetchone()
    reserved = connection.execute(
        "SELECT operation.id, json_extract(started.payload_json, '$.plan_id') "
        "FROM assessment_operations operation JOIN assessment_records started "
        "ON started.kind='operation_start' AND started.id=operation.id "
        "WHERE operation.grant_id=? AND operation.state='reserved' ORDER BY operation.id",
        (grant_id,),
    ).fetchall()
    if row is None or row[0] or any(plan_id is None or item[1] == plan_id for item in reserved):
        raise RuntimeError("missing, revoked or unsettled authority")
    last = connection.execute(
        "SELECT digest FROM assessment_records WHERE kind='budget_amendment' "
        "AND json_extract(payload_json, '$.authorization_id')=? ORDER BY rowid DESC LIMIT 1",
        (grant_id,),
    ).fetchone()
    return {
        "root": content_digest(root),
        "predecessor": last[0] if last else None,
        "limits": effective.limits.model_dump(mode="json"),
        "counters": list(row),
        "other_plan_reservations_preserved": [item[0] for item in reserved],
        "expires_at": effective.expires_at.isoformat(),
    }


def scanner_review(work, source):
    manifest = SCANNER / "cli-manifest.json"
    original = ScannerRuntimeDefinition.model_validate(load(SCANNER / "scanner-runtime.json"))
    runtime = str(original.environment.container_runtime)
    difference = changed(original.executable_dependencies)
    if set(difference) != {runtime}:
        raise RuntimeError("unexpected scanner dependency changes")
    environment = original.environment
    image = subprocess.run(
        [
            runtime,
            "--host",
            f"unix://{environment.container_socket}",
            "image",
            "inspect",
            str(environment.container_image),
            "--format",
            "{{.Id}} {{.Os}}/{{.Architecture}}",
        ],
        env={"PATH": "/usr/bin:/bin"},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    ).stdout.strip()
    if image != f"{environment.container_image} linux/arm64":
        raise RuntimeError("retained scanner image is unavailable")
    database = Path(load(manifest)["database"])
    accounting = load(SCANNER / "cli-accounting.json")
    with ReceiptStore(database, read_only=True) as store:
        repo = AssessmentRepository(store)
        baselines = {
            role: debit_baseline(repo, grant)
            for role, grant in (
                ("scan", original.request.authorization_id),
                ("wrapper", accounting["request"]["authorization_id"]),
            )
        }
        runtime_ref = content_digest(original)
        assert content_digest(repo.get("toolkit_scanner_runtime", runtime_ref)) == runtime_ref
    worker = ROOT / "src/aeep_toolkit/scanner_worker.py"
    assert file_digest(worker) == original.worker_sha256
    definition = original.model_copy(
        update={
            "executable_dependencies": {
                runtime: difference[runtime]["current"],
                str(worker): original.worker_sha256,
            }
        }
    )
    runtime_file = save(work / "scanner-runtime.json", definition.model_dump(mode="json"))
    workflow = load(SCANNER / "cli-workflow.json")
    for configuration in workflow["configurations"].values():
        configuration["scanner"] = pin(runtime_file)
    workflow_file = save(work / "cli-workflow.json", workflow)
    accounting.update(
        workflow_sha256=file_digest(workflow_file),
        source_digest=source,
        manifest_path=str(manifest),
        manifest_sha256=file_digest(manifest),
    )
    accounting_file = save(work / "cli-accounting.json", accounting)
    preview, checked, candidate = scan_preview(workflow_file, "document-data")
    assert checked == definition and candidate.sha256 == original.candidate_sha256
    operation_key = f"cisco-readiness-{source[:10]}"
    operation_id = f"workflow:{accounting['request']['plan_id']}:{operation_key}"
    with ReceiptStore(database, read_only=True) as store:
        assert not store._connection.execute(
            "SELECT id FROM assessment_operations WHERE id IN (?,?)",
            (operation_id, operation_id + ":skill-scanner"),
        ).fetchall()
    return {
        "original_review": pin(SCANNER / "operation-review.json"),
        "historical_scan": pin(SCANNER / "cli-execution/scan.json"),
        "runtime_image": image,
        "executable_change": difference,
        "baselines": baselines,
        "database": str(database),
        "runtime": pin(runtime_file),
        "workflow": pin(workflow_file),
        "accounting": pin(accounting_file),
        "manifest": pin(manifest),
        "operation_key": operation_key,
        "preview": pin(save(work / "cli-preview.json", preview)),
        "review_sha256": preview["review_sha256"],
        "maximum_additional_operations": 2,
        "maximum_reserved_seconds": definition.timeout_seconds
        + 40
        + accounting["maximum_overhead_seconds"],
        "command": [
            "workflow",
            "scan",
            "--workflow",
            str(workflow_file),
            "--configuration",
            "document-data",
            "--accounting",
            str(accounting_file),
            "--operation-id",
            operation_key,
            "--reviewed-digest",
            preview["review_sha256"],
        ],
        "acceptance": "Ordinary CLI finds the exact pinned image and returns a canonical analyzer receipt and settled exclusive wrapper. Abort and retain records if verified cleanup or accounting is absent.",
    }


def ase_review(work, source):
    definition = SchedulerDefinition.model_validate(load(ASE_DEFINITION))
    difference = changed(definition.executable_dependencies)
    assert set(difference) == {str(SANDBOX)}
    subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(SANDBOX)], check=True)
    assert snapshot(Path(definition.runtime_root)) == definition.runtime_tree_digest
    probe_dir = work / "ase-native-probe"
    probe_dir.mkdir(mode=0o700)
    for directory in ("home", "tmp", "candidate", "responses"):
        (probe_dir / directory).mkdir(mode=0o700)
    canary = work / "outside-read-canary.txt"
    canary.write_text("First-party non-secret sandbox canary.\n")
    profile = Path(definition.boundary_profile)
    text = profile.read_text().replace(definition.workspace, str(probe_dir))
    # Bind metadata on the new owned ancestors. Preserve all original content access rules.
    ancestors = (work, *work.parents)
    metadata = (
        "(allow file-read-metadata "
        + " ".join("(literal " + json.dumps(str(path)) + ")" for path in ancestors)
        + ")\n"
    )
    updated = work / "scheduler-native-study.sb"
    updated.write_text(text + metadata)
    check = ASE / "native-check.py"
    git = Path(
        next(name for name in definition.executable_dependencies if name.endswith("/tools/git"))
    )
    assert check.is_file() and git.is_file()
    argv = [
        str(SANDBOX),
        "-f",
        str(updated),
        str(Path(definition.runtime_root) / "bin/python"),
        "-I",
        "-B",
        str(check),
    ]
    contract = REPORT.parent / "ase-runtime-contract-20261103"
    database = Path(load(contract / "operation-review.json")["database"])
    request = load(contract / "authority.json")["request"]
    operation = request["plan_id"] + ":native-readiness-" + source[:10]
    with ReceiptStore(database, read_only=True) as store:
        repo = AssessmentRepository(store)
        baseline = debit_baseline(repo, request["authorization_id"], plan_id=request["plan_id"])
        assert repo.get("conformance_request", request["plan_id"]) == request
        assert not store._connection.execute(
            "SELECT id FROM assessment_operations WHERE id=?", (operation,)
        ).fetchone()
    return {
        "database": str(database),
        "baseline": baseline,
        "request": request,
        "operation_id": operation,
        "historical_scheduler": pin(ASE_DEFINITION),
        "historical_profile": pin(profile),
        "historical_native_control": pin(ASE / "native-controls.json"),
        "historical_definition_ref": content_digest(definition),
        "executable_change": difference,
        "runtime_tree_sha256": definition.runtime_tree_digest,
        "current_profile": pin(updated),
        "probe": pin(check),
        "git": pin(git),
        "command": argv,
        "workspace": str(probe_dir),
        "workspace_tree_sha256": snapshot(probe_dir),
        "environment": {
            "PATH": f"{git.parent}:/usr/bin:/bin",
            "HOME": str(probe_dir / "home"),
            "TMPDIR": str(probe_dir / "tmp"),
            "LC_ALL": "C",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        "stdin": {
            "outside": str(canary),
            "outside_write": str(work / "denied-write"),
            "git": str(git),
        },
        "outside_canary": pin(canary),
        "maximum_additional_operations": 1,
        "maximum_reserved_seconds": 35,
        "acceptance": "Six first-party native isolation/Git observations with verified process exit, journal and settled charge. Exact dependency bridge is used for current readiness after validation. Historical plan and model receipt remain bound to the original scheduler.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expires", required=True)
    args = parser.parse_args()
    expiry = datetime.fromisoformat(args.expires)
    assert datetime.now(UTC) < expiry and shutil.disk_usage(ROOT).free >= 50 * GIB
    work = args.output.resolve()
    work.mkdir(mode=0o700)
    source = verification_source_digest(ROOT)
    review = {
        "schema_version": "aeep.operator.toolkit-boundary-repeat.v1",
        "purpose": "Revalidate two local execution boundaries without replaying historical model trials.",
        "implementation_source": source,
        "expires_at": expiry.isoformat(),
        "prepared_by": pin(Path(__file__).resolve()),
        "driver": pin(REPORT / "run-boundary-repeat.py"),
        "scanner": scanner_review(work, source),
        "agent_skill_eval": ase_review(work, source),
        "model_turns": 0,
        "maximum_cash_usd": 0,
        "network_downloads": 0,
        "accounting": "Use the existing scanner/ASE grants with exact finite zero-model amendments and preserved predecessor and counters. Native workspace is retained. Scanner cleanup is owned and identity checked.",
        "limits": "One ordinary static scan and one first-party native boundary check. No retry, provider disclosure, sign-in, credential access, image build/pull/deletion, package install, comparison, admission or release.",
    }
    file = save(work / "operation-review.json", review)
    print(json.dumps({"path": str(file), "sha256": file_digest(file)}, indent=2))


if __name__ == "__main__":
    main()
