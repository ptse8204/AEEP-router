"""Test whether cohort capacity survives conservative cross-year source linkage."""

import json
import re
from collections import Counter, defaultdict
from itertools import permutations, product
from pathlib import Path
from unittest.mock import patch

import audit_extractbench_transport_capacity as transport
from audit_extractbench_collection_shapes import SPLITS, collection_paths
from recover_extractbench_schemas import bound_inputs
from stage_repository_transport import HERE, WORK, digest, read

ACQUISITION = WORK / "extractbench-transport-metadata-unstarted-20261118"
ACQUISITION_REVIEW = "5c3008b8d5608dfeaea2716fee74c3eda72a2b511a74c0de651e59e5403189d5"
FILE_EVIDENCE = HERE / "document-archive-instruction-verification-20261118.json"
YEAR_SUFFIX = re.compile(r"(.+)-(202[1-4])\.pdf")
STAGE_SIZES = (8, 28, 105, 105)
ANNUAL = "year-family-metadata-sensitivity"


def linked_groups(rows, groups, unresolved):
    """Keep repeated filename stems in one source family without rounding away cases."""
    case_to_group = {case: group for group, cases in groups.items() for case in cases}
    family = defaultdict(set)
    years = defaultdict(set)
    permit_cases = []
    for case in sorted(case_to_group):
        row = rows[case]
        if row["files"][transport.SCHEMA] not in unresolved:
            continue
        name = Path(row["pdf"]).name
        stem = YEAR_SUFFIX.fullmatch(name)
        if stem:
            family[stem[1].casefold()].add(case_to_group[case])
            years[stem[1].casefold()].add(stem[2])
        elif name.startswith("W14-"):
            permit_cases.append(case)
        else:
            raise ValueError("unresolved publisher filename family changed")
    linked = set().union(*family.values())
    repeated = [groups[case_to_group[case]] for case in permit_cases]
    if (
        len(linked) != 4
        or len(family) != 5
        or min(map(len, years.values())) < 3
        or sorted(len(groups[group]) for group in linked) != [4, 4, 5, 5]
        or len(permit_cases) != 13
        or not all(cases == repeated[0] for cases in repeated)
        or case_to_group[permit_cases[0]] in linked
    ):
        raise ValueError("year and permit families differ from the audited public metadata")
    remaining = {group: cases for group, cases in groups.items() if group not in linked}
    combined = sorted(case for group in linked for case in groups[group])
    remaining[ANNUAL] = combined
    assert sum(map(len, remaining.values())) == sum(map(len, groups.values()))
    return remaining, combined, permit_cases, Counter(map(len, years.values()))


def homogeneous_witness(groups, requirements):
    """Try bounded stage orders. A found witness is checked; search failure is inconclusive."""
    if sum(map(len, groups.values())) < sum(requirements):
        return None
    for order in permutations(range(len(SPLITS))):
        remaining = dict(sorted(groups.items()))
        stages = [[] for _ in SPLITS]
        for index in order:
            target = requirements[index]
            if not target:
                continue
            largest = max(map(len, remaining.values()), default=0)
            options = {0: ()}
            for group, cases in remaining.items():
                for total, picked in tuple(options.items()):
                    if total < target and total + len(cases) < target + largest:
                        options.setdefault(total + len(cases), (*picked, group))
            possible = [total for total in options if total >= target]
            if not possible:
                break
            selected = [
                (group, case) for group in options[min(possible)] for case in remaining.pop(group)
            ]
            stages[index] = selected[:target]
        else:
            return stages
    return None


def evaluate(rows, groups, classifications):
    """Allow the linked family to contribute both shapes to one stage."""
    pure = [{}, {}]
    mixed = [[], []]
    totals = [0, 0]
    labels = {}
    for group, cases in groups.items():
        by_shape = [[], []]
        for case in cases:
            shape = int(classifications[rows[case]["files"][transport.SCHEMA]] >= 2)
            by_shape[shape].append(case)
            labels[case] = shape
            totals[shape] += 1
        if all(by_shape):
            if group != ANNUAL:
                raise ValueError("unexpected mixed nonannual group")
            mixed = by_shape
        else:
            for shape, members in enumerate(by_shape):
                if members:
                    pure[shape][group] = members
    if min(totals) < 122 or max(totals) < 124:
        return totals, "insufficient_population"
    for low, high in ((52, 53), (53, 52)):
        for mixed_stage in range(4) if all(mixed) else (None,):
            requirements = [[4, 14, low, low], [4, 14, high, high]]
            before = [values.copy() for values in requirements]
            reserved = [[], []]
            if mixed_stage is not None:
                for shape in range(2):
                    count = min(requirements[shape][mixed_stage], len(mixed[shape]))
                    reserved[shape] = [(ANNUAL, case) for case in mixed[shape][:count]]
                    requirements[shape][mixed_stage] -= count
            witnesses = [
                homogeneous_witness(pure[shape], requirements[shape]) for shape in range(2)
            ]
            if any(value is None for value in witnesses):
                continue
            if mixed_stage is not None:
                for shape in range(2):
                    witnesses[shape][mixed_stage].extend(reserved[shape])
            stages = [witnesses[0][i] + witnesses[1][i] for i in range(4)]
            used = [{group for group, _ in stage} for stage in stages]
            identities = [case for stage in stages for _, case in stage]
            assert len(identities) == len(set(identities)) == sum(STAGE_SIZES)
            assert tuple(map(len, stages)) == STAGE_SIZES
            assert len(set().union(*used)) == sum(map(len, used))
            assert all(
                len([case for _, case in stage if labels[case] == shape]) == before[shape][i]
                for i, stage in enumerate(stages)
                for shape in range(2)
            )
            return totals, "verified_capacity_witness"
    return totals, "bounded_search_found_no_witness"


