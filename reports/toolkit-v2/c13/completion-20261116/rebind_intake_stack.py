"""Revalidate the November 20 committed stack against the retained receipts."""

import argparse
import json
import shutil
import socket
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import rebind_current_stack as retained

from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.store import ReceiptStore
from aeep_toolkit.benchmarks import BenchmarkPack
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.stack_verification import ROOT
from aeep_toolkit.workflow import StackWorkflow, _read
from aeep_toolkit.workflow_preparation import require_rights

REPO = retained.HERE.parents[3]
PRIOR = REPO / ".aeep/c13-document-archive-verification.wvK9pP"
CURRENT = REPO / ".aeep/c13-combined-full-verification.4ae1bc40"
COMMIT = "943016e029bed9028f833aa3748cb3eb779f2a36"
PRIOR_SOURCE = "e060413cc2af11fd3c967384ad908026d8e8d467aaa430729ae28462b4f5afc7"
CURRENT_SOURCE = "2896e52509b33a5628f8d5833a9b6111ebff9f0ed374faa08da539a57753c896"
BINDING = "08ab46252a1f2c644deb0c1ab64ba315f634243193ebf39ed5b05a7f9d7f75ca"
WHEEL_HASH = "0ebadb2fd9b2635e15b6203989aae710f0054352207a72d7a79f054822bb770a"
CHANGED_RUNTIME = {
    "src/aeep/assessment/models.py",
    "src/aeep/assessment/repository_suites.py",
    "src/aeep_toolkit/benchmarks.py",
    "src/aeep_toolkit/workflow.py",
    "src/aeep_toolkit/workflow_preparation.py",
}
BASIS = (
    "This source adds explicit repository-suite v7 inputs and file creation, and reviewed "
    "document packs with individual asset source pins. Both retained ordinary journeys use "
    "the same v1 SkillsBench pack, existing rights records and protected graders. Current "
    "preparation revalidates each pack and canonical recipe, and the rights check revalidates "
    "both retained asset decisions. Historical grades, accounting, runtime, receipts and "
    "reports remain bound to their original sources. Component verification and runtime "
    "dependencies are unchanged. The new pack and suite contracts have separate source tests."
)


def check_delta():
    if (
        verification_source_digest(PRIOR / "source") != PRIOR_SOURCE
        or verification_source_digest(ROOT) != CURRENT_SOURCE
    ):
        raise ValueError("expected the two audited source snapshots")
    delta = retained.diff(retained.sources(PRIOR / "source"), retained.sources(ROOT))
    if {name for name in delta if not name.startswith("tests/")} != CHANGED_RUNTIME:
        raise ValueError("implementation drift exceeds the reviewed source delta")
    wheel = CURRENT / "corrected/dist" / retained.WHEEL
    if file_digest(wheel) != WHEEL_HASH:
        raise ValueError("audited wheel changed")
    before, requirements_before = retained.wheel_entries(PRIOR / "dist" / retained.WHEEL)
    after, requirements_after = retained.wheel_entries(wheel)
    members = retained.diff(before, after)
    runtime = {name for name in members if name.startswith(("aeep/", "aeep_toolkit/"))}
    if requirements_before != requirements_after or runtime != {
        path.removeprefix("src/") for path in CHANGED_RUNTIME
    }:
        raise ValueError("wheel runtime or dependency delta differs")
    for name in runtime:
        if after[name] != file_digest(ROOT / "src" / name):
            raise ValueError("wheel member differs from committed source")
    return delta, members


def verify_rights(database, records):
    checked = {}
    with ReceiptStore(database) as store:
        repo = AssessmentRepository(store)
        for component, item in records.items():
            if item["kind"] != retained.WORKFLOW_KIND:
                continue
            request = retained.EvidenceRequest.model_validate(item["value"]["request"])
            path = Path(request.selected_workflow.path)
            workflow = StackWorkflow.model_validate_json(path.read_bytes())
            config = workflow.configurations[request.configuration]
            pack = BenchmarkPack.model_validate_json(_read(config.benchmark, path.parent)[1])
            if pack.pack_id != "skillsbench" or pack.task_sources is not None:
                raise ValueError("retained workflow no longer uses the reviewed SkillsBench pack")
            require_rights(repo, pack, config.task_ids)
            checked[component] = list(config.task_ids)
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output", type=Path, help="New private output directory on the repository volume"
    )
    output = parser.parse_args().output.resolve()
    source_db = PRIOR / "readiness-copy.sqlite3"
    if shutil.disk_usage(output.parent).free < 50 * 2**30 + 2 * source_db.stat().st_size:
        raise ValueError("insufficient space for an isolated ledger copy")
    changed, members = check_delta()
    retained.BASE = PRIOR / "source-stack-binding.json"
    retained.BASIS = BASIS
    if file_digest(retained.BASE) != BINDING:
        raise ValueError("prior evidence binding changed")
    frozen = retained.get(retained.BASE)
    output.mkdir(mode=0o700)
    database = output / "audit.sqlite3"
    with (
        closing(sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True)) as source,
        closing(sqlite3.connect(database)) as copy,
    ):
        source.backup(copy)
    database.chmod(0o600)
    with patch.object(socket.socket, "connect", side_effect=AssertionError("network denied")):
        rights = verify_rights(database, frozen["records"])
        completion, ref, records, facts, status, checks = retained.register_copy(
            database, PRIOR_SOURCE, CURRENT_SOURCE
        )
    if verification_source_digest(ROOT) != CURRENT_SOURCE:
        raise ValueError("implementation changed during receipt verification")
    retained.put(
        output / "binding.json",
        {
            "completion": completion.model_dump(mode="json"),
            "stack_completion_ref": ref,
            "records": records,
        },
    )
    retained.put(output / "status.json", status)
    summary = {
        "tested_commit": COMMIT,
        "prior_source": PRIOR_SOURCE,
        "implementation_source": CURRENT_SOURCE,
        "source_changes": changed,
        "wheel_archive_sha256": WHEEL_HASH,
        "wheel_member_changes": sorted(members),
        "runtime_requirements_unchanged": True,
        "wheel_installed": False,
        "previous_completion": frozen["stack_completion_ref"],
        "private_completion": ref,
        "private_packet_sha256": file_digest(output / "binding.json"),
        "ordinary_cli_status_sha256": file_digest(output / "status.json"),
        "accepted_components": len(records),
        "accepted_checks": checks,
        "workflow_rights_revalidated": rights,
        "workflow_preparation_reference_changes": {
            name: audit["changed_observations"]["prepared_workflow_ref"]
            for name, audit in facts.items()
            if "changed_observations" in audit
        },
        "old_source_binding_rejected": True,
        "unreviewed_completion_rejected": True,
        "explicit_waza_selection_rejected": True,
        "operational_ledger_modified": False,
        "assessment_accounting_jobs_and_history_preserved": True,
        "compatibility_basis": BASIS,
        "new_model_turns": 0,
        "cash_usd": 0,
        "comparisons_paused": True,
        "release": False,
    }
    retained.put(output / "result.json", summary)
    print(
        json.dumps(
            {
                "accepted_checks": checks,
                "accepted_components": len(records),
                "private_completion": ref,
                "workflow_rights_revalidated": rights,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
