"""Rehearse v7 source addition transport on the retained Locify case."""

import base64
import gzip
import json
import tempfile
import tomllib
from pathlib import Path

from stage_repository_transport import HERE, ROOT, WORK, digest, encode, read, write

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import (
    SuiteInput,
    archive_files,
    compressed_patch_artifact,
    pack_files,
    public_archive,
)
from aeep.assessment.repository_tasks import RepositoryPatch, checked_files

CASE = "ryanhoangt__locify-8"
INTAKE = HERE / "full-rebench-three-leads-result-20261119.json"
RESULT = WORK / "locify-creation-contract-20261119.json"
ADDED = "locify/indexing/prompts.py"
EDITED = ("locify/indexing/full_map/strategy.py", "locify/indexing/repo_map/strategy.py")


def load_asset(entry):
    return read(ROOT / entry["path"], entry["sha256"])


def main():
    intake = json.loads(INTAKE.read_bytes())
    frozen = intake["cases"][CASE]
    staged = json.loads(load_asset(intake["protected_staging"]))
    case, = [row for row in staged["cases"] if row["case"] == CASE]
    assets = case["assets"]
    source_bytes = load_asset(assets["untouched-source"])
    source = archive_files(source_bytes, large=True)
    overlay = archive_files(load_asset(frozen["protected_overlay"]), large=True)
    repaired = archive_files(load_asset(frozen["reference_archive"]), large=True)
    original = archive_files(load_asset(frozen["original_with_verifier"]), large=True)
    if original != source | overlay or repaired.keys() - original.keys() != {ADDED}:
        raise ValueError("exact original overlay or module creation changed")
    if {name for name in original if original[name] != repaired.get(name)} != {*EDITED, "pyproject.toml"}:
        raise ValueError("published reference replacement set changed")
    source_meta, repaired_meta = (tomllib.loads(tree["pyproject.toml"].decode()) for tree in (source, repaired))
    source_description = source_meta["tool"]["poetry"].pop("description")
    repaired_description = repaired_meta["tool"]["poetry"].pop("description")
    if source_meta != repaired_meta or source_description == repaired_description:
        raise ValueError("excluded packaging edit alters the dependency graph")
    statement = load_asset(frozen["full_statement"]).decode()
    task = SuiteInput(
        task_id=CASE, task=statement,
        family="repository-mapping", source_sha256=digest(source_bytes),
        editable_paths=[*EDITED, ADDED],
    )
    value = task.model_dump(mode="json")
    with tempfile.TemporaryDirectory(prefix="aeep-locify-public-", dir="/private/tmp") as temporary:
        root = Path(temporary).resolve()
        write(root / (task.source_sha256 + ".tar.gz"), source_bytes)
        projection = public_archive(value, [str(root)], large=True)
    edits = checked_files({name: repaired[name].decode() for name in task.editable_paths})
    patch = RepositoryPatch(base_sha256=projection["base_sha256"], files=edits)
    compact = compressed_patch_artifact(patch)
    decoded = RepositoryPatch.model_validate_json(gzip.decompress(base64.b64decode(compact["patch_gzip_b64"])))
    reconstructed = source | {name: text.encode() for name, text in decoded.files.items()} | overlay
    protected_archive = pack_files(reconstructed, large=True)
    roles = json.loads(load_asset(assets["required.json"]))
    if (
        base64.b64decode(projection["source_b64"]) != source_bytes
        or decoded != patch or decoded.base_sha256 != content_digest(value)
        or reconstructed != repaired | {"pyproject.toml": source["pyproject.toml"]}
        or archive_files(protected_archive, large=True) != reconstructed
        or len(roles["fail_to_pass"]) != 1 or len(roles["pass_to_pass"]) != 1
        or set(overlay) & set(task.editable_paths)
    ):
        raise ValueError("public/protected transport differs from the reviewed scope")
    write(RESULT, encode({
        "scope": "inert projection using retained publisher source and verifier bytes",
        "case": CASE,
        "publisher_revision": frozen["source_revision"],
        "public_archive_sha256": task.source_sha256,
        "public_task_sha256": content_digest(value),
        "created_files": [ADDED],
        "replacement_files": list(EDITED),
        "compressed_patch_sha256": content_digest(compact),
        "protected_reference_projection_sha256": digest(protected_archive),
        "excluded_metadata_paths": ["pyproject.toml"],
        "required_identities": {key: len(items) for key, items in roles.items()},
        "upstream_grader_invocations": 0,
    }))


if __name__ == "__main__":
    main()
