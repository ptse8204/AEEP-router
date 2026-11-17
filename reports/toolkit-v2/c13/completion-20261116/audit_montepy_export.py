"""Verify a retained Git export by reversing its declared version substitution."""

import json
import tarfile
from pathlib import Path

from rebind_cached_repository_sources import git_object, git_tree, inventory
from stage_repository_transport import digest, read

ROOT = Path(__file__).resolve().parents[4]
GROUP = ROOT / "reports/toolkit-v2/c13/completion-20261116/offline-evidence-reviews.json"
GROUP_SHA = "6b758e65254042640df8aa36b8341bfbcad7975e931ed063a2060ed986aa0c1a"
FORMATS = (
    "%(describe:tags=true,match=*[0-9]*)",
    "%(describe:tags=true)",
    "%(describe)",
    "%(describe:match=*[0-9]*)",
    "%D",
)


def audit():
    group = json.loads(read(GROUP, GROUP_SHA))
    scope, = (row for row in group["reviews"] if row["scope"] == "retained_software_tree_recovery")
    review_path = ROOT / scope["path"]
    review = json.loads(read(review_path, scope["sha256"]))
    target, = (row for row in review["targets"] if row["case"] == "idaholab__montepy-933_interface")
    attempt = review_path.parent / "execution" / target["case"]
    outcome = json.loads((attempt / "result.json").read_bytes())
    raw_commit = read(attempt / "commit.json", outcome["commit_metadata_sha256"])
    commit = json.loads(raw_commit)
    if (
        outcome["publisher_binding_verified"] is not False
        or commit["sha"] != target["revision"]
        or commit["tree"]["sha"] != outcome["published_tree"]
        or outcome["archived_tree"] != target["archived_tree"]
        or outcome["omitted_gitlinks"]
    ):
        raise ValueError("expected the unchanged export mismatch from the approved publisher check")
    archive = ROOT / target["archive_path"]
    tree, notices, count, archive_sha = inventory(archive, target["revision"])
    if (tree, notices, count, archive_sha) != (
        target["archived_tree"], target["license_notices"], target["entry_count"], target["archive_sha256"]
    ):
        raise ValueError("retained archive no longer matches its reviewed inventory")
    entries = {}
    archival = None
    with tarfile.open(archive) as snapshot:
        for member in snapshot:
            if member.isdir():
                continue
            parts = tuple(member.name.split("/")[1:])
            if member.issym():
                mode, data = b"120000", member.linkname.encode("utf-8", "surrogateescape")
            else:
                mode = b"100755" if member.mode & 0o111 else b"100644"
                data = snapshot.extractfile(member).read()
            if parts in entries:
                raise ValueError("duplicate export file")
            entries[parts] = (mode, git_object("blob", data))
            if parts == (".gitattributes",) and data != b".git_archival.txt  export-subst\n":
                raise ValueError("publisher has not declared the expected single export substitution")
            if parts == (".git_archival.txt",):
                archival = data
    if (
        git_tree(entries) != target["archived_tree"] or archival is None
        or (".gitattributes",) not in entries
        or not archival.startswith(f"node: {target['revision']}\n".encode())
    ):
        raise ValueError("exported Git tree or revision differs")
    attempts = []
    matches = []
    for description in FORMATS:
        candidate = (
            "node: $Format:%H$\nnode-date: $Format:%cI$\n"
            f"describe-name: $Format:{description}$\n"
        ).encode()
        proposed = {**entries, (".git_archival.txt",): (b"100644", git_object("blob", candidate))}
        restored_tree = git_tree(proposed)
        matched = restored_tree == outcome["published_tree"]
        attempts.append({"describe_format": description, "tree": restored_tree, "matched": matched})
        if matched:
            matches.append({"publisher_blob": git_object("blob", candidate).hex(),
                            "publisher_template": candidate.decode(), "restored_tree": restored_tree})
    if len(matches) != 1 or digest(archive.read_bytes()) != archive_sha:
        raise ValueError("the one-file inverse export does not uniquely reproduce the published tree")
    return {
        "schema_version": "aeep.c13.montepy-export-binding.v1",
        "group_sha256": GROUP_SHA, "review_sha256": scope["sha256"],
        "case": target["case"], "source_revision": target["revision"],
        "archive_sha256": archive_sha, "archive_tree": tree, "publisher_tree": outcome["published_tree"],
        "commit_metadata_sha256": digest(raw_commit),
        "original_attempt_result_sha256": digest((attempt / "result.json").read_bytes()),
        "license_notices": notices, "entries": count,
        "declared_export_attribute": ".git_archival.txt  export-subst",
        "expanded_file_sha256": digest(archival),
        "one_file_inverse_export": matches[0], "bounded_template_checks": attempts,
        "publisher_binding_verified": True, "protected_runtime_verified": False,
        "archive_mutations": 0, "new_network_requests": 0, "upstream_execution": 0,
        "formal_cases_adopted": 0,
        "scope": "All archived file modes and blobs reproduce the publisher tree after the one declared Git export substitution is reversed for hashing. Original archive and worker bytes stay bound to their exact expanded form.",
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True, allow_nan=False))
