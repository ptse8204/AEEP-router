"""Check balanced two-cohort capacity using retained receipts and published leads."""

import argparse
import json
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path

import audit_current_software_pool as current
from audit_corpus_capacity import FAMILIES, balanced, prior_origins
from audit_staged_repository_graders import index_paths
from plan_repository_expansion import TARGET, previous_repositories, repository
from stage_repository_transport import HERE, ROOT, digest, read, write

from aeep.assessment.models import content_digest

INVENTORY = "software-inventory-with-parser-audits-20261124.json"
ADDITIONS = (
    "protected-nested-pandas-20261124.json",
    "protected-pyformlang-20261124.json",
    "protected-pdoc-20261124.json",
)
STAGES = {"qualification": 8, "training": 28, "candidate_holdout": 105, "selection_holdout": 105}


def lineage(value):
    name = repository(value)
    return {"ds4sd/docling": "docling-project/docling"}.get(name, name)


def load(name):
    return json.loads((HERE / name).read_bytes())


def referenced(value):
    return json.loads(read(ROOT / value["path"], value["sha256"]))


def sealed_leads():
    summary = json.loads((TARGET / "summary.json").read_bytes())
    leads = referenced(summary["leads"])
    rows = referenced(summary["rows"])
    if len(leads) != len(rows) or len(leads) != summary["candidate_rows"]:
        raise ValueError("published lead count changed")
    return leads, rows, summary


def source_pools():
    case_inventory = load(INVENTORY)
    if current.audit(ADDITIONS) != case_inventory:
        raise ValueError("current software pool differs from settled protected evidence")
    verified = {
        (lineage(row["repository"]), row["revision"]): row["family"]
        for row in case_inventory["rows"]
    }
    if len(verified) != len(case_inventory["rows"]):
        raise ValueError("verified origin occurs more than once")

    staged = defaultdict(set)

    def add(slug, revision, family):
        if family not in FAMILIES:
            raise ValueError("unknown staged workload family")
        staged[(lineage(slug), revision)].add(family)

    def index(rows):
        for row in rows:
            add(row["source_repository"], row["source_revision"], row["input"]["family"])

    prior, _ = prior_origins()
    index(prior)
    for location, sha in index_paths():
        index(json.loads(read(location, sha)))
    legacy = load("retained-multifile-backup-preflight.json")
    index(referenced({"path": legacy["private_index"], "sha256": legacy["private_index_sha256"]}))
    for row in load("repository-expansion-acquisition-result.json")["candidates"]:
        add(row["repository"], row["revision"], row["family"])
    for row in load("scientific-python-source-intake-20261124.json")["cases"]:
        add(row["repository"], row["revision"], row["family"])
    followup = load("followup-source-batches-20261124.json")
    index(referenced(followup["case_dispositions"]["Point72__ccflow-24"]["transport_index"]))
    for origin, family in verified.items():
        staged[origin] = {family}
    return verified, dict(staged)


def attempted_origins():
    first = json.loads((TARGET / "acquisition-review.json").read_bytes())
    observed = load("repository-expansion-acquisition-result.json")
    if observed["review_sha256"] != digest((TARGET / "acquisition-review.json").read_bytes()):
        raise ValueError("retained source intake does not bind the historical review")
    if len(first["sources"]) != observed["attempts_reconciled"]:
        raise ValueError("some reviewed sources lack a terminal intake result")
    attempted = {(lineage(row["repository"]), row["revision"]) for row in first["sources"]}

    def add_attempts(scope_ref, result_ref):
        scope = referenced(scope_ref)
        result = referenced(result_ref)
        if result["review_sha256"] != scope_ref["sha256"]:
            raise ValueError("source result does not bind its review")
        sources = {row["case_id"]: row for row in scope["sources"]}
        for entry in result["observations"]:
            row = sources[entry["case_id"]]
            attempted.add((lineage(row["repository"]), row["revision"]))

    for item in load("followup-source-batches-20261124.json")["source_acquisitions"]:
        add_attempts(item["review"], item["result"])

    parser = load("parser-documentation-source-intake-20261124.json")
    add_attempts(parser["review"], parser["result"])

    scientific = load("scientific-python-source-intake-20261124.json")
    add_attempts(scientific["source_acquisition_review"], scientific["source_acquisition_result"])

    workspace = ROOT / ".aeep/c13-cohort-runtime-20261124"
    for marker in workspace.glob("*/intake/attempts/*/started.json"):
        review = marker.parents[3] / "review.json"
        if not review.exists():
            raise ValueError("source attempt is missing its exact review")
        raw = review.read_bytes()
        reviewed = json.loads(raw)
        if reviewed["schema_version"] not in {
            "aeep.c13.first-public-source-intake.v1",
            "aeep.c13.multi-snapshot-source-intake.v1",
        }:
            continue
        (source,) = [item for item in reviewed["sources"] if item["case_id"] == marker.parent.name]
        if json.loads(marker.read_bytes()) != {
            "case_id": source["case_id"],
            "review_sha256": digest(raw),
        }:
            raise ValueError("source attempt marker differs from the exact review")
        attempted.add((lineage(source["repository"]), source["revision"]))
    return attempted


