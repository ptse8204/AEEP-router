"""Check whether verified ExtractBench schemas can support balanced cohorts."""

import argparse
import json
from collections import Counter
from pathlib import Path

from audit_extractbench_schema_variations import (
    ANSWER,
    CFPB,
    CFPB_SHA,
    INTAKE,
    INTAKE_SHA,
    MANIFEST_SHA,
    PAGE_SUFFIX,
    RECAPTURE,
    SCHEMA,
    digest,
    metadata,
    partition,
    read,
    unique_object,
)

AT_MOST_ONE = "at-most-one-collection"
MULTIPLE = "multiple-collections"
SINGLE_LIMIT = 122
MATCHED_LIMIT = 124
SPLITS = ("qualification", "training", "first_holdout", "second_holdout")


def collection_paths(raw):
    root = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(root, dict) or root.get("type") != "object":
        raise ValueError("expected object schema")
    result = set()
    visited = set()

    def walk(node, path, ancestors):
        if isinstance(node, bool):
            return
        if (not isinstance(node, dict) or id(node) in ancestors or len(ancestors) > 64
                or len(visited) > 20_000):
            raise ValueError("unsupported or recursive schema")
        point = id(node), path
        if point in visited:
            return
        visited.add(point)
        lineage = ancestors | {id(node)}
        kind = node.get("type", [])
        if (kind == "array" or (isinstance(kind, list) and "array" in kind)
                or node.keys() & {"items", "prefixItems", "contains"}):
            result.add(path)
        if node.keys() & {"$dynamicRef", "$recursiveRef"}:
            raise ValueError("unsupported lookup")
        if "$ref" in node:
            ref = node["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/") or "%" in ref:
                raise ValueError("unsupported reference")
            target = root
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
            walk(target, path, lineage)
        for key in ("properties", "patternProperties"):
            for name, child in node.get(key, {}).items():
                walk(child, (*path, (key, name)), lineage)
        for key in ("allOf", "anyOf", "oneOf"):
            for child in node.get(key, ()):
                walk(child, path, lineage)
        for child in node.get("dependentSchemas", {}).values():
            walk(child, path, lineage)
        for key in ("then", "else"):
            if key in node:
                walk(node[key], path, lineage)
        for key in ("additionalProperties", "unevaluatedProperties"):
            if key in node:
                walk(node[key], (*path, (key, "")), lineage)
        if "contains" in node:
            walk(node["contains"], (*path, ("item", "*")), lineage)
        if "items" in node and not isinstance(node["items"], list):
            walk(node["items"], (*path, ("item", "*")), lineage)
        sequence = node.get("prefixItems", node.get("items", ()))
        if isinstance(sequence, list):
            for index, child in enumerate(sequence):
                walk(child, (*path, ("item", str(index))), lineage)

    walk(root, (), set())
    return result


def eligible_groups(rows):
    links = [
        (identity, (kind, key))
        for identity, row in rows.items()
        for kind, key in (
            ("answer", row["files"][ANSWER]),
            ("capture", RECAPTURE.sub("", row["pdf"])),
            ("parent", PAGE_SUFFIX.sub("", row["pdf"])),
        )
    ]
    representatives = {
        min(group, key=lambda name: (bool(RECAPTURE.search(rows[name]["pdf"])), name))
        for group in partition(sorted(rows), links)
    }
    schema_links = [(identity, ("schema", row["files"][SCHEMA])) for identity, row in rows.items()]
    development = json.loads(read(INTAKE, INTAKE_SHA))["task"]["task_id"]
    cfpb = {row["case"] for row in json.loads(read(CFPB, CFPB_SHA))["cases"]}
    groups = {
        digest(json.dumps(group).encode()): sorted(representatives.intersection(group))
        for group in partition(sorted(rows), links + schema_links)
        if development not in group and not cfpb.intersection(group)
    }
    if sum(map(len, groups.values())) != 291:
        raise ValueError("unexpected source capacity")
    return groups


def cohort_witness(known_groups, holdout_size):
    """Find a bounded whole-family allocation with minimal excess per split."""
    remaining = dict(known_groups)
    chosen = {}
    allowance = (4, 14, holdout_size, holdout_size)
    for split, target in zip(SPLITS, allowance, strict=True):
        limit = target + max(map(len, remaining.values()), default=0)
        options = {0: ()}
        for group, cases in remaining.items():
            for total, previous in tuple(options.items()):
                if total < target and total + len(cases) < limit:
                    options.setdefault(total + len(cases), (*previous, group))
        capacities = [total for total in options if total >= target]
        if not capacities:
            return None
        groups = options[min(capacities)]
        candidates = [(group, case) for group in groups for case in remaining.pop(group)]
        chosen[split] = candidates[:target]
    return chosen


