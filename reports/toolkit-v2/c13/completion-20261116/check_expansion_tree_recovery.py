"""Recover publisher tree bindings for five archived repository intake failures."""

import argparse
import json
import re
import shutil
import tarfile
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import PurePosixPath

from audit_expansion_acquisition_result import INTAKE, QUEUE, RESULT, REVIEW as ORIGINAL_REVIEW
from check_linux_install import HERE, ROOT, WORK
from rebind_cached_repository_sources import (
    COMMIT_METADATA_LIMIT,
    REVISION,
    inventory,
)
from stage_repository_transport import digest, encode, read, write

PRIVATE = WORK / "repository-expansion-retained-tree-recovery-20261117"
REVIEW = PRIVATE / "operation-review.json"
APPROVAL = PRIVATE / "approval.json"
RUN = PRIVATE / "execution"
TREE_LIMIT = 1_500_000
RESERVE = 52 * 1024**3
TARGETS = {
    "idaholab__montepy-933_interface": False,
    "gitpython-developers__GitPython-2051": True,
    "rwth-i6__returnn-1764": True,
    "bluesky__ophyd-async-1165": True,
    "openai__openai-agents-python-1965": False,
}
SLUG = re.compile(r"[a-z0-9_.-]+/[a-z0-9_.-]+")


def bindings():
    parent = json.loads(read(QUEUE / "acquisition-review.json", ORIGINAL_REVIEW))
    outcome = json.loads(read(INTAKE / "result.json", RESULT))
    attempts = {row["case_id"]: row for row in outcome["observations"]}
    candidate_rows = []
    for source in parent["sources"]:
        case = source["case_id"]
        if case not in TARGETS:
            continue
        repository, revision = source["repository"].lower(), source["revision"]
        archive = INTAKE / "archives" / case / "source-original.tar.gz"
        previous = attempts[case]
        if (
            not SLUG.fullmatch(repository) or not REVISION.fullmatch(revision)
            or source["commit_url"] != f"https://api.github.com/repos/{repository}/git/commits/{revision}"
            or previous["status"] != "source_or_transport_unverified"
            or json.loads((INTAKE / "attempts" / case / "result.json").read_bytes()) != previous
        ):
            raise ValueError("candidate is outside the previous failed acquisition scope")
        base_tree, notices, entries, archive_sha = inventory(archive, revision)
        with tarfile.open(archive) as raw:
            has_gitmodules = any(
                member.isfile() and member.name.split("/")[1:] == [".gitmodules"] for member in raw
            )
        if not notices or TARGETS[case] != has_gitmodules:
            raise ValueError("retained archive is missing its reviewed notice or Git submodule shape")
        candidate_rows.append({
            "case": case, "repository": repository, "revision": revision,
            "archive_path": str(archive.relative_to(ROOT)), "archive_sha256": archive_sha,
            "entry_count": entries, "license_notices": notices, "archived_tree": base_tree,
            "commit_url": source["commit_url"], "permit_recursive_tree": has_gitmodules,
            "previous_outcome": previous,
        })
    if {row["case"] for row in candidate_rows} != TARGETS.keys():
        raise ValueError("the retained recovery inventory changed")
    return {
        "schema_version": "aeep.c13.retained-expansion-tree-recovery.v1",
        "original_review_sha256": ORIGINAL_REVIEW, "original_result_sha256": RESULT,
        "driver_files": {name: digest((HERE / name).read_bytes()) for name in (
            "check_expansion_tree_recovery.py", "rebind_cached_repository_sources.py",
            "audit_expansion_acquisition_result.py", "stage_repository_transport.py",
        )},
        "targets": candidate_rows, "expires_at": parent["expires_at"],
        "maximum_commit_requests": len(TARGETS),
        "maximum_recursive_tree_requests": sum(TARGETS.values()),
        "maximum_response_bytes": len(TARGETS) * (COMMIT_METADATA_LIMIT + 1) + sum(TARGETS.values()) * (TREE_LIMIT + 1),
        "maximum_archives_downloaded": 0, "upstream_tests": 0, "models": 0,
        "cash_usd": 0, "formal_cases_adopted": 0,
        "minimum_host_free_bytes": RESERVE, "retries": 0,
    }


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("unexpected publisher tree redirect")


