"""Find additional protected multi-file workloads in the exact retained publisher pages."""

import argparse
import json
import runpy
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

from plan_repository_expansion import UNION, patch_paths, previous_repositories, repository, screen
from screen_candidate_patches import python_source, test_roots
from stage_repository_transport import HERE, ROOT, WORK, digest, encode, read

from aeep.assessment.repository_suites import SuiteInput, SuiteTruthV6

SCREEN = HERE / "retained-issue-overlap-screen.json"
FRAME_BUDGET = 400_000
FRAME_ALLOWANCE = 4096


def metadata_limit(model, key):
    return next(
        item.max_length for item in model.model_fields[key].metadata if hasattr(item, "max_length")
    )


def long_suite(row):
    """Apply unchanged path and identity checks after the prior intake-size cutoff."""
    try:
        screen(row)
    except ValueError as error:
        if str(error) != "large_required_test_scope":
            return None
    else:
        return None
    issue, preserve = row["FAIL_TO_PASS"], row["PASS_TO_PASS"]
    if any(
        len(values) > metadata_limit(SuiteTruthV6, key)
        for key, values in (("fail_to_pass", issue), ("pass_to_pass", preserve))
    ):
        return None
    frame = len(json.dumps(dict.fromkeys(issue + preserve, "SKIPPED")).encode()) + FRAME_ALLOWANCE
    if frame > FRAME_BUDGET:
        return None
    _, roots = test_roots(issue + preserve)
    source = patch_paths(row["patch"])
    editable = {name for name in source if python_source(name, roots)}
    if (
        len(editable) < 2
        or any(source.values())
        or any(
            PurePosixPath(name).suffix not in {".md", ".rst"} for name in source.keys() - editable
        )
    ):
        return None
    overlay = patch_paths(row["test_patch"])
    if any(
        not any(PurePosixPath(name).is_relative_to(root) for root in roots)
        or any(change != "new file mode 100644" for change in changes)
        for name, changes in overlay.items()
    ):
        return None
    instruction = (row["problem_statement"] or "") + "\n" + (row["interface"] or "")
    if len(instruction) > min(3700, metadata_limit(SuiteInput, "task")):
        return None
    return identity(row, editable) | {
        "repository": repository(row["repo"]),
        "declared_python": row["install_config"]["python"],
        "requires_preinstall_review": bool(row["install_config"]["pre_install"]),
        "requires_requirements_review": bool(row["install_config"]["reqs_path"]),
        "required_tests": len(issue + preserve),
        "required_reply_shape_bytes": frame,
        "row_sha256": digest(encode(row)),
    }


def identity(row, editable):
    issue = frozenset(node.casefold() for node in row["FAIL_TO_PASS"])
    return {
        "case_id": row["instance_id"],
        "revision": row["base_commit"],
        "patch_sha256": digest(row["patch"].encode()),
        "edit_paths": frozenset(path.casefold() for path in editable),
        "issue_ids": issue,
        "issue_modules": frozenset(node.partition("::")[0] for node in issue),
    }


def artifact(reference):
    return read(ROOT / reference["path"], reference["sha256"])


