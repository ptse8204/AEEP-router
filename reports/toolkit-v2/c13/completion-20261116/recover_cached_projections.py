"""Stage verified archive projections for three retained multi-file repairs."""

import argparse
import gzip
import io
import json
import shutil
import tarfile
from collections import Counter
from functools import partial
from pathlib import Path, PurePosixPath

from audit_formal_inputs import repository
from prepare_contract_audits import INTAKE_SHA, prior_origins
from rebind_cached_repository_sources import inventory
from screen_candidate_patches import INTAKE, assess, load_reviewed_helpers, stage_file
from stage_repository_transport import HERE, ROOT, WORK, bind_row, digest, encode, read, write

from aeep.assessment.repository_suites import pack_files

CACHED = WORK / "multifile-acquisition"
TARGET = WORK / "cached-multifile-projections"
PUBLISHER = {
    "getsentry__sentry-python-4231": {
        "tree": "afd347c733a9433fe26de841a0c41cb2b6976b3d",
        "archive": "b0e3e1ccf1c91544391ac60950ff791f78f9560faf887c4e34f4a9b1912b15dc",
        "omitted_gitlinks": {"checkouts/data-schemas": "6d2c435b8ce3a67e2065f38374bb437f274d0a6c"},
    },
    "py-pdf__pdfly-219": {
        "tree": "f06844368c8eb3a9f52a9152b70fcd00d47be99c",
        "archive": "fbf9a68b7d397a5aba7e64b8c61202c98375cbbc7de4b32c701eae4e8194aa63",
        "omitted_gitlinks": {"sample-files": "91b6d24a3b86bad1f20b707ec54555d89acc0c12"},
    },
    "huggingface__huggingface_hub-4056": {
        "tree": "fb454d52b8dd48b5c43e5a96d0b31dc498cbd7ef",
        "archive": "cadd8d0f3b9fb6329cb163cdfabc91b256fb96d93090da4b9a046f0ad8937078",
        "omitted_instructions": ("AGENTS.md", "CLAUDE.md"),
    },
}


def omit_agent_instruction_files(data, *, excluded):
    """Read only regular source files, omitting the two reviewed instruction entries."""
    files = {}
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
        raw = compressed.read(24_000_001)
    if len(raw) > 24_000_000:
        raise ValueError("archive expanded beyond the repository transport limit")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        root = archive.next()
        if root is None or not root.isdir() or "/" in root.name:
            raise ValueError("archive projection needs a single package root")
        seen = set()
        for member in archive:
            path = PurePosixPath(member.name)
            if member is root:
                continue
            if (
                not path.parts
                or path.parts[0] != root.name
                or path.is_absolute()
                or member.name != path.as_posix()
                or ".." in path.parts
                or "\\" in member.name
            ):
                raise ValueError("archive member outside the bound package root")
            if member.isdir():
                continue
            name = PurePosixPath(*path.parts[1:]).as_posix()
            if name in files or name in seen:
                raise ValueError("duplicate projected entry")
            if name == "AGENTS.md" and member.isreg():
                handle = archive.extractfile(member)
                if handle is None:
                    raise ValueError("could not hash omitted file")
                seen.add(name)
                excluded[name] = {"kind": "regular", "sha256": digest(handle.read())}
                continue
            if name == "CLAUDE.md" and member.issym() and member.linkname == "AGENTS.md":
                seen.add(name)
                excluded[name] = {"kind": "symlink", "target": "AGENTS.md"}
                continue
            if not member.isreg() or member.sparse is not None:
                raise ValueError("unreviewed irregular entry in worker projection")
            handle = archive.extractfile(member)
            if handle is None:
                raise ValueError("missing projected source entry")
            files[name] = handle.read()
    if seen != {"AGENTS.md", "CLAUDE.md"}:
        raise ValueError("reviewed instruction projection changed")
    pack_files(files, large=True)
    return files


