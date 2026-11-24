"""Prove a source-group-preserving fit for the staged VAREX pack."""

import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

from audit_varex_archive_lineage import STAGED, STAGED_SHA
from review_varex_balanced_capacity import COUNTS, STAGES
from stage_repository_transport import HERE, ROOT, digest, read, write

LINEAGE_SHA = "1c7b45019dd17fb3697f16c7133f02bfa7ee396e21681ec6d831e9c32b952661"
CALIBRATION_SHA = "5acc5860a8dbc05352201f6b22ec18aef9e1f2c39da637fa28becb628672b637"
RIGHTS_SHA = "bab0de4e6a672a6f0f29831e109958a2ebc39e41f46da98c339e429222911a5e"
SHAPES = ("multiple-collections", "at-most-one-collection")


def allocate(families, related):
    """Keep every member of a known family together and use every staged case."""
    grouped = [name for group in related for name in group]
    if len(grouped) != len(set(grouped)) or not set(grouped) <= families.keys():
        raise ValueError("related groups are not disjoint subsets of the staged pack")
    sizes = [Counter(families[name] for name in group) for group in related]
    remaining = sorted(families.keys() - set(grouped))
    singles = {shape: [name for name in remaining if families[name] == shape] for shape in SHAPES}
    for placements in itertools.product(range(len(STAGES)), repeat=len(related)):
        stages = {stage: [] for stage in STAGES}
        capacities = [dict(zip(SHAPES, counts, strict=True)) for counts in COUNTS]
        for group, size, index in zip(related, sizes, placements, strict=True):
            stages[STAGES[index]].extend(group)
            for shape, count in size.items():
                capacities[index][shape] -= count
        if any(count < 0 for capacity in capacities for count in capacity.values()):
            continue
        for shape, cases in singles.items():
            cursor = 0
            for stage, capacity in zip(STAGES, capacities, strict=True):
                count = capacity[shape]
                stages[stage].extend(cases[cursor : cursor + count])
                cursor += count
            if cursor != len(cases):
                raise ValueError("singleton cases do not match the required shape totals")
        return {stage: sorted(names) for stage, names in stages.items()}
    raise ValueError("no exact allocation keeps all related staged cases together")


def audit():
    staged = json.loads(read(STAGED / "staged.json", STAGED_SHA))
    lineage = json.loads(read(HERE / "varex-full-page-lineage-20261124.json", LINEAGE_SHA))
    calibration = json.loads(
        read(HERE / "varex-calibration-lineage-20261124.json", CALIBRATION_SHA)
    )
    rights = json.loads(read(HERE / "varex-asset-use-inventory-20261124.json", RIGHTS_SHA))
    path, pin = (rights["draft_inventory"][key] for key in ("path", "sha256"))
    inventory = json.loads(read(ROOT / path, pin))
    cases = {name: entry["input"] for name, entry in staged["cases"].items()}
    drafts = {draft["task_id"]: draft for draft in inventory["drafts"]}
    if (
        len(cases) != 246
        or len(drafts) != 246
        or len(inventory["drafts"]) != 246
        or set(drafts) != {row["task_id"] for row in cases.values()}
        or any(
            draft["local_execution_allowed"] or draft["provider_disclosure_allowed"]
            for draft in drafts.values()
        )
        or any(item["staging_sha256"] != STAGED_SHA for item in (lineage, calibration, rights))
        or staged["formal_assignments"]
        or staged["asset_use_approved"]
        or inventory["pack_sha256"] != staged["benchmark_pack_sha256"]
        or lineage["unresolved_text"]
        or lineage["additional_review_leads"]
        or calibration["held_for_calibration_lineage"]
        or calibration["additional_group_members_held"]
        or calibration["additional_numbered_groups"]
        or set(calibration["calibration_seeds"]) & cases.keys()
        or lineage["input_pdf_sha256"]
        != {name: row["document_sha256"] for name, row in cases.items()}
    ):
        raise ValueError("staged assets, lineage or unsigned authority bindings changed")
    families = {name: row["family"] for name, row in cases.items()}
    related = lineage["groups_with_multiple_cases"]
    stages = allocate(families, related)
    members = [name for names in stages.values() for name in names]
    stage_counts = {
        stage: dict(Counter(families[name] for name in names)) for stage, names in stages.items()
    }
    if (
        Counter(members) != Counter(families.keys())
        or any(not any(set(group) <= set(names) for names in stages.values()) for group in related)
        or list(stage_counts.values())
        != [dict(zip(SHAPES, counts, strict=True)) for counts in COUNTS]
    ):
        raise ValueError("packing witness does not meet disjointness and balance requirements")
    return stages, {
        "schema_version": "aeep.c13.varex-packing-witness.v1",
        "stage_shapes": stage_counts,
        "cases": len(cases),
        "related_groups_kept_intact": len(related),
        "calibration_cases_excluded": len(calibration["calibration_seeds"]),
        "pack_sha256": staged["benchmark_pack_sha256"],
        "staging_sha256": STAGED_SHA,
        "document_lineage_sha256": LINEAGE_SHA,
        "calibration_lineage_sha256": CALIBRATION_SHA,
        "unsigned_asset_review_inventory_sha256": pin,
        "formal_assignments": 0,
        "authorized_cases": 0,
        "model_turns": 0,
        "cash_usd": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-witness", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    args = parser.parse_args()
    stages, proof = audit()
    witness = (json.dumps(stages, indent=2, sort_keys=True) + "\n").encode()
    write(args.private_witness, witness)
    proof["private_witness_sha256"] = digest(witness)
    write(args.proof, (json.dumps(proof, indent=2, sort_keys=True) + "\n").encode())
