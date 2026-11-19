"""Apply the published repairs and protected overlays as data."""

import io
import json
import shutil
import tarfile
import tempfile
import tomllib
from pathlib import Path

from acquire_full_rebench_leads import RESERVE, TARGET, ref
from screen_candidate_patches import ROW_KEYS, load_reviewed_helpers, snapshot, test_roots
from stage_repository_transport import ROOT, digest, encode, read, write

from aeep.assessment.repository_suites import archive_files, pack_files

LOCIFY = "ryanhoangt__locify-8"
EOS = "Akkudoktor-EOS__EOS-459"
PROFILES = {
    LOCIFY: {
        "overlay": {"tests/integration/test_repo_map_strategy.py"},
        "changes": {
            "locify/indexing/full_map/strategy.py",
            "locify/indexing/repo_map/strategy.py",
            "pyproject.toml",
        },
        "additions": {"locify/indexing/prompts.py"},
        "counts": (1, 1),
    },
    EOS: {
        "overlay": {"tests/testdata/optimize_input_1.json"},
        "changes": {"src/akkudoktoreos/utils/visualize.py"},
        "additions": set(),
        "counts": (1, 342),
    },
}
OUTPUT = TARGET / "retained-reference-assets"


def stage(case, source, profile, helpers):
    raw_pin = source["archive"]
    path = ROOT / raw_pin["path"]
    raw = read(path, raw_pin["sha256"])
    omitted = {}
    if case == EOS:
        # Preserve the exact publisher tar separately. The ordinary carrier forbids
        # .env files in trial payloads; retain only its digest in this projection.
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as source_tar:
            original = {}
            for member in source_tar:
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError("projection would change a nonregular member")
                name = member.name.split("/", 1)[1]
                data = source_tar.extractfile(member).read()
                if name == ".env":
                    omitted[name] = {"sha256": digest(data), "bytes": len(data)}
                elif name in original:
                    raise ValueError("projection repeats a publisher member")
                else:
                    original[name] = data
        if omitted.keys() != {".env"} or len(original) + 1 != source["files"]:
            raise ValueError("publisher projection changed its approved omission")
        pack_files(original, large=True)
    else:
        original = helpers["archive"].normalize_large(raw)
    row_pin = ref(path.with_name("row.json"))
    row = json.loads(read(ROOT / row_pin["path"], row_pin["sha256"]))
    semantic = digest(json.dumps({key: row[key] for key in ROW_KEYS}, sort_keys=True).encode())
    if (
        row["instance_id"] != case
        or row["base_commit"] != source["source_revision"]
        or row["repo"].casefold() != source["repository"].casefold()
        or semantic != source["metadata_semantic_sha256"]
        or row["install_config"].get("env_vars")
    ):
        raise ValueError("verified publisher binding changed")
    for notice in source["license_notices"]:
        body = original[notice["file"]]
        if digest(body) != notice["sha256"] or len(body) != notice["bytes"]:
            raise ValueError("publisher notice changed")

    issue, preserve = row["FAIL_TO_PASS"], row["PASS_TO_PASS"]
    nodes = issue + preserve
    modules, roots = test_roots(nodes)
    if (len(issue), len(preserve)) != profile["counts"] or len(set(nodes)) != len(nodes):
        raise ValueError("published verifier identity inventory changed")
    with tempfile.TemporaryDirectory(prefix="aeep-rebench-inert-", dir="/private/tmp") as temp:
        root = Path(temp).resolve()
        for name, data in original.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        helpers["patch"].apply(root, row["test_patch"], root.parent)
        overlaid = snapshot(root)
        if (
            original.keys() - overlaid.keys()
            or {name for name in overlaid if original.get(name) != overlaid[name]}
            != profile["overlay"]
            or set(modules) - overlaid.keys()
        ):
            raise ValueError("standalone test overlay changed")
        helpers["patch"].apply(root, row["patch"], root.parent)
        repaired = snapshot(root)
    if (
        overlaid.keys() - repaired.keys()
        or repaired.keys() - overlaid.keys() != profile["additions"]
        or {name for name in overlaid if overlaid[name] != repaired[name]} != profile["changes"]
        or any(not name.startswith("tests/") for name in profile["overlay"])
        or any(name.startswith("tests/") for name in profile["changes"] | profile["additions"])
    ):
        raise ValueError("repair and protected test boundaries changed")
    if case == LOCIFY:
        normalized = [
            tomllib.loads(tree["pyproject.toml"].decode()) for tree in (original, repaired)
        ]
        first, second = normalized
        if (
            first["tool"]["poetry"].pop("description")
            == second["tool"]["poetry"].pop("description")
            or first != second
        ):
            raise ValueError("published packaging change is no longer description-only")

    folder = OUTPUT / case
    folder.mkdir(mode=0o700, exist_ok=True)
    assets = {}
    for label, tree in (
        ("untouched-source", original),
        ("protected-overlay", {name: overlaid[name] for name in profile["overlay"]}),
        ("original-with-verifier", overlaid),
        ("reference-with-verifier", repaired),
    ):
        data = pack_files(tree, large=True)
        if archive_files(data, large=True) != tree:
            raise ValueError("protected archive round trip changed its inputs")
        target = folder / f"{label}.tar.gz"
        retain(target, data)
        assets[label] = ref(target) | {"bytes": len(data), "files": len(tree)}
    prompt = row["problem_statement"] + ("\n\n" + row["interface"] if row.get("interface") else "")
    for name, data in (
        ("statement.txt", prompt.encode()),
        ("required.json", encode({"fail_to_pass": issue, "pass_to_pass": preserve})),
    ):
        target = folder / name
        retain(target, data)
        assets[name] = ref(target) | {"bytes": len(data)}
    return {
        "case": case,
        "publisher_archive": raw_pin,
        "row": row_pin,
        "ordinary_archive_omissions": omitted,
        "assets": assets,
        "required_issue": len(issue),
        "required_preservation": len(preserve),
        "test_roots": roots,
        "source_additions": sorted(profile["additions"]),
        "source_changes": sorted(profile["changes"]),
        "protected_changes": sorted(profile["overlay"]),
        "statement_characters": len(prompt),
        "grader_invocations": 0,
        "ordinary_task_binding": {
            LOCIFY: "The ordinary patch guard requires editable paths in the original archive.",
            EOS: "The frozen statement exceeds the 4,000-character ordinary task input limit.",
        }[case],
        "published_python": row["install_config"]["python"],
    }


def retain(path, data):
    if path.exists():
        read(path, digest(data))
    else:
        write(path, data)


def main():
    if shutil.disk_usage(TARGET).free < RESERVE + 16 * 1024**2:
        raise RuntimeError("source staging needs 16 MiB above the 52 GiB floor")
    source_path = TARGET / "archives-result.json"
    sources = json.loads(source_path.read_bytes())
    helpers = load_reviewed_helpers()
    OUTPUT.mkdir(mode=0o700, exist_ok=True)
    results = [stage(case, sources[case], profile, helpers) for case, profile in PROFILES.items()]
    write(
        OUTPUT / "result.json",
        encode(
            {
                "publisher_bindings": ref(source_path),
                "staging_driver": ref(Path(__file__).resolve()),
                "cases": results,
                "comparisons_paused": True,
                "waza_excluded": True,
            }
        ),
    )


if __name__ == "__main__":
    main()
