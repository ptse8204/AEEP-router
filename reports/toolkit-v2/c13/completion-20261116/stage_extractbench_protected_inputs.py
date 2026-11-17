"""Verify the scorer archive against Git blobs and stage only protected grader inputs."""

import argparse
import hashlib
import json
import tarfile
from io import BytesIO
from pathlib import PurePosixPath

from audit_extractbench_audent import HERE, ROOT, SCORER, TASK, task_assets
from audit_extractbench_runtime import TREE_PIN
from stage_repository_transport import digest, read

ARCHIVE_PIN = "0944aadd5c76f959c3de445056db701b365f889d92e20380f597ad3dc0d0432b"
SOURCE_BYTES = 6_441_881
STAGED = ROOT / "protected-runtime-input"
RUNTIME_AUDIT = HERE / "extractbench-runtime-audit.json"
INTAKE = HERE / "extractbench-audent-intake.json"
ROLES = {
    "reference": ("oracle.json", "reference.test.json", "perfect"),
    "missing_row": ("missing-row.json", "reference.test.json", "partial"),
    "changed_value": ("changed-value.json", "reference.test.json", "partial"),
    "repeated_row": ("repeated-row.json", "reference.test.json", "partial"),
    "malformed": ("malformed.json", "reference.test.json", "invalid_submission"),
    "no_output": (None, "reference.test.json", "invalid_submission"),
    "no_reference": ("oracle.json", None, "infrastructure_error"),
}


def verify_source_archive(raw, tree):
    if tree["sha"] != SCORER or tree["truncated"]:
        raise ValueError("wrong or incomplete official Git tree")
    expected = {row["path"]: row for row in tree["tree"] if row["type"] == "blob"}
    if len(expected) != 379 or sum(row["size"] for row in expected.values()) != SOURCE_BYTES:
        raise ValueError("unexpected repository inventory")
    root = f"ExtractBench-{SCORER}"
    dirs = {root} | {root + "/" + row["path"] for row in tree["tree"] if row["type"] == "tree"}
    seen_dirs, files = set(), {}
    with tarfile.open(fileobj=BytesIO(raw), mode="r:gz") as archive:
        for item in archive:
            path = PurePosixPath(item.name)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != root:
                raise ValueError("source archive escaped its publisher prefix")
            if item.isdir():
                if item.name not in dirs or item.name in seen_dirs:
                    raise ValueError("unexpected or repeated source directory")
                seen_dirs.add(item.name)
                continue
            relative = path.relative_to(root).as_posix()
            row = expected.get(relative)
            if not item.isfile() or row is None or relative in files or row["mode"] != "100644" or item.size != row["size"]:
                raise ValueError("unexpected Git blob or file type")
            with archive.extractfile(item) as stream:
                data = stream.read(item.size + 1)
            header = f"blob {len(data)}\0".encode()
            if len(data) != row["size"] or hashlib.sha1(header + data, usedforsecurity=False).hexdigest() != row["sha"]:
                raise ValueError("archive bytes do not match the official Git blob")
            files[relative] = data
    if set(files) != set(expected) or seen_dirs != dirs:
        raise ValueError("source archive is incomplete")
    return files


def verifier_with_document_path(raw, document):
    old = b'Path("/app/document.pdf")'
    if raw.count(old) != 1 or not document.is_absolute():
        raise ValueError("upstream document-path binding changed")
    # This is the only change to the source verifier. The loader and score stay exact.
    selected = b"Path(" + json.dumps(str(document)).encode() + b")"
    adjusted = raw.replace(old, selected)
    if adjusted.replace(selected, old, 1) != raw:
        raise ValueError("verifier path substitution is not reversible")
    compile(adjusted, "<adapted ExtractBench verifier>", "exec")
    return adjusted


