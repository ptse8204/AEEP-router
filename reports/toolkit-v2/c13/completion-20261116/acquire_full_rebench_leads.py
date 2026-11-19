"""Bind exact full-release SWE-rebench rows and the three publisher snapshots."""

import argparse
import json
import shutil
import tarfile
import urllib.error
from pathlib import Path

import screen_full_rebench_metadata as metadata
from reacquire_repository_sources import download
from rebind_cached_repository_sources import ARCHIVE_BOUND, inventory, published_tree
from screen_candidate_patches import ROW_KEYS
from stage_repository_transport import HERE, ROOT, WORK, digest, encode, read, write

TARGET = WORK / "full-rebench-three-leads-20261119"
INTAKE = HERE / "full-rebench-metadata-intake-20261118.json"
INTAKE_SHA = "1c5cc5ad6596ef5e344dc2040ab4408426bbb612e98e342ef41d01c44b2db480"
RECOVERY = HERE / "recovery-67a93f4c-result-20261119.json"
MAX_ROW_BYTES = 36 * 1024**2
RESERVE = 52 * 1024**3
COLUMNS = ("patch", "test_patch", "problem_statement", "install_config")


def ref(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(path.read_bytes())}


def source_rows():
    intake = json.loads(read(INTAKE, INTAKE_SHA))
    recovery = json.loads(RECOVERY.read_bytes())["rebench_intake"]
    root = ROOT / recovery["result"]["path"]
    read(root, recovery["result"]["sha256"])
    size, lfs = metadata.SHARDS[1]
    footer_path = metadata.TARGET / "shard-1-footer.bin"
    footer = read(footer_path, intake["shards"][1]["footer_sha256"])
    parsed = metadata.pq.read_metadata(metadata.pa.BufferReader(b"PAR1" + footer))
    leads = {
        case: data
        for case, data in recovery["cases"].items()
        if data["state"] == "ready_for_source_and_verifier_review"
    }
    catalogue = intake["provisional_lanes"]["declared_3_12"]["catalog"]
    source_pins = {
        row["instance_id"]: row
        for row in json.loads(read(ROOT / catalogue["path"], catalogue["sha256"]))
        if row["instance_id"] in leads
    }
    plan = {}
    for source in intake["protected_identity_intake_plan"]["row_groups"]:
        group_id = source["row_group"]
        row_indices = {case: pos for case, pos in source["row_positions"].items() if case in leads}
        if not row_indices:
            continue
        if source["shard_sha256"] != lfs or source["shard"] != metadata.shard_path(1):
            raise ValueError("intake points at a different Parquet shard")
        group = parsed.row_group(group_id)
        ranges = {}
        for position in range(group.num_columns):
            column = group.column(position)
            name = column.path_in_schema
            if name.split(".")[0] not in COLUMNS:
                continue
            start = min(
                value for value in (column.dictionary_page_offset, column.data_page_offset) if value
            )
            length = column.total_compressed_size
            if column.file_path or not 4 <= start < start + length <= size - len(footer):
                raise ValueError("unexpected external column byte range")
            ranges[name] = {"start": start, "bytes": length}
        plan[group_id] = {"row_positions": row_indices, "ranges": ranges}
    requested = sum(item["bytes"] for group in plan.values() for item in group["ranges"].values())
    if len(leads) != 3 or set(leads) != source_pins.keys() or requested > MAX_ROW_BYTES:
        raise ValueError("source metadata scope changed")
    return intake, recovery, source_pins, plan, requested, parsed, footer


