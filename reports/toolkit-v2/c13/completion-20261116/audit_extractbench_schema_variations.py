"""Classify public ExtractBench schema bytes before any cohort is frozen."""

import argparse
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path

from audit_extractbench_source_groups import (
    ANSWER,
    EXTRACT,
    HERE,
    INTAKE,
    INTAKE_SHA,
    MANIFEST,
    MANIFEST_SHA,
    PAGE_SUFFIX,
    RECAPTURE,
    SCHEMA,
    WORK,
    digest,
    partition,
    read,
)

CFPB = HERE / "extractbench-cfpb-protected-preparation.json"
CFPB_SHA = "10c71bc17c7961e2268c30140957bd22967d2869b63415258762d6b062a61141"
ORIGINAL_REVISION = "51bf3a03eb7feeaef8952be1fc2fc7f924ee72dc"
PUBLISHER = f"https://huggingface.co/datasets/llamaindex/ExtractBench/raw/{EXTRACT}"
WITH_ARRAY = "array-valued"
WITHOUT_ARRAY = "fixed-fields"
MAX_SCHEMA_BYTES = 128 * 1024
MAX_DOWNLOAD_BYTES = 4 * 1024 * 1024
LOCAL_SCHEMAS = (
    WORK / "extractbench-audent-source/agent/environment/schema.json",
    WORK / "extractbench-cfpb-workflow-bound/pack-assets/tasks"
    / "short--cfpb-closing-disclosure-h25f-094db1040b/environment/schema.json",
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def unique_object(pairs):
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError("duplicate schema key")
    return value


def variation(raw):
    """Follow constraint children and local JSON Pointers, ignoring annotations."""
    root = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(root, dict) or root.get("type") != "object":
        raise ValueError("expected a named-field schema")
    pending = [root]
    seen = set()
    found = False
    while pending:
        node = pending.pop()
        if isinstance(node, bool) or id(node) in seen:
            continue
        if not isinstance(node, dict):
            raise ValueError("invalid schema node")
        seen.add(id(node))
        kind = node.get("type", [])
        if kind == "array" or (isinstance(kind, list) and "array" in kind):
            found = True
        if node.keys() & {"items", "prefixItems", "contains"}:
            found = True
        for ref_key in ("$ref", "$dynamicRef", "$recursiveRef"):
            if ref_key not in node:
                continue
            ref = node[ref_key]
            if ref_key != "$ref" or not isinstance(ref, str) or not ref.startswith("#/") or "%" in ref:
                raise ValueError("unsupported schema reference")
            target = root
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
            pending.append(target)
        for key in ("properties", "patternProperties", "dependentSchemas"):
            pending.extend(node.get(key, {}).values())
        for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
            pending.extend(node.get(key, ()))
        for key in ("items", "contains", "additionalProperties", "unevaluatedProperties",
                    "then", "else"):
            if key in node:
                item = node[key]
                pending.extend(item if isinstance(item, list) else [item])
    return WITH_ARRAY if found else WITHOUT_ARRAY


def metadata():
    manifest = json.loads(read(MANIFEST, MANIFEST_SHA))
    if (manifest["source_repo"] != "llamaindex/ExtractBench"
            or manifest["source_revision"] != ORIGINAL_REVISION):
        raise ValueError("unexpected publisher revision")
    rows = manifest["tasks"]
    refs = {}
    for identity, row in sorted(rows.items()):
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]+", identity):
            raise ValueError("unexpected publisher path")
        pin = row["files"][SCHEMA]
        if not re.fullmatch(r"[0-9a-f]{64}", pin):
            raise ValueError("invalid schema digest")
        refs.setdefault(pin, identity)
    if len(rows) != 370 or len(refs) != 71:
        raise ValueError("publisher inventory changed")
    return rows, refs


