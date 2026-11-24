"""Check distinct issue shapes before treating same-repository leads as capacity."""

import argparse
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import audit_two_cohort_source_capacity as capacity
from plan_repository_expansion import DATASET, REVISION, UNION, load, screen
from stage_repository_transport import ROOT, digest, encode, read, write

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, archive_files

MULTIFILE = "multi-file-repair"
BOUND = 15
SQLGLOT_ASSERTIONS = {
    "4683": "DEFAULT 0 ON CONVERSION ERROR",
    "5075": "PIVOT(MAX(type_id)",
    "5359": "LAMBDA x, y : COALESCE",
    "5431": "ALTER TABLE foo ADD col1 VARCHAR(512), col2",
    "5566": "CREATE SEQUENCE serial START 101",
    "6067": "INSERT INTO t DEFAULT VALUES RETURNING",
    "7187": "LAST_VALUE(x ORDER BY x IGNORE NULLS) OVER",
}


def publisher_rows(origins):
    metadata = load(UNION)
    if metadata["dataset"] != DATASET or metadata["revision_before_and_after"] != REVISION:
        raise ValueError("publisher dataset pin changed")
    found = {}
    for page in metadata["sources"]:
        path = ROOT / page["private_cache"]
        raw = read(path, page["sha256"])
        if len(raw) != page["bytes"]:
            raise ValueError("publisher page size changed")
        for item in json.loads(raw)["rows"]:
            row = item["row"]
            origin = capacity.lineage(row["repo"]), row["base_commit"]
            if origin not in origins or item["truncated_cells"]:
                continue
            key = origin, row["instance_id"]
            if found.setdefault(key, row) != row:
                raise ValueError("retained records disagree for one case")
    return found, digest(UNION.read_bytes())


def exact_shapes(rows):
    found = defaultdict(dict)
    for (origin, _), row in rows.items():
        try:
            lead = screen(row)
        except ValueError:
            continue
        if len(lead["candidate_python_paths"]) < 2:
            continue
        identities = {name.casefold() for name in row["FAIL_TO_PASS"]}
        shape = {
            "case_id": lead["case_id"],
            "patch": digest(row["patch"].encode()),
            "paths": {name.casefold() for name in lead["candidate_python_paths"]},
            "issue_tests": identities,
            "issue_modules": {name.partition("::")[0] for name in identities},
        }
        found[origin][lead["case_id"]] = shape
    return found


def conflict(first, second):
    output = {key for key in ("paths", "issue_tests", "issue_modules") if first[key] & second[key]}
    if first["patch"] == second["patch"]:
        output.add("patch")
    if first["case_id"] == second["case_id"]:
        output.add("case_id")
    return output


def select_group(origins, hard, conflicts, retained):
    """Return the largest conservative subset, preferring already staged sources."""
    if len(origins) > BOUND:
        raise ValueError("one repository exceeds the bounded distinct-issue screen")
    free = sorted(set(origins) - hard)
    for size in range(len(free), -1, -1):
        options = []
        for choice in combinations(free, size):
            selected = set(choice) | hard
            if not any(frozenset(pair) in conflicts for pair in combinations(selected, 2)):
                options.append(choice)
        if options:
            best = min(options, key=lambda choice: (-len(set(choice) & retained), choice))
            return set(best) | hard
    raise ValueError("protected grades conflict in the prospective issue screen")


def sqlglot_assertion_readback(rows, pairs):
    """Verify that overlapping test methods contain the distinct published examples."""
    manifest = capacity.load("formal-transport-preparation.json")
    history = capacity.load("retained-grader-evidence.json")["cases_with_verified_observations"]
    pool = capacity.referenced(
        {
            "path": manifest["prepared_pool_relative_path"],
            "sha256": manifest["prepared_pool_sha256"],
        }
    )
    recorded = {item["independent_case_id"]: item for item in pool}
    covered = {}
    for (origin, case), row in rows.items():
        number = case.removeprefix("tobymao__sqlglot-")
        if number not in SQLGLOT_ASSERTIONS:
            continue
        identity = case + "-declared-tests"
        item = RepositorySuiteCase.model_validate(recorded[identity])
        expected = history[identity]
        if (
            content_digest(item) != expected["case_sha256"]
            or origin != (capacity.lineage(item.source_repository), item.source_revision)
            or item.truth.fail_to_pass != row["FAIL_TO_PASS"]
        ):
            raise ValueError("publisher assertion must bind the already graded case")
        files = {
            path: set(body.splitlines())
            for path, body in archive_files(item.truth.tests.read(), large=True).items()
        }
        verified_lines = defaultdict(list)
        path = None
        for line in row["test_patch"].splitlines():
            if line.startswith("+++ b/"):
                path = line.removeprefix("+++ b/")
            elif line.startswith("+") and not line.startswith("+++ ") and line[1:].strip():
                if path not in files or line[1:].encode() not in files[path]:
                    raise ValueError("protected test overlay is missing a publisher addition")
                verified_lines[path].append(line[1:])
        (assertion,) = [
            line
            for lines in verified_lines.values()
            for line in lines
            if SQLGLOT_ASSERTIONS[number] in line
        ]
        covered[case] = {
            "publisher_issue": case,
            "protected_test_archive_sha256": item.truth.tests.sha256,
            "publisher_test_patch_sha256": digest(row["test_patch"].encode()),
            "confirmed_added_test_lines": sum(map(len, verified_lines.values())),
            "reviewed_assertion_sha256": digest(assertion.strip().encode()),
        }
    selected = [
        p
        for p in pairs
        if p["left"][0].startswith("tobymao__sqlglot-") and "issue_tests" in p["reasons"]
    ]
    required = {value for pair in selected for side in ("left", "right") for value in pair[side]}
    if required != set(covered) or len(
        {r["reviewed_assertion_sha256"] for r in covered.values()}
    ) != len(required):
        raise ValueError("a shared test method lacks distinct bound assertions")
    return {"shared_test_id_pairs_reviewed": len(selected), "cases": list(covered.values())}


