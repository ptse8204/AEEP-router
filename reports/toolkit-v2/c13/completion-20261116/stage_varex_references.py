"""Retain the published VAREX reference columns for the locally verified PDF cohort."""

import argparse
import hashlib
import io
import json
import shutil
from pathlib import Path

import pyarrow
import pyarrow.parquet as parquet
from audit_varex_schema_projection import COLUMNS, TREE_SHA, RangeStore, project
from stage_varex_calibration import (
    CASES,
    METADATA,
    REV,
    ROOT,
    WORK,
    digest,
    pinned,
    schema_audit,
    write,
)

HIGH = WORK.parent / "varex-protected-reference-intake"
COMPLEMENT = WORK.parent / "varex-complement-intake"
BATCH = HIGH
CATALOG = "9d4604b731be1922926567e2ee2e31c6594a375801d8dea9901727cfe9a9d606"
METADATA_RECEIPTS = "06d7d6b9717c33e515810ff11031db52f253bde0796b62928a0a9dc66c150be0"
CALIBRATION_RECEIPTS = "42b8fe614f393dc039423eabbcfdf153da30d5eac93dab00352ab887b28f143f"
COHORT_RECEIPTS = "8d5a056c1fd5ea131bb61b860884906055792d0ca2fb0a50e4f161e7c3785410"
LIMIT = 2_000_000
MAX_NEW_RANGES = 12
FLOOR = 50 * 2**30


def range_key(row):
    return row["object"], row["offset"], row["size"]


def known_ranges(complement=False):
    inventories = (
        (METADATA, "range-receipts.json", METADATA_RECEIPTS),
        (WORK, "retained-reference-ranges.json", CALIBRATION_RECEIPTS),
    )
    if complement:
        inventories += ((HIGH, "range-receipts.json", COHORT_RECEIPTS),)
    result = {}
    for directory, name, checksum in inventories:
        records = json.loads(pinned(directory / name, checksum))
        for row in records:
            obj, offset, size = key = range_key(row)
            path = directory / "ranges" / f"{obj[:16]}-{offset}-{size}.bin"
            if key in result or len(pinned(path, row["sha256"])) != size:
                raise ValueError("retained range has conflicting bindings")
            result[key] = (path, row["sha256"])
    return result


def reviewed_scope(cached, complement=False):
    if pyarrow.__version__ != "21.0.0":
        raise ValueError("publication reader version differs")
    catalog = json.loads(pinned(METADATA / "multiple-collection-prospects.json", CATALOG))
    cases = {name: row for name, row in catalog["cases"].items() if name not in CASES}
    shards = json.loads(pinned(METADATA / "publisher-tree.json", TREE_SHA))
    if catalog["dataset_revision"] != REV or len(cases) != 131 or len(shards) != 4:
        raise ValueError("reviewed cohort inventory changed")
    if complement:
        result_path = COMPLEMENT / "pdf-intake.json"
        result = json.loads(result_path.read_bytes())
        plan = json.loads(pinned(COMPLEMENT / "review.json", result["review_sha256"]))
        if (
            plan["dataset_revision"] != REV or set(result["files"]) | result["unverified"].keys() != set(plan["cases"])
            or set(result["files"]) & result["unverified"].keys()
        ):
            raise ValueError("complementary PDF review differs from its readback")
        cases = {name: plan["cases"][name] | {"pdf_sha256": info["sha256"]} for name, info in result["files"].items()}
        for name, info in result["files"].items():
            pdf = COMPLEMENT / "public-pdfs" / (digest(name.encode()) + ".pdf")
            body = pinned(pdf, info["sha256"])
            blob = hashlib.sha1(f"blob {len(body)}\0".encode() + body, usedforsecurity=False)
            if len(body) != cases[name]["bytes"] or blob.hexdigest() != cases[name]["git_oid"] or cases[name]["collections"] > 1:
                raise ValueError("complementary document bytes or case shape changed")
    missing = []
    for shard in shards:
        obj, total = shard["lfs"]["oid"], shard["size"]
        tail = pinned(*cached[obj, total - 8, 8])
        size = int.from_bytes(tail[:4], "little")
        if tail[-4:] != b"PAR1" or not 1 <= size <= 131_072:
            raise ValueError("unexpected Parquet footer")
        footer = pinned(*cached[obj, total - 8 - size, size])
        meta = parquet.read_metadata(io.BytesIO(b"PAR1" + footer + tail))
        for index in range(meta.num_row_groups):
            group = meta.row_group(index)
            (column,) = [group.column(i) for i in range(group.num_columns)
                         if group.column(i).path_in_schema == "ground_truth"]
            offset = column.dictionary_page_offset or column.data_page_offset
            length = column.total_compressed_size
            if column.physical_type != "BYTE_ARRAY" or not 4 <= offset < offset + length <= total - size - 8:
                raise ValueError("reference column exceeds its source object")
            if (obj, offset, length) not in cached:
                missing.append({"object": obj, "offset": offset, "size": length})
    if len(missing) > MAX_NEW_RANGES or sum(row["size"] for row in missing) > LIMIT:
        raise ValueError("projected reference acquisition exceeds its bound")
    if complement and missing:
        raise ValueError("complementary references require only the retained publisher ranges")
    return {
        "schema_version": "aeep.c13.varex-review-reference-intake.v1",
        "dataset_revision": REV, "driver_sha256": digest(Path(__file__).read_bytes()),
        "projection_driver_sha256": digest(Path(project.__code__.co_filename).read_bytes()),
        "tree_sha256": TREE_SHA, "catalog_sha256": CATALOG, "existing_ranges": len(cached),
        "cases": cases, "shards": shards, "projected_columns": [*COLUMNS, "ground_truth"],
        "approved_new_ranges": missing, "exact_new_range_bytes": sum(row["size"] for row in missing),
        "license": "CDLA-Permissive-2.0", "host_free_floor_bytes": FLOOR,
        "authority": "C13 bounded local cohort preparation. Keep original reference rows inside the protected workspace.",
        "retries": 0, "new_upstream_calls": 0, "model_turns": 0, "cash_usd": 0, "provider_disclosure": False,
    }


