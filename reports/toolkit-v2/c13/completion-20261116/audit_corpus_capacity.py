"""Check prospective stage capacity without assigning cases or running sources."""

import json
from collections import Counter, defaultdict
from itertools import combinations, product

from audit_formal_inputs import REQUIRED
from plan_repository_expansion import HERE, ROOT, load, previous_repositories, read, repository
from prepare_contract_audits import prior_origins
from stage_repository_transport import digest

FAMILIES = ("contract-audit", "multi-file-repair", "single-file-repair")
PREPARATION = HERE / "repository-expansion-preflight.json"
EXTRA_INDEXES = (
    ("additional-contract-audits.json", "private_index"),
    ("ancillary-contract-audits.json", "private_index"),
    ("cached-multifile-projections.json", "private_transport_index"),
)


def grouped(rows):
    counts = defaultdict(Counter)
    origins = set()
    for name, revision, family in rows:
        if (name, revision) in origins or family not in FAMILIES:
            raise ValueError("duplicate origin or unknown workload family")
        origins.add((name, revision))
        counts[name][family] += 1
    return dict(counts)


def balanced(size):
    baseline, extras = divmod(size, len(FAMILIES))
    for added in combinations(FAMILIES, extras):
        yield Counter({family: baseline + (family in added) for family in FAMILIES})


def totals(groups):
    return sum(groups.values(), Counter())


def minimum_profiles(available, additional):
    screening = tuple(balanced(REQUIRED["qualification"]))
    training = tuple(balanced(REQUIRED["training"]))
    (holdout,) = balanced(REQUIRED["holdout"])
    candidates = []
    for qualification, train in product(screening, training):
        extra = qualification + train + holdout - available
        if extra <= additional:
            candidates.append((extra, qualification, train, holdout))
    smallest = min((sum(extra.values()) for extra, *_ in candidates), default=0)
    return [candidate for candidate in candidates if sum(candidate[0].values()) == smallest]


def witness(retained, staged, candidate):
    """Realize a capacity bound with singleton groups in both early stages."""
    extra, qualification, training, holdout = candidate
    remaining = extra.copy()
    expanded = dict(retained)
    for name, count in sorted(staged.items()):
        if count <= remaining:
            expanded[name] = count
            remaining -= count
    if remaining:
        raise ValueError("known source review cannot supply the requested projection")

    # Keep large or mixed repositories available for holdout in this witness.
    # Only aggregate capacities are returned. This operation creates no cohort.
    early = {}
    for stage, targets in (("qualification", qualification), ("training", training)):
        early[stage] = targets
        for family, size in targets.items():
            singleton = [name for name, value in expanded.items() if value == {family: 1}]
            if len(singleton) < size:
                raise ValueError(
                    "cannot demonstrate disjoint stage capacity with singleton sources"
                )
            for name in sorted(singleton)[:size]:
                del expanded[name]
    if not holdout <= totals(expanded):
        raise ValueError("disjoint capacity lower than population-only lower bound")
    return {**early, "holdout": holdout}


def audit():
    prior, _ = prior_origins()
    for filename, field in EXTRA_INDEXES:
        record = load(HERE / filename)
        prior.extend(json.loads(read(ROOT / record[field], record[field + "_sha256"])))
    retained = grouped(
        (repository(row["source_repository"]), row["source_revision"], row["input"]["family"])
        for row in prior
    )
    prior_repositories, _, exposed = previous_repositories()
    if retained.keys() != prior_repositories or retained.keys() & exposed:
        raise ValueError("retained provisional source identities changed")
    preparation = load(PREPARATION)
    review = json.loads(read(ROOT / preparation["review_path"], preparation["review_sha256"]))
    staged = grouped(
        (
            repository(row["repository"]),
            row["revision"],
            "contract-audit" if row["intent"] == "audit" else row["intent"],
        )
        for row in review["sources"]
    )
    if (
        retained.keys() & staged.keys()
        or staged.keys() & exposed
        or max(map(sum, (value.values() for value in staged.values()))) != 1
    ):
        raise ValueError("proposal no longer has one origin per unused repository")
    available, added = totals(retained), totals(staged)
    profiles = minimum_profiles(available, added)
    options = {}
    for row in profiles:
        extra = row[0]
        options[tuple(extra[family] for family in FAMILIES)] = witness(retained, staged, row)
    if not options:
        raise ValueError("no balanced projection within the pending source review")
    lead_ref = preparation["leads"]
    leads = json.loads(read(ROOT / lead_ref["path"], lead_ref["sha256"]))
    replacement_repos = {
        repository(row["repository"])
        for row in leads
        if len(row["candidate_python_paths"]) > 1
        and repository(row["repository"]) not in (retained.keys() | staged.keys() | exposed)
    }
    (holdout,) = balanced(REQUIRED["holdout"])
    return {
        "schema_version": "aeep.c13.repository-capacity.v1",
        "source_preflight_sha256": digest(PREPARATION.read_bytes()),
        "source_review_sha256": preparation["review_sha256"],
        "retained_repositories": len(retained),
        "provisional_rows": sum(available.values()),
        "provisional_counts": dict(available),
        "proposed_unique_repositories": len(staged),
        "proposed_counts": dict(added),
        "reproduction_runs_performed_by_audit": 0,
        "required_stage_counts": REQUIRED,
        "row_count_lower_bound": sum(REQUIRED.values()) - sum(available.values()),
        "holdout_family_lower_bounds": dict(holdout - available),
        "minimum_additions_for_balance_in_each_stage": min(sum(key) for key in options),
        "minimal_new_source_profiles_with_disjoint_witnesses": [
            {
                "new_sources_required": dict(zip(FAMILIES, key, strict=True)),
                "pending_sources_that_may_fail_if_all_retained_rows_survive": {
                    family: added[family] - need for family, need in zip(FAMILIES, key, strict=True)
                },
                "stage_capacity_example": stages,
            }
            for key, stages in sorted(options.items())
        ],
        "other_multifile_repository_leads": len(replacement_repos),
        "formal_stages_assigned": False,
        "verification": "Read-only counts. Witnesses use repository families in one stage.",
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