def prepared():
    _, assets = task_assets()
    archive = read(ROOT / "scorer-publisher-commit.tar.gz", ARCHIVE_PIN)
    tree = json.loads(read(ROOT / "scorer-git-tree.json", TREE_PIN))
    source = verify_source_archive(archive, tree)
    audit = json.loads(RUNTIME_AUDIT.read_bytes())
    if digest(source["LICENSE"]) != audit["source_license_sha256"]:
        raise ValueError("scorer license differs from verified prior record")
    intake = json.loads(INTAKE.read_bytes())
    entries = {path.removeprefix("src/"): value for path, value in source.items()
               if path.startswith("src/extract_bench/")}
    entries["licenses/ExtractBench-LICENSE"] = source["LICENSE"]
    entries["verifier/reference.test.json"] = assets["tests/reference.test.json"].read_bytes()
    entries["verifier/document.pdf"] = assets["environment/document.pdf"].read_bytes()
    upstream = assets["tests/verifier.py"].read_bytes()
    entries["verifier/harbor_original.py"] = upstream
    document = STAGED / "verifier/document.pdf"
    entries["verifier/harbor_on_carrier.py"] = verifier_with_document_path(upstream, document)
    entries.update({f"controls/{name}": read(ROOT / "calibration" / name, pin)
                    for name, pin in intake["control_pins"].items()})
    if set(intake["control_pins"]) != {prediction for prediction, _, _ in ROLES.values() if prediction}:
        raise ValueError("protected fault inventory changed")
    manifest = {name: {"bytes": len(value), "sha256": digest(value)} for name, value in sorted(entries.items())}
    record = {
        "schema_version": "aeep.c13.extractbench-protected-intake.v1",
        "task_id": TASK, "scorer_revision": SCORER, "source_tree_sha256": TREE_PIN,
        "source_archive": {"sha256": ARCHIVE_PIN, "bytes": len(archive), "verified_git_blobs": len(source)},
        "scorer_files_staged": sum(name.startswith("extract_bench/") for name in entries),
        "mount": str(STAGED.relative_to(HERE.parents[3])),
        "protected_inventory_sha256": digest(json.dumps(manifest, sort_keys=True).encode()),
        "protected_inventory_count": len(entries),
        "protected_bytes": sum(len(value) for value in entries.values()),
        "native_metric": "extract_unified_value_f1",
        "separate_independent_binary": "perfect",
        "roles": {role: {"prediction": prediction, "reference": reference, "expected_disposition": expected}
                  for role, (prediction, reference, expected) in ROLES.items()},
        "path_adaptation": {
            "original_document": "/app/document.pdf", "container_document": str(document),
            "original_verifier_sha256": digest(upstream),
            "adapted_verifier_sha256": digest(entries["verifier/harbor_on_carrier.py"]),
            "scope": "One document location. The original loader, metric implementation and oracle stay byte-bound.",
        },
        "runtime_audit_sha256": digest(RUNTIME_AUDIT.read_bytes()),
        "native_grades_observed": 0, "formal_cases_adopted": 0,
        "remaining": "Acquire the reviewed missing wheels and validate the seven roles on an offline carrier.",
    }
    return record, manifest, entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--stage", action="store_true")
    action.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    record, manifest, files = prepared()
    if args.stage:
        STAGED.mkdir(mode=0o755)
        for name, value in files.items():
            path = STAGED / name
            path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(value)
            path.chmod(0o444)
        with (ROOT / "protected-runtime-input-manifest.json").open("x") as stream:
            json.dump(manifest, stream, sort_keys=True, indent=2)
            stream.write("\n")
    expected_dirs = {parent.as_posix() for name in files for parent in PurePosixPath(name).parents} - {"."}
    tree = list(STAGED.rglob("*"))
    actual_dirs = {path.relative_to(STAGED).as_posix() for path in tree if path.is_dir()}
    actual_files = {path.relative_to(STAGED).as_posix() for path in tree if path.is_file()}
    if (
        STAGED.is_symlink() or any(path.is_symlink() for path in tree)
        or actual_dirs != expected_dirs or actual_files != set(files) or len(tree) != len(actual_dirs) + len(actual_files)
        or any(read(STAGED / name, manifest[name]["sha256"]) != value for name, value in files.items())
    ):
        raise ValueError("protected mount changed or contains unexpected files")
    print(json.dumps(record, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
