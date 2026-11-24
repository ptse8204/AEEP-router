"""Materialize the reviewed VAREX PDFs as ordinary document task archives."""

import argparse
import io
import json
import re
import shutil
import subprocess
from zipfile import ZipFile

from audit_varex_source_families import verified_pdfs
from check_varex_cohort import INTAKE
from review_varex_balanced_capacity import packing
from review_varex_form_lineage import audit
from stage_varex_calibration import (
    DATASET,
    LICENCE,
    MANIFEST,
    REV,
    ROLES,
    SCORER,
    WORK,
    digest,
    pinned,
    write,
)
from stage_varex_references import BATCH, COMPLEMENT, FLOOR

from aeep.assessment.models import content_digest
from aeep_toolkit.benchmarks import (
    BenchmarkPack,
    BenchmarkTask,
    document_archive,
    stage_document_archive,
)
from aeep_toolkit.models import SourcePin

DESTINATION = BATCH / "staged-prospects"
BALANCED = BATCH / "balanced-prospects"
CAPACITY = "a7eca5939be12d832c2112f58de5bff09f321a1451ce4c69f06c8d1a4a7423e1"
COMPLEMENT_INTAKE = "c7ebc8dba5b5aec1884c91274c1052a7c20c3f259bcca9ea1748be7cc50ece74"
LICENSE_SHA = "4531a67d443284d93ffed0803df5b10634aff21c3d77e381f2d48af01d875868"
SOURCE_RIGHTS = "CDLA Permissive 2.0 publisher data. Protected local cohort preparation only. No transfer is authorized."
INSTRUCTIONS = (
    "Read environment/document.pdf and extract the visible values into output.json following "
    "environment/schema.json. Preserve repeated entries in arrays. Use null for missing values "
    f"where the schema allows it. VAREX data license: {LICENCE}.\n"
).encode()
ARCHIVE_FILES = {"environment/document.pdf", "environment/schema.json", "instruction.md"}


def task_id(name):
    return "varex-" + re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")


def stage_asset(source, body, target):
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if target.is_symlink():
        raise ValueError("staged inputs cannot be symlinks")
    if target.exists():
        pinned(target, digest(body))
        if target.stat().st_nlink == 1:
            return
        if source is None or not target.samefile(source):
            raise ValueError("staged link is not the owned alias of this publisher input")
        clone = target.with_suffix(target.suffix + ".clone")
        if clone.exists() or clone.is_symlink():
            raise ValueError("a previous independent copy is present")
        subprocess.run(["/bin/cp", "-c", str(source), str(clone)], check=True, timeout=10)
        pinned(clone, digest(body))
        if clone.stat().st_nlink != 1:
            raise ValueError("the archive member requires an independent file")
        clone.replace(target)
    elif source is None:
        with target.open("xb") as stream:
            stream.write(body)
    else:
        subprocess.run(["/bin/cp", "-c", str(source), str(target)], check=True, timeout=10)
    if target.stat().st_nlink != 1:
        raise ValueError("the archive member requires an independent file")
    pinned(target, digest(body))


def candidates(balanced):
    lineage, _ = audit()
    receipts = json.loads(pinned(BATCH / "reference-intake.json", INTAKE))
    pdfs, _, unavailable = verified_pdfs()
    high = set(lineage["prospects"])
    selected = {name: (BATCH, receipts["cases"][name], pdfs[name], "multiple-collections") for name in high}
    if len(selected) != 122 or unavailable:
        raise ValueError("prospective case inventory or normalized IDs changed")
    if not balanced:
        return selected
    report_path = BATCH.parents[2] / "reports/toolkit-v2/c13/completion-20261116/varex-balanced-capacity-20261124.json"
    capacity = json.loads(pinned(report_path, CAPACITY))
    low = set(capacity["complementary_prospects"])
    groups = capacity["provisional_source_groups"]
    singles = sorted(group[0] for group in groups if len(group) == 1 and group[0] in low)
    if not capacity["a_provisional_source_disjoint_packing_fits"] or not 0 <= len(low) - 124 <= len(singles):
        raise ValueError("balanced prospective pack cannot fit the reviewed sources")
    low -= set(singles[:len(low) - 124])
    retained = high | low
    retained_groups = [sorted(retained.intersection(group)) for group in groups]
    if not packing([group for group in retained_groups if group], high, low):
        raise ValueError("retained archive membership loses provisional source separation")
    refs = COMPLEMENT / "protected-references"
    low_receipts = json.loads(pinned(refs / "reference-intake.json", COMPLEMENT_INTAKE))
    downloads = json.loads((COMPLEMENT / "pdf-intake.json").read_bytes())
    for name in low:
        doc = downloads["files"][name]
        source = COMPLEMENT / "public-pdfs" / (digest(name.encode()) + ".pdf")
        selected[name] = (
            refs, low_receipts["cases"][name], (source, doc["sha256"], doc["bytes"]), "at-most-one-collection",
        )
    return selected


