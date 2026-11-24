"""Check whether two balanced document holdouts can fit the reviewed VAREX sources."""

import argparse
import itertools
import json
import subprocess
from functools import cache
from pathlib import Path

from audit_extractbench_source_groups import partition
from audit_varex_source_families import POPPLER, POPPLER_SHA, first_page, verified_pdfs
from review_varex_form_lineage import audit
from stage_varex_calibration import REV, digest, pinned, write
from stage_varex_complement import form_code
from stage_varex_references import COMPLEMENT

from aeep.assessment.models import content_digest

LOW = COMPLEMENT / "protected-references"
STAGES = ("qualification", "training", "candidate_holdout", "selection_holdout")
COUNTS = ((4, 4), (14, 14), (52, 53), (52, 53))


def complementary_grades():
    ready = LOW / "native-execution"
    intake = json.loads((COMPLEMENT / "pdf-intake.json").read_bytes())
    result = json.loads((ready / "result.json").read_bytes())
    receipt = json.loads((ready / "receipt.json").read_bytes())
    ledger = json.loads((ready / "ledger.json").read_bytes())
    review = json.loads(pinned(LOW / "native-review.json", result["review_sha256"]))
    (charge,) = ledger["operations"]
    if (
        review["pdf_inventory"] != digest((COMPLEMENT / "pdf-intake.json").read_bytes())
        or review["reference_intake"] != digest((LOW / "reference-intake.json").read_bytes())
        or receipt["receipt_id"] != result["receipt_id"] or not receipt["execution_success"]
        or receipt["metadata"]["grade_observation_digest"] != content_digest(result["cases"])
        or not receipt["metadata"]["container_absent"] or charge["elapsed_seconds"] is None
        or charge["operation_id"] != receipt["action_id"] or set(intake["files"]) != set(result["cases"])
    ):
        raise ValueError("complementary protected grades do not settle against the PDF and reference inventory")
    passed = {case for case, row in result["cases"].items() if row["reference_check_passed"]}
    return result, passed, intake, ledger


def packing(groups, high, low):
    singles = [group[0] for group in groups if len(group) == 1]
    capacities = len(set(singles) & high), len(set(singles) & low)
    sizes = tuple(sorted(
        ((len(set(group) & high), len(set(group) & low)) for group in groups if len(group) > 1), reverse=True,
    ))

    @cache
    def fit(index, remaining):
        if index == len(sizes):
            return sum(x for x, _ in remaining) <= capacities[0] and sum(y for _, y in remaining) <= capacities[1]
        a, b = sizes[index]
        for stage, (x, y) in enumerate(remaining):
            if a <= x and b <= y:
                tail = (*remaining[:stage], (x - a, y - b), *remaining[stage + 1:])
                if fit(index + 1, tail):
                    return True
        return not a and fit(index + 1, remaining)

    return fit(0, COUNTS)


def audit_balance():
    pinned(POPPLER, POPPLER_SHA)
    high_review, _ = audit()
    high = set(high_review["prospects"])
    result, low, intake, ledger = complementary_grades()
    if high & low:
        raise ValueError("shape families overlap")
    retained, _, unavailable = verified_pdfs()
    if unavailable:
        raise ValueError("multiple-collection inventory is incomplete")
    candidates = {doc_id: path for doc_id, (path, _, _) in retained.items() if doc_id in high}
    for name in low:
        path = COMPLEMENT / "public-pdfs" / (digest(name.encode()) + ".pdf")
        pinned(path, intake["files"][name]["sha256"])
        candidates[name] = path
    features, insufficient = {}, []
    for name, path in sorted(candidates.items()):
        try:
            words = first_page(path)
        except (OSError, ValueError, subprocess.SubprocessError):
            insufficient.append(name)
            continue
        if len(words) >= 40:
            features[name] = words
        else:
            insufficient.append(name)
    if set(insufficient) & high:
        raise ValueError("previously screened multiple-collection inputs changed")
    low -= set(insufficient)
    links = [(name, ("known-form-code", form_code(name))) for name in sorted(high | low)]
    for group_index, group in enumerate(high_review["keep_related_forms_in_one_stage"]):
        links.extend((case, ("publisher-family", group_index)) for case in group)
    similar = []
    for left, right in itertools.combinations(sorted(high | low), 2):
        if left in high and right in high:
            continue
        a, b = features[left], features[right]
        overlap = len(a & b) / len(a | b)
        if overlap >= 0.60:
            similar.append({"forms": [left, right], "first_page_bigram_jaccard": round(overlap, 4)})
            links.extend((name, ("page-similarity", left, right)) for name in (left, right))
    # Conservatively hold lower-collection versions from a group that already
    # contains a reviewed multiple-collection form. Within the lower family
    # retain one representative until the publisher documents distinct tasks.
    held = {}
    for group in partition(sorted(high | low), links):
        keep = sorted(high.intersection(group))
        same_shape = sorted(low.intersection(group))
        if not same_shape:
            continue
        if not keep:
            keep = same_shape[:1]
            same_shape = same_shape[1:]
        for name in same_shape:
            low.remove(name)
            held[name] = keep[0]
    groups = partition(sorted(high | low), [(name, group) for name, group in links if name in high or name in low])
    feasible = packing(groups, high, low)
    return {
        "schema_version": "aeep.c13.varex-balanced-capacity.v1", "dataset_revision": REV,
        "complementary_pdfs_verified": intake["verified_pdfs"],
        "complementary_reference_checks_passed": result["protected_reference_checks_passed"],
        "complementary_grades": result["cases"], "complementary_receipt_id": result["receipt_id"],
        "complementary_review_sha256": result["review_sha256"], "complementary_operation_ledger": ledger,
        "multiple_collection_prospects": len(high), "at_most_one_collection_prospects": len(low),
        "complementary_prospects": sorted(low),
        "provisional_source_groups": [list(group) for group in groups],
        "unresolved_first_page_text": sorted(insufficient), "related_complementary_forms_held": held,
        "provisional_related_form_pairs": similar,
        "preferred_stage_shapes": {
            name: {"multiple_collections": a, "at_most_one_collection": b}
            for name, (a, b) in zip(STAGES, COUNTS, strict=True)
        },
        "a_provisional_source_disjoint_packing_fits": feasible, "candidate_groups": len(groups),
        "scope": "Local publisher grouping and archive readiness projection. Uses provisional text similarity and form codes.",
        "formal_assignments": 0, "model_turns": 0, "cash_usd": 0, "provider_disclosure": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    write(parser.parse_args().out, audit_balance())
