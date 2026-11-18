"""Reproduce the intake and publisher manifest checks from their retained bytes."""

import json
import struct
import tomllib
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import screen_full_rebench_metadata as intake
from packaging.specifiers import SpecifierSet
from stage_repository_transport import ROOT, digest, read

ACQUISITION = ROOT / ".aeep/rebench-full-metadata-result-20261118.json"
SCOPE = ROOT / ".aeep/rebench-full-first-source-review-20261118.json"
FIXTURE = ROOT / ".aeep/rebench-range-fixture.7xxedt"
MANIFESTS = intake.TARGET / "project-metadata-result.json"


def ref(path: Path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path.read_bytes())}


def replay(shard, index):
    source = f"shard-{index}-"
    data = intake.TARGET / f"{source}ranges.json"
    ranges = json.loads(read(data, shard["retained_chunk_inventory_sha256"]))
    size = shard["publisher_shard_bytes"]
    footer = read(intake.TARGET / f"{source}footer.bin", shard["footer_sha256"])
    length, magic = struct.unpack("<I4s", footer[-8:])
    if len(footer) != length + 8 or magic != b"PAR1":
        raise ValueError("retained Parquet footer differs")
    start = size - len(footer)
    by_offset = {}
    for item in ranges:
        name = item["name"]
        if not name.startswith(source) or "/" in name:
            raise ValueError("invalid retained fragment path")
        body = read(intake.TARGET / name, item["sha256"])
        if len(body) != item["bytes"] or item["start"] in by_offset:
            raise ValueError("retained fragment duplicated or changed")
        by_offset[item["start"]] = body

    def retained_range(_url, current_size, offset, count):
        if current_size != size:
            raise ValueError("retained shard size differs from the publisher pin")
        if offset == size - 8 and count == 8:
            return footer[-8:]
        if offset == start and count == length:
            return footer[:-8]
        raise ValueError("footer parser attempted an unexpected read")

    with patch.object(intake, "get_range", retained_range):
        _, metadata, metadata_start, _, _, wanted = intake.footer_plan(index, size, "retained")
    if (
        metadata_start != start
        or {(offset, limit) for _, _, offset, limit in wanted}
        != {(offset, len(body)) for offset, body in by_offset.items()}
        or not ranges
        or len(wanted) != len(ranges)
        or metadata.num_rows != shard["rows"]
    ):
        raise ValueError("retained fragment inventory differs from the selected projection")
    chunks = {0: b"PAR1", start: footer} | by_offset
    with (
        intake.SparseParquet(size, chunks) as sparse,
        intake.pq.ParquetFile(sparse, metadata=metadata, pre_buffer=False) as projection,
    ):
        return projection.read(columns=list(intake.COLUMNS), use_threads=False).to_pylist()


def verify_manifests():
    previous = json.loads(MANIFESTS.read_bytes())
    facts = {}
    for candidate, row in previous["rows"].items():
        source, notice = (row["files"][name] for name in ("pyproject.toml", "LICENSE"))
        body = read(ROOT / source["path"], source["sha256"])
        notice_body = read(ROOT / notice["path"], notice["sha256"])
        if (
            len(body) != source["bytes"]
            or len(notice_body) != notice["bytes"]
            or not notice["notice_detected"]
        ):
            raise ValueError("publisher file scope differs")
        definition = tomllib.loads(body.decode())
        constraint = definition.get("project", {}).get("requires-python")
        origin = "project.requires-python"
        if constraint is None:
            origin = "tool.poetry.dependencies.python"
            constraint = (
                definition.get("tool", {}).get("poetry", {}).get("dependencies", {}).get("python")
            )
        if constraint == "^3.12" and origin == "tool.poetry.dependencies.python":
            parsed = ">=3.12,<4.0"
        else:
            parsed = constraint
        if constraint is None:
            origin = None
        admits = SpecifierSet(parsed).contains("3.13.15") if parsed else None
        facts[candidate] = {
            "repository": row["repository"],
            "revision": row["base_commit"],
            "metadata_constraint_source": origin,
            "metadata_constraint": constraint,
            "admits_retained_python_3_13_15_in_project_metadata": admits,
            "publisher_metadata_and_license": [source, notice],
            "reference_grader_or_redistribution_verified": False,
        }
    if (
        len(facts) != 6
        or sum(
            row["admits_retained_python_3_13_15_in_project_metadata"] is True
            for row in facts.values()
        )
        != 4
    ):
        raise ValueError("candidate manifest results changed")
    return facts


