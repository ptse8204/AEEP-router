"""Verify cached tar contents against public Git commit trees without importing them."""

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import tarfile
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from audit_formal_inputs import repository
from screen_candidate_patches import assess, load_reviewed_helpers, sha, stage_file

from aeep.errors import ConfigurationError

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / ".aeep/completion-20261116"
LEADS = WORK / "source-bound-leads.json"
COMMIT_METADATA_LIMIT = 192_000
ARCHIVE_BOUND = 3_500_000
EXPANDED_BOUND = 48_000_000
ENTRY_BOUND = 18000
REVISION = re.compile(r"[0-9a-f]{40}")
LICENSE = re.compile(
    r"(?:licen[cs]es?|copying|unlicense|copyright|notice)(?:[-_.].*)?", re.IGNORECASE
)


def git_object(kind, data):
    content = f"{kind} {len(data)}\0".encode() + data
    return hashlib.sha1(content).digest()


def git_tree(entries):
    root = {}
    for parts, (mode, fingerprint) in entries.items():
        node = root
        for name in parts[:-1]:
            node = node.setdefault(name, {})
            if not isinstance(node, dict):
                raise ValueError("archive path overlaps a file")
        if parts[-1] in node:
            raise ValueError("duplicate archive member or directory")
        node[parts[-1]] = (mode, fingerprint)

    def tree(nodes):
        children = []
        for name, item in nodes.items():
            encoded = name.encode("utf-8", "surrogateescape")
            if isinstance(item, dict):
                children.append((encoded + b"/", b"40000", encoded, tree(item)))
            else:
                children.append((encoded, item[0], encoded, item[1]))
        return git_object(
            "tree",
            b"".join(
                mode + b" " + name + b"\0" + fingerprint
                for _, mode, name, fingerprint in sorted(children)
            ),
        )

    return tree(root).hex()


def inventory(path, revision, *, omitted_gitlinks=None):
    if (
        path.resolve() != path
        or not path.is_relative_to(ROOT / ".aeep")
        or not path.is_file()
        or path.stat().st_size > ARCHIVE_BOUND
    ):
        raise ValueError("cached archive outside reviewed path or size")
    with path.open("rb") as archive:
        raw = archive.read(ARCHIVE_BOUND + 1)
    if len(raw) > ARCHIVE_BOUND:
        raise ValueError("cached archive exceeds the read bound")
    file_entries, notices = {}, []
    total = 0
    with tarfile.open(
        fileobj=io.BytesIO(raw), mode="r|gz", encoding="utf-8", errors="surrogateescape"
    ) as snapshot:
        top = snapshot.next()
        if (
            top is None
            or not top.isdir()
            or "/" in top.name
            or not top.name.endswith("-" + revision)
        ):
            raise ValueError("archive directory does not bind the revision")
        if snapshot.pax_headers.get("comment") != revision:
            raise ValueError("archive comment does not bind the revision")
        for index, item in enumerate(snapshot):
            if index == 0 and item.name == top.name:
                continue
            path = PurePosixPath(item.name)
            if (
                index >= ENTRY_BOUND
                or not path.parts
                or path.parts[0] != top.name
                or path.as_posix() != item.name
                or "." in path.parts
                or ".." in path.parts
                or not path.parts[1:]
                or "\\" in item.name
            ):
                raise ValueError("unsafe archive member or entry limit reached")
            if item.isdir():
                continue
            relative = path.parts[1:]
            if relative in file_entries:
                raise ValueError("archive repeats a source member")
            if item.issym():
                mode, data = b"120000", item.linkname.encode("utf-8", "surrogateescape")
            else:
                if (
                    not item.isreg()
                    or item.sparse is not None
                    or item.size < 0
                    or total + item.size > EXPANDED_BOUND
                ):
                    raise ValueError("unsupported entry type or expanded byte limit")
                handle = snapshot.extractfile(item)
                if handle is None:
                    raise ValueError("missing tar payload")
                data = handle.read()
                if len(data) != item.size:
                    raise ValueError("truncated archive member")
                total += len(data)
                mode = b"100755" if item.mode & 0o111 else b"100644"
                if (
                    len(relative) == 1
                    and LICENSE.fullmatch(relative[0])
                    and 100 <= len(data) <= 300000
                    and b"\0" not in data
                ):
                    notices.append({"file": relative[0], "sha256": sha(data), "bytes": len(data)})
            file_entries[relative] = (mode, git_object("blob", data))
    if not file_entries:
        raise ValueError("archive has no source files")
    archive_entries = len(file_entries)
    for name, revision in (omitted_gitlinks or {}).items():
        relative = PurePosixPath(name)
        if (
            relative.is_absolute() or not relative.parts or relative.as_posix() != name
            or ".." in relative.parts or relative.parts in file_entries
            or REVISION.fullmatch(revision) is None
        ):
            raise ValueError("invalid omitted submodule pointer")
        file_entries[relative.parts] = (b"160000", bytes.fromhex(revision))
    return git_tree(file_entries), notices, archive_entries, sha(raw)


class CommitRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        revision = req.full_url.rsplit("/", 1)[-1]
        if (
            "/repos/" not in req.full_url
            or target.scheme != "https"
            or target.netloc != "api.github.com"
            or re.fullmatch(rf"/repositories/[0-9]+/git/commits/{revision}", target.path) is None
            or target.query
            or target.fragment
        ):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def published_tree(slug, revision):
    if not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", slug) or REVISION.fullmatch(revision) is None:
        raise ValueError("unsafe public commit identity")
    url = f"https://api.github.com/repos/{slug}/git/commits/{revision}"
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": "AEEP-provenance-read"}
    )
    with urllib.request.build_opener(CommitRedirect()).open(request, timeout=10) as response:
        data = response.read(COMMIT_METADATA_LIMIT + 1)
        resolved_url = response.geturl()
    if len(data) > COMMIT_METADATA_LIMIT:
        raise ValueError("public commit metadata exceeds the review bound")
    record = json.loads(data)
    root = record["tree"]["sha"]
    if record["sha"] != revision or REVISION.fullmatch(root) is None:
        raise ValueError("publisher did not return the requested commit")
    return {
        "url": url,
        "resolved_url": resolved_url,
        "commit_metadata_sha256": sha(data),
        "published_tree": root,
    }


def examine(lead):
    result = {"case_id": lead["instance_id"], "source_revision": lead["base_commit"]}
    archive = ROOT / lead["archives"][0]
    try:
        tree, notices, entries, digest = inventory(archive, lead["base_commit"])
    except (OSError, ValueError, tarfile.TarError) as failure:
        return {"status": "archive_not_proven", "error": str(failure)[:155], **result}
    result.update(
        archive_sha256=digest, reconstructed_tree=tree, entries=entries, license_notices=notices
    )
    if not notices:
        return {"status": "root_license_notice_missing", **result}
    try:
        published = published_tree(repository(lead["repository"]), lead["base_commit"])
    except urllib.error.HTTPError as failure:
        return {"status": "commit_request_failed", "http_status": failure.code, **result}
    except (ConnectionError, TimeoutError, OSError, ValueError, KeyError) as failure:
        return {"status": "commit_request_failed", "error_type": type(failure).__name__, **result}
    result.update(published)
    if tree != published["published_tree"]:
        return {"status": "tree_mismatch", **result}
    result["status"] = "archive_tree_and_notice_bound"
    return result


def stage_issues(target, rebinding, by_case):
    staged = []
    helpers = load_reviewed_helpers()
    for result in rebinding:
        if result["status"] != "archive_tree_and_notice_bound":
            continue
        case = result["case_id"]
        lead = by_case[case]
        amended_lead = {
            **lead,
            "source_bindings": [
                {
                    "archive": lead["archives"][0],
                    "sha256": result["archive_sha256"],
                    "license_notices": result["license_notices"],
                }
            ],
        }
        try:
            facts, files = assess(amended_lead, helpers)
        except (
            OSError,
            ValueError,
            KeyError,
            SyntaxError,
            AssertionError,
            ConfigurationError,
            subprocess.CalledProcessError,
        ) as failure:
            staged.append(
                {
                    "case_id": case,
                    "status": "scope_or_asset_review_needed",
                    "reason": type(failure).__name__,
                    "detail": str(failure).splitlines()[0][:170] if str(failure) else "",
                }
            )
            continue
        path = target / "staged" / case
        path.mkdir(parents=True, mode=0o700)
        staged.append(
            {
                "case_id": case,
                "status": "ready_for_runtime_review",
                **facts,
                "assets": [stage_file(path, name, data) for name, data in files.items()],
            }
        )
    return staged


def write(path, record):
    with path.open("x") as file:
        json.dump(record, file, indent=2)
        file.write("\n")


def run(target):
    need = json.loads((HERE / "repository-patch-batch-intake.json").read_bytes())
    raw = LEADS.read_bytes()
    if sha(raw) != need["case_inventory_sha256"]:
        raise ValueError("retained input custody changed")
    candidates = [
        lead
        for lead in json.loads(raw)
        if lead["source_status"] == "requires_source_binding_or_license_record"
    ]
    assert len(candidates) == 57
    target = target.resolve()
    if target.parent != WORK or shutil.disk_usage(WORK).free < 52 * 1024**3:
        raise ValueError("use a fresh output under the private C13 workspace")
    target.mkdir(mode=0o700)
    with ThreadPoolExecutor(max_workers=4) as pool:
        rebinding = list(pool.map(examine, candidates))
    write(target / "source-results.json", rebinding)
    staged = stage_issues(target, rebinding, {case["instance_id"]: case for case in candidates})
    write(target / "stage-results.json", staged)
    counts = Counter(row["status"] for row in rebinding)
    ready = [row for row in staged if row["status"] == "ready_for_runtime_review"]
    result = {
        "schema_version": "aeep.c13.cached-repository-rebinding.v1",
        "original_input_sha256": sha(raw),
        "source_binding_results": dict(counts),
        "private_source_results_sha256": sha((target / "source-results.json").read_bytes()),
        "private_stage_results_sha256": sha((target / "stage-results.json").read_bytes()),
        "provisional_staged_cases": len(ready),
        "staged_families": dict(Counter(row["family"] for row in ready)),
        "staged_assets": sum(len(row["assets"]) for row in ready),
        "byte_bound_protected_tests": sum(
            row["required_issue_tests"] + row["required_preservation_tests"] for row in ready
        ),
        "staged_repository_count": len({repository(row["repository"]) for row in ready}),
        "asset_rights_and_runtime_approval": "pending",
        "new_subject_executions": 0,
        "new_archive_downloads": 0,
        "new_model_turns": 0,
        "formal_cases_adopted": 0,
    }
    write(target / "summary.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
