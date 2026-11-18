"""Read only the reviewed protected identity columns for four software leads."""

import argparse
import json
import shutil

import reconcile_full_rebench_metadata as evidence
import screen_full_rebench_metadata as intake
from screen_candidate_patches import test_roots
from stage_repository_transport import HERE, digest, read

REPORT = HERE / "full-rebench-metadata-intake-20261118.json"
TARGET = intake.TARGET / "protected-identities"
RESERVE = 52 * 1024**3


def inspect_identities(observation):
    issue, preservation = (observation[key] for key in ("FAIL_TO_PASS", "PASS_TO_PASS"))
    if not issue or not preservation:
        return {"state": "excluded_missing_issue_or_preservation", "required_tests": None}
    selected = issue + preservation
    if any(not isinstance(item, str) for item in selected) or len(set(selected)) != len(selected):
        return {"state": "excluded_unusable_identities", "required_tests": None}
    try:
        modules, roots = test_roots(selected)
    except ValueError:
        return {"state": "excluded_unsupported_native_identity", "required_tests": len(selected)}
    return {
        "state": "ready_for_source_and_verifier_review",
        "issue_tests": len(issue),
        "preservation_tests": len(preservation),
        "required_tests": len(selected),
        "test_file_count": len(modules),
        "test_root_count": len(roots),
        "requires_large_suite_preflight": len(selected) > 170,
    }


def verified_scope(exact):
    record = json.loads(read(REPORT, exact))
    plan = record["protected_identity_intake_plan"]
    if plan != evidence.run()["protected_identity_intake_plan"]:
        raise ValueError("protected row positions or byte ranges differ")
    if (
        plan["executed"]
        or plan["maximum_range_requests"] != 6
        or plan["maximum_range_bytes"] != 5_026_939
    ):
        raise ValueError("protected identity scope differs from the bounded preparation")
    return record, plan


def acquire(exact):
    record, plan = verified_scope(exact)
    if TARGET.exists():
        raise ValueError("preserve the existing execution and any partial inputs")
    if shutil.disk_usage(intake.TARGET).free < RESERVE + plan["maximum_range_bytes"]:
        raise ValueError("52 GiB of usable space plus the planned inputs is required")
    TARGET.mkdir(mode=0o700)
    size, sha = intake.SHARDS[1]
    if any(group["shard_sha256"] != sha for group in plan["row_groups"]):
        raise ValueError("identity acquisition does not match the pinned shard")
    url = intake.locate(1, size, sha)
    pinned_shard = record["shards"][1]
    footer = read(intake.TARGET / "shard-1-footer.bin", pinned_shard["footer_sha256"])
    metadata = intake.pq.read_metadata(intake.pa.BufferReader(b"PAR1" + footer))
    summary = {}
    for group in plan["row_groups"]:
        if shutil.disk_usage(TARGET).free < RESERVE:
            raise ValueError("host space changed during protected identity acquisition")
        observed = []
        chunks = {0: b"PAR1", size - len(footer): footer}
        for column, byte_range in group["allowed_ranges"].items():
            start, count = byte_range["start"], byte_range["bytes"]
            fragment = intake.get_range(url, size, start, count)
            chunks[start] = fragment
            observation = {
                "column": column,
                "start": start,
                "bytes": count,
                "sha256": digest(fragment),
            }
            name = f"shard-1-group-{group['row_group']}-{column}-receipt.json"
            (TARGET / name).write_text(json.dumps(observation, sort_keys=True))
            observed.append(observation)
        with (
            intake.SparseParquet(size, chunks) as sparse,
            intake.pq.ParquetFile(sparse, metadata=metadata, pre_buffer=False) as projection,
        ):
            values = projection.read_row_group(
                group["row_group"], columns=["FAIL_TO_PASS", "PASS_TO_PASS"], use_threads=False
            )
            for case, offset in group["row_positions"].items():
                (selected,) = values.slice(offset, 1).to_pylist()
                encoded = json.dumps(selected, sort_keys=True).encode()
                name = f"{case}.json"
                (TARGET / name).write_bytes(encoded)
                summary[case] = inspect_identities(selected) | {
                    "protected_record_sha256": digest(encoded),
                    "column_observations": observed,
                }
    result = {
        "review_sha256": exact,
        "cases": summary,
        "task_payload_or_tests_downloaded": False,
        "executed_upstream_tests": 0,
        "formal_cases_adopted": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }
    (TARGET / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake-sha256", required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    result = (
        verified_scope(args.intake_sha256)[1] if args.verify_only else acquire(args.intake_sha256)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
