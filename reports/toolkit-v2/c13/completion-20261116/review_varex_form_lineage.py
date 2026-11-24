"""Reconcile protected VAREX grades with the publisher's form families."""

import argparse
import json
from pathlib import Path

from check_varex_cohort import INTAKE, REVIEW, RUN, SCREEN
from stage_varex_calibration import digest, pinned, write
from stage_varex_references import BATCH

from aeep.assessment.models import content_digest

GSA_FORMS = "https://www.gsa.gov/forms-library"
FDA_MANUAL = "https://www.fda.gov/media/182173/download"
CDPH_REGISTRATION = "https://www.cdph.ca.gov/Programs/CEH/DFDCS/Pages/FDBPrograms/FoodSafetyProgram/ProcessedFoodRegistration.aspx"
CDPH_APPLICATIONS = "https://www.cdph.ca.gov/Programs/CEH/DFDCS/Pages/CertificatesandLicenses.aspx"
CDPH_PROCESSED_COLD_STORAGE = (
    "https://www.cdph.ca.gov/Programs/CEH/DFDCS/Pages/FDBPrograms/FoodSafetyProgram/ColdStorageFacilities.aspx",
    "https://www.cdph.ca.gov/Programs/CEH/DFDCS/Pages/FDBPrograms/FoodSafetyProgram/FrozenFoodLockerFacilities.aspx",
)
SAME_TASK = (
    ("GSA3683-18", "GSA3683A-18", "GSA3683N-18"),
    ("SF1152-11", "sf1152"),
    ("SF1153-11", "sf1153"),
    ("SF85PS-17", "sf85ps"),
    ("cdph8610", "cdph8611"),
    ("cdph8610ih", "cdph8611ih"),
)
FDA_FAMILY = (
    "FDA-3511a_stat_sec_ext_03-09-22", "FDA-3511b_stat_sec_ext_03-10-22",
    "FDA-3511d_stat_sec_ext_03-10-22", "FDA-3511f_stat_sec_ext_03-11-22_0",
)
DISTINCT_RELATED = (FDA_FAMILY, ("cdph8591", "cdph8592"))


def settled_grades():
    result = json.loads((RUN / "result.json").read_bytes())
    ledger = json.loads((RUN / "ledger.json").read_bytes())
    receipt = json.loads((RUN / "receipt.json").read_bytes())
    observation = result["cases"]
    (charged,) = ledger["operations"]
    review = json.loads(pinned(REVIEW, result["review_sha256"]))
    if (
        review["reference_intake"] != INTAKE or review["pdf_inventory"] != digest(SCREEN.read_bytes())
        or receipt["receipt_id"] != result["receipt_id"] or not receipt["execution_success"]
        or receipt["metadata"]["grade_observation_digest"] != content_digest(observation)
        or not receipt["metadata"]["container_absent"] or charged["elapsed_seconds"] is None
        or charged["operation_id"] != receipt["action_id"]
        or result["protected_reference_checks_passed"] != sum(row["reference_check_passed"] for row in observation.values())
    ):
        raise ValueError("protected grades differ from the reviewed, settled operation")
    return result, receipt, ledger


def count_scored_collections(node):
    if isinstance(node, dict):
        return sum(count_scored_collections(value) for value in node.values())
    if isinstance(node, list):
        return int(bool(node)) + sum(count_scored_collections(value) for value in node)
    return 0


def audit():
    result, receipt, ledger = settled_grades()
    screen = json.loads(SCREEN.read_bytes())
    cohort = json.loads(pinned(BATCH / "reference-intake.json", INTAKE))
    groups = {frozenset(group) for group in screen["connected_related_form_groups"]}
    if groups != {frozenset(group) for group in (*SAME_TASK, *DISTINCT_RELATED)}:
        raise ValueError("the form review does not cover the exact screened groups")
    eligible = {case for case, grade in result["cases"].items() if grade["reference_check_passed"]}
    unscreened = set(screen["insufficient_first_page_text"])
    selected = eligible - unscreened
    held = {}
    for group in SAME_TASK:
        representatives = sorted(selected.intersection(group))
        for case in representatives[1:]:
            held[case] = representatives[0]
            selected.remove(case)
    families = [
        group for group in (*SAME_TASK[:-2], (*SAME_TASK[-2], *SAME_TASK[-1]), *DISTINCT_RELATED)
    ]
    for index, group in enumerate(families):
        if group == FDA_FAMILY:
            families[index] = (*group, "FDA-3511-2_07-20-21_Secured_extended")
    for case in selected:
        evidence = cohort["cases"][case]
        reference = pinned(BATCH / "protected" / evidence["protected_case"] / "reference.json", evidence["reference_sha256"])
        if count_scored_collections(json.loads(reference)) < 2:
            raise ValueError("published reference lacks two populated collections")
    return {
        "schema_version": "aeep.c13.varex-form-lineage-review.v1",
        "protected_reference_grade_count": len(eligible),
        "incompatible_reference_schemas": sorted(result["cases"].keys() - eligible),
        "unresolved_text_screen": sorted(unscreened),
        "duplicate_form_versions_held": held,
        "prospects_after_grading_and_variant_review": len(selected),
        "minimum_multiple_collection_cases": 122,
        "prospects": sorted(selected),
        "keep_related_forms_in_one_stage": [sorted(set(group) & selected) for group in families],
        "source_facts": [
            {"forms": "SF1152, SF1153, SF85PS and GSA3683 variants", "source": GSA_FORMS,
             "finding": "Retain one case per numbered form or common appraisal task."},
            {"forms": "FDA 3511 series", "source": FDA_MANUAL,
             "finding": "Publisher distinguishes forms for separate inspection workflows. Keep the series together."},
            {"forms": "CDPH 8610 and 8611", "source": CDPH_REGISTRATION,
             "finding": "Retain one county variant of the same registration task."},
            {"forms": "CDPH 8610 IH and 8611 IH", "source": CDPH_APPLICATIONS,
             "finding": "Retain one county variant of the separate authorization task."},
            {"forms": "CDPH 8591 and 8592", "sources": CDPH_PROCESSED_COLD_STORAGE,
             "finding": "The publisher uses separate applications for different facility types. Keep them together."},
        ],
        "receipt": receipt["receipt_id"], "review_sha256": result["review_sha256"],
        "ledger": ledger, "reference_result_sha256": digest((RUN / "result.json").read_bytes()),
        "formal_assignments": 0, "model_turns": 0, "cash_usd": 0,
        "scope": "Controlled grader checks and documented variant handling. Asset-use, complete lineage, and held-out assignment are pending.",
    }, result["cases"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    report, cases = audit()
    write(args.out, report | {"native_grades": cases})
