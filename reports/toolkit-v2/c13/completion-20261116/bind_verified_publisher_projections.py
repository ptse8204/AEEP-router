"""Join retained publisher proofs to unchanged ordinary task and grader inputs."""

import asyncio
import json
import runpy
import sys
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.verification import verification_source_digest
from audit_montepy_export import audit as export_audit
from audit_staged_repository_graders import audit_row, bind, wheel_probe_assets
from stage_repository_transport import digest, read

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / ".aeep/completion-20261116"
RECONCILER = WORK / "publisher-reconciliation-20261117/reconcile-publisher.py"
RECONCILER_SHA = "8809acd018313cc3299431ffb88cbab90a64352493f8496099cb928908acea71"
DIRECT = WORK / "repository-expansion-retained-tree-recovery-20261117/publisher-reconciled.json"
INVERSE = HERE / "montepy-export-binding.json"


def join_proof(target, row, staged, proof):
    if (
        proof["case"] != target["case"]
        or proof["revision"] != target["revision"] or row["source_revision"] != target["revision"]
        or proof["publisher_tree"] != proof["restored_tree"]
        or proof["archived_source_sha256"] != target["archive_sha256"]
        or staged["original_archive_sha256"] != target["archive_sha256"]
        or proof["public_archive_sha256"] != row["input"]["source_sha256"]
        or row["source_repository"].casefold() != target["repository"]
        or row["publisher_binding_verified"] is not False
    ):
        raise ValueError("publisher proof belongs to different source or staged bytes")
    return True


async def audit():
    read(RECONCILER, RECONCILER_SHA)
    previous = runpy.run_path(str(RECONCILER))
    exact, review = previous["pin_scope"]()
    reconstructed = await previous["reconcile"](
        previous["RUN"], previous["RUN"].parent / "approval.json", fixture=False
    )
    if reconstructed != json.loads(DIRECT.read_bytes()) or reconstructed["fixture"]:
        raise ValueError("actual publisher reconciliation differs from retained terminal evidence")
    inverted = export_audit()
    if inverted != json.loads(INVERSE.read_bytes()) or not inverted["publisher_binding_verified"]:
        raise ValueError("inverse export differs from retained whole-tree proof")
    projected, reports = previous["bind_projections"](review)
    direct = {row["case"]: row for row in reconstructed["binding_candidates"]}
    wheel_review, wheels = wheel_probe_assets()
    result = []
    for target in review["targets"]:
        name = target["case"]
        row, staged, transport, index_sha = projected[name]
        if name in direct:
            source = direct[name]
            proof = {**source, "restored_tree": source["publisher_tree"]}
            method = "publisher_tree_with_reviewed_submodule_pointers"
            proof_ref = digest(DIRECT.read_bytes())
        else:
            if name != inverted["case"] or inverted["source_revision"] != target["revision"]:
                raise ValueError("no applicable actual publisher proof")
            proof = {
                "case": name, "revision": inverted["source_revision"],
                "publisher_tree": inverted["publisher_tree"],
                "restored_tree": inverted["one_file_inverse_export"]["restored_tree"],
                "archived_source_sha256": inverted["archive_sha256"],
                "public_archive_sha256": row["input"]["source_sha256"],
            }
            method = "publisher_tree_with_single_declared_inverse_export"
            proof_ref = digest(INVERSE.read_bytes())
        join_proof(target, row, staged, proof)
        task, truth, _, _, metadata = bind(row, transport, wheels)
        replay = await audit_row(row, transport, wheels)
        if (
            replay["reference_transport"] != staged["reference_transport"]
            or replay["original_transport"] != staged["original_transport"]
        ):
            raise ValueError("ordinary graded payloads changed after publisher verification")
        notices = {entry["file"]: entry["sha256"] for entry in target["license_notices"]}
        result.append({
            "case": name, "task_id": task.task_id, "family": task.family,
            "source_revision": target["revision"], "source_repository": target["repository"],
            "publisher_tree": proof["publisher_tree"], "publisher_proof_method": method,
            "publisher_proof_sha256": proof_ref,
            "original_archive_sha256": target["archive_sha256"],
            "staged_index_sha256": index_sha, "input_digest": content_digest(task),
            "public_archive_sha256": task.source_sha256, "protected_tests_sha256": truth.tests.sha256,
            "protected_identity_digest": content_digest(truth.fail_to_pass + truth.pass_to_pass),
            "required_test_identities": replay["test_identities"],
            "editable_paths": task.editable_paths, "source_license_notices": notices,
            "reference_archive_sha256": replay["reference_transport"]["archive_sha256"],
            "original_archive_sha256_for_grading": replay["original_transport"]["archive_sha256"],
            "publisher_binding_verified": True, "protected_runtime_verified": False,
            "formal_stage": None, "ordinary_callback_replay": "first_party_substituted_reply",
            "declared_runtime": metadata,
        })
    if len(result) != 5 or len({row["source_repository"] for row in result}) != 5:
        raise ValueError("expected five distinct reviewed repository families")
    return {
        "schema_version": "aeep.c13.verified-publisher-projection-bindings.v1",
        "workspace_source": verification_source_digest(ROOT), "publisher_review_sha256": exact,
        "direct_reconciliation_sha256": digest(DIRECT.read_bytes()),
        "inverse_export_sha256": digest(INVERSE.read_bytes()),
        "original_staging_reports": reports, "wheel_probe_review_sha256": wheel_review,
        "bindings": result, "source_bindings_verified": 5,
        "protected_test_identities": sum(row["required_test_identities"] for row in result),
        "network_requests": 0, "new_upstream_executions": 0, "formal_cases_adopted": 0,
        "scope": "Source proofs apply to these exact unchanged task, overlay and output archive hashes. Runtime dependencies and actual protected grading remain pending. Historical staged indexes keep their original status.",
    }


def deny_network(event, _args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.bind", "socket.sendto"}:
        raise PermissionError("publisher projection binding is offline")


if __name__ == "__main__":
    sys.addaudithook(deny_network)
    print(json.dumps(asyncio.run(audit()), indent=2, sort_keys=True, allow_nan=False))
