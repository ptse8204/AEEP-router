"""Prepare one unsigned rights-review inventory for the staged VAREX cohort."""

import argparse
import json
from collections import Counter
from pathlib import Path

from audit_varex_archive_lineage import STAGED, STAGED_SHA
from stage_repository_transport import HERE, ROOT, digest, read, write
from stage_varex_calibration import DATASET, REV
from stage_varex_prospects import LICENSE_SHA

from aeep.assessment.models import content_digest
from aeep_toolkit.benchmarks import BenchmarkPack, inspect_pack
from aeep_toolkit.workflow_preparation import TaskRightsReview

HEAD = HERE / "varex-balanced-archives-20261124.json"
LICENSE = "CDLA-Permissive-2.0"


def review_inventory(destination):
    staged = json.loads(read(STAGED / "staged.json", STAGED_SHA))
    manifest = STAGED / "benchmark-pack.json"
    pack = BenchmarkPack.model_validate_json(read(manifest, staged["manifest_file_sha256"]))
    if staged["asset_use_approved"] or staged["formal_assignments"] or len(pack.tasks) != 246:
        raise ValueError("unexpected staged cohort or authority status")
    ids = tuple(task.task_id for task in pack.tasks)
    contents = inspect_pack(pack, STAGED / "pack", ids)
    parent = json.loads(HEAD.read_bytes())
    if (
        contents["executed"]
        or contents["official_benchmark_reproduction"]
        or contents["pack_sha256"] != staged["benchmark_pack_sha256"]
        or contents["pack_sha256"] != parent["pack_sha256"]
        or parent["staging_record"]["sha256"] != STAGED_SHA
        or pack.source.repository != DATASET
        or pack.source.revision != REV
    ):
        raise ValueError("ordinary inspection did not match the retained pack")
    drafts = []
    counts = Counter()
    for task in pack.tasks:
        source = pack.source_for_task(task.task_id)
        if (
            task.domain != "document-data"
            or task.rights_review_ref is not None
            or source.repository != DATASET
            or source.revision != REV
            or source.license_expression != LICENSE
            or Counter(asset.role for asset in task.assets)
            != {
                "instruction": 1,
                "input": 2,
                "oracle": 1,
                "verifier": 1,
                "license": 1,
            }
        ):
            raise ValueError("task bounds, license context or unsigned review status changed")
        (license_asset,) = [asset for asset in task.assets if asset.role == "license"]
        (pdf,) = [
            asset for asset in task.assets if asset.role == "input" and asset.path.endswith(".pdf")
        ]
        if license_asset.sha256 != LICENSE_SHA or pdf.sha256 != source.artifact_sha256:
            raise ValueError("publisher PDF or license evidence differs from the case source pin")
        draft = TaskRightsReview(
            source_revision=source.revision,
            source_pin_sha256=content_digest(source.model_dump(mode="json")),
            task_id=task.task_id,
            assets={asset.path: asset.sha256 for asset in task.assets},
            basis=[
                "Pinned VAREX publisher revision and case PDF identity.",
                "Pack inspection verified the case's CDLA-Permissive-2.0 notice and all asset hashes.",
                "Pending source-lineage and use review. No local study execution or provider disclosure is authorized by this draft.",
            ],
            local_execution_allowed=False,
            provider_disclosure_allowed=False,
        )
        drafts.append(draft.model_dump(mode="json"))
        counts.update(asset.role for asset in task.assets)
    record = {
        "schema_version": "aeep.c13.unsigned-asset-use-inventory.v1",
        "pack_sha256": contents["pack_sha256"],
        "source_revision": REV,
        "license_sha256": LICENSE_SHA,
        "local_execution_approvals": 0,
        "provider_disclosure_approvals": 0,
        "formal_assignments": 0,
        "operator_review_required": True,
        "drafts": drafts,
    }
    output = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
    write(destination, output)
    return {
        "schema_version": "aeep.c13.varex-asset-use-inventory-proof.v1",
        "pack_sha256": contents["pack_sha256"],
        "pack_file_sha256": file_sha(manifest),
        "staging_sha256": STAGED_SHA,
        "source_revision": REV,
        "license_expression": LICENSE,
        "license_sha256": LICENSE_SHA,
        "asset_roles_verified": dict(counts),
        "case_records_prepared": len(drafts),
        "draft_inventory": {
            "path": destination.relative_to(ROOT).as_posix(),
            "sha256": digest(output),
        },
        "local_execution_approvals": 0,
        "provider_disclosure_approvals": 0,
        "formal_assignments": 0,
        "models": 0,
        "cash_usd": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }


def file_sha(path):
    return digest(path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drafts", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    args = parser.parse_args()
    proof = review_inventory(args.drafts.resolve())
    write(args.proof.resolve(), (json.dumps(proof, indent=2, sort_keys=True) + "\n").encode())


if __name__ == "__main__":
    main()
