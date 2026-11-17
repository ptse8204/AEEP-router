"""Reconcile the exact repository intake and check its offline grader bindings."""

import asyncio
import json
import tarfile
from collections import Counter

from audit_staged_repository_graders import audit_row, wheel_probe_assets
from check_linux_install import ROOT, WORK
from plan_repository_expansion import previous_repositories, repository
from rebind_cached_repository_sources import inventory
from stage_repository_transport import digest, read

QUEUE = WORK / "repository-expansion-queue"
INTAKE = WORK / "repository-expansion-acquisition"
REVIEW = "bb4a134feb5af19dac075f5ed362e80f20d9b83eec132d97886ef517dd721998"
APPROVAL = "1d456d6efb824b6cde861e591ec6c0b61e7e410a85c4a06fad1727c66167967a"
RESULT = "88bc973f326033a94c623d28537cc963acef28b8b9f0abce0c3c188017f1ceaa"


def reconcile_attempt(source, record):
    case = source["case_id"]
    attempt = INTAKE / "attempts" / case
    if json.loads((attempt / "started.json").read_bytes()) != {"case_id": case, "review_sha256": REVIEW}:
        raise ValueError("source start record changed")
    if json.loads((attempt / "result.json").read_bytes()) != record or record["case_id"] != case:
        raise ValueError("source result disagrees with the attempt record")
    path = INTAKE / "archives" / case / "source-original.tar.gz"
    if not path.is_file():
        return "archive_not_retained", None
    if record["status"] != "transport_staged" and (path.parent / "row.json").is_file():
        return "publisher_inventory_passed_staging_failed", None
    try:
        tree, notices, entries, sha = inventory(path, source["revision"])
    except (ValueError, tarfile.TarError) as error:
        if record["status"] == "transport_staged":
            raise
        return "retained_archive_rejected_by_inventory", str(error)
    if record["status"] != "transport_staged":
        return "archive_inventory_readable_publisher_match_unverified", None
    if (
        record["publisher"]["url"] != source["commit_url"]
        or record["publisher"]["published_tree"] != tree
        or (record["archive_sha256"], record["archive_entries"], record["archive_bytes"], record["license_notices"])
        != (sha, entries, path.stat().st_size, notices)
    ):
        raise ValueError("retained source differs from the reviewed Git tree")
    return "staged_publisher_git_tree_bound", None


async def audit():
    review = json.loads(read(QUEUE / "acquisition-review.json", REVIEW))
    approval = json.loads(read(QUEUE / "acquisition-approval.json", APPROVAL))
    result = json.loads(read(INTAKE / "result.json", RESULT))
    index = read(INTAKE / "index.json", result["candidate_index"]["sha256"])
    if (
        approval != {"approved": True, "review_sha256": REVIEW} or approval["approved"] is not True
        or result["review_sha256"] != REVIEW or result["stopped"] is not None
        or len(index) != result["candidate_index"]["bytes"]
        or not len(result["observations"]) == result["started"] == len(review["sources"])
        or any(result[key] != 0 for key in ("formal_cases_adopted", "upstream_tests", "models", "cash_usd"))
    ):
        raise ValueError("acquisition did not settle within its reviewed scope")
    staged, exclusions = {}, []
    for source, record in zip(review["sources"], result["observations"], strict=True):
        phase, reason = reconcile_attempt(source, record)
        if record["status"] == "transport_staged":
            staged[(source["repository"], source["revision"])] = (source, record)
        else:
            exclusions.append({**record, "retained_evidence": phase, "offline_inventory_error": reason})
    _, wheels = wheel_probe_assets()
    retained, _, exposed = previous_repositories()
    rows, families, seen = [], Counter(), set()
    for row in json.loads(index):
        identity = (row["source_repository"], row["source_revision"])
        slug = repository(identity[0])
        source, record = staged.pop(identity)
        task = row["input"]
        family = "contract-audit" if source["intent"] == "audit" else source["intent"]
        if (
            slug in (retained | exposed | seen) or task["family"] != family
        ):
            raise ValueError("candidate identity, license or evidence boundary differs")
        if family == "contract-audit":
            if (
                row["original_source_sha256"] != record["archive_sha256"]
                or row["license_notices"] != record["license_notices"]
                or row["runtime_verified"] is not False or row["formal_assignment"] is not None
            ):
                raise ValueError("authored audit source or evidence boundary differs")
        elif row["protected_runtime_verified"] is not False or row["formal_stage"] is not None:
            raise ValueError("multi-file repair received unverified runtime or stage credit")
        seen.add(slug)
        families[family] += 1
        observations = await audit_row(row, INTAKE / "transport", wheels)
        rows.append({
            "case": task["task_id"], "repository": identity[0], "revision": identity[1],
            "family": family, "published_tree": record["publisher"]["published_tree"],
            "archive_sha256": record["archive_sha256"], "source_sha256": task["source_sha256"],
            "license_notices": record["license_notices"], "protected_bindings": observations,
        })
    if staged or dict(families) != result["staged_by_family"]:
        raise ValueError("staged index could not be reconciled")
    prior = json.loads((ROOT / "reports/toolkit-v2/c13/completion-20261116/pyserde-ordinary-result.json").read_bytes())
    capacity = prior["conditional_software_capacity"]
    stages = capacity["example_family_counts"]
    required = sum(sum(counts.values()) for counts in stages.values())
    upper = capacity["provisional_candidates"] + len(rows)
    return {
        "schema_version": "aeep.c13.repository-expansion-result-audit.v1",
        "review_sha256": REVIEW, "acquisition_result_sha256": RESULT, "candidate_index_sha256": digest(index),
        "attempts_reconciled": result["started"], "staged_by_family": dict(families),
        "substituted_grader_callback_checks": 2 * len(rows), "candidates": rows,
        "exclusions_by_error": dict(sorted(Counter(row["error_type"] for row in exclusions).items())),
        "exclusions": exclusions,
        "prospective_capacity": {
            "prior_pool": capacity["provisional_candidates"], "staged_pool_upper_bound": upper,
            "required_cases": required, "row_shortfall_at_least": required - upper,
            "additional_sources_for_prior_balanced_profile": dict(Counter(capacity["requires_at_least"]) - families),
            "prior_balanced_profile": stages, "assumptions": "Every prior prospect and all staged inputs qualify.",
        },
        "upstream_tests": 0, "models": 0, "cash_usd": 0, "formal_cases_adopted": 0,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(audit()), indent=2))
