"""Pin the minimum publisher column ranges needed to review eight reserve ideas."""

import argparse
import json
from pathlib import Path

import audit_two_cohort_source_capacity as capacity
import reconcile_full_rebench_metadata as retained
from stage_repository_transport import HERE, ROOT, digest, encode, read, write

COLUMNS = frozenset(
    {"patch", "test_patch", "FAIL_TO_PASS.list.element", "PASS_TO_PASS.list.element"}
)
HEADROOM_LIMIT = 36 * 1024**2


def definition(overlap_ref):
    overlap = capacity.referenced(overlap_ref)
    if overlap["schema_version"] != "aeep.c13.multifile-issue-overlap.v1":
        raise ValueError("reserve review requires a current issue-overlap check")
    metadata = HERE / "full-rebench-metadata-intake-20261118.json"
    raw = metadata.read_bytes()
    intake = json.loads(raw)
    choices, inventory = capacity.reserve_leads(set())
    if (
        intake["revision"] != retained.intake.REVISION
        or len(choices) != overlap["supplementary_metadata_still_needs_issue_shapes"]
        or overlap["formal_assignments"]
    ):
        raise ValueError("reserve identities changed")
    selected = set()
    ranges = []
    for number, shard in enumerate(intake["shards"]):
        rows = retained.replay(shard, number)
        footer_path = retained.intake.TARGET / f"shard-{number}-footer.bin"
        footer = read(footer_path, shard["footer_sha256"])
        offset = 0
        parsed = retained.intake.pq.read_metadata(retained.intake.pa.BufferReader(b"PAR1" + footer))
        for group_id in range(parsed.num_row_groups):
            group = parsed.row_group(group_id)
            positions = []
            for i, row in enumerate(rows[offset : offset + group.num_rows]):
                origin = capacity.lineage(row["repo"]), row["base_commit"]
                if origin in choices:
                    if origin in selected or row["meta"]["has_test_patch"] is not True:
                        raise ValueError("ambiguous reserve row or missing test metadata")
                    positions.append(
                        {
                            "row": i,
                            "case": row["instance_id"],
                            "repository": origin[0],
                            "revision": origin[1],
                        }
                    )
                    selected.add(origin)
            offset += group.num_rows
            if not positions:
                continue
            columns = {}
            for i in range(group.num_columns):
                col = group.column(i)
                if col.path_in_schema not in COLUMNS:
                    continue
                start = min(
                    n for n in (col.dictionary_page_offset, col.data_page_offset) if n is not None
                )
                size = col.total_compressed_size
                end = shard["publisher_shard_bytes"] - len(footer)
                if col.file_path or not 4 <= start < start + size <= end:
                    raise ValueError("exact column range leaves the pinned shard")
                columns[col.path_in_schema] = {"start": start, "bytes": size}
            if columns.keys() != COLUMNS:
                raise ValueError("a protected column is missing")
            ranges.append(
                {
                    "shard_number": number,
                    "shard": shard["name"],
                    "shard_sha256": shard["publisher_lfs_sha256"],
                    "shard_bytes": shard["publisher_shard_bytes"],
                    "footer_sha256": shard["footer_sha256"],
                    "row_group": group_id,
                    "selected_rows": positions,
                    "columns": columns,
                }
            )
        if offset != len(rows):
            raise ValueError("retained identity rows do not cover the Parquet layout")
    total = sum(entry["bytes"] for group in ranges for entry in group["columns"].values())
    if selected != choices.keys() or total > HEADROOM_LIMIT:
        raise ValueError("the complete protected metadata scope exceeds the review bound")
    return {
        "schema_version": "aeep.c13.supplementary-multifile-range-preview.v1",
        "overlap_evidence": overlap_ref,
        "metadata_intake_sha256": digest(raw),
        "dataset": intake["dataset"],
        **inventory,
        "row_groups": ranges,
        "maximum_range_requests": sum(len(group["columns"]) for group in ranges),
        "maximum_response_bytes": total,
        "minimum_prelaunch_free_bytes": 50 * 1024**3 + total,
        "selected_case_count": len(selected),
        "started": False,
        "raw_patches_or_tests_published": False,
        "upstream_tests": 0,
        "model_turns": 0,
        "formal_assignments": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("overlap", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    overlap = args.overlap.resolve()
    ref = {"path": overlap.relative_to(ROOT).as_posix(), "sha256": digest(overlap.read_bytes())}
    print(write(args.output, encode(definition(ref))))
