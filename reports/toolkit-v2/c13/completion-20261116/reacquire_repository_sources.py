"""Recover bounded published source archives without running their contents."""

import argparse
import http.client
import json
import re
import shutil
import tarfile
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from audit_formal_inputs import repository
from rebind_cached_repository_sources import (
    ARCHIVE_BOUND,
    COMMIT_METADATA_LIMIT,
    HERE,
    LEADS,
    ROOT,
    WORK,
    inventory,
    published_tree,
    stage_issues,
    write,
)
from screen_candidate_patches import sha

PRIORITIES = WORK / "cached-source-tree-rebinding/truncated-archive-priorities.json"
REBOUND = HERE / "rebound-worker-transport.json"
REVIEW = HERE / "multifile-acquisition-review.json"
APPROVAL = WORK / "multifile-acquisition-approval.json"
OUTPUT = WORK / "multifile-acquisition"
RESERVE = 52 * 1024**3


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def definition():
    priorities = PRIORITIES.read_bytes()
    if sha(priorities) != json.loads(REBOUND.read_bytes())["truncated_archive_priorities_sha256"]:
        raise ValueError("truncated archive inventory differs from the retained audit")
    lead_bytes = LEADS.read_bytes()
    if sha(lead_bytes) != json.loads((HERE / "repository-patch-batch-intake.json").read_bytes())["case_inventory_sha256"]:
        raise ValueError("repository case inventory changed")
    leads = {lead["instance_id"]: lead for lead in json.loads(lead_bytes)}

    choices = {}
    for item in sorted(json.loads(priorities), key=lambda row: row["case_id"]):
        if item["priority"] != "multi_file_patch_lead":
            continue
        slug = repository(item["repository"])
        lead = leads[item["case_id"]]
        revision = lead["base_commit"]
        url = f"https://codeload.github.com/{slug}/tar.gz/{revision}"
        if (
            re.fullmatch(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-[0-9]+(?:_interface)?", item["case_id"]) is None
            or re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", slug) is None
            or repository(lead["repository"]) != slug
            or item["commit"] != revision
            or item["possible_reacquisition_source"] != url
            or len(revision) != 40
            or any(letter not in "0123456789abcdef" for letter in revision)
        ):
            raise ValueError("source identities disagree")
        # Pick one stable acquisition per repository family. Retain other leads.
        choices.setdefault(slug, {
            "case_id": item["case_id"],
            "repository": slug,
            "revision": revision,
            "archive_url": url,
            "prior_incomplete_sha256": item["cached_prefix_sha256"],
        })
    return {
        "schema_version": "aeep.c13.multifile-acquisition.v1",
        "driver_sha256": sha(Path(__file__).read_bytes()),
        "source_helpers": {
            name: sha((HERE / name).read_bytes()) for name in (
                "audit_formal_inputs.py", "rebind_cached_repository_sources.py", "screen_candidate_patches.py"
            )
        },
        "priority_sha256": sha(priorities),
        "source_inventory_sha256": sha(lead_bytes),
        "choices": list(choices.values()),
        "max_archive_downloads": len(choices),
        "max_archive_response_bytes": len(choices) * ARCHIVE_BOUND,
        "max_archive_response_bytes_each": ARCHIVE_BOUND,
        "max_commit_metadata_lookups": len(choices),
        "max_commit_metadata_response_bytes": len(choices) * (COMMIT_METADATA_LIMIT + 1),
        "archive_retries": 0,
        "downloads_only_public_pinned_sources": True,
        "upstream_programs_executed": False,
        "models": 0,
        "cash_usd": 0,
    }, leads


def download(url, destination):
    request = urllib.request.Request(
        url, headers={"Accept-Encoding": "identity", "User-Agent": "AEEP-provenance-read"}
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=12) as response:
        if response.geturl() != url or response.status != 200:
            raise ValueError("source response differs from the exact destination")
        declared = response.headers.get("Content-Length")
        if declared is not None and not 0 < int(declared) < ARCHIVE_BOUND:
            raise ValueError("declared source exceeds the reviewed cap")
        data = response.read(ARCHIVE_BOUND)
    if not 0 < len(data) < ARCHIVE_BOUND or (declared is not None and len(data) != int(declared)):
        raise ValueError("source response truncated or at the reviewed cap")
    with destination.open("xb") as stream:
        stream.write(data)


def run(exact):
    scope, leads = definition()
    raw = REVIEW.read_bytes()
    approval = json.loads(APPROVAL.read_bytes())
    sealed = json.loads(raw)
    expires = datetime.fromisoformat(sealed.pop("expires_at"))
    if (
        sha(raw) != exact or sealed != scope
        or expires <= datetime.now(UTC)
        or approval.get("approved") is not True or approval.get("review_sha256") != exact
        or shutil.disk_usage(WORK).free < RESERVE
    ):
        raise ValueError("exact acquisition, approval or host reserve unavailable")
    OUTPUT.mkdir(mode=0o700)
    observations = []
    staged_leads = {}
    for row in scope["choices"]:
        if expires <= datetime.now(UTC) or shutil.disk_usage(WORK).free < RESERVE:
            raise RuntimeError("host reserve or authorization changed before acquisition")
        identity = row["case_id"]
        folder = OUTPUT / identity
        folder.mkdir(mode=0o700)
        write(folder / "started.json", {"case_id": identity, "review_sha256": exact})
        archive = folder / "source.tar.gz"
        try:
            download(row["archive_url"], archive)
            tree, licenses, entries, fingerprint = inventory(archive, row["revision"])
            published = published_tree(row["repository"], row["revision"])
            if tree != published["published_tree"] or not licenses:
                raise ValueError("published tree or root license notice could not be verified")
            result = {
                **row, **published, "case_id": identity, "archive_sha256": fingerprint,
                "license_notices": licenses, "entries": entries, "size_bytes": archive.stat().st_size,
                "status": "archive_tree_and_notice_bound",
            }
            staged_leads[identity] = {**leads[identity], "archives": [str(archive.relative_to(ROOT))]}
        except (OSError, ValueError, tarfile.TarError, http.client.HTTPException, KeyError) as failure:
            result = {**row, "status": "acquisition_unverified", "error_type": type(failure).__name__}
        write(folder / "result.json", result)
        observations.append(result)
    write(OUTPUT / "source-results.json", observations)
    staged = stage_issues(OUTPUT, observations, staged_leads)
    write(OUTPUT / "stage-results.json", staged)
    print(json.dumps({
        "review_sha256": exact,
        "tree_verified": len(staged_leads),
        "staged_for_runtime_review": sum(row["status"] == "ready_for_runtime_review" for row in staged),
        "cases_adopted": 0,
    }))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--prepare", action="store_true")
    commands.add_argument("--exact-review")
    options = parser.parse_args()
    if options.prepare:
        scope, _ = definition()
        scope["expires_at"] = (datetime.now(UTC) + timedelta(days=7)).isoformat()
        write(REVIEW, scope)
        print(sha(REVIEW.read_bytes()))
    else:
        run(options.exact_review)
