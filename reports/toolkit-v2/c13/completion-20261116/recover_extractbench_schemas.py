"""Recover only the exact five public schema bodies selected by an operator."""

import argparse
import json
import urllib.request
from pathlib import Path

from audit_extractbench_collection_shapes import eligible_groups, feasibility, observed_paths
from audit_extractbench_schema_variations import (
    EXTRACT,
    MANIFEST_SHA,
    PUBLISHER,
    SCHEMA,
    NoRedirect,
    digest,
    metadata,
    read,
)


def write(path, value):
    with path.open("x") as output:
        output.write(json.dumps(value, sort_keys=True, indent=2) + "\n")


def bound_inputs(review, work):
    if (review["publisher_revision"] != EXTRACT or review["manifest_sha256"] != MANIFEST_SHA
            or review["driver_sha256"] != digest(Path(__file__).read_bytes())):
        raise ValueError("source or executable changed from the review")
    from audit_extractbench_collection_shapes import __file__ as classifier
    if review["classifier_sha256"] != digest(Path(classifier).read_bytes()):
        raise ValueError("classifier changed from the review")
    for name, pin in review["helper_sha256"].items():
        if "/" in name or "\\" in name:
            raise ValueError("helper must be a local filename")
        read(Path(__file__).resolve().parent / name, pin)
    cache = Path(review["retained_cache"])
    acquisition = json.loads(read(cache / "schema-acquisition.json", review["acquisition_sha256"]))
    rows, refs = metadata()
    requests = review["requests"]
    failed = {pin for pin, item in acquisition["sources"].items()
              if item["status"] == "digest_mismatch"}
    if (len(requests) != 5 or {item["schema_sha256"] for item in requests} != failed
            or review["maximum_body_read_bytes"] != sum(item["published_size_bytes"] + 1
                                                       for item in requests)):
        raise ValueError("scope must bind exactly the unresolved artifacts and their sizes")
    for item in requests:
        pin = item["schema_sha256"]
        relative = f"tasks/{refs[pin]}/{SCHEMA}"
        tree = json.loads(read(work / item["publisher_metadata_file"], item["publisher_metadata_sha256"]))
        row, = [asset for asset in tree if asset["path"] == relative]
        if (item["schema_url"] != f"{PUBLISHER}/{relative}"
                or row["oid"] != item["published_git_blob"]
                or row["size"] != item["published_size_bytes"]
                or row["type"] != "file" or row.get("lfs")
                or not 0 < row["size"] < 1024 * 1024):
            raise ValueError("published file differs from the exact review")
    retained = {pin: read(cache / "schemas" / pin, pin)
                for pin, item in acquisition["sources"].items() if item["status"] == "verified"}
    if set(retained) | failed != refs.keys() or len(retained) != 66:
        raise ValueError("retained schema inventory changed")
    return rows, acquisition, retained


def checked_reply(item, raw):
    if len(raw) != item["published_size_bytes"] or digest(raw) != item["schema_sha256"]:
        raise ValueError("response length or checksum differs from the publisher pin")


def require_approval(work, review_pin):
    path = work / "recovery-approval.json"
    if not path.is_file() or path.is_symlink() or json.loads(path.read_bytes()) != {
        "approved": True, "review_sha256": review_pin,
    }:
        raise ValueError("exact operator approval is required for this repeat")
    if (work / "recovery").exists():
        raise ValueError("recovery already attempted; inspect the retained record")


def recover(work, review, review_pin, rows, acquisition, retained):
    require_approval(work, review_pin)
    output = work / "recovery"
    output.mkdir(mode=0o700, exist_ok=False)
    write(output / "started.json", {"review_sha256": review_pin})
    schema_root = output / "schemas"
    schema_root.mkdir(mode=0o700)
    for pin, raw in retained.items():
        (schema_root / pin).write_bytes(raw)

    client = urllib.request.build_opener(NoRedirect())
    observations = []
    for item in review["requests"]:
        pin, source = item["schema_sha256"], item["schema_url"]
        observation = {"pin": pin, "source": source, "body_read_bytes": None}
        try:
            with client.open(source, timeout=15) as response:
                raw = response.read(item["published_size_bytes"] + 1)
            observation["body_read_bytes"] = len(raw)
            checked_reply(item, raw)
        except (OSError, ValueError) as error:
            observation["status"] = type(error).__name__
        else:
            (schema_root / pin).write_bytes(raw)
            observation["status"] = "verified"
            acquisition["sources"][pin] = {
                "source": source, "status": "verified", "bytes": len(raw), "kind": "publisher-recovery",
            }
        observations.append(observation)
        write(output / (pin + ".json"), observation)

    write(output / "recovered-acquisition.json", {"sources": acquisition["sources"],
                                                   "recovery_observations": observations})
    paths, unsupported = observed_paths(output, acquisition)
    counts, _, _, witness = feasibility(rows, eligible_groups(rows), paths)
    write(output / "provisional-layout.json", witness)
    write(output / "result.json", {
        "review_sha256": review_pin, "requests": observations, "variation_slot_counts": counts,
        "unsupported_schema_pins": unsupported, "provisional_layout_found": witness is not None,
        "formal_cases_adopted": 0, "model_turns": 0, "protected_graders_executed": 0,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--reviewed-digest", required=True)
    parser.add_argument("--execute-approved", action="store_true")
    args = parser.parse_args()
    exact = json.loads(read(args.review, args.reviewed_digest))
    work = args.review.parent
    rows, acquisition, retained = bound_inputs(exact, work)
    if args.execute_approved:
        recover(work, exact, args.reviewed_digest, rows, acquisition, retained)
    else:
        print(json.dumps({"review_sha256": args.reviewed_digest,
                          "retained_schema_bodies_verified": len(retained),
                          "reviewed_body_count": len(exact["requests"]),
                          "requests_dispatched": 0}, indent=2))
