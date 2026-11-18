"""Count new repository leads from pinned Parquet metadata columns only."""

import argparse
import io
import json
import re
import struct
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from itertools import pairwise
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import pyarrow as pa
import pyarrow.parquet as pq
from plan_repository_expansion import CASE, GIT_REV, UNION, previous_repositories
from plan_repository_expansion import DATASET as LEADERBOARD
from stage_repository_transport import ROOT, WORK, digest, read

DATASET = "nebius/SWE-rebench"
REVISION = "6aecac9ae07f7efa62e93873b239fdfa1f8aa258"
TARGET = WORK / "rebench-full-metadata-20261118"
CARD = "65258ae8c6f702e55ff87fcaa2ae28201e88ee32"
HUB = "https://huggingface.co"
CDN = "us.aws.cdn.hf.co"
SHARDS = (
    (104_004_857, "e0a33a5fc618aac8c24c0a17125dbd6442f79be1cc0f4c67e2edab03de70e1b7"),
    (135_730_600, "81994a30bd2e89fb5e5aedf9196e6425c700b4898720c4d74a0cfd7314f56eeb"),
)
COLUMNS = (
    "instance_id",
    "base_commit",
    "repo",
    "license_name",
    "meta.has_test_patch",
    "meta.num_modified_files",
    "install_config.python",
    "install_config.log_parser",
)
MAX_RANGE_REQUESTS = 180
MAX_RANGE_BYTES = 2_500_000
MAX_FOOTER = 220_000
PERMISSIVE_LABELS = {
    "0bsd",
    "apache-2.0",
    "bsd-2-clause",
    "bsd-3-clause",
    "isc",
    "mit",
    "psf-2.0",
    "unlicense",
    "zlib",
}
LICENSE_ALIAS = {
    "apache license 2.0": "apache-2.0",
    'bsd 2-clause "simplified" license': "bsd-2-clause",
    'bsd 3-clause "new" or "revised" license': "bsd-3-clause",
    "isc license": "isc",
    "mit license": "mit",
    "python software foundation license": "psf-2.0",
    "the unlicense": "unlicense",
}
SLUG = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
PYTHON = re.compile(r"3\.(\d+)(?:\.\d+)?$")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def opener():
    # Public requests run without saved headers, credentials, or redirect handling.
    return build_opener(ProxyHandler({}), NoRedirect())


def shard_path(index):
    return f"data/test-{index:05d}-of-00002.parquet"


def locate(index, expected_size, sha):
    url = f"{HUB}/datasets/{DATASET}/resolve/{REVISION}/{shard_path(index)}"
    try:
        opener().open(Request(url, method="HEAD"), timeout=15).close()
    except HTTPError as error:
        with error:
            location = error.headers.get("Location", "")
            parsed = urlsplit(location)
            if (
                error.code != 302
                or error.headers.get("X-Repo-Commit") != REVISION
                or error.headers.get("X-Linked-Etag", "").strip('"') != sha
                or error.headers.get("X-Linked-Size") != str(expected_size)
                or parsed.scheme != "https"
                or parsed.netloc != CDN
            ):
                raise ValueError("pinned public shard redirect changed") from None
            return location
    raise ValueError("expected a publisher redirect with immutable shard identity")