def feasibility(rows, groups, path_counts):
    counts = Counter()
    groups_by_label = {AT_MOST_ONE: {}, MULTIPLE: {}}
    lengths = {AT_MOST_ONE: Counter(), MULTIPLE: Counter(), "unresolved": Counter()}
    mixed_groups = 0
    for group, cases in groups.items():
        labels = {}
        for case in cases:
            paths = path_counts.get(rows[case]["files"][SCHEMA])
            name = "unresolved" if paths is None else AT_MOST_ONE if paths < 2 else MULTIPLE
            labels[case] = name
            counts[name] += 1
            lengths[name][case.split("--", 1)[0]] += 1
        categories = set(labels.values()) - {"unresolved"}
        if len(categories) == 1:
            name, = categories
            groups_by_label[name][group] = [case for case in cases if labels[case] == name]
        elif categories:
            mixed_groups += 1

    witness = None
    for low_target, high_target in ((52, 53), (53, 52)):
        low = cohort_witness(groups_by_label[AT_MOST_ONE], low_target)
        high = cohort_witness(groups_by_label[MULTIPLE], high_target)
        if low is None or high is None:
            continue
        witness = {split: low[split] + high[split] for split in SPLITS}
        allocated = [{group for group, _ in entries} for entries in witness.values()]
        if len(set.union(*allocated)) != sum(map(len, allocated)):
            raise ValueError("source group used across splits")
        break
    return counts, lengths, mixed_groups, witness


def observed_paths(cache, sources):
    path_counts, unsupported = {}, {}
    for pin, observation in sources["sources"].items():
        if observation["status"] == "verified":
            raw = read(cache / "schemas" / pin, pin)
            try:
                path_counts[pin] = len(collection_paths(raw))
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                unsupported[pin] = type(error).__name__
    return path_counts, unsupported


def audit(cache, review_path, review_pin):
    review = json.loads(read(review_path, review_pin))
    sources = json.loads(read(cache / "schema-acquisition.json", review["acquisition_sha256"]))
    if review["required_stage_sizes"] != {"qualification": 8, "training": 28, "holdout": 105}:
        raise ValueError("reviewed counts changed")
    rows, schema_refs = metadata()
    if set(schema_refs) != sources["sources"].keys():
        raise ValueError("cached inventory differs")
    path_counts, unsupported = observed_paths(cache, sources)
    counts, lengths, mixed_groups, witness = feasibility(rows, eligible_groups(rows), path_counts)
    summary = {
        "schema_version": "aeep.c13.extractbench-collection-shape-capacity.v1",
        "classifier_and_allocation_sha256": digest(Path(__file__).read_bytes()),
        "review_sha256": review_pin, "publisher_manifest_sha256": MANIFEST_SHA,
        "schema_acquisition_sha256": review["acquisition_sha256"],
        "schemas_by_array_path_count": dict(Counter(path_counts.values())),
        "unsupported_schema_pins": unsupported,
        "variation_slot_counts": dict(counts),
        "variation_lengths": lengths,
        "mixed_groups_excluded_from_witness": mixed_groups,
        "minimum_cases_per_variant_with_shared_early_stages": SINGLE_LIMIT,
        "minimum_cases_in_larger_variant_with_matching_holdout_mix": MATCHED_LIMIT,
        "min_additional_by_variant_in_best_case": {
            label: max(0, SINGLE_LIMIT - counts[label] - counts["unresolved"])
            for label in (AT_MOST_ONE, MULTIPLE)
        },
        "witness": (
            {split: {"observations": len(entries),
                     "by_length": Counter(case.split("--", 1)[0] for _, case in entries)}
             for split, entries in witness.items()} if witness else None
        ),
        "formal_cases_adopted": 0, "model_turns": 0, "protected_graders_executed": 0,
    }
    return summary, witness


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--review-pin", required=True)
    parser.add_argument("--witness", required=True, type=Path)
    args = parser.parse_args()
    summary, witness = audit(args.cache, args.review, args.review_pin)
    with args.witness.open("x") as out:
        out.write(json.dumps(witness, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