def acquire_rows():
    _, recovery, pins, plan, requested, parsed, footer = source_rows()
    if shutil.disk_usage(TARGET).free < RESERVE + requested + len(pins) * ARCHIVE_BOUND:
        raise ValueError("usable storage is below the bounded intake headroom")
    review = {
        "schema_version": "aeep.c13.full-rebench-three-leads-acquisition.v1",
        "operator_instruction": "Continue C13 with the three SWE-rebench leads. Verify their sources and run the protected grader checks when ready.",
        "intake": ref(INTAKE),
        "previous_recovery": ref(RECOVERY),
        "driver": ref(Path(__file__)),
        "dataset": metadata.DATASET,
        "revision": metadata.REVISION,
        "rows": pins,
        "column_ranges": plan,
        "maximum_column_bytes": requested,
        "archive_limit_each": ARCHIVE_BOUND,
        "maximum_archive_bytes": len(pins) * ARCHIVE_BOUND,
        "models": 0,
        "cash_usd": 0,
        "provider_disclosure": False,
        "comparison": False,
        "waza_excluded": True,
    }
    write(TARGET / "source-acquisition-review.json", encode(review))
    size, lfs = metadata.SHARDS[1]
    locator = metadata.locate(1, size, lfs)
    receipts = []
    for index, group in plan.items():
        chunks = {0: b"PAR1", size - len(footer): footer}
        for key, boundary in group["ranges"].items():
            offset, length = boundary["start"], boundary["bytes"]
            raw = metadata.get_range(locator, size, offset, length)
            receipts.append({"row_group": index, "column": key, "sha256": digest(raw), **boundary})
            chunks[offset] = raw
        with (
            metadata.SparseParquet(size, chunks) as sparse,
            metadata.pq.ParquetFile(sparse, metadata=parsed, pre_buffer=False) as reader,
        ):
            rows = reader.read_row_group(index, columns=list(COLUMNS), use_threads=False)
            for case, slot in group["row_positions"].items():
                (row,) = rows.slice(slot, 1).to_pylist()
                exact = recovery["cases"][case]
                identity_root = (ROOT / recovery["result"]["path"]).parent
                tests = json.loads(
                    read(identity_root / f"{case}.json", exact["protected_record_sha256"])
                )
                pin = pins[case]
                if (
                    row["install_config"]["python"] != pin["declared_python"]
                    or row["install_config"]["log_parser"] != "parse_log_pytest"
                ):
                    raise ValueError("row did not match the pinned runtime metadata")
                canonical = {
                    **row,
                    **tests,
                    "instance_id": case,
                    "repo": pin["repository"],
                    "base_commit": pin["base_commit"],
                }
                if not all(
                    isinstance(row[k], str) and row[k].strip()
                    for k in ("patch", "test_patch", "problem_statement")
                ):
                    raise ValueError("one selected row lacks protected input")
                write(TARGET / "rows" / f"{case}.json", encode(canonical))
    return {
        "review": ref(TARGET / "source-acquisition-review.json"),
        "range_receipts": receipts,
        "column_bytes": sum(x["bytes"] for x in receipts),
        "row_files": {case: ref(TARGET / "rows" / f"{case}.json") for case in pins},
    }


def acquire_archives():
    inputs = json.loads((TARGET / "rows-result.json").read_bytes())
    review = json.loads(read(TARGET / "source-acquisition-review.json", inputs["review"]["sha256"]))
    results = {}
    for case, row_ref in inputs["row_files"].items():
        row = json.loads(read(ROOT / row_ref["path"], row_ref["sha256"]))
        pin = review["rows"][case]
        if (row["instance_id"], row["repo"], row["base_commit"]) != (
            case,
            pin["repository"],
            pin["base_commit"],
        ):
            raise ValueError("row identity differs from the exact acquisition review")
        if shutil.disk_usage(TARGET).free < RESERVE + ARCHIVE_BOUND:
            results[case] = {"state": "storage_floor_unstarted"}
            continue
        folder = TARGET / "archives" / case
        folder.mkdir(mode=0o700, parents=True)
        archive = folder / "source-original.tar.gz"
        write(folder / "row.json", read(ROOT / row_ref["path"], row_ref["sha256"]))
        repo, revision = row["repo"], row["base_commit"]
        url = f"https://codeload.github.com/{repo}/tar.gz/{revision}"
        try:
            source = published_tree(repo, revision)
            download(url, archive)
            tree, notices, count, sha = inventory(archive, revision)
            if tree != source["published_tree"] or not notices:
                raise ValueError(
                    "source archive could not be tied to the publisher tree and notice"
                )
        except urllib.error.HTTPError as exc:
            results[case] = {"state": "publisher_request_failed", "status": exc.code}
            if exc.code in (403, 429):
                break
        except (ValueError, OSError, tarfile.TarError) as exc:
            results[case] = {"state": "unverified_archive", "reason": str(exc)}
        else:
            results[case] = {
                "state": "publisher_tree_verified",
                "source": source,
                "archive": ref(archive),
                "license_notices": notices,
                "size": archive.stat().st_size,
                "files": count,
                "metadata_semantic_sha256": digest(
                    json.dumps({key: row[key] for key in ROW_KEYS}, sort_keys=True).encode()
                ),
                "case_id": case,
                "repository": repo,
                "source_revision": revision,
                "archive_content_sha256": sha,
            }
        write(folder / "verification.json", encode(results[case]))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--rows", action="store_true")
    mode.add_argument("--archives", action="store_true")
    args = parser.parse_args()
    if args.rows:
        result = acquire_rows()
        write(TARGET / "rows-result.json", encode(result))
    else:
        result = acquire_archives()
        write(TARGET / "archives-result.json", encode(result))
    print(json.dumps(result, indent=2))
