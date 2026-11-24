"""Read exact reserve metadata from the pinned public release in one batch."""

import argparse
import json
import shutil
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from itertools import combinations
from pathlib import Path, PurePosixPath

import prepare_supplementary_multifile_ranges as preview_driver
import screen_full_rebench_metadata as publisher
from audit_multifile_issue_overlap import conflict, select_group
from plan_repository_expansion import CASE, patch_paths
from screen_candidate_patches import python_source, test_roots
from stage_repository_transport import HERE, ROOT, digest, encode, read, write

BASE = ROOT / ".aeep/c13-cohort-runtime-20261124"
PREVIEW = HERE / "supplementary-multifile-range-preview-20261124.json"
ROOT_COLUMNS = ("patch", "test_patch", "FAIL_TO_PASS", "PASS_TO_PASS")
HOST_RESERVE = 50 * 1024**3


def private_path(path):
    if path.resolve() != path or not path.is_relative_to(BASE) or not path.parent.is_dir():
        raise ValueError("use a new, canonical path within the private C13 area")
    return path


def pinned_definition():
    raw = PREVIEW.read_bytes()
    preview = json.loads(raw)
    if preview != preview_driver.definition(preview["overlap_evidence"]):
        raise ValueError("supplementary scope differs from the retained publisher layout")
    return {
        "schema_version": "aeep.c13.supplementary-multifile-intake.v1",
        "scope_preview": {
            "path": PREVIEW.relative_to(ROOT).as_posix(),
            "sha256": digest(raw),
        },
        "driver_sha256": {
            file: digest((HERE / file).read_bytes())
            for file in (
                Path(__file__).name,
                "prepare_supplementary_multifile_ranges.py",
                "screen_full_rebench_metadata.py",
                "reconcile_full_rebench_metadata.py",
                "audit_multifile_issue_overlap.py",
                "plan_repository_expansion.py",
                "screen_candidate_patches.py",
                "stage_repository_transport.py",
            )
        },
        "dataset": preview["dataset"],
        "dataset_revision": preview["dataset_revision"],
        "maximum_head_requests": len({group["shard_number"] for group in preview["row_groups"]}),
        "maximum_range_requests": preview["maximum_range_requests"],
        "maximum_response_bytes": preview["maximum_response_bytes"],
        "minimum_prelaunch_free_bytes": preview["minimum_prelaunch_free_bytes"],
        "selected_case_count": preview["selected_case_count"],
        "retries": 0,
        "model_turns": 0,
        "cash_usd": 0,
        "provider_disclosure": False,
        "upstream_code_execution": False,
        "comparisons_paused": True,
        "waza_excluded": True,
    }, preview


def shape(case, payload):
    if set(payload) != set(ROOT_COLUMNS):
        raise ValueError("protected_column_set")
    patch, test_patch, issue, preserve = (payload[key] for key in ROOT_COLUMNS)
    if not all(isinstance(value, str) and value.strip() for value in (patch, test_patch)):
        raise ValueError("missing_published_patch")
    if any(
        not isinstance(nodes, list)
        or not nodes
        or not all(isinstance(node, str) and node.strip() for node in nodes)
        for nodes in (issue, preserve)
    ):
        raise ValueError("missing_published_test_identities")
    if len(issue + preserve) != len(set(issue + preserve)):
        raise ValueError("duplicate_published_test_identities")
    try:
        source_changes = patch_paths(patch)
        test_changes = patch_paths(test_patch)
        _, roots = test_roots(issue + preserve)
    except ValueError:
        raise ValueError("unreviewed_patch_or_test_path") from None
    if any(
        not any(PurePosixPath(name).is_relative_to(root) for root in roots) for name in test_changes
    ):
        raise ValueError("test_overlay_outside_published_roots")
    paths = {name.casefold() for name in source_changes if python_source(name, roots)}
    if len(paths) < 2:
        raise ValueError("fewer_than_two_python_source_paths")
    issue_tests = {node.casefold() for node in issue}
    return {
        "case_id": case,
        "patch": digest(patch.encode()),
        "test_patch": digest(test_patch.encode()),
        "paths": paths,
        "issue_tests": issue_tests,
        "issue_modules": {node.partition("::")[0] for node in issue_tests},
        "preservation_test_count": len(preserve),
        "test_patch_paths": len(test_changes),
    }