def prepare(target):
    target = target.resolve()
    if (
        not target.is_relative_to(WORK)
        or target == WORK
        or shutil.disk_usage(WORK).free < 52 * 1024**3
    ):
        raise ValueError("use a new private work directory above the storage reserve")
    report = json.loads((HERE / "multifile-acquisition-result.json").read_bytes())
    source_file = CACHED / "source-results.json"
    pin = report["private_evidence_sha256"][source_file.relative_to(ROOT).as_posix()]
    historical = {row["case_id"]: row for row in json.loads(read(source_file, pin))}
    leads = {item["instance_id"]: item for item in json.loads(read(INTAKE, INTAKE_SHA))}
    audit_index = json.loads((HERE / "additional-contract-audits.json").read_bytes())
    existing, origins = prior_origins()
    existing.extend(
        json.loads(read(ROOT / audit_index["private_index"], audit_index["private_index_sha256"]))
    )
    origins |= {(repository(row["source_repository"]), row["source_revision"]) for row in existing}
    source_hashes = {row["input"]["source_sha256"] for row in existing}
    helpers, prepared, proofs = load_reviewed_helpers(), [], []
    target.mkdir(mode=0o700)
    protected = target / "review-inputs"
    protected.mkdir(mode=0o700)
    for case_id, expected in PUBLISHER.items():
        lead, prior = leads[case_id], historical[case_id]
        revision = prior["revision"]
        slug = repository(lead["repository"])
        if (
            revision != lead["base_commit"]
            or slug != prior["repository"]
            or (slug, revision) in origins
        ):
            raise ValueError("recovered archive differs from the independent review scope")
        archive = CACHED / case_id / "source.tar.gz"
        raw_tree, _, _, raw_sha = inventory(archive, revision)
        gitlinks = expected.get("omitted_gitlinks")
        tree, notices, entries, sha = inventory(archive, revision, omitted_gitlinks=gitlinks)
        if tree != expected["tree"] or sha != raw_sha or sha != expected["archive"] or not notices:
            raise ValueError("retained source could not be replayed against the published tree")
        original = ROOT / lead["archives"][0]
        case = protected / case_id
        case.mkdir()
        source_copy = stage_file(case, "source-original.tar.gz", read(archive, sha))
        row_bytes = original.with_name("row.json").read_bytes()
        # The exact row remains beside the archive for the established patch preflight.
        stage_file(case, "row.json", row_bytes)
        review = {
            **lead,
            "source_bindings": [
                {
                    "archive": (case / "source-original.tar.gz").relative_to(ROOT).as_posix(),
                    "sha256": source_copy["sha256"],
                    "license_notices": notices,
                },
            ],
        }
        omitted = {}
        normalizer = (
            partial(omit_agent_instruction_files, excluded=omitted)
            if "omitted_instructions" in expected
            else None
        )
        facts, staged = assess(review, helpers, normalize_source=normalizer)
        if facts["family"] != "multi-file-repair" or (
            normalizer and set(omitted) != set(expected["omitted_instructions"])
        ):
            raise ValueError("transport changed the reviewed repair type or projection")
        row = {
            **facts,
            "case_id": case_id,
            "assets": [stage_file(case, name, data) for name, data in staged.items()],
        }
        mapped = bind_row(
            row, review, target / "worker-transport", protected, str(original.relative_to(ROOT))
        )
        source_hash = mapped["input"]["source_sha256"]
        if source_hash in source_hashes:
            raise ValueError("recovered repair duplicates a retained source snapshot")
        source_hashes.add(source_hash)
        prepared.append(mapped)
        proofs.append(
            {
                "case_id": case_id,
                "repository": slug,
                "revision": revision,
                "publisher_commit": f"https://github.com/{slug}/commit/{revision}",
                "publisher_tree": tree,
                "retained_archive_tree": raw_tree,
                "source_sha256": sha,
                "public_worker_archive_sha256": source_hash,
                "retained_entries": entries,
                "omitted_gitlinks": gitlinks or {},
                "omitted_agent_instructions": omitted,
                "omitted_non_executable_patch_changes": facts["omitted_documentation_changes"],
                "published_issue_identities": facts["required_issue_tests"],
                "published_preservation_identities": facts["required_preservation_tests"],
                "license_notices": notices,
                "protected_tests_sha256": mapped["protected_tests"]["sha256"],
                "runtime_verified": False,
            }
        )
    index = target / "worker-transport/private-index.json"
    pin = write(index, encode(prepared))
    families = Counter(row["input"]["family"] for row in [*existing, *prepared])
    return {
        "schema_version": "aeep.c13.cached-multifile-projections.v1",
        "private_transport_index": index.relative_to(ROOT).as_posix(),
        "private_transport_index_sha256": pin["sha256"],
        "cases": proofs,
        "optimistic_rows": len(existing) + len(prepared),
        "optimistic_case_counts": dict(families),
        "minimum_additional_rows_before_independence": 141 - len(existing) - len(prepared),
        "minimum_additional_holdout_rows": {
            name: max(0, 35 - count) for name, count in families.items()
        },
        "new_downloads": 0,
        "upstream_tests_executed": 0,
        "models": 0,
        "formal_cases_adopted": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=TARGET)
    print(json.dumps(prepare(parser.parse_args().output), indent=2))
