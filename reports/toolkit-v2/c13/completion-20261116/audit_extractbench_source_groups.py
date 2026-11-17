"""Project ExtractBench capacity using pinned metadata and conservative source grouping."""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from audit_document_corpus_capacity import EXTRACT
from audit_formal_inputs import REQUIRED
from stage_repository_transport import HERE, WORK, digest, read, write

MANIFEST = WORK / "document-corpus-metadata/extract-manifest"
INTAKE = HERE / "extractbench-audent-intake.json"
MANIFEST_SHA = "0452463e5b1be2c627c0b7d1a076531f0fd301b3297affdb7d9613735bc04840"
INTAKE_SHA = "a737313cdd760b2bed001820d67a52fa63e8a09c3767db43d9274c99c5ccb507"
LENGTHS = ("short", "medium", "long")
SCHEMA = "environment/schema.json"
ANSWER = "solution/expected.json"
PDF = "environment/document.pdf"
RECAPTURE = re.compile(r"[-_]corrupted(?=\.pdf$)")
PAGE_SUFFIX = re.compile(r"-p[0-9]{4}(?=\.pdf$)")


def partition(ids, edges):
    parents = dict(zip(ids, ids, strict=True))

    def root(identity):
        while identity != parents[identity]:
            identity = parents[identity]
        return identity

    first = {}
    for identity, key in edges:
        parents[root(identity)] = root(first.setdefault(key, identity))
    groups = defaultdict(list)
    for identity in ids:
        groups[root(identity)].append(identity)
    return sorted(tuple(sorted(group)) for group in groups.values())


def count_lengths(ids):
    counts = Counter(identity.split("--", 1)[0] for identity in ids)
    if not counts.keys() <= set(LENGTHS):
        raise ValueError("unexpected publisher length")
    return counts


def exact_stage(families, count):
    # An illustrative packing only. Each stage includes every published length.
    best = {(0, 0): ()}
    for index, sizes in sorted(families.items(), key=lambda item: (item[1].total(), item[0])):
        size = sizes.total()
        mask = sum(1 << bit for bit, length in enumerate(LENGTHS) if sizes[length])
        for (total, seen), chosen in tuple(best.items()):
            if total + size <= count:
                best.setdefault((total + size, seen | mask), (*chosen, index))
    return best.get((count, 7))


def example_capacity(families):
    pools = dict(enumerate(families))
    reserve = next((index for index, sizes in pools.items() if len(sizes) == len(LENGTHS)), None)
    witnesses = {"first": {}, "second": {}}
    for stage, target in REQUIRED.items():
        for cohort in witnesses:
            available = {
                key: val
                for key, val in pools.items()
                if key != reserve or (stage, cohort) == ("holdout", "second")
            }
            chosen = exact_stage(available, target)
            if chosen is None:
                return None
            lengths = sum((pools.pop(index) for index in chosen), Counter())
            if lengths.total() != target or lengths.keys() != set(LENGTHS):
                raise ValueError("invalid metadata packing")
            witnesses[cohort][stage] = {
                "slots": target,
                "lengths": dict(lengths),
                "families": len(chosen),
            }
    return {"cohorts": witnesses, "unused_slots": sum(sizes.total() for sizes in pools.values())}


def audit():
    rows = json.loads(read(MANIFEST, MANIFEST_SHA))["tasks"]
    intake = json.loads(read(INTAKE, INTAKE_SHA))
    keys = sorted(rows)
    pdfs = {identity: row["pdf"] for identity, row in rows.items()}
    by_path = {path: identity for identity, path in pdfs.items()}
    if len(by_path) != len(keys) or len({row["files"][PDF] for row in rows.values()}) != len(keys):
        raise ValueError("publisher paths or PDF hashes are duplicated")
    recaptures = {
        identity: RECAPTURE.sub("", pdf) for identity, pdf in pdfs.items() if RECAPTURE.search(pdf)
    }
    if any(path not in by_path for path in recaptures.values()):
        raise ValueError("named recapture has no published counterpart")
    relations = [
        (identity, (kind, value))
        for identity, row in rows.items()
        for kind, value in (
            ("answer", row["files"][ANSWER]),
            ("capture_path", RECAPTURE.sub("", pdfs[identity])),
            ("parent_path", PAGE_SUFFIX.sub("", pdfs[identity])),
        )
    ]
    same_document = partition(keys, relations)
    representatives = {
        min(group, key=lambda identity: (identity in recaptures, identity))
        for group in same_document
    }
    same_schema = [(identity, ("schema", row["files"][SCHEMA])) for identity, row in rows.items()]
    families = partition(keys, relations + same_schema)
    group_by_case = {identity: group for group in families for identity in group}
    exposed = group_by_case[intake["task"]["task_id"]]
    held_out_siblings = set(intake["related_schema_family"]["members"])
    if intake["development_only"] is not True or not held_out_siblings <= set(exposed):
        raise ValueError("prior development exposure is missing from the excluded family")
    for alternate, path in recaptures.items():
        if group_by_case[alternate] != group_by_case[by_path[path]]:
            raise ValueError("clean/degraded relation was lost")
    available = [
        count_lengths(representatives.intersection(group)) for group in families if group != exposed
    ]
    example = example_capacity(available)
    return {
        "schema_version": "aeep.c13.extractbench-source-group-capacity.v1",
        "data_revision": EXTRACT,
        "publisher_manifest_sha256": MANIFEST_SHA,
        "development_intake_sha256": INTAKE_SHA,
        "audit_sha256": digest(Path(__file__).read_bytes()),
        "published_tasks": len(keys),
        "distinct_published_schemas": len({key for _, (_, key) in same_schema}),
        "named_clean_degraded_pairs": len(recaptures),
        "named_pairs_with_different_answer_hashes": sum(
            rows[alternate]["files"][ANSWER] != rows[by_path[path]]["files"][ANSWER]
            for alternate, path in recaptures.items()
        ),
        "page_excerpt_count": sum(bool(PAGE_SUFFIX.search(pdf)) for pdf in pdfs.values()),
        "representatives_before_development_exclusion": len(representatives),
        "development_family_excluded": len(exposed),
        "family_count_after_exclusion": len(available),
        "remaining_metadata_slots_by_length": dict(sum(available, Counter())),
        "example_two_cohort_capacity": example,
        "scope": [
            "Metadata-only upper bound under known aliases. Unreviewed provenance can further reduce capacity.",
            "Identical answer hashes, named recaptures and page excerpts share one representative slot.",
            "Linked schema and alias groups stay within one stage across the two illustrative cohorts.",
            "No membership, order, rubric, length quota or formal stage is frozen. Length is not task difficulty.",
            "Matched source provenance, permitted use and protected reference and fault grading remain open.",
        ],
        "task_asset_downloads": 0,
        "upstream_graders_executed": 0,
        "model_turns": 0,
        "formal_cases_adopted": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write(args.output, (json.dumps(audit(), indent=2, sort_keys=True) + "\n").encode())
