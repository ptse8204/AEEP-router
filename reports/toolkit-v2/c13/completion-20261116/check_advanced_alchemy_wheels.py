"""Acquire and inspect the exact remaining unit-grader wheels as inert files."""

import argparse
import json
import shutil
import urllib.request
from pathlib import Path

from acquire_larger_multifile_source import AUTHORITY, binding
from check_expansion_contracts import inspect_wheel
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from reacquire_repository_sources import NoRedirect
from stage_advanced_alchemy_unit_grader import TARGET, prepare
from stage_repository_transport import ROOT, digest, encode, read, write

DESTINATION = TARGET / "wheel-acquisition"
REVIEW = TARGET / "wheel-acquisition-review.json"
MAX_BYTES = 20 * 1024**2
RESERVE = 52 * 1024**3


def reviewed_closure():
    spec = prepare(None)
    preflight = TARGET / "preflight.json"
    if spec != json.loads(preflight.read_bytes()):
        raise ValueError("wheel projection changed")
    inventory = TARGET / "cache-projection.json"
    cache = json.loads(inventory.read_bytes())
    candidate = {row["project"]: row for row in spec["wheel_candidates"]}
    retain = {row["project"]: row for row in cache["verified_cache"]}
    missing = {row["project"]: row for row in cache["missing"]}
    if (
        len(candidate) != len(spec["wheel_candidates"])
        or len(retain) != len(cache["verified_cache"])
        or len(missing) != len(cache["missing"])
        or retain.keys() & missing.keys()
        or retain.keys() | missing.keys() != candidate.keys()
        or any(candidate[name] != row for name, row in missing.items())
    ):
        raise ValueError("cache partition differs from the locked closure")
    for name, row in retain.items():
        path = ROOT / row["path"]
        wheel = candidate[name]
        if (
            not path.is_relative_to(ROOT / ".aeep")
            or path.name != wheel["filename"]
            or row["sha256"] != wheel["sha256"]
            or len(read(path, wheel["sha256"])) != wheel["bytes"]
        ):
            raise ValueError("retained wheel changed")
    count = len(missing)
    required_bytes = sum(row["bytes"] for row in missing.values())
    if count != 12 or not 0 < required_bytes <= MAX_BYTES:
        raise ValueError("new wheel scope exceeds the first reviewed batch")
    return {
        "schema_version": "aeep.c13.advanced-alchemy-wheel-intake.v1",
        "driver": binding(Path(__file__)),
        "inspector": binding(Path(inspect_wheel.__code__.co_filename)),
        "delegated_authority": binding(AUTHORITY),
        "protected_unit_preflight": binding(preflight),
        "cache_projection": binding(inventory),
        "retained_wheels": cache["verified_cache"],
        "acquire": cache["missing"],
        "maximum_downloads": count,
        "maximum_response_bytes": required_bytes + count,
        "minimum_usable_storage_bytes": RESERVE + required_bytes,
        "automatic_retries": 0,
        "models": 0,
        "cash_usd": 0,
        "installs": 0,
        "code_execution": False,
        "comparison_dispatch": False,
    }, candidate


def verify_files(review, candidates, downloaded):
    local = {row["project"]: ROOT / row["path"] for row in review["retained_wheels"]}
    local.update((row["project"], downloaded / row["filename"]) for row in review["acquire"])
    versions = {name: row["version"] for name, row in candidates.items()}
    facts = []
    for key, path in sorted(local.items()):
        wheel = candidates[key]
        raw = read(path, wheel["sha256"])
        if len(raw) != wheel["bytes"]:
            raise ValueError("wheel size differs from the project lock")
        outcome = inspect_wheel(path, key, wheel["sha256"], wheel["version"])
        for value in outcome["active_requires_dist"]:
            req = Requirement(value)
            version = versions.get(canonicalize_name(req.name))
            if req.url or req.extras or version is None or version not in req.specifier:
                raise ValueError(f"active wheel dependency is unresolved for {key}: {req}")
        facts.append(outcome)
    return facts


def execute(pin):
    approval = TARGET / "wheel-acquisition-authority.json"
    review, candidates = reviewed_closure()
    record = json.loads(read(REVIEW, pin))
    if (
        record != review
        or json.loads(approval.read_bytes())["exact_review_sha256"] != pin
        or shutil.disk_usage(TARGET).free < review["minimum_usable_storage_bytes"]
    ):
        raise ValueError("wheel intake authority, storage or pins changed")
    DESTINATION.mkdir(mode=0o700)
    journal = DESTINATION / "journal"
    journal.mkdir()
    write(DESTINATION / "started.json", encode({"review_sha256": pin}))
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    count = transferred = 0
    try:
        for row in review["acquire"]:
            path = DESTINATION / row["filename"]
            source = row["wheel_url"]
            if (
                source
                != "https://files.pythonhosted.org/packages/" + source.split("/packages/", 1)[1]
                or source.rsplit("/", 1)[-1] != path.name
            ):
                raise ValueError("wheel URL escaped its reviewed publisher path")
            write(journal / f"{row['project']}-started.json", encode(row))
            count += 1
            with client.open(source, timeout=30) as response:
                if response.geturl() != source or response.status != 200:
                    raise ValueError("unexpected wheel publisher response")
                raw = response.read(row["bytes"] + 1)
            transferred += len(raw)
            if len(raw) != row["bytes"] or digest(raw) != row["sha256"]:
                raise ValueError("publisher wheel size or checksum mismatch")
            write(path, raw)
            path.chmod(0o400)
        facts = verify_files(review, candidates, DESTINATION)
    except Exception as exc:
        write(
            DESTINATION / "result.json",
            encode(
                {
                    "verified": False,
                    "error": type(exc).__name__,
                    "detail": str(exc).splitlines()[0][:190],
                    "requests": count,
                    "bytes_read": transferred,
                    "review_sha256": pin,
                }
            ),
        )
        raise
    result = {
        "verified": True,
        "requests": count,
        "bytes_read": transferred,
        "review_sha256": pin,
        "active_metadata_closure": facts,
        "models": 0,
        "installs": 0,
        "tasks_run": 0,
    }
    write(DESTINATION / "result.json", encode(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    if args.prepare:
        print(write(REVIEW, encode(reviewed_closure()[0]))["sha256"])
    else:
        evidence = execute(args.exact_review)
        print(json.dumps({key: evidence[key] for key in ("verified", "requests", "bytes_read")}))
