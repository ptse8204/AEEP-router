"""Prepare a bounded complementary VAREX intake before any trial assignments."""

import argparse
import json
import re
import shutil
from collections import Counter
from pathlib import Path

from audit_varex_schema_projection import TREE_SHA, RangeStore, collection_paths, project
from review_varex_form_lineage import audit
from stage_varex_calibration import (
    METADATA,
    PDF_TREE,
    REV,
    WORK,
    digest,
    pdf,
    pinned,
    schema_audit,
    write,
)
from stage_varex_references import FLOOR, METADATA_RECEIPTS

TARGET = WORK.parent / "varex-complement-intake"
QUOTAS = {(0, "Flat"): 32, (0, "Nested"): 40, (1, "Flat"): 6, (1, "Nested"): 14, (1, "Table"): 52}
MAX_PDF_BYTES = 500_000


def form_code(name):
    code = name.casefold()
    # Hold known form-code variants together across both shape families.
    match = re.fullmatch(r"(sf|gsa|hud|of|fda)[_-]?(d{2,5}[a-z]*?)(?:[-_].*)?", code)
    return "".join(match.groups()) if match else re.sub(r"[^a-z0-9]+", "", code)


def review():
    lineage, _ = audit()
    blocked_codes = set(map(form_code, lineage["prospects"]))
    pinned(METADATA / "range-receipts.json", METADATA_RECEIPTS)
    cached = RangeStore({"max_bytes": 1_000_000}, False, work=METADATA)
    shards = json.loads(pinned(METADATA / "publisher-tree.json", TREE_SHA))
    paths = {}
    for name, sha in PDF_TREE.items():
        for row in json.loads(pinned(METADATA / name, sha)):
            if row["path"] in paths:
                raise ValueError("duplicate PDF object")
            paths[row["path"]] = row
    cohorts = {key: [] for key in QUOTAS}
    for shard in shards:
        for row in project(shard, cached):
            name = row["doc_id"]
            source = paths[f"pdfs/{name}.pdf"]
            if source.get("lfs") or source["size"] > MAX_PDF_BYTES or form_code(name) in blocked_codes:
                continue
            raw = row["schema"].encode()
            schema = json.loads(raw)
            count = len(collection_paths(schema))
            key = (count, row["split"])
            if key not in cohorts or len(schema.get("properties", {})) < 3:
                continue
            try:
                schema_audit(schema)
            except ValueError:
                continue
            cohorts[key].append({
                "doc_id": name, "pdf_path": source["path"], "bytes": source["size"],
                "git_oid": source["oid"], "lfs_sha256": None, "schema_sha256": digest(raw),
                "collections": count, "split": row["split"], "shard_sha256": shard["lfs"]["oid"],
            })
    selected = {}
    codes, schemas = set(), set()
    for key, quota in sorted(QUOTAS.items(), key=lambda item: len(cohorts[item[0]])):
        choices = []
        for item in sorted(cohorts[key], key=lambda candidate: digest(candidate["doc_id"].encode())):
            name, sha = item["doc_id"], item["schema_sha256"]
            code = form_code(name)
            if code in codes or sha in schemas:
                continue
            selected[name] = item
            codes.add(code)
            schemas.add(sha)
            choices.append(name)
            if len(choices) == quota:
                break
        if len(choices) != quota:
            raise ValueError(f"insufficient reviewed variety for {key}")
    distribution = Counter(f"{r['collections']}/{r['split']}" for r in selected.values())
    return {
        "schema_version": "aeep.c13.varex-complement-intake.v1",
        "dataset_revision": REV, "driver_sha256": digest(Path(__file__).read_bytes()),
        "pdf_tree_hashes": PDF_TREE, "parquet_tree_sha256": TREE_SHA,
        "scope": "Public Git blobs for the complementary at-most-one-collection family. No formal stage selection.",
        "source_screen": "Stable ID hash ordering within declared shape bins. Distinct schema and normalized form code, three top-level properties, up to 500,000 PDF bytes.",
        "case_shape_counts": dict(distribution), "cases": selected,
        "maximum_pdf_bytes": sum(item["bytes"] for item in selected.values()),
        "maximum_acquisitions": len(selected), "host_free_floor_bytes": FLOOR,
        "provider_disclosure": False, "model_turns": 0, "cash_usd": 0, "installations": 0, "retries": 0,
    }


def acquire(scope, exact):
    saved = TARGET / "review.json"
    if json.loads(pinned(saved, exact)) != scope or shutil.disk_usage(TARGET).free < FLOOR + scope["maximum_pdf_bytes"]:
        raise ValueError("reviewed intake or disk availability changed")
    folder = TARGET / "public-pdfs"
    folder.mkdir(mode=0o700)
    retained, excluded = {}, {}
    for name, item in scope["cases"].items():
        if shutil.disk_usage(TARGET).free < FLOOR + item["bytes"] + 4096:
            excluded[name] = "storage_reserve"
            continue
        try:
            body = pdf(item)
        except (OSError, ValueError) as error:
            excluded[name] = type(error).__name__
            continue
        with (folder / (digest(name.encode()) + ".pdf")).open("xb") as stream:
            stream.write(body)
        retained[name] = {"bytes": len(body), "git_oid": item["git_oid"], "sha256": digest(body)}
    result = {
        "review_sha256": exact, "verified_pdfs": len(retained), "files": retained, "unverified": excluded,
        "model_turns": 0, "formal_assignments": 0,
    }
    write(TARGET / "pdf-intake.json", result)
    print(json.dumps({name: value for name, value in result.items() if name != "files"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--acquire")
    args = parser.parse_args()
    scope = review()
    if args.prepare:
        TARGET.mkdir(mode=0o700, exist_ok=True)
        target = TARGET / "review.json"
        write(target, scope)
        print(digest(target.read_bytes()))
    else:
        acquire(scope, args.acquire)