def task_pack(*, stage, balanced):
    selected = candidates(balanced)
    if len(set(map(task_id, selected))) != len(selected):
        raise ValueError("normalized task IDs collide")
    license_body = pinned(WORK / "LICENSE", LICENSE_SHA)
    scorer = pinned(MANIFEST.parent / "score.py", SCORER)
    dest = BALANCED if balanced else DESTINATION
    root = dest / "pack"
    public = dest / "public"
    if stage:
        prospective_bytes = sum(pdf[2] for _, _, pdf, _ in selected.values())
        if shutil.disk_usage(BATCH).free < FLOOR + prospective_bytes + 3_000_000:
            raise ValueError("archive staging would cross the host reserve")
        public.mkdir(parents=True, mode=0o700, exist_ok=True)
    tasks, sources = [], {}
    for name, (case_root, row, (pdf, pdf_sha, _), _) in sorted(selected.items()):
        identity = task_id(name)
        protected = case_root / "protected" / row["protected_case"]
        schema, oracle = protected / "schema.json", protected / "reference.json"
        files = {
            "instruction.md": (None, INSTRUCTIONS),
            "environment/document.pdf": (pdf, pinned(pdf, pdf_sha)),
            "environment/schema.json": (schema, pinned(schema, row["schema_sha256"])),
            "solution/expected.json": (oracle, pinned(oracle, row["reference_sha256"])),
            "tests/verifier.py": (None, scorer),
            "LICENSE": (WORK / "LICENSE", license_body),
        }
        assets = []
        for relative, (path, content) in files.items():
            target = f"tasks/{identity}/{relative}"
            if stage:
                stage_asset(path, content, root / target)
            assets.append(
                {"path": target, "bytes": len(content), "sha256": digest(content), "role": ROLES[relative]}
            )
        tasks.append(BenchmarkTask(
            task_id=identity, domain="document-data", difficulty="unknown", assets=assets,
            output_paths=["output.json"], upstream_score="native_reward",
            adaptations=["Local extraction instruction and earlier protected native reference verification."],
        ))
        sources[identity] = SourcePin(
            repository=DATASET, revision=REV, license_expression="CDLA-Permissive-2.0",
            data_rights=SOURCE_RIGHTS, artifact_sha256=pdf_sha,
        )
    inventory = {
        "tasks": [task.model_dump(mode="json") for task in tasks],
        "task_sources": {name: pin.model_dump(mode="json") for name, pin in sources.items()},
    }
    pack = BenchmarkPack(
        schema_version="aeep.toolkit.benchmark-pack.v2", pack_id="reviewed-documents", tasks=tasks,
        task_sources=sources, source=SourcePin(
            repository=DATASET, revision=REV, license_expression="CDLA-Permissive-2.0",
            data_rights=SOURCE_RIGHTS, artifact_sha256=content_digest(inventory),
        ),
    )
    return pack, root, public, {name: selected[name][3] for name in sorted(selected)}


def ready(stage, balanced=False):
    pack, root, public, selected = task_pack(stage=stage, balanced=balanced)
    manifest = root.parent / "benchmark-pack.json"
    serialized = pack.model_dump(mode="json")
    if stage and not manifest.exists():
        write(manifest, serialized)
    elif json.loads(manifest.read_bytes()) != serialized:
        raise ValueError("staged benchmark pack drift")
    results = {}
    for name, family in selected.items():
        task = task_id(name)
        model, _ = document_archive(pack, root, task, family, archive_instructions=True)
        value = model.model_dump(mode="json")
        output_path = public / (value["task_archive_sha256"] + ".zip")
        if stage and not output_path.exists():
            if shutil.disk_usage(BATCH).free < FLOOR + 4_000_000:
                raise ValueError("staged archive would cross the host reserve")
            if value != stage_document_archive(pack, root, task, family, public, archive_instructions=True):
                raise ValueError("public archive content drifted during staging")
        archive_sha = value["task_archive_sha256"]
        body = pinned(public / (archive_sha + ".zip"), archive_sha)
        with ZipFile(io.BytesIO(body)) as archive:
            if len(archive.namelist()) != 3 or set(archive.namelist()) != ARCHIVE_FILES:
                raise ValueError("public archive contains a protected asset")
            for member in archive.infolist():
                pinned_file = next(a for a in pack.task(task).assets if a.path.endswith("/" + member.filename))
                if member.file_size != pinned_file.bytes or digest(archive.read(member)) != pinned_file.sha256:
                    raise ValueError("public archive entry differs from its reviewed artifact")
        results[name] = {"input": value, "archive_bytes": len(body)}
    result = {
        "schema_version": "aeep.c13.varex-staged-prospects.v1", "benchmark_pack_sha256": content_digest(serialized),
        "manifest_file_sha256": digest(manifest.read_bytes()), "prepared_cases": len(results),
        "public_archives_bytes": sum(row["archive_bytes"] for row in results.values()),
        "cases": results, "reference_intake": INTAKE, "asset_use_approved": False,
        "model_turns": 0, "cash_usd": 0, "formal_assignments": 0,
    }
    if balanced:
        result["complement_intake"] = COMPLEMENT_INTAKE
        result["provisional_capacity_report"] = CAPACITY
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "verify"))
    parser.add_argument("--balanced", action="store_true")
    args = parser.parse_args()
    bound = ready(args.action == "stage", args.balanced)
    evidence = (BALANCED if args.balanced else DESTINATION) / "staged.json"
    if args.action == "stage":
        write(evidence, bound)
    elif json.loads(evidence.read_bytes()) != bound:
        raise ValueError("document archive readback differs from its staging record")
    print(json.dumps({name: value for name, value in bound.items() if name != "cases"}))