def audit():
    verified, staged = capacity.source_pools()
    additional = capacity.load("retained-multifile-publisher-and-runtime-20261124.json")
    for row in additional["cases"]:
        origin = capacity.lineage(row["repository"]), row["revision"]
        if row["status"] != "matched_publisher_tree" or origin in staged:
            raise ValueError("additional staged origin is unbound or already counted")
        staged[origin] = {MULTIFILE}
    exposed = {capacity.lineage(name) for name in capacity.previous_repositories()[2]}
    attempted = capacity.attempted_origins()
    leads, _ = capacity.lead_pools(staged, exposed, attempted)
    multi = {origin for origin, families in (staged | leads).items() if MULTIFILE in families}
    rows, union_sha = publisher_rows(multi)
    excluded_cases = capacity.load("post-protected-corpus-status.json")["software"][
        "excluded_after_protected_check"
    ]
    excluded_origins = {
        origin for origin, case in rows if case in excluded_cases and origin in staged
    }
    if excluded_origins & verified.keys() or len(excluded_origins) != len(excluded_cases):
        raise ValueError("previously excluded cases do not match the retained evidence")
    for origin in excluded_origins:
        del staged[origin]
    shapes = exact_shapes(rows)
    if any(origin not in shapes for origin in multi & leads.keys()):
        raise ValueError("an unstarted detailed multi-file lead has no valid publisher shape")

    groups = defaultdict(set)
    for origin in multi - excluded_origins:
        groups[origin[0]].add(origin)
    held_staged, held_leads = set(), set()
    observed, reasons = Counter(), Counter()
    pairs = []
    for origins in groups.values():
        conflicts = set()
        for left, right in combinations(sorted(origins & shapes.keys()), 2):
            collision = set().union(
                *(
                    conflict(first, second)
                    for first in shapes[left].values()
                    for second in shapes[right].values()
                )
            )
            if not collision:
                continue
            reasons.update(collision)
            observed["same_repository_pairs_flagged"] += 1
            pairs.append(
                {
                    "left": sorted(shapes[left]),
                    "right": sorted(shapes[right]),
                    "reasons": sorted(collision),
                }
            )
            # Keep actual protected results intact. These collisions still need
            # task-level review before counting the affected cases as independent.
            if left in verified and right in verified:
                observed["paired_protected_grades_needing_task_level_review"] += 1
            else:
                conflicts.add(frozenset((left, right)))
        picked = select_group(origins, origins & verified.keys(), conflicts, staged.keys())
        held_staged.update((origins - picked) & staged.keys())
        held_leads.update((origins - picked) & leads.keys())

    for origin in held_staged:
        remaining = staged[origin] - {MULTIFILE}
        if remaining:
            staged[origin] = remaining
        else:
            del staged[origin]
    for origin in held_leads:
        del leads[origin]
    prior, seen, _ = (
        {capacity.lineage(name) for name in names} for names in capacity.previous_repositories()
    )
    reserve, _ = capacity.reserve_leads(
        {repo for repo, _ in staged | leads}
        | prior
        | seen
        | exposed
        | {repo for repo, _ in attempted}
    )
    before = len(multi)
    after = before - len(excluded_origins) - len(held_staged) - len(held_leads)
    required = sum(size // len(capacity.FAMILIES) for size in capacity.STAGES.values())
    return {
        "schema_version": "aeep.c13.multifile-issue-overlap.v1",
        "dataset_response_manifest_sha256": union_sha,
        "before_issue_screen": before,
        "previously_excluded_after_protected_check": sorted(excluded_cases),
        "after_known_issue_overlaps": after,
        "minimum_multifile_cases": required,
        "minimum_additional_cases_on_this_route": max(0, required - after),
        "multi_file_origins_with_complete_detailed_metadata": len(shapes),
        "staged_origins_requiring_separate_issue_scope_review": len(
            multi - excluded_origins - shapes.keys()
        ),
        "staged_multifile_alternatives_held": len(held_staged),
        "metadata_multifile_leads_held": len(held_leads),
        "collision_counts": dict(observed),
        "collision_reasons": dict(sorted(reasons.items())),
        "same_repository_public_issue_pairs": sorted(
            pairs, key=lambda pair: (pair["left"], pair["right"])
        ),
        "sqlglot_shared_test_assertions": sqlglot_assertion_readback(rows, pairs),
        "supplementary_metadata_still_needs_issue_shapes": len(reserve),
        "optimistic_capacity_after_known_overlap_screen": capacity.feasible_witness(
            verified, staged, leads, reserve
        ),
        "protected_tests": 0,
        "model_turns": 0,
        "formal_assignments": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(write(parser.parse_args().output, encode(audit())))