def plan_identity_intake(rows, facts, recorded):
    """Keep exact next admission inputs private and separate from the catalogue."""
    remaining = {
        case
        for case, entry in facts.items()
        if entry["admits_retained_python_3_13_15_in_project_metadata"]
    }
    planned = []
    index = 0
    for number, shard in enumerate(recorded["shards"]):
        footer = read(intake.TARGET / f"shard-{number}-footer.bin", shard["footer_sha256"])
        metadata = intake.pq.read_metadata(intake.pa.BufferReader(b"PAR1" + footer))
        for group in range(metadata.num_row_groups):
            layout = metadata.row_group(group)
            selected = {
                row["instance_id"]: offset
                for offset, row in enumerate(rows[index : index + layout.num_rows])
                if row["instance_id"] in remaining
            }
            index += layout.num_rows
            if not selected:
                continue
            remaining.difference_update(selected)
            exact = {}
            for i in range(layout.num_columns):
                col = layout.column(i)
                if col.path_in_schema not in (
                    "FAIL_TO_PASS.list.element",
                    "PASS_TO_PASS.list.element",
                ):
                    continue
                start = min(
                    value for value in (col.dictionary_page_offset, col.data_page_offset) if value
                )
                length = col.total_compressed_size
                limit = shard["publisher_shard_bytes"] - len(footer)
                if col.file_path or not 4 <= start < start + length <= limit:
                    raise ValueError("test identity range exceeds publisher shard")
                exact[col.path_in_schema] = {"start": start, "bytes": length}
            if len(exact) != 2:
                raise ValueError("both publisher assertion lists are required")
            planned.append(
                {
                    "shard": shard["name"],
                    "shard_sha256": shard["publisher_lfs_sha256"],
                    "row_group": group,
                    "row_positions": selected,
                    "allowed_ranges": exact,
                }
            )
    if remaining or index != len(rows):
        raise ValueError("candidate records do not resolve into the verified shards")
    return {
        "purpose": "Check published issue and preservation identity availability for four initial software leads.",
        "row_groups": planned,
        "maximum_range_requests": sum(len(item["allowed_ranges"]) for item in planned),
        "maximum_range_bytes": sum(
            item["bytes"] for group in planned for item in group["allowed_ranges"].values()
        ),
        "next_control": "Use one public pinned shard HEAD and exact ranges after at least 52 GiB is usable. Discard unrelated rows after extraction and retain selected test identities outside worker inputs.",
        "executed": False,
    }


def run():
    recorded = json.loads(ACQUISITION.read_bytes())
    reviewed = json.loads(SCOPE.read_bytes())
    driver = Path(intake.__file__)
    if (
        ref(driver)["sha256"] != reviewed["driver_sha256"]
        or ref(FIXTURE)["sha256"] != reviewed["fixture_sha256"]
    ):
        raise ValueError("first-run metadata driver binding changed")
    reconstructed = [
        row for index, shard in enumerate(recorded["shards"]) for row in replay(shard, index)
    ]
    original, case_names = intake.leaderboard_origins()
    prior, seen, exposed = intake.previous_repositories()
    lanes, refused = intake.screen(
        reconstructed, excluded=prior | seen | exposed, old_origins=original, old_cases=case_names
    )
    if (
        len(reconstructed) != recorded["rows"]
        or refused != recorded["rejections"]
        or sum(map(len, lanes.values())) + sum(refused.values()) != len(reconstructed)
    ):
        raise ValueError("intake totals do not reconcile")
    counts = defaultdict(list)
    for key, rows in lanes.items():
        rows.sort(key=lambda row: (row["repository"], row["instance_id"].casefold()))
        catalog = recorded["provisional_lanes"][key]["catalog"]
        if json.dumps(rows, indent=2, sort_keys=True).encode() != read(
            ROOT / catalog["path"], catalog["sha256"]
        ):
            raise ValueError("source catalogue is irreproducible")
        for row in rows:
            counts[".".join(row["declared_python"].strip().split(".")[:2])].append(row)
    projects = verify_manifests()
    return recorded | {
        "first_acquisition": ref(SCOPE),
        "driver": ref(driver),
        "local_fixture": ref(FIXTURE),
        "replay_driver": ref(Path(__file__)),
        "offline_replay_verified": True,
        "retained_data_fragments_hash_verified": sum(
            r["data_range_requests"] for r in recorded["shards"]
        ),
        "declared_python_minor_profiles": {
            minor: {
                "provisional_rows": len(rows),
                "repository_families": len({row["repository"] for row in rows}),
            }
            for minor, rows in counts.items()
        },
        "publisher_manifest_batch": {
            "checks": projects,
            "coverage_scope": "The dataset uses Python 3.12 for these six leads. Four projects declare a version range that admits Python 3.13.15. Test compatibility, dependency closure, archive rights and workload validity remain open.",
            "poetry_caret_reference": "https://python-poetry.org/docs/dependency-specification/#caret-requirements",
            "raw_observations": ref(MANIFESTS),
            "public_requests": 12,
            "response_bytes": 21_084,
        },
        "protected_identity_intake_plan": plan_identity_intake(reconstructed, projects, recorded),
        "column_scope": "Full task-body, patches, dependency commands and expected-test columns were excluded. The Parquet footer may contain statistics referencing other columns. Retained raw ranges and candidate lists stay private.",
        "latest_v2_discovery": {
            "dataset": "nebius/SWE-rebench-V2",
            "revision": "d7608f017a29ab256400ad4b73d5248d97204966",
            "published_parquet_bytes": 428_839_266,
            "one_trailer_footer_length_bytes": 4_589_318,
            "data_columns_requested": 0,
            "status": "Separate prospective source. Its footer is above the bounded V1 review; no feasibility count inferred.",
        },
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