def audit():
    review = json.loads(read(transport.RECOVERY, transport.RECOVERY_PIN))
    rows, _, schemas = bound_inputs(review, transport.RECOVERY.parent)
    observed = {sha: len(collection_paths(raw)) for sha, raw in schemas.items()}
    unresolved = sorted(item["schema_sha256"] for item in review["requests"])
    original = transport.eligible_groups(rows)
    linked, annual, permits, stems = linked_groups(rows, original, unresolved)
    _, entries = transport.acquisition(ACQUISITION, ACQUISITION_REVIEW)
    inventory, _ = transport.file_sizes(rows, entries)
    evidence = json.loads(FILE_EVIDENCE.read_bytes())
    limits = evidence["definition"]
    if (
        limits["file_instruction_bytes"] != 600_000
        or limits["compressed_zip_bytes"] != transport.ZIP_LIMIT
    ):
        raise ValueError("expected the verified file instruction and ZIP limits")
    with patch.object(transport, "INSTRUCTION_LIMIT", limits["file_instruction_bytes"]):
        classes = {
            c: transport.transport_class(inventory[c]) for cases in original.values() for c in cases
        }
    assumptions = [
        dict(zip(unresolved, p, strict=True)) for p in product((1, 2), repeat=len(unresolved))
    ]
    reports = {}
    for envelope, allowed in (
        ("stored_size_screen", {"stored_zip_size_within_limit"}),
        (
            "includes_unmeasured_compression",
            {"stored_zip_size_within_limit", "compressed_zip_size_needed"},
        ),
    ):
        matrix = {}
        for case_scope, held in (
            ("all_metadata_slots", set()),
            ("year_family_held_pending_review", set(annual)),
        ):
            viable = {
                name: [case for case in cases if classes[case] in allowed and case not in held]
                for name, cases in linked.items()
            }
            counts = Counter()
            max_multiple = 0
            for hypothesis in assumptions:
                totals, outcome = evaluate(rows, viable, observed | hypothesis)
                max_multiple = max(max_multiple, totals[1])
                counts[outcome] += 1
            matrix[case_scope] = {
                "conditional_results": dict(counts),
                "maximum_multiple_collection_slots": max_multiple,
                "eligible_metadata_slots": sum(map(len, viable.values())),
            }
        reports[envelope] = matrix
    return {
        "schema_version": "aeep.c13.extractbench-year-source-sensitivity.v1",
        "file_delivery_evidence_sha256": digest(FILE_EVIDENCE.read_bytes()),
        "metadata_acquisition_receipt_sha256": digest((ACQUISITION / "terminal.json").read_bytes()),
        "schema_recovery_review_sha256": transport.RECOVERY_PIN,
        "script_sha256": digest(Path(__file__).read_bytes()),
        "metadata_slots": sum(map(len, original.values())),
        "prior_groups": len(original),
        "groups_after_linkage": len(linked),
        "linked_year_metadata_slots": len(annual),
        "permit_filename_metadata_slots": len(permits),
        "distinct_recurring_stems_by_year_coverage": dict(stems),
        "stage_sizes": dict(zip(SPLITS, STAGE_SIZES, strict=True)),
        "models": 0,
        "task_bodies_fetched": 0,
        "new_schema_downloads": 0,
        "rights_granted": False,
        "formal_cases_adopted": 0,
        "results": reports,
        "interpretation": [
            "Repeated filename stems across years are a conservative linkage scenario. Underlying filer identity and lineage remain unverified.",
            "The publisher names Texas Railroad Commission filings among its sources. The W14 naming pattern alone cannot bind the exact PDF bytes or establish use rights.",
            "Observed and assumed schema classifications are separate. Grouping keeps every linked source in one stage, including when it contributes both variants.",
            "A valid witness demonstrates metadata capacity only. A bounded search without a witness is inconclusive unless the population floor fails.",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True, allow_nan=False))
