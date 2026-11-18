"""Bound the cohort feasibility impact of the five unresolved public schemas."""

import argparse
import json
from collections import Counter
from itertools import product
from pathlib import Path

from audit_extractbench_collection_shapes import (
    MULTIPLE,
    SINGLE_LIMIT,
    SPLITS,
    collection_paths,
    eligible_groups,
    feasibility,
)
from recover_extractbench_schemas import SCHEMA, bound_inputs, digest, read
from stage_repository_transport import ROOT


def audit(path, pin):
    review = json.loads(read(path, pin))
    rows, _, retained = bound_inputs(review, path.parent)
    observed = {sha: len(collection_paths(raw)) for sha, raw in retained.items()}
    groups = eligible_groups(rows)
    unresolved = {item["schema_sha256"]: item["case_slots"] for item in review["requests"]}
    counts = Counter(rows[case]["files"][SCHEMA] for group in groups.values() for case in group)
    if ({sha: count for sha, count in counts.items() if sha not in observed} != unresolved
            or len(unresolved) != 5):
        raise ValueError("schema capacities differ from the reviewed public inputs")

    scenarios = []
    sufficient = set()
    for hypotheses in product((1, 2), repeat=len(unresolved)):
        assumed = dict(zip(unresolved, hypotheses, strict=True))
        capacity, _, mixed, witness = feasibility(rows, groups, observed | assumed)
        leads = frozenset(sha for sha, size in assumed.items() if size == 2)
        seats = capacity[MULTIPLE]
        if witness:
            if set(witness) != set(SPLITS) or tuple(map(len, witness.values())) != (8, 28, 105, 105):
                raise ValueError("baseline stage counts changed")
            sufficient.add(leads)
        if bool(witness) != (seats >= SINGLE_LIMIT):
            raise ValueError("need a separate source-group feasibility check")
        scenarios.append({
            "assumed_multiple_collection_schemas": sorted(leads),
            "multiple_collection_slots": seats,
            "mixed_source_groups": mixed,
            "witness_found": witness is not None,
        })

    minimal = sorted(sorted(combination) for combination in sufficient
                     if not any(other < combination for other in sufficient))
    return {
        "schema_version": "aeep.c13.extractbench-recovery-capacity.v1",
        "review": {"path": path.relative_to(ROOT).as_posix(), "sha256": pin},
        "audit_driver_sha256": digest(Path(__file__).read_bytes()),
        "manifest_sha256": review["manifest_sha256"],
        "verified_schema_bodies": len(retained),
        "unresolved_schema_case_slots": unresolved,
        "scenarios": scenarios,
        "scenarios_with_witness": len(sufficient),
        "scenarios_without_enough_slots": len(scenarios) - len(sufficient),
        "minimal_sufficient_multiple_collection_subsets": minimal,
        "scope": "A sensitivity check on retained metadata with shared early stages. "
                 "Hypothetical labels cannot establish asset rights, task eligibility, grading or independence.",
        "formal_cases_adopted": 0,
        "network_requests": 0,
        "protected_grader_calls": 0,
        "model_turns": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("sha256")
    args = parser.parse_args()
    print(json.dumps(audit(args.review, args.sha256), indent=2, sort_keys=True))