def gitlinks(raw, expected_root):
    value = json.loads(raw)
    if (
        not isinstance(value, dict) or value.get("sha") != expected_root
        or value.get("truncated") is not False
        or not isinstance(value.get("tree"), list) or len(value["tree"]) > 8_000
    ):
        raise ValueError("publisher returned a different or incomplete Git tree")
    paths = set()
    links = {}
    for entry in value["tree"]:
        name = entry["path"]
        path = PurePosixPath(name)
        if (
            not path.parts or path.is_absolute() or path.as_posix() != name
            or ".." in path.parts or "\\" in name or name in paths
        ):
            raise ValueError("publisher Git tree contains an ambiguous path")
        paths.add(name)
        if entry["mode"] == "160000" or entry["type"] == "commit":
            if (entry["mode"], entry["type"]) != ("160000", "commit") or not REVISION.fullmatch(entry["sha"]):
                raise ValueError("publisher Git tree contains malformed submodule metadata")
            links[name] = entry["sha"]
    if not links:
        raise ValueError("publisher tree has no omitted Git submodule entries")
    return links


def fetch_metadata(url, limit):
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": "AEEP-provenance-read"}
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RejectRedirect())
    with opener.open(request, timeout=12) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError("unexpected publisher metadata destination")
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("publisher metadata exceeds the response cap")
    return raw


def resolve_commit(target):
    raw = fetch_metadata(target["commit_url"], COMMIT_METADATA_LIMIT)
    record = json.loads(raw)
    root = record["tree"]["sha"]
    if record["sha"] != target["revision"] or not REVISION.fullmatch(root):
        raise ValueError("publisher returned a different Git commit")
    return {"url": target["commit_url"], "commit_metadata_sha256": digest(raw), "published_tree": root}, raw


def resolve_tree(repository, root):
    url = f"https://api.github.com/repos/{repository}/git/trees/{root}?recursive=1"
    raw = fetch_metadata(url, TREE_LIMIT)
    return gitlinks(raw, root), raw


def recover(target, attempts):
    publisher, raw = resolve_commit(target)
    write(attempts / "commit.json", raw)
    archive = ROOT / target["archive_path"]
    links = {}
    if publisher["published_tree"] != target["archived_tree"] and target["permit_recursive_tree"]:
        links, raw = resolve_tree(target["repository"], publisher["published_tree"])
        write(attempts / "tree.json", raw)
    tree, notices, count, sha = inventory(archive, target["revision"], omitted_gitlinks=links)
    if (notices, count, sha) != (target["license_notices"], target["entry_count"], target["archive_sha256"]):
        raise ValueError("retained bytes changed while acquiring publisher metadata")
    return {
        "case": target["case"], **publisher, "archived_tree": target["archived_tree"],
        "omitted_gitlinks": links, "reconstructed_tree": tree, "archive_sha256": sha,
        "publisher_binding_verified": tree == publisher["published_tree"],
    }


def verify():
    raw = REVIEW.read_bytes()
    record = json.loads(raw)
    if (
        record != bindings() or datetime.fromisoformat(record["expires_at"]) <= datetime.now(UTC)
        or shutil.disk_usage(WORK).free < RESERVE or RUN.exists()
    ):
        raise ValueError("retained recovery review expired, drifted, or already started")
    return record, digest(raw)


def execute(exact):
    record, pin = verify()
    expected = {"approved": True, "review_sha256": exact}
    approval = json.loads(APPROVAL.read_bytes())
    if pin != exact or approval != expected or approval["approved"] is not True:
        raise ValueError("exact operator approval is required for publisher requests")
    RUN.mkdir(mode=0o700)
    write(RUN / "started.json", encode({"review_sha256": pin, "automatic_retry": False}))
    observed = []
    for target in record["targets"]:
        if (
            digest(REVIEW.read_bytes()) != exact or json.loads(APPROVAL.read_bytes()) != expected
            or datetime.fromisoformat(record["expires_at"]) <= datetime.now(UTC)
            or shutil.disk_usage(WORK).free < RESERVE
        ):
            raise ValueError("review, expiry or storage changed during publisher recovery")
        attempts = RUN / target["case"]
        attempts.mkdir(mode=0o700)
        stop = False
        try:
            row = recover(target, attempts)
        except (OSError, ValueError, KeyError, tarfile.TarError) as error:
            row = {"case": target["case"], "publisher_binding_verified": False, "error_type": type(error).__name__}
            if isinstance(error, urllib.error.HTTPError):
                row["http_status"] = error.code
                stop = error.code in {403, 429}
        write(attempts / "result.json", encode(row))
        observed.append(row)
        if stop:
            break
    write(RUN / "result.json", encode({"review_sha256": pin, "observations": observed, "upstream_tests": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--verify", action="store_true")
    actions.add_argument("--execute-approved")
    args = parser.parse_args()
    if args.execute_approved:
        execute(args.execute_approved)
    else:
        if args.prepare:
            scope = bindings()
            PRIVATE.mkdir(mode=0o700)
            write(REVIEW, encode(scope))
        _, fingerprint = verify()
        print(fingerprint)
