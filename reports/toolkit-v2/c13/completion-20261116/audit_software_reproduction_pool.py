"""Reconcile the retained software reproductions across the C13 evidence sets."""

import json
from collections import Counter

from audit_formal_inputs import REQUIRED, repository
from plan_repository_expansion import previous_repositories
from stage_repository_transport import HERE, ROOT, digest, read

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase

PROFILE = ("contract-audit", "multi-file-repair", "single-file-repair")


def load(name, pins):
    path = HERE / name
    raw = path.read_bytes()
    pins[name] = digest(raw)
    return json.loads(raw)


def artifact(ref):
    path = ROOT / ref["path"]
    if not path.is_relative_to(ROOT) or not path.resolve().is_relative_to(ROOT):
        raise ValueError("evidence pointer leaves the Toolkit checkout")
    return json.loads(read(path, ref["sha256"]))


def case_row(case, repo, revision, family, evidence, receipt_ids):
    if family not in PROFILE or len(set(receipt_ids)) != len(receipt_ids) or len(receipt_ids) < 2:
        raise ValueError("software case needs distinct graded observations")
    return {
        "case": case, "repository": repository(repo), "revision": revision,
        "family": family, "evidence": evidence, "receipt_ids": receipt_ids,
    }


def original_pool(pins):
    manifest = load("formal-transport-preparation.json", pins)
    history = load("retained-grader-evidence.json", pins)
    if history["prepared_pool_sha256"] != manifest["prepared_pool_sha256"]:
        raise ValueError("historical evidence refers to a different cohort")
    source = ROOT / manifest["prepared_pool_relative_path"]
    models = [RepositorySuiteCase.model_validate(raw)
              for raw in json.loads(read(source, manifest["prepared_pool_sha256"]))]
    cases = {case.independent_case_id: case for case in models}
    if len(cases) != len(models):
        raise ValueError("repeated case in historical manifest")
    result = []
    for case_id, observation in history["cases_with_verified_observations"].items():
        case = cases[case_id]
        if (case.used_for_development or case.origin_kind == "synthetic_fixture"
                or content_digest(case) != observation["case_sha256"]
                or case.source_revision != observation["source_revision"]):
            raise ValueError("historical source or scope differs")
        variants = {v["variant"]: v for v in observation["variants"]}
        fault_matches = observation["current_fault_bindings"]
        if [content_digest(fault) for fault in case.fault_outputs] != [
            row["artifact_sha256"] for row in fault_matches
        ] or any(not row["matching_variant"] for row in fault_matches):
            raise ValueError("historical faults differ")
        roles = ["reference", *(row["matching_variant"] for row in fault_matches)]
        receipts = []
        for role in dict.fromkeys(roles):
            item = variants[role]
            grade = item["grade"]
            if (grade["trust"] != "verified" or grade["valid"] is not (role == "reference")
                    or grade["quality_score"] != int(role == "reference")
                    or not item["original_cleanup_confirmed"]):
                raise ValueError("historical outcome differs")
            artifact({"path": item["raw_observation_path"], "sha256": item["raw_observation_sha256"]})
            receipts.append(item["receipt_id"])
        result.append(case_row(
            case_id, case.source_repository, case.source_revision, case.input.family,
            "historical_callback_with_settled_receipts", receipts,
        ))
    if len(result) != history["cases_with_all_current_faults_observed"]:
        raise ValueError("historical completeness count differs")
    return result, sorted(history["unresolved_cases"])


def new_software(pins):
    first = load("offline-group-result-20261117.json", pins)
    corrections = load("software-correction-result-20261117.json", pins)
    batch = load("group-software-results-20261117.json", pins)
    staged = artifact(first["software_evidence"]["staged_result"])
    cached = artifact(first["software_evidence"]["cached_result"])
    original_rows = {row["case"] for row in batch["observations"] if row.get("role") == "reference"}
    candidate_index = {}
    for report, key in (
        ("rebound-worker-transport.json", "private_index_relative_path"),
        ("cached-multifile-projections.json", "private_transport_index"),
        ("additional-contract-audits.json", "private_index"),
        ("ancillary-contract-audits.json", "private_index"),
    ):
        catalog = load(report, pins)
        hash_key = key.removesuffix("_relative_path") + "_sha256"
        rows = artifact({"path": catalog[key], "sha256": catalog[hash_key]})
        candidate_index.update((r["input"]["task_id"], r) for r in rows)
    ordinary = {}
    for row in corrections["observations"]:
        artifact(row["raw_file"])
        grade = row["ordinary_callback_grade"]
        if (grade["trust"] != "verified" or grade["valid"] is not (row["role"] == "reference")
                or grade["quality_score"] != int(row["role"] == "reference")):
            raise ValueError("corrected score does not match the observed role")
        source = candidate_index[row["case"]]
        if (row["source_revision"] != source["source_revision"]
                or row["source_archive_sha256"] != source["input"]["source_sha256"]
                or not row["container_absent_at_settlement"] or not row["container_absent_now"]):
            raise ValueError("corrected outcome belongs to another source")
        ordinary.setdefault(row["case"], {})[row["role"]] = row["receipt_id"]
    result = []
    for case_id, roles in first["software_cases"].items():
        row = candidate_index[case_id]
        if all(roles[role]["contract_matched"] and roles[role]["score"] == score
               for role, score in (("reference", 1), ("original", 0))):
            if case_id in original_rows:
                receipts = [item["receipt"]["receipt_id"] for item in batch["observations"]
                            if item.get("case") == case_id and item["contract_matched"]]
            else:
                receipts = [item["receipt_id"] for item in cached["observations"]
                            if f":{case_id}:" in item["operation"] and item["contract_matched"]]
        else:
            observed = ordinary[case_id]
            if "reference" not in observed:
                old_reference = corrections["py_fsrs_compatible_pair"]
                artifact(old_reference["reference_observation"])
                observed["reference"] = old_reference["reference"]["receipt_id"]
            receipts = [observed[role] for role in ("reference", "original")]
        if len(receipts) != 2 or not (staged and cached["verified"]):
            raise ValueError("incomplete staged software reproduction")
        result.append(case_row(
            case_id, row["source_repository"], row["source_revision"], row["input"]["family"],
            "settled_ordinary_reference_and_original", receipts,
        ))
    return result