def acquire(directory, refs):
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    local = {digest(raw): raw for path in LOCAL_SCHEMAS if path.is_file()
             for raw in [path.read_bytes()]}
    downloaded = 0
    outcomes = {}
    client = urllib.request.build_opener(NoRedirect())
    for pin, identity in refs.items():
        source = f"{PUBLISHER}/tasks/{identity}/{SCHEMA}"
        if pin in local:
            raw = local[pin]
            kind = "retained"
        else:
            if downloaded == MAX_DOWNLOAD_BYTES:
                outcomes[pin] = {"source": source, "status": "download_ceiling"}
                continue
            try:
                with client.open(source, timeout=12) as response:
                    raw = response.read(min(MAX_SCHEMA_BYTES, MAX_DOWNLOAD_BYTES - downloaded))
                downloaded += len(raw)
                kind = "publisher"
            except OSError as error:
                outcomes[pin] = {"source": source, "status": type(error).__name__}
                continue
        if digest(raw) != pin:
            outcomes[pin] = {"source": source, "status": "digest_mismatch"}
            continue
        (directory / pin).write_bytes(raw)
        outcomes[pin] = {"source": source, "status": "verified", "bytes": len(raw), "kind": kind}
    return {"downloaded_bytes": downloaded, "sources": outcomes}


def audit(directory, rows, refs, acquisition):
    labels, unsupported = {}, {}
    for pin in refs:
        if acquisition["sources"][pin]["status"] != "verified":
            continue
        raw = read(directory / pin, pin)
        try:
            labels[pin] = variation(raw)
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            unsupported[pin] = type(error).__name__
    relations = [(identity, (kind, value))
                 for identity, row in rows.items()
                 for kind, value in (
                     ("answer", row["files"][ANSWER]),
                     ("capture", RECAPTURE.sub("", row["pdf"])),
                     ("parent", PAGE_SUFFIX.sub("", row["pdf"])),
                 )]
    representatives = {min(group, key=lambda name: (bool(RECAPTURE.search(rows[name]["pdf"])), name))
                       for group in partition(sorted(rows), relations)}
    schemas = [(identity, ("schema", row["files"][SCHEMA])) for identity, row in rows.items()]
    families = partition(sorted(rows), relations + schemas)
    intake = json.loads(read(INTAKE, INTAKE_SHA))["task"]["task_id"]
    cfpb = {row["case"] for row in json.loads(read(CFPB, CFPB_SHA))["cases"]}
    eligible = [sorted(representatives.intersection(group)) for group in families
                if intake not in group and not cfpb.intersection(group)]
    if sum(map(len, eligible)) != 291:
        raise ValueError("retained cohort capacity changed")
    counts = Counter()
    lengths = {label: Counter() for label in (WITH_ARRAY, WITHOUT_ARRAY, "unknown")}
    for group in eligible:
        for case in group:
            label = labels.get(rows[case]["files"][SCHEMA], "unknown")
            counts[label] += 1
            lengths[label][case.split("--", 1)[0]] += 1
    return {
        "schema_version": "aeep.c13.extractbench-variation-capacity.v1",
        "manifest_sha256": MANIFEST_SHA, "publisher_revision": EXTRACT,
        "original_source_revision": ORIGINAL_REVISION,
        "cfpb_exclusion_sha256": CFPB_SHA,
        "development_exclusion_sha256": INTAKE_SHA,
        "classifier_sha256": digest(Path(__file__).read_bytes()),
        "acquisition": acquisition, "labels_by_schema_sha256": labels,
        "unsupported_schemas": unsupported,
        "eligible_source_families": len(eligible),
        "families_with_multiple_known_variations": sum(
            len({labels[rows[case]["files"][SCHEMA]] for case in group
                 if rows[case]["files"][SCHEMA] in labels}) > 1 for group in eligible
        ),
        "capacity_by_variation": dict(counts), "capacity_by_variation_and_length": lengths,
        "minimum_per_variation_for_two_balanced_holdouts": 104,
        "minimum_per_variation_with_balanced_shared_early_stages": 122,
        "minimum_shortfall_with_shared_early_stages": {
            label: max(0, 122 - counts[label] - counts["unknown"])
            for label in (WITH_ARRAY, WITHOUT_ARRAY)
        },
        "formal_cases_adopted": 0, "protected_graders_executed": 0, "model_turns": 0,
        "scope": "Schema shape feasibility before rights review and source-disjoint assignment.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--acquire", action="store_true", help="Fetch only pinned public schema bytes once")
    args = parser.parse_args()
    rows, refs = metadata()
    directory = args.directory / "schemas"
    acquisition_path = args.directory / "schema-acquisition.json"
    if args.acquire:
        observation = acquire(directory, refs)
        with acquisition_path.open("x") as stream:
            stream.write(json.dumps(observation, sort_keys=True, indent=2) + "\n")
    else:
        observation = json.loads(acquisition_path.read_bytes())
    print(json.dumps(audit(directory, rows, refs, observation), sort_keys=True, indent=2))