def audit():
    prior = json.loads(SCREEN.read_bytes())
    binding = prior["verification"]
    driver = binding["driver"]
    artifact(driver)
    previous = runpy.run_path(str(ROOT / driver["path"]))
    index = json.loads(artifact(binding["private_index_location"]))
    union = json.loads(read(UNION, prior["supplemental_screen"]["union_manifest_sha256"]))
    envelopes = [
        entry
        for page in union["sources"]
        for entry in json.loads(
            artifact({"path": page["private_cache"], "sha256": page["sha256"]})
        )["rows"]
    ]
    rows = {entry["row"]["instance_id"]: entry for entry in envelopes}
    if len(rows) != len(envelopes) or len(rows) != union["rows"]:
        raise ValueError("publisher identity count changed")
    review = json.loads(
        read(previous["BASE"] / "acquisition-review.json", previous["SOURCE_REVIEW"])
    )
    prepared, _, exposed = previous_repositories()
    attempted = {repository(row["repository"]) for row in review["sources"]}
    selected = defaultdict(list)
    for group in index["unattempted_repository_groups"]:
        repo = group["repository_family"]
        for seed in group["case_seeds"]:
            source = rows[seed["case_id"]]["row"]
            checked = previous["shape"](screen(source), source)
            if seed["row_sha256"] != checked["row_sha256"] or checked["repository"] != repo:
                raise ValueError("earlier choice no longer matches its source")
            selected[repo].append(checked)
    for seed in index["supplemental_multifile_leads"]:
        source = rows[seed["case_id"]]["row"]
        checked = previous["shape"](screen(source), source)
        repo = seed["repository_family"]
        if seed["row_sha256"] != checked["row_sha256"] or checked["repository"] != repo:
            raise ValueError("earlier supplemental choice changed")
        selected[repo].append(checked)
    disjoint = previous["disjoint"]
    screened = Counter()
    candidates = defaultdict(list)
    for entry in envelopes:
        row = entry["row"]
        name = repository(row["repo"])
        if entry["truncated_cells"] or name in prepared | exposed | attempted:
            continue
        try:
            candidate = long_suite(row)
        except ValueError:
            continue
        if candidate is None:
            continue
        screened["shape_matched"] += 1
        if not all(disjoint(candidate, first) for first in selected[name]):
            screened["prior_case_overlap"] += 1
            continue
        candidates[name].append(candidate)
    retained = []
    for _, records in sorted(candidates.items()):
        kept = previous["select_group"](sorted(records, key=lambda row: row["case_id"]))
        for row in kept:
            retained.append(row | {"prior_cases_checked": len(selected[row["repository"]])})
    # The prior 26-row ceiling included possible overlaps. Count the selected rows here.
    earlier_distinct_multi = sum(
        seed["multiple_python_paths"]
        for group in index["unattempted_repository_groups"]
        for seed in group["case_seeds"]
    )
    earlier_supply = prior["conditional_prior_plus_projected_by_family"]["multi-file-repair"]
    standard_metadata = earlier_distinct_multi + len(index["supplemental_multifile_leads"])
    target = prior["recorded_balanced_two_cohort_profile"]["multi-file-repair"]
    report = {
        "schema_version": "aeep.c13.larger-multifile-intake.v1",
        "publisher_revision": union["revision_before_and_after"],
        "prior_screen_sha256": digest(SCREEN.read_bytes()),
        "publisher_manifest_sha256": digest(UNION.read_bytes()),
        "audit_driver_sha256": digest(Path(__file__).read_bytes()),
        "recorded_balanced_profile_multifile_target": target,
        "prior_prospective_multifile_source_rows": earlier_supply,
        "prior_metadata_only_multifile_rows_after_overlap_screen": standard_metadata,
        "new_shape_counts": dict(screened),
        "new_metadata_leads_after_overlap_screen": len(retained),
        "new_lead_repositories": len({row["repository"] for row in retained}),
        "required_test_count_by_lead": sorted(row["required_tests"] for row in retained),
        "declared_python_counts": dict(Counter(row["declared_python"] for row in retained)),
        "projected_capacity_before_new_leads": earlier_supply + standard_metadata,
        "projected_capacity_with_new_leads": earlier_supply + standard_metadata + len(retained),
        "required_reply_estimate_maximum_bytes": max(
            (row["required_reply_shape_bytes"] for row in retained), default=0
        ),
        "scope": "Existing publisher metadata only. Preserve every required identity and keep each repository in one stage. Reply estimates cover required identities; collection can add more. Source archives, local-use rights, runtime and actual grades remain unverified.",
        "archive_downloads": 0,
        "protected_tests_executed": 0,
        "formal_cases_adopted": 0,
        "model_turns": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }
    private = [
        {
            key: row[key]
            for key in (
                "case_id",
                "repository",
                "revision",
                "declared_python",
                "requires_preinstall_review",
                "requires_requirements_review",
                "required_tests",
                "required_reply_shape_bytes",
                "row_sha256",
                "patch_sha256",
                "prior_cases_checked",
            )
        }
        for row in retained
    ]
    report["private_leads_sha256"] = digest(encode(private))
    return report, private


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-leads", type=Path)
    args = parser.parse_args()
    result, leads = audit()
    if args.private_leads:
        path = args.private_leads.resolve()
        if path.parent != WORK:
            raise ValueError("private leads must stay under the C13 local evidence root")
        with path.open("xb") as stream:
            stream.write(encode(leads))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
