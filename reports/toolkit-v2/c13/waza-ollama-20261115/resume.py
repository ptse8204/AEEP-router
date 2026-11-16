"""Continue Waza using the already acquired archive and model blobs."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

import check
import prepare
import run

from aeep.assessment.repository import AssessmentRepository
from aeep.store import ReceiptStore

ROOT, HERE = prepare.ROOT, prepare.HERE
OLD = ROOT / ".aeep/waza-ollama-20261115-exact"
PARENT = "25d22dca75bb830f39bf35d367d6c31032315bde19fd8cc3e26b71f88f05dce8"
STAGES = prepare.STAGES | {
    "download_and_install": {"operations": 1, "model_turns": 0, "reserved_seconds": 150},
}


def pin(path):
    return {"path": str(path), "sha256": run.file_digest(path)}


def safe_name(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or path == PurePosixPath("."):
        raise ValueError("archive member escaped the reviewed directory")
    return path.as_posix()


def archive_index(archive):
    members = {}
    expanded = 0
    with tarfile.open(archive, "r|gz") as stream:
        for item in stream:
            name = safe_name(item.name)
            if name in members or len(members) >= 4096:
                raise ValueError("archive has duplicate paths or excessive members")
            if item.isfile():
                expanded += item.size
                if item.size < 0 or expanded > prepare.GIB:
                    raise ValueError("archive expansion exceeds 1 GiB")
                opened = stream.extractfile(item)
                if opened is None:
                    raise ValueError("archive file is unreadable")
                with opened:
                    digest = hashlib.file_digest(opened, "sha256").hexdigest()
                members[name] = {
                    "kind": "file",
                    "size": item.size,
                    "sha256": digest,
                    "executable": bool(item.mode & 0o100),
                }
            elif item.isdir():
                members[name] = {"kind": "directory"}
            elif item.issym():
                target = safe_name(item.linkname)
                if (
                    "/" in name
                    or "/" in target
                    or not name.endswith(".dylib")
                    or not target.endswith(".dylib")
                ):
                    raise ValueError("only root-local library aliases are accepted")
                members[name] = {"kind": "library_alias", "target": target}
            else:
                raise ValueError("unreviewed archive member type")
    for name, item in members.items():
        parents = (parent.as_posix() for parent in PurePosixPath(name).parents if parent.parts)
        if any(
            members.get(parent, {"kind": "directory"})["kind"] != "directory" for parent in parents
        ):
            raise ValueError("archive member descends through a nondirectory")
        if item["kind"] != "library_alias":
            continue
        seen = {name}
        target = item["target"]
        while target in members and members[target]["kind"] == "library_alias":
            if target in seen:
                raise ValueError("cyclic library alias")
            seen.add(target)
            target = members[target]["target"]
        if members.get(target, {}).get("kind") != "file":
            raise ValueError("library alias is unresolved")
    return {"expanded_bytes": expanded, "members": members}


def extract(archive, target, expected):
    # Once the exact archive and inventory match, write files first. An alias
    # cannot redirect any archive write because aliases are created last.
    if archive_index(archive) != expected:
        raise ValueError("retained archive inventory differs")
    target.mkdir(mode=0o700)
    for name, value in expected["members"].items():
        if value["kind"] == "directory":
            (target / name).mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r|gz") as content:
        for item in content:
            if not item.isfile():
                continue
            name = safe_name(item.name)
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            opened = content.extractfile(item)
            if opened is None:
                raise RuntimeError("reviewed member disappeared")
            with opened, path.open("xb") as out:
                shutil.copyfileobj(opened, out, length=1024 * 1024)
            expected_file = expected["members"][name]
            if run.file_digest(path) != expected_file["sha256"]:
                raise ValueError("installed runtime member digest differs")
            path.chmod(0o755 if expected_file["executable"] else 0o644)
    aliases = {
        target / name: value["target"]
        for name, value in expected["members"].items()
        if value["kind"] == "library_alias"
    }
    for path, destination in aliases.items():
        path.symlink_to(destination)
    for path in aliases:
        resolved = path.resolve(strict=True)
        if resolved.parent != target or not resolved.is_file():
            raise ValueError("installed library alias escaped")


def verify_parents(review):
    parent = prepare.load(OLD / "operation-review.json")
    if run.file_digest(OLD / "operation-review.json") != PARENT:
        raise ValueError("parent execution review changed")
    old = prepare.load(OLD / "result.json")
    [operation] = old["operations"]["operations"]
    if (
        old["passed"] is not False
        or old["cleanup_uncertain"] is not False
        or operation["stage"] != "waza_local_download_and_install"
        or operation["reserved"]["max_model_turns"] != 0
        or operation["operation_id"] != review["prior_operation"]["operation_id"]
    ):
        raise ValueError("prior terminal acquisition differs")
    with ReceiptStore(review["database"], read_only=True) as store:
        repo = AssessmentRepository(store)
        charge = repo.get("operation_measurement", operation["operation_id"])
        if run.content_digest(charge) != review["prior_operation"]["measurement_ref"]:
            raise ValueError("prior settlement drifted")
    if review["archive"] != parent["archive"] or review["model_assets"] != parent["model_assets"]:
        raise ValueError("continuation acquired an unreviewed resource identity")


def install_retained(review, work, max_seconds):
    if review["maximum_download_response_bytes"] or review["allowed_download_hosts"]:
        raise ValueError("the continuation is offline")
    verify_parents(review)
    started = run.time.monotonic()
    kept = work / "retained"
    kept.mkdir(mode=0o700)
    run.disk_guard(kept, review["minimum_host_free_bytes"] + 4 * prepare.GIB)
    runtime = kept / "runtime"
    old_archive = OLD / "retained/ollama-darwin.tgz"
    if run.file_digest(old_archive) != review["archive"]["sha256"]:
        raise ValueError("retained archive bytes differ")
    extract(old_archive, runtime, prepare.load(review["archive_index"]))
    executable = runtime / "ollama"
    for program in (executable, runtime / "llama-server"):
        subprocess.run(
            ["/usr/bin/codesign", "--verify", "--strict", str(program)],
            env={"PATH": "/usr/bin:/bin"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=15,
        )
    models = kept / "models"
    blobs = models / "blobs"
    blobs.mkdir(mode=0o700, parents=True)
    for asset in review["model_assets"]:
        name = "sha256-" + asset["sha256"]
        src, dst = OLD / "retained/models/blobs" / name, blobs / name
        run.disk_guard(blobs, review["minimum_host_free_bytes"] + asset["size"])
        shutil.copyfile(src, dst)
        if (
            dst.stat().st_size != asset["size"]
            or run.file_digest(dst) != asset["sha256"]
            or run.time.monotonic() - started >= max_seconds - 5
        ):
            raise ValueError("retained model did not verify within the setup window")
    namespace, tag = review["model"].split(":")
    manifest = models / "manifests" / "registry.ollama.ai" / "library" / namespace / tag
    manifest.parent.mkdir(parents=True)
    prepare.write(manifest, Path(review["model_manifest"]).read_bytes())
    return {
        "executable": str(executable),
        "executable_sha256": run.file_digest(executable),
        "retained_artifacts_reused": 1 + len(review["model_assets"]),
        "download_bytes": 0,
        "model_manifest_sha256": run.file_digest(manifest),
    }


def prepare_review(work):
    candidate = prepare.prepare(work)
    review = prepare.load(candidate)
    candidate.rename(work / "unapproved-parent-template.json")
    old = prepare.load(OLD / "result.json")
    [operation] = old["operations"]["operations"]
    with ReceiptStore(review["database"], read_only=True) as store:
        repo = AssessmentRepository(store)
        charge = repo.get("operation_measurement", operation["operation_id"])
    archive = OLD / "retained/ollama-darwin.tgz"
    if run.file_digest(archive) != review["archive"]["sha256"]:
        raise ValueError("parent archive bytes differ")
    index = archive_index(archive)
    for item in ("ollama", "llama-server", "llama-quantize"):
        assert index["members"][item]["kind"] == "file" and index["members"][item]["executable"]
    for name, member in index["members"].items():
        partial = OLD / "retained/runtime" / name
        if partial.is_file():
            assert run.file_digest(partial) == member["sha256"]
    inventory = prepare.write(work / "archive-index.json", index)
    found = {
        str(OLD / file): run.file_digest(OLD / file)
        for file in ("operation-review.json", "result.json", "started.json")
    }
    seconds = sum(item["reserved_seconds"] for item in STAGES.values())
    review.update(
        purpose="Correct private extraction of the same pinned Ollama archive, then run the previously unstarted Waza task and protected grade once.",
        allowed_download_hosts=[],
        maximum_download_response_bytes=0,
        archive_index=str(inventory),
        stages=STAGES,
        maximum_reserved_seconds=seconds,
        prior_operation={
            "operation_id": operation["operation_id"],
            "measurement_ref": run.content_digest(charge),
        },
        archive_symlinks=[
            name for name, meta in index["members"].items() if meta["kind"] == "library_alias"
        ],
        additional_setup_operations_vs_original=1,
    )
    baseline = review["grant_baseline"]
    assert baseline["state"][1] == 7 and baseline["state"][2] == 0
    review["grant_absolute_limits"]["max_elapsed_seconds"] = max(
        baseline["effective_limits"]["max_elapsed_seconds"], baseline["state"][3] + seconds
    )
    review["boundaries"][0] = (
        "Offline reuse only. Verify the retained archive and five model blobs. "
        "Create exactly audited intra-directory dynamic-library aliases after writing owned runtime files."
    )
    review["retention"] = (
        "Preserve original downloaded artifacts and partial tree. Keep the new verified runtime and model copy. "
        "Remove only new owned scratch after verified process stop."
    )
    review["pins"].update(
        found
        | {
            str(Path(__file__).resolve()): run.file_digest(Path(__file__).resolve()),
            str(inventory): run.file_digest(inventory),
        }
    )
    for asset in review["model_assets"]:
        blob = OLD / "retained/models/blobs" / ("sha256-" + asset["sha256"])
        if blob.stat().st_size != asset["size"] or run.file_digest(blob) != asset["sha256"]:
            raise ValueError("retained model bytes differ")
    file = prepare.write(work / "operation-review.json", review)
    verify_parents(review)
    return file


def alias_controls(work):
    good = work / "valid.tgz"
    with tarfile.open(good, "w:gz") as archive:
        source = work / "lib.1.dylib"
        source.write_text("first-party fixture")
        archive.add(source, arcname="lib.1.dylib")
        for name, link in (("lib.dylib", "lib.0.dylib"), ("lib.0.dylib", "lib.1.dylib")):
            entry = tarfile.TarInfo(name)
            entry.type = tarfile.SYMTYPE
            entry.linkname = link
            archive.addfile(entry)
    output = work / "installed"
    extract(good, output, archive_index(good))
    installed = output / "lib.dylib"
    assert installed.is_symlink() and installed.read_text() == "first-party fixture"
    for idx, target in enumerate(
        ("../outside.dylib", "/etc/test.dylib", "cycle.dylib", "missing.dylib")
    ):
        denied = work / f"denied-{idx}.tgz"
        with tarfile.open(denied, "w:gz") as archive:
            entry = tarfile.TarInfo("cycle.dylib")
            entry.type = tarfile.SYMTYPE
            entry.linkname = target
            archive.addfile(entry)
        try:
            archive_index(denied)
        except ValueError:
            continue
        raise AssertionError("unreviewed library alias passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--execute-approved")
    args = parser.parse_args()
    file = prepare_review(args.path.resolve()) if args.prepare else args.path.resolve()
    review = prepare.load(file)
    verify_parents(review)
    # Reuse the unchanged supervised Waza run, settling the retained setup under
    # its own bounded stage. No code path calls the original acquisition function.
    run.STAGES = check.STAGES = STAGES
    run.install = install_retained
    ref = run.file_digest(file)
    run.verify(review, file)
    if args.execute_approved:
        approval = prepare.load(file.with_name("operator-approval.json"))
        if not (
            args.execute_approved == ref == approval["review_sha256"]
            and approval["approved"] is True
        ):
            raise SystemExit("explicit approval for this exact continuation is required")
        result = run.run(review, file, ref)
        print(json.dumps(result, indent=2))
        raise SystemExit(not result["passed"])
    with tempfile.TemporaryDirectory(prefix="archive-controls-", dir=file.parent) as control:
        alias_controls(Path(control))
    check.main(file)
