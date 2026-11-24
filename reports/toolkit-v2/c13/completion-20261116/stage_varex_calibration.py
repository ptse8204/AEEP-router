"""Acquire and bind two public VAREX cases for local protected calibration."""

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener
from zipfile import ZipFile

import pyarrow
from audit_varex_schema_projection import (
    CDN,
    COLUMNS,
    MANIFEST,
    MANIFEST_SHA,
    REV,
    ROOT,
    TREE_SHA,
    BoundRedirect,
    RangeStore,
    collection_paths,
    digest,
    pinned,
    project,
    write,
)
from audit_varex_schema_projection import (
    WORK as METADATA,
)

WORK = METADATA.parent / "varex-calibration"
DATASET = "https://huggingface.co/datasets/ibm-research/VAREX"
LICENCE = "https://cdla.dev/permissive-2-0/"
LICENCE_TEXT = "https://raw.githubusercontent.com/Community-Data-License-Agreements/Releases/main/CDLA-Permissive-2.0.txt"
SCORER = "f878742c621a43a8d4bd5f8d0815b66afec46b84abffe6ad6c79d37fde7c9379"
EXCLUSIONS = "b07e545709b337176e50d7a6b3460cabce62029552b5d41c5881ff7fea04fdd9"
CASES = ("GSA_3418", "HUD-11706")
SOURCE = "2896e52509b33a5628f8d5833a9b6111ebff9f0ed374faa08da539a57753c896"
FROZEN = ROOT / ".aeep/c13-intake-wheel-20261124/linux/source"
RANGE_LIMIT = 180_000
ROLES = {
    "instruction.md": "instruction", "environment/document.pdf": "input",
    "environment/schema.json": "input", "solution/expected.json": "oracle",
    "tests/verifier.py": "verifier", "LICENSE": "license",
}
PDF_TREE = {
    "pdf-tree-0.json": "4790c7e98c391cb0a18f7d85e6faa272d18b0e5948b7507093d2303bf4da6194",
    "pdf-tree-1.json": "9f554d3779219f1919985234802ec99f56b3e624d5855a0823a4f4df05079ea6",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("unexpected redirect from the license publisher")


class ReferenceColumns:
    def __init__(self):
        self.retained = RangeStore({"max_bytes": 1_000_000}, False, work=METADATA)
        self.additional = RangeStore({"max_bytes": RANGE_LIMIT}, True, work=WORK)

    def read(self, row, start, size):
        key = (row["lfs"]["oid"], start, size)
        store = self.retained if key in self.retained.expected else self.additional
        if store is self.additional and len(store.transfers) >= 3:
            raise ValueError("reference projection uses more than three new ranges")
        return store.read(row, start, size)


def scope():
    prospects = json.loads(pinned(
        METADATA / "multiple-collection-prospects.json",
        "9d4604b731be1922926567e2ee2e31c6594a375801d8dea9901727cfe9a9d606",
    ))
    pdfs = json.loads(pinned(
        METADATA / "pdf-metadata-result.json",
        "7ed679a52a481e6d842658a1f28476eb75a9c40dcfa650485ed45b4f316b1d28",
    ))
    pinned(METADATA / "range-receipts.json",
           "06d7d6b9717c33e515810ff11031db52f253bde0796b62928a0a9dc66c150be0")
    pinned(MANIFEST, MANIFEST_SHA)
    cases = {row["doc_id"]: row for row in pdfs["prospects"] if row["doc_id"] in CASES}
    for doc_id, case in cases.items():
        case.update(prospects["cases"][doc_id])
        if case["pdf_path"] != f"pdfs/{doc_id}.pdf" or not case["lfs_sha256"]:
            raise ValueError("case requires an exact publisher PDF")
    tree = json.loads(pinned(METADATA / "publisher-tree.json", TREE_SHA))
    shards = [row for row in tree if row["lfs"]["oid"] in {c["shard_sha256"] for c in cases.values()}]
    if set(cases) != set(CASES) or len(shards) != 1 or pyarrow.__version__ != "21.0.0":
        raise ValueError("reviewed row, shard or decoder drift")
    return {
        "dataset_revision": REV, "scorer_revision": "3cce9c18530748cfc843f38c02e2f43e0694d167",
        "driver_sha256": digest(Path(__file__).read_bytes()),
        "reader_sha256": digest(Path(project.__code__.co_filename).read_bytes()),
        "cases": cases, "shard": shards[0], "projected_columns": [*COLUMNS, "ground_truth"],
        "maximum_new_ranges": 3, "maximum_range_bytes": RANGE_LIMIT,
        "license_url": LICENCE, "license_text_url": LICENCE_TEXT, "license_maximum_bytes": 16_384,
        "maximum_pdf_bytes": sum(c["bytes"] for c in cases.values()),
        "minimum_host_free_bytes": 50 * 2**30, "model_turns": 0, "cash_usd": 0,
        "disclosure": False, "retries": 0,
        "authority": "C13 bounded local cohort verification and standing first-check delegation",
    }


def schema_audit(node):
    if isinstance(node, dict):
        if node.keys() & {"default", "example", "examples", "const"}:
            raise ValueError("public schema requires a separate embedded-answer review")
        if "$ref" in node and not node["$ref"].startswith("#/"):
            raise ValueError("schema references an external source")
        for child in node.values():
            schema_audit(child)
    elif isinstance(node, list):
        for child in node:
            schema_audit(child)


def pdf(case):
    size = case["bytes"]
    redirect = BoundRedirect({"lfs": {"oid": case["lfs_sha256"]}, "size": size})
    with build_opener(redirect).open(f"{DATASET}/resolve/{REV}/{case['pdf_path']}", timeout=30) as reply:
        if not redirect.observed or urlsplit(reply.geturl()).hostname != CDN or reply.status != 200:
            raise ValueError("PDF is outside the reviewed storage binding")
        body = reply.read(size + 1)
    if len(body) != size or not body.startswith(b"%PDF-") or digest(body) != case["lfs_sha256"]:
        raise ValueError("complete PDF differs from the pinned object")
    return body


def acquire(review):
    if shutil.disk_usage(ROOT).free < review["minimum_host_free_bytes"]:
        raise ValueError("host reserve is unavailable")
    WORK.mkdir(mode=0o700)
    (WORK / "ranges").mkdir(mode=0o700)
    write(WORK / "acquisition-review.json", review)
    ranges = ReferenceColumns()
    try:
        selected = {}
        for row in project(review["shard"], ranges, columns=tuple(review["projected_columns"])):
            if row["doc_id"] in review["cases"]:
                if row["doc_id"] in selected:
                    raise ValueError("duplicate reviewed document")
                selected[row["doc_id"]] = row
        if set(selected) != set(CASES):
            raise ValueError("the publication does not include both selected rows")
        with build_opener(NoRedirect()).open(LICENCE_TEXT, timeout=15) as reply:
            license_body = reply.read(review["license_maximum_bytes"] + 1)
        if (
            not 0 < len(license_body) <= review["license_maximum_bytes"]
            or b"Permissive, Version 2.0" not in license_body
        ):
            raise ValueError("published license text differs")
        (WORK / "LICENSE").write_bytes(license_body)
        files = {}
        for doc_id, row in selected.items():
            case = review["cases"][doc_id]
            schema, reference = row["schema"].encode(), row["ground_truth"].encode()
            if digest(schema) != case["schema_sha256"] or row["split"] != case["split"]:
                raise ValueError("publisher row drift")
            if not isinstance(json.loads(reference), dict):
                raise ValueError("protected reference is not a JSON object")
            folder = WORK / "acquired" / doc_id
            folder.mkdir(parents=True, mode=0o700)
            bodies = {"schema.json": schema, "expected.json": reference, "document.pdf": pdf(case)}
            for name, body in bodies.items():
                (folder / name).write_bytes(body)
            files[doc_id] = {name: digest(body) for name, body in bodies.items()}
        write(WORK / "acquisition-result.json", {
            "license_sha256": digest(license_body), "cases": files,
            "projected_reference_rows_retained": len(selected),
        })
    finally:
        write(WORK / "retained-reference-ranges.json", ranges.additional.transfers)


def stage():
    import subprocess
    import sys

    from aeep.assessment.models import content_digest
    from aeep.assessment.verification import verification_source_digest
    from aeep_toolkit.benchmarks import BenchmarkPack, BenchmarkTask
    from aeep_toolkit.models import SourcePin

    if verification_source_digest(FROZEN) != SOURCE:
        raise ValueError("current verified source changed")
    review = scope()
    saved = json.loads((WORK / "acquisition-review.json").read_bytes())
    if saved["driver_sha256"] != review["driver_sha256"]:
        pinned(WORK / "acquisition-driver.py", saved["driver_sha256"])
    if saved != review | {"driver_sha256": saved["driver_sha256"]}:
        raise ValueError("acquisition review drift")
    result = json.loads((WORK / "acquisition-result.json").read_bytes())
    license_body = pinned(WORK / "LICENSE", result["license_sha256"])
    scorer = pinned(MANIFEST.parent / "score.py", SCORER)
    pinned(MANIFEST.parent / "field_exclusions.json", EXCLUSIONS)
    pack_root = WORK / "pack"
    public = WORK / "public-verified"
    public.mkdir(mode=0o700)
    task_sources, tasks = {}, []
    rights_statement = "CDLA Permissive 2.0 publisher data. Reviewed local calibration only. No provider disclosure."
    for doc_id in CASES:
        case = review["cases"][doc_id]
        task_id = f"varex-{doc_id.lower().replace('_', '-')}"
        raw = {name: pinned(WORK / "acquired" / doc_id / name, sha)
               for name, sha in result["cases"][doc_id].items()}
        schema_audit(json.loads(raw["schema.json"]))
        instruction = (
            "Extract the data visible in document.pdf into output.json following schema.json. "
            "Keep each repeated entry as a separate array item. Use null for missing values "
            "where the schema permits it. The document is from VAREX and is distributed under "
            f"CDLA Permissive 2.0 ({LICENCE}).\n"
        ).encode()
        contents = dict(zip(ROLES, (
            instruction, raw["document.pdf"], raw["schema.json"], raw["expected.json"],
            scorer, license_body,
        ), strict=True))
        assets = []
        for name, body in contents.items():
            path = f"tasks/{task_id}/{name}"
            target = pack_root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                pinned(target, digest(body))
            else:
                with target.open("xb") as output:
                    output.write(body)
            assets.append({"path": path, "bytes": len(body), "sha256": digest(body), "role": ROLES[name]})
        rights = {
            "source": f"{DATASET}/blob/{REV}/{case['pdf_path']}", "synthetic_filled_form": True,
            "license": LICENCE, "license_sha256": digest(license_body),
            "document_sha256": case["lfs_sha256"], "runtime_use": "local protected calibration",
            "provider_disclosure": False,
        }
        rights_path = WORK / f"{task_id}-rights.json"
        if not rights_path.exists():
            write(rights_path, rights)
        elif json.loads(rights_path.read_bytes()) != rights:
            raise ValueError("case rights review drift")
        tasks.append(BenchmarkTask(
            task_id=task_id, domain="document-data", difficulty="unknown", assets=assets,
            output_paths=["output.json"], upstream_score="native_reward",
            rights_review_ref=content_digest(rights),
            adaptations=["Local extraction instruction and ordinary CLI asset layout. Original PDF, schema, reference and scorer preserved."],
        ))
        task_sources[task_id] = SourcePin(
            repository=DATASET, revision=REV, license_expression="CDLA-Permissive-2.0",
            data_rights=rights_statement,
            artifact_sha256=case["lfs_sha256"],
        )
    inventory = {
        "tasks": [task.model_dump(mode="json") for task in tasks],
        "task_sources": {name: pin.model_dump(mode="json") for name, pin in task_sources.items()},
    }
    manifest = WORK / "benchmark-pack.json"
    pack = BenchmarkPack(
        schema_version="aeep.toolkit.benchmark-pack.v2", pack_id="reviewed-documents",
        source=SourcePin(repository=DATASET, revision=REV, license_expression="CDLA-Permissive-2.0",
                         data_rights=rights_statement, artifact_sha256=content_digest(inventory)),
        tasks=tasks, task_sources=task_sources,
    )
    if not manifest.exists():
        write(manifest, pack.model_dump(mode="json"))
    elif json.loads(manifest.read_bytes()) != pack.model_dump(mode="json"):
        raise ValueError("existing pack manifest drift")
    for task in tasks:
        result = subprocess.run(
            [sys.executable, "-B", "-m", "aeep_toolkit", "benchmark", "stage-document", "--pack", str(manifest),
             "--root", str(pack_root), "--task", task.task_id, "--family", "multiple-collections",
             "--archive-instructions", "--destination", str(public)],
            capture_output=True, check=True, timeout=20,
        )
        binding = json.loads(result.stdout)
        with ZipFile(public / (binding["task_archive_sha256"] + ".zip")) as archive:
            if set(archive.namelist()) != {"environment/document.pdf", "environment/schema.json", "instruction.md"}:
                raise ValueError("archive includes an unexpected asset")
        write(WORK / f"{task.task_id}-input.json", binding)


def cohort_capacity():
    """Measure the remaining publisher catalog against the existing archive and shape screen."""
    pinned(METADATA / "range-receipts.json",
           "06d7d6b9717c33e515810ff11031db52f253bde0796b62928a0a9dc66c150be0")
    store = RangeStore({"max_bytes": 1_000_000}, False, work=METADATA)
    shards = json.loads(pinned(METADATA / "publisher-tree.json", TREE_SHA))
    pdfs = [row for name, pin in PDF_TREE.items() for row in json.loads(pinned(METADATA / name, pin))]
    paths = {row["path"]: row for row in pdfs}
    if len(paths) != 1777 or len(pdfs) != 1777:
        raise ValueError("publisher PDF inventory count changed")
    counts = {"at_most_one_collection": Counter(), "multiple_collections": Counter()}
    seen = set()
    for shard in shards:
        for row in project(shard, store):
            doc_id = row["doc_id"]
            if doc_id in seen:
                raise ValueError("duplicate publication record")
            seen.add(doc_id)
            schema = json.loads(row["schema"])
            label = "multiple_collections" if len(collection_paths(schema)) >= 2 else "at_most_one_collection"
            bucket = counts[label]
            bucket["publisher_rows"] += 1
            if doc_id in CASES:
                bucket["held_for_calibration"] += 1
                continue
            try:
                schema_audit(schema)
            except ValueError:
                bucket["requires_schema_review"] += 1
                continue
            pdf = paths[f"pdfs/{doc_id}.pdf"]
            if pdf["size"] + len(row["schema"].encode()) + 1024 >= 4_000_000:
                bucket["exceeds_stored_archive_screen"] += 1
                continue
            bucket["metadata_prospects"] += 1
            bucket["lfs_sha256" if pdf.get("lfs") else "git_blob"] += 1
    if len(seen) != len(paths):
        raise ValueError("publisher task and PDF inventories differ")
    return {
        "schema_version": "aeep.c13.varex-cohort-capacity.v1",
        "dataset_revision": REV, "pdf_tree_sha256": PDF_TREE, "parquet_tree_sha256": TREE_SHA,
        "rows": {label: dict(bucket) for label, bucket in counts.items()},
        "holdouts": 2, "cases_per_holdout": 105, "shared_early_cases": 36,
        "minimum_multiple_collection_cases": 122,
        "bound_scope": "Schema and stored archive sizes only. Source family, asset rights and qualifying grades remain case-specific.",
        "formal_assignments": 0, "new_protected_calls": 0, "model_turns": 0, "downloads": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("review", "acquire", "stage", "audit-cohort"))
    action = parser.parse_args().action
    if action == "review":
        print(json.dumps(scope(), indent=2, sort_keys=True))
    elif action == "acquire":
        acquire(scope())
    elif action == "stage":
        stage()
    else:
        print(json.dumps(cohort_capacity(), indent=2, sort_keys=True))