class ProjectedReferences:
    def __init__(self, cached, review, execute):
        self.cached = cached
        self.allow = {range_key(row) for row in review["approved_new_ranges"]}
        self.extra = RangeStore({"max_bytes": review["exact_new_range_bytes"]}, execute, work=BATCH)
        self.seen = set()

    def read(self, row, offset, size):
        key = (row["lfs"]["oid"], offset, size)
        if key in self.cached:
            return pinned(*self.cached[key])
        if key not in self.allow or key in self.seen:
            raise ValueError("Parquet requested an unreviewed reference range")
        self.seen.add(key)
        return self.extra.read(row, offset, size)


def retain(review, sources, *, execute):
    rows = {}
    for shard in review["shards"]:
        for row in project(shard, sources, columns=tuple(review["projected_columns"])):
            name = row["doc_id"]
            if name not in review["cases"]:
                continue
            original = review["cases"][name]
            raw = row["schema"].encode()
            reference = row["ground_truth"].encode()
            if (
                name in rows or original["shard_sha256"] != shard["lfs"]["oid"]
                or digest(raw) != original["schema_sha256"] or original["split"] != row["split"]
                or not isinstance(json.loads(reference), dict)
            ):
                raise ValueError("bound reference row differs from the publication")
            schema_audit(json.loads(raw))
            files = {"schema.json": raw, "reference.json": reference}
            folder = BATCH / "protected" / digest(name.encode())
            if execute:
                folder.mkdir(mode=0o700)
            for filename, body in files.items():
                if execute:
                    with (folder / filename).open("xb") as stream:
                        stream.write(body)
                else:
                    pinned(folder / filename, digest(body))
            rows[name] = {
                "protected_case": folder.name, "reference_sha256": digest(reference), "schema_sha256": digest(raw),
                "publisher_shard": original["shard_sha256"], "split": original["split"],
            }
    if rows.keys() != review["cases"].keys() or sources.seen != sources.allow:
        raise ValueError("reference coverage does not match the scoped cases and ranges")
    return rows


def main():
    global BATCH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "acquire", "verify"))
    parser.add_argument("--exact")
    parser.add_argument("--complement", action="store_true")
    args = parser.parse_args()
    if args.complement:
        BATCH = COMPLEMENT / "protected-references"
    cached = known_ranges(complement=args.complement)
    review = reviewed_scope(cached, complement=args.complement)
    path = BATCH / "reference-review.json"
    if args.action == "prepare":
        BATCH.mkdir(mode=0o700)
        write(path, review)
        print(digest(path.read_bytes()))
        return
    saved = json.loads(pinned(path, args.exact)) if args.exact else {}
    if args.action == "verify" and saved.get("driver_sha256") != review["driver_sha256"]:
        pinned(BATCH / "acquisition-driver.py", saved["driver_sha256"])
        review["driver_sha256"] = saved["driver_sha256"]
    if saved != review:
        raise ValueError("exact reference scope drifted")
    execute = args.action == "acquire"
    if execute:
        if shutil.disk_usage(ROOT).free < FLOOR + LIMIT:
            raise ValueError("reference preparation would cross the host reserve")
        (BATCH / "ranges").mkdir(mode=0o700)
        (BATCH / "protected").mkdir(mode=0o700)
    sources = ProjectedReferences(cached, review, execute)
    try:
        rows = retain(review, sources, execute=execute)
    finally:
        if execute:
            write(BATCH / "range-receipts.json", sources.extra.transfers)
    result = {
        "review_sha256": args.exact, "reference_rows": len(rows), "cases": rows,
        "reference_range_bytes": sum(item["size"] for item in sources.extra.transfers),
        "reference_ranges": len(sources.extra.transfers),
        "model_turns": 0, "cash_usd": 0, "formal_assignments": 0,
    }
    if execute:
        write(BATCH / "reference-intake.json", result)
    elif json.loads((BATCH / "reference-intake.json").read_bytes()) != result:
        raise ValueError("reference intake readback differs")
    print(json.dumps({name: value for name, value in result.items() if name != "cases"}))


if __name__ == "__main__":
    main()