def read_group(group, location, journal):
    shard = group["shard_number"]
    size = group["shard_bytes"]
    footer = read(publisher.TARGET / f"shard-{shard}-footer.bin", group["footer_sha256"])
    layout = publisher.pq.read_metadata(publisher.pa.BufferReader(b"PAR1" + footer))
    chunks = {0: b"PAR1", size - len(footer): footer}
    for column, bound in group["columns"].items():
        offset, length = bound["start"], bound["bytes"]
        if shutil.disk_usage(journal.parent).free < HOST_RESERVE + length:
            raise ValueError("insufficient_space_for_next_range")
        receipt = journal / f"{shard}-{group['row_group']}-{column}"
        journal_entry = {"column": column, **bound}
        write(receipt.with_name(receipt.name + ".started.json"), encode(journal_entry))
        body = publisher.get_range(location, size, offset, length)
        if len(body) != length or offset in chunks:
            raise ValueError("unexpected_byte_range")
        chunks[offset] = body
        write(
            receipt.with_name(receipt.name + ".received.json"),
            encode(journal_entry | {"sha256": digest(body)}),
        )
    with (
        publisher.SparseParquet(size, chunks) as sparse,
        publisher.pq.ParquetFile(sparse, metadata=layout, pre_buffer=False) as parquet,
    ):
        table = parquet.read_row_group(
            group["row_group"], columns=list(ROOT_COLUMNS), use_threads=False
        )
        if table.num_rows != layout.row_group(group["row_group"]).num_rows:
            raise ValueError("protected_row_count_drift")
        for item in group["selected_rows"]:
            (payload,) = table.slice(item["row"], 1).to_pylist()
            yield item, payload


def collect(preview, output):
    groups = defaultdict(set)
    shapes, outcomes, locators = {}, {}, {}
    for item in preview["row_groups"]:
        shard = item["shard_number"]
        if shard not in locators:
            location = {"shard": shard, "sha256": item["shard_sha256"]}
            write(output / f"shard-{shard}.started.json", encode(location))
            locators[shard] = publisher.locate(shard, item["shard_bytes"], item["shard_sha256"])
            write(output / f"shard-{shard}.located.json", encode(location))
        for record, payload in read_group(item, locators[shard], output / "ranges"):
            case = record["case"]
            if CASE.fullmatch(case) is None or case in outcomes:
                raise ValueError("invalid_or_duplicate_reserve_case")
            try:
                shaped = shape(case, payload)
            except ValueError as stop:
                outcomes[case] = record | {"state": str(stop)}
                continue
            path = output / "protected" / f"{case}.json"
            preserved = write(path, encode(record | {"columns": payload}))
            outcomes[case] = record | {
                "state": "detailed_shape_reviewed",
                "private_row": {"path": str(path.relative_to(ROOT)), "sha256": preserved["sha256"]},
                "python_source_paths": len(shaped["paths"]),
                "test_patch_paths": shaped["test_patch_paths"],
                "issue_tests": len(shaped["issue_tests"]),
                "preservation_tests": shaped["preservation_test_count"],
            }
            shapes[case] = shaped
            groups[record["repository"]].add(case)
    if len(outcomes) != preview["selected_case_count"]:
        raise ValueError("selected_reserve_cases_missing")

    capacity = set()
    for cases in groups.values():
        collisions = {
            frozenset((left, right))
            for left, right in combinations(cases, 2)
            if conflict(shapes[left], shapes[right])
        }
        capacity.update(select_group(cases, set(), collisions, set()))
    for case in capacity:
        outcomes[case]["prospective_nonoverlapping_issue"] = True
    return {
        "case_status_counts": dict(
            sorted(Counter(row["state"] for row in outcomes.values()).items())
        ),
        "case_rows": [outcomes[key] for key in sorted(outcomes)],
        "prospective_nonoverlapping_issues": len(capacity),
    }


def run(review, expected, output):
    report = json.loads(read(review, expected))
    expiry = datetime.fromisoformat(report.pop("expires_at"))
    current, preview = pinned_definition()
    private_path(output)
    if report != current or expiry <= datetime.now(UTC):
        raise ValueError("review is stale or out of scope")
    if shutil.disk_usage(output.parent).free < report["minimum_prelaunch_free_bytes"]:
        raise ValueError("usable space below the 50 GiB reserve and exact response allowance")
    output.mkdir(mode=0o700)
    state = {
        "review_sha256": expected,
        "provider_disclosure": False,
        "model_turns": 0,
        "formal_assignments": 0,
        "new_protected_grades": 0,
    }
    try:
        state.update(collect(preview, output), status="complete")
    except (OSError, ValueError) as failure:
        write(
            output / "result.json",
            encode(state | {"status": "interrupted", "error_type": type(failure).__name__}),
        )
        raise
    return write(output / "result.json", encode(state))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("--execute")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    review = private_path(args.review.absolute())
    if args.execute is None:
        definition, _ = pinned_definition()
        expires = (datetime.now(UTC) + timedelta(hours=4)).isoformat()
        print(write(review, encode(definition | {"expires_at": expires})))
    elif args.output is not None:
        print(run(review, args.execute, args.output.absolute()))
    else:
        parser.error("execution requires a new private output directory")


if __name__ == "__main__":
    main()
