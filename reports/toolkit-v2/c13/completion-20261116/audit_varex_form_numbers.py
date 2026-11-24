"""Check numbered form variants and calibration relatives in the local VAREX pack."""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from audit_extractbench_source_groups import partition
from audit_varex_archive_lineage import CAPACITY_SHA, STAGED, STAGED_SHA, matches, pages
from audit_varex_source_families import POPPLER, POPPLER_SHA
from review_varex_balanced_capacity import packing
from stage_varex_calibration import CASES, REV, WORK, pinned, write

ACQUISITION_SHA = "2f0771c4bb9503f8b8c9576ef4537a681729b30b0386611c12094bad0b4b7363"


def government_form_number(name):
    match = re.fullmatch(r"(sf|gsa|hud|of|fda)[_-]?(\d{2,5}[a-z]*)(?:[-_].*)?", name.casefold())
    return "".join(match.groups()) if match else None


def audit():
    pinned(POPPLER, POPPLER_SHA)
    staged = json.loads(pinned(STAGED / "staged.json", STAGED_SHA))
    pack = json.loads(pinned(STAGED / "benchmark-pack.json", staged["manifest_file_sha256"]))
    earlier = json.loads(
        pinned(Path(__file__).parent / "varex-balanced-capacity-20261124.json", CAPACITY_SHA)
    )
    calibration = json.loads(pinned(WORK / "acquisition-result.json", ACQUISITION_SHA))
    if set(calibration["cases"]) != set(CASES):
        raise ValueError("calibration exclusion inventory changed")
    sources = {
        task["task_id"]: next(a for a in task["assets"] if a["path"].endswith("/document.pdf"))
        for task in pack["tasks"]
    }
    old = {
        name: number
        for number, group in enumerate(earlier["provisional_source_groups"])
        for name in group
    }
    calibration_text = {}
    for name, files in calibration["cases"].items():
        input_path = WORK / "acquired" / name / "document.pdf"
        pinned(input_path, files["document.pdf"])
        calibration_text[name] = pages(input_path)
        if not calibration_text[name] or max(map(len, calibration_text[name])) < 40:
            raise ValueError("calibration family requires detailed manual lineage review")
    numbers = defaultdict(list)
    shapes = defaultdict(set)
    held = {}
    old_groups = [(name, ("old", old[name])) for name in staged["cases"]]
    for name, row in sorted(staged["cases"].items()):
        task = row["input"]
        known = sources[task["task_id"]]
        path = STAGED / "pack" / known["path"]
        pinned(path, task["document_sha256"])
        if number := government_form_number(name):
            numbers[number].append(name)
        shapes[task["family"]].add(name)
        candidate = pages(path)
        for seed, features in calibration_text.items():
            similar = list(matches({name: candidate, seed: features}, {name: 0, seed: 1}))
            same_object = task["document_sha256"] == calibration["cases"][seed]["document.pdf"]
            same_number = bool(number and number == government_form_number(seed))
            if similar or same_number or same_object:
                held.setdefault(seed, []).append(
                    {
                        "case": name,
                        "same_publisher_form_number": same_number,
                        "same_pdf_hash": same_object,
                        "text_match": similar,
                    }
                )
    new_groups = [group for group in numbers.values() if len({old[name] for name in group}) > 1]
    numbered_edges = [(case, ("form", code)) for code, group in numbers.items() for case in group]
    all_groups = partition(sorted(staged["cases"]), old_groups + numbered_edges)
    direct_holds = {row["case"] for rows in held.values() for row in rows}
    exclusions = {
        case for group in all_groups if direct_holds.intersection(group) for case in group
    }
    groups = [group for group in all_groups if not exclusions.intersection(group)]
    high, low = (
        shapes["multiple-collections"] - exclusions,
        shapes["at-most-one-collection"] - exclusions,
    )
    return {
        "schema_version": "aeep.c13.varex-calibration-lineage.v1",
        "revision": REV,
        "staging_sha256": STAGED_SHA,
        "provisional_capacity_sha256": CAPACITY_SHA,
        "calibration_acquisition_sha256": ACQUISITION_SHA,
        "pdf_tool_sha256": POPPLER_SHA,
        "calibration_seeds": list(CASES),
        "staged_cases_screened": len(staged["cases"]),
        "additional_numbered_groups": sorted(new_groups),
        "held_for_calibration_lineage": held,
        "additional_group_members_held": sorted(exclusions - direct_holds),
        "case_count_after_hold": len(high | low),
        "counts_by_shape": {
            "multiple-collections": len(high),
            "at-most-one-collection": len(low),
        },
        "fits_with_calibration_relatives_held": packing(groups, high, low),
        "method": "Exact publisher form-number variants and an all-page text screen against both local calibration cases.",
        "formal_assignments": 0,
        "provider_disclosure": False,
        "models": 0,
        "cash_usd": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    write(parser.parse_args().out, audit())