def lead_pools(staged, exposed, attempted):
    leads, rows, summary = sealed_leads()
    choices = defaultdict(set)
    for lead in leads:
        origin = lineage(lead["repository"]), lead["revision"]
        source = rows[lead["case_id"]]
        if source["base_commit"] != origin[1] or lineage(source["repo"]) != origin[0]:
            raise ValueError("lead refers to a different source snapshot")
        if origin in staged or origin in attempted or origin[0] in exposed:
            continue
        choices[origin].update(
            {"multi-file-repair"}
            if len(lead["candidate_python_paths"]) > 1
            else {"single-file-repair", "contract-audit"}
        )
    return dict(choices), summary


def family_capacity(choices):
    return {family: sum(family in options for options in choices.values()) for family in FAMILIES}


def feasible_witness(verified, staged, leads, reserve):
    """Check an optimistic fit without writing a study assignment."""
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import coo_matrix

    choices = staged | leads | reserve
    repos = sorted({repo for repo, _ in choices})
    stage_names = list(STAGES)
    variables = list(product(repos, stage_names))
    group_index = {value: n for n, value in enumerate(variables)}
    placements = [
        (origin, stage, family)
        for origin, allowed in sorted(choices.items())
        for stage, family in product(stage_names, sorted(allowed))
    ]
    origin_rows, stage_rows, type_rows, group_rows = (defaultdict(list) for _ in range(4))
    for n, (origin, stage, family) in enumerate(placements, start=len(variables)):
        origin_rows[origin].append(n)
        stage_rows[stage].append(n)
        type_rows[stage, family].append(n)
        group_rows[origin[0], stage].append(n)

    offsets, cols, values, lower, upper = [], [], [], [], []

    def constraint(terms, least, most):
        n = len(lower)
        offsets.extend([n] * len(terms))
        cols.extend(col for col, _ in terms)
        values.extend(value for _, value in terms)
        lower.append(least)
        upper.append(most)

    def count(keys, least, most):
        constraint([(key, 1) for key in keys], least, most)

    for slug in repos:
        count([group_index[slug, stage] for stage in stage_names], 0, 1)
    for origin, columns in origin_rows.items():
        count(columns, int(origin in verified), 1)
    for stage, size in STAGES.items():
        count(stage_rows[stage], size, size)
        for family in FAMILIES:
            count(type_rows[stage, family], size // 3, (size + 2) // 3)
    for group, columns in group_rows.items():
        constraint(
            [(col, 1) for col in columns] + [(group_index[group], -len(columns))],
            -float("inf"),
            0,
        )

    total = len(variables) + len(placements)
    matrix = coo_matrix((values, (offsets, cols)), shape=(len(lower), total)).tocsc()
    # Prefer staged cases first and prefer detailed leaderboard leads over
    # the supplementary catalog's reported file counts.
    objective = [0] * len(variables) + [
        int(origin not in staged) * (sum(STAGES.values()) + 1) + int(origin in reserve)
        for origin, _, _ in placements
    ]
    result = milp(
        objective,
        integrality=[1] * total,
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(matrix, lower, upper),
        options={"time_limit": 30, "mip_rel_gap": 0.01},
    )
    if result.x is None:
        return {"witness_verified": False, "solver_status": result.status}
    selected = [
        row for flag, row in zip(result.x[len(variables) :], placements, strict=True) if flag > 0.5
    ]
    origins = [row[0] for row in selected]
    if len(origins) != len(set(origins)) or not verified.keys() <= set(origins):
        raise ValueError("solver split or discarded a required origin")
    by_repo, counts = defaultdict(set), defaultdict(Counter)
    for (repo, _), stage, family in selected:
        by_repo[repo].add(stage)
        counts[stage][family] += 1
    if any(len(stages) != 1 for stages in by_repo.values()) or any(
        counts[stage] not in tuple(balanced(size)) for stage, size in STAGES.items()
    ):
        raise ValueError("solver split a repository or missed a review threshold")
    new_count = sum(origin not in staged for origin in origins)
    return {
        "witness_verified": True,
        "solver_status": result.status,
        "selected_reproduced": len(verified),
        "selected_staged_ungraded": len(origins) - len(verified) - new_count,
        "selected_metadata_only": new_count,
        "selected_supplementary_metadata": sum(origin in reserve for origin in origins),
        "selected_repositories": len(by_repo),
        "stage_family_counts": {stage: dict(counts[stage]) for stage in stage_names},
        "metadata_only_by_family": dict(
            Counter(family for origin, _, family in selected if origin not in staged)
        ),
        "same_repo_same_stage_verified": True,
        "opaque_witness_sha256": content_digest(selected),
    }


def reserve_leads(excluded):
    intake = load("full-rebench-metadata-intake-20261118.json")
    selected = {
        "acoular/acoular",
        "bobotig/ebook-reader-dict",
        "mmcdermott/meds_transforms",
    }
    choices, lanes = {}, {}
    for lane in ("declared_3_13", "declared_3_12"):
        ref = intake["provisional_lanes"][lane]["catalog"]
        lanes[lane] = ref["sha256"]
        for row in referenced(ref):
            repo = lineage(row["repository"])
            if repo in selected - excluded and row["reported_modified_files"] >= 3:
                choices[(repo, row["base_commit"])] = {"multi-file-repair"}
    return choices, {"dataset_revision": intake["revision"], "catalog_sha256": lanes}


def audit():
    verified, staged = source_pools()
    prior, seen, exposure = ({lineage(x) for x in group} for group in previous_repositories())
    if any(repo in exposure for repo, _ in staged):
        raise ValueError("retained prospective pool includes an exposed repository")
    attempted = attempted_origins()
    leads, summary = lead_pools(staged, exposure, attempted)
    metadata_touched = {
        lineage(row["repository"])
        for row in json.loads((TARGET / "publisher-metadata.json").read_bytes())["rows"]
    }
    known_repos = {repo for repo, _ in staged}
    clean_first_route = known_repos | prior | seen | exposure | {repo for repo, _ in attempted}
    family_limit = family_capacity(staged)
    holdouts = 2 * (STAGES["candidate_holdout"] // len(FAMILIES))
    early_minimum = STAGES["qualification"] // len(FAMILIES) + STAGES["training"] // len(FAMILIES)
    multi = "multi-file-repair"

    def multi_repo_bound(excluded):
        return len(
            {
                repo
                for (repo, _), options in leads.items()
                if repo not in excluded and multi in options
            }
        )

    fresh = multi_repo_bound(clean_first_route | metadata_touched)
    metadata_only = multi_repo_bound(clean_first_route)
    reserve, reserve_source = reserve_leads(
        known_repos | {repo for repo, _ in leads} | clean_first_route
    )
    return {
        "schema_version": "aeep.c13.two-cohort-source-capacity.v1",
        "verified_software_cases": len(verified),
        "prospective_source_snapshots": len(staged),
        "prospective_family_ceilings": family_limit,
        "lineage_distinct_lead_snapshots": len(leads),
        "published_queue_sha256": summary["leads"]["sha256"],
        "required_stage_sizes": STAGES,
        "minimum_multi_file_cases_in_holdouts": holdouts,
        "minimum_multi_file_cases_in_all_four_stages": holdouts + early_minimum,
        "one_new_case_per_repository_route": {
            "fresh_multifile_repositories": fresh,
            "optimistic_multifile_ceiling": family_limit[multi] + fresh,
            "holdout_shortfall_at_least": max(0, holdouts - family_limit[multi] - fresh),
            "four_stage_shortfall_at_least": max(
                0, holdouts + early_minimum - family_limit[multi] - fresh
            ),
            "extra_families_if_metadata_only_lookups_are_reused": metadata_only - fresh,
            "four_stage_shortfall_after_metadata_only_reuse": max(
                0, holdouts + early_minimum - family_limit[multi] - metadata_only
            ),
        },
        "detailed_queue_multifile_ceiling": family_limit[multi] + family_capacity(leads)[multi],
        "conditional_same_stage_multiple_snapshot_route": feasible_witness(
            verified, staged, leads, reserve
        ),
        "additional_v1_metadata_leads": reserve_source
        | {
            "repository_families": len({repo for repo, _ in reserve}),
            "multi_file_hints": len(reserve),
        },
        "formal_assignments": 0,
        "model_turns": 0,
        "protected_tests": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proof", type=Path)
    result = audit()
    print(
        write(
            parser.parse_args().proof,
            (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(),
        )
    )