def additional_observations(pins):
    pyserde = load("pyserde-ordinary-result.json", pins)
    source = load("pyserde-production-repair-preflight.json", pins)
    if (not pyserde["protected_ordinary_verification_passed"]
            or pyserde["case"] != source["case_id"] or pyserde["source_revision"] != source["revision"]
            or len(source["production_files"]) != 2 or [row["score"] for row in pyserde["roles"]] != [1, 0, 0, 0]
            or not all(row["owned_container_absent"] for row in pyserde["roles"])):
        raise ValueError("Pyserde evidence binding differs")
    return [case_row(
        pyserde["case"], source["repository"], source["revision"], "multi-file-repair",
        "settled_ordinary_reference_original_and_partial_repairs",
        [row["receipt_id"] for row in pyserde["roles"]],
    )]


def assess(rows, excluded_repositories):
    if len({row["case"] for row in rows}) != len(rows):
        raise ValueError("case counted twice")
    if len({(row["repository"], row["revision"]) for row in rows}) != len(rows):
        raise ValueError("source snapshot counted twice")
    all_receipts = [receipt for row in rows for receipt in row["receipt_ids"]]
    if len(all_receipts) != len(set(all_receipts)):
        raise ValueError("protected receipt counted twice")
    counts = Counter(row["family"] for row in rows)
    repos = Counter(row["repository"] for row in rows)
    if repos.keys() & excluded_repositories:
        raise ValueError("corpus still contains a development-exposed repository")
    twice_holdout = REQUIRED["holdout"] * 2
    requirement = twice_holdout + REQUIRED["qualification"] + REQUIRED["training"]
    return {
        "reproduced_rows": len(rows), "repository_families": len(repos),
        "counts_by_family": dict(counts), "distinct_receipts": len(all_receipts),
        "largest_repository_group_rows": max(repos.values()),
        "two_cohorts_shared_early_minimum": requirement,
        "minimum_missing_rows_if_all_reproduced_rows_are_eligible": max(0, requirement - len(rows)),
        "two_balanced_holdouts_minimum_missing_by_family_before_early_stages": {
            family: max(0, twice_holdout // len(PROFILE) - counts[family]) for family in PROFILE
        },
    }


def audit():
    pins = {}
    historical, unverified = original_pool(pins)
    staged = new_software(pins)
    extra = additional_observations(pins)
    rows = sorted(historical + staged + extra, key=lambda row: row["case"])
    a2a = load("approved-a2a-batch-results.json", pins)
    bridge = load("a2a-receipt-bridge-audit.json", pins)
    _, _, excluded = previous_repositories()
    if set(a2a["reproduced"]) != set(bridge["cases"]) or bridge["ordinary_tests_executed"]:
        raise ValueError("A2A legacy observer scope changed")
    return {
        "schema_version": "aeep.c13.software-reproduction-pool.v1",
        "scope": "Retained exact ordinary-callback reproductions. Current common runtime, rights, independent assignment and formal acceptance remain separate.",
        "inputs": pins,
        "capacity": assess(rows, excluded),
        "groups": {"historical_callback": len(historical), "recent_reproductions": len(staged) + len(extra)},
        "development_repository_exclusions_checked": len(excluded),
        "rows": rows,
        "historical_pending_exact_controls": unverified,
        "legacy_observer_reproductions_pending_ordinary_runtime": sorted(a2a["reproduced"]),
        "formal_cases_adopted": 0,
        "formal_assignments": 0,
        "new_upstream_tests": 0,
        "new_model_turns": 0,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True, allow_nan=False))