def get_range(location, size, start, length):
    end = start + length - 1
    if start < 0 or length < 1 or end >= size:
        raise ValueError("range exceeds pinned shard")
    headers = {"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}
    try:
        with opener().open(Request(location, headers=headers), timeout=15) as response:
            expected = f"bytes {start}-{end}/{size}"
            if (
                response.status != 206
                or response.headers.get("Content-Range") != expected
                or response.headers.get("Content-Encoding", "identity") != "identity"
            ):
                raise ValueError("response does not match the requested byte range")
            body = response.read(length + 1)
    except HTTPError as error:
        code = error.code
        error.close()
        raise ValueError(f"public range request failed with HTTP {code}") from None
    if len(body) != length:
        raise ValueError("response is truncated or exceeds requested length")
    return body


def footer_plan(index, size, location):
    tail = get_range(location, size, size - 8, 8)
    length, magic = struct.unpack("<I4s", tail)
    if magic != b"PAR1" or not 0 < length <= MAX_FOOTER:
        raise ValueError("unsupported or oversized Parquet footer")
    start = size - 8 - length
    metadata = get_range(location, size, start, length)
    parsed = pq.read_metadata(pa.BufferReader(b"PAR1" + metadata + tail))
    offsets = []
    for group in range(parsed.num_row_groups):
        row_group = parsed.row_group(group)
        columns = {
            row_group.column(i).path_in_schema: row_group.column(i)
            for i in range(row_group.num_columns)
        }
        for path in COLUMNS:
            col = columns[path]
            first = min(pos for pos in (col.data_page_offset, col.dictionary_page_offset) if pos)
            length = col.total_compressed_size
            if col.file_path or first < 4 or length < 1 or first + length > start:
                raise ValueError("column data exceeds the paired shard")
            offsets.append((group, path, first, length))
    intervals = sorted((first, first + size) for _, _, first, size in offsets)
    if any(left[1] > right[0] for left, right in pairwise(intervals)):
        raise ValueError("selected column chunks overlap")
    return index, parsed, start, metadata, tail, offsets


class SparseParquet(io.RawIOBase):
    """Reject any read outside explicitly retained byte ranges."""

    def __init__(self, size, chunks):
        super().__init__()
        self.size = size
        self.chunks = chunks
        self.position = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        target = {io.SEEK_SET: 0, io.SEEK_CUR: self.position, io.SEEK_END: self.size}[
            whence
        ] + offset
        if not 0 <= target <= self.size:
            raise ValueError("offset is outside the pinned shard")
        self.position = target
        return target

    def readinto(self, buffer):
        length = len(buffer)
        if self.position == self.size or not length:
            return 0
        for start, data in self.chunks.items():
            at = self.position - start
            if at >= 0 and at + length <= len(data):
                buffer[:] = data[at : at + length]
                self.position += length
                return length
        raise ValueError("reader requested an unreviewed range")


def aggregate(plan, size, location, root):
    index, meta, start, footer, tail, offsets = plan
    chunks = {0: b"PAR1", start: footer + tail}

    def acquire(row):
        group, key, first, length = row
        return group, key, first, get_range(location, size, first, length)

    with ThreadPoolExecutor(max_workers=8) as pool:
        acquired = list(pool.map(acquire, offsets))
    ranges = []
    for group, key, first, body in acquired:
        chunks[first] = body
        name = f"shard-{index}-{group}-{key}.bin"
        (root / name).write_bytes(body)
        ranges.append({"name": name, "start": first, "bytes": len(body), "sha256": digest(body)})
    footer_file = f"shard-{index}-footer.bin"
    (root / footer_file).write_bytes(footer + tail)
    with (
        SparseParquet(size, chunks) as sparse,
        pq.ParquetFile(sparse, metadata=meta, pre_buffer=False) as projection,
    ):
        table = projection.read(columns=list(COLUMNS), use_threads=False)
        if table.num_rows != meta.num_rows:
            raise ValueError("column projection lost rows")
        rows = table.to_pylist()
    (root / f"shard-{index}-ranges.json").write_text(json.dumps(ranges, indent=2, sort_keys=True))
    return rows, {
        "name": shard_path(index),
        "publisher_shard_bytes": size,
        "publisher_lfs_sha256": SHARDS[index][1],
        "footer_bytes": len(footer) + 8,
        "footer_sha256": digest(footer + tail),
        "retained_chunk_inventory_sha256": digest(
            (root / f"shard-{index}-ranges.json").read_bytes()
        ),
        "data_range_requests": len(ranges),
        "data_range_bytes": sum(row["bytes"] for row in ranges),
        "rows": meta.num_rows,
    }


def leaderboard_origins():
    record = json.loads(UNION.read_text())
    if record["dataset"] != LEADERBOARD or record["rows"] != 860:
        raise ValueError("pilot source inventory differs")
    origins, cases = set(), set()
    for page in record["sources"]:
        data = read(ROOT / page["private_cache"], page["sha256"])
        if len(data) != page["bytes"]:
            raise ValueError("retained leaderboard byte binding differs")
        for envelope in json.loads(data)["rows"]:
            row = envelope["row"]
            origins.add((row["repo"].casefold(), row["base_commit"]))
            cases.add(row["instance_id"].casefold())
    if len(cases) != record["rows"]:
        raise ValueError("retained leaderboard IDs are incomplete")
    return origins, cases


def screen(rows, *, excluded, old_origins, old_cases):
    accepted = {"declared_3_13": [], "declared_3_12": [], "other_pinned_version": []}
    excluded_count = Counter()
    seen = set()
    for row in rows:
        case, repo, revision = row["instance_id"], row["repo"], row["base_commit"]
        if not CASE.fullmatch(case) or not SLUG.fullmatch(repo) or not GIT_REV.fullmatch(revision):
            excluded_count["invalid_publisher_identity"] += 1
            continue
        repo, lower_case = repo.casefold(), case.casefold()
        origin = (repo, revision)
        if origin in seen:
            excluded_count["duplicate_full_release_origin"] += 1
            continue
        seen.add(origin)
        if repo in excluded:
            excluded_count["previously_considered_or_development_exposed_repository"] += 1
            continue
        if origin in old_origins or lower_case in old_cases:
            excluded_count["already_in_leaderboard_revision"] += 1
            continue
        label = row["license_name"].strip().casefold() if row["license_name"] else ""
        license_id = LICENSE_ALIAS.get(label, label)
        if license_id not in PERMISSIVE_LABELS:
            excluded_count["license_label_needs_separate_review"] += 1
            continue
        meta, setup = row["meta"], row["install_config"]
        declared = PYTHON.fullmatch((setup["python"] or "").strip())
        if setup["log_parser"] != "parse_log_pytest" or not declared:
            excluded_count["unreviewed_test_runner_or_python"] += 1
            continue
        if (
            meta["has_test_patch"] is not True
            or type(meta["num_modified_files"]) is not int
            or meta["num_modified_files"] < 1
        ):
            excluded_count["missing_test_patch_or_edit_count"] += 1
            continue
        lead = {
            "instance_id": case,
            "repository": repo,
            "base_commit": revision,
            "declared_python": setup["python"],
            "dataset_license_hint": license_id,
            "reported_modified_files": meta["num_modified_files"],
        }
        key = f"declared_3_{declared[1]}" if declared[1] in ("12", "13") else "other_pinned_version"
        accepted[key].append(lead)
    return accepted, excluded_count


def run():
    if TARGET.exists():
        raise ValueError("preserve the existing intake")
    TARGET.mkdir(mode=0o700)
    urls = [locate(i, *pin) for i, pin in enumerate(SHARDS)]
    plans = [footer_plan(i, pin[0], urls[i]) for i, pin in enumerate(SHARDS)]
    total_ranges = 2 * len(plans) + sum(len(p[-1]) for p in plans)
    total_bytes = sum(len(plan[3]) + 8 + sum(row[-1] for row in plan[-1]) for plan in plans)
    if total_ranges > MAX_RANGE_REQUESTS or total_bytes > MAX_RANGE_BYTES:
        raise ValueError("column projection exceeds the recorded metadata-only envelope")
    rows, shards = [], []
    for i, plan in enumerate(plans):
        current, summary = aggregate(plan, SHARDS[i][0], urls[i], TARGET)
        rows.extend(current)
        shards.append(summary)
    if len(rows) != 21_336:
        raise ValueError("published full corpus count differs")
    prior, seen, exposed = previous_repositories()
    leaderboard, case_names = leaderboard_origins()
    cohorts, refused = screen(
        rows, excluded=prior | seen | exposed, old_origins=leaderboard, old_cases=case_names
    )
    summary = {}
    for key, values in cohorts.items():
        values.sort(key=lambda row: (row["repository"], row["instance_id"].casefold()))
        encoded = json.dumps(values, indent=2, sort_keys=True).encode()
        path = TARGET / f"{key}.json"
        path.write_bytes(encoded)
        summary[key] = {
            "provisional_rows": len(values),
            "repository_families": len({row["repository"] for row in values}),
            "rows_publisher_reports_at_least_two_changed_files": sum(
                row["reported_modified_files"] >= 2 for row in values
            ),
            "catalog": {"path": str(path.relative_to(ROOT)), "sha256": digest(encoded)},
        }
    return {
        "schema_version": "aeep.c13.full-rebench-metadata-screen.v1",
        "dataset": DATASET,
        "revision": REVISION,
        "upstream_card_git_blob": CARD,
        "upstream_dataset_license": "CC-BY-4.0",
        "project_rights_verified": False,
        "full_shard_hash_verified": False,
        "transport": "The pinned Hub resolver returned the expected LFS identity. Only listed byte ranges were read and individually hashed.",
        "columns": list(COLUMNS),
        "pinned_repositories_excluded": len(prior | seen | exposed),
        "existing_leaderboard_origins_excluded": len(leaderboard),
        "existing_leaderboard_cases_excluded": len(case_names),
        "rows": len(rows),
        "rejections": dict(refused),
        "provisional_lanes": summary,
        "shards": shards,
        "requests": {"head": len(SHARDS), "range_gets": total_ranges},
        "metadata_body_bytes": total_bytes,
        "pyarrow_version": pa.__version__,
        "task_sources_downloaded": 0,
        "new_model_turns": 0,
        "formal_cases_adopted": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire-metadata", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(run(), indent=2, sort_keys=True))
