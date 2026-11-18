"""Inspect only the pinned SpreadsheetBench 2 ZIP indexes."""

import argparse
import binascii
import json
import stat
import struct
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections import Counter
from pathlib import PurePosixPath
from typing import NamedTuple

from stage_repository_transport import HERE, WORK, digest

DATASET = "KAKA22/SpreadsheetBench-v2"
REVISION = "5a2215ed4121945ab09d8723df2995602090b042"
TARGET = WORK / "spreadsheet-archive-index-20261117"
SOURCE = HERE / "document-corpus-metadata.json"
INDEX_LIMIT = 256 * 1024
END = struct.Struct("<4s4H2LH")
ENTRY = struct.Struct("<4s6H3I5H2I")
LOCAL = struct.Struct("<4s5H3I2H")
CATEGORIES = ("Debugging", "Financial_Model", "Template", "Visualization")
LATEST = "spreadsheetbench-v2-09-10.zip"
PRIOR = "spreadsheetbench-v2.zip"


class Member(NamedTuple):
    method: int
    crc: int
    compressed: int
    expanded: int
    header_offset: int


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def fetch_range(filename, archive, start, count):
    if not 0 <= start < archive["bytes"] or not 1 <= count <= INDEX_LIMIT:
        raise ValueError("range exceeds the public index limit")
    end = start + count - 1
    if end >= archive["bytes"]:
        raise ValueError("range extends beyond the pinned archive")
    headers = {"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}
    resolve = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{filename}"
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        origin = client.open(urllib.request.Request(resolve, headers=headers), timeout=20)
    except urllib.error.HTTPError as response:
        with response:
            expected = (
                response.code in (302, 307)
                and response.headers.get("X-Repo-Commit") == REVISION
                and response.headers.get("X-Linked-Size") == str(archive["bytes"])
                and response.headers.get("X-Linked-ETag", "").strip('"') == archive["sha256"]
            )
            if not expected:
                raise ValueError("publisher redirect does not bind the pinned archive") from None
            target = response.headers["Location"]
    else:
        with origin:
            raise ValueError("expected a pinned hosted-object redirect")
    parsed = urllib.parse.urlsplit(target)
    if (parsed.scheme != "https" or parsed.netloc != "us.aws.cdn.hf.co"
            or parsed.username is not None or parsed.password is not None):
        raise ValueError("unreviewed archive index destination")
    with client.open(urllib.request.Request(target, headers=headers), timeout=20) as response:
        if (response.status != 206
                or response.headers.get("Content-Range") != f"bytes {start}-{end}/{archive['bytes']}"
                or response.headers.get("Content-Length") != str(count)
                or response.headers.get("Content-Encoding", "identity") != "identity"):
            raise ValueError("host did not return the exact reviewed index range")
        raw = response.read(count + 1)
        if len(raw) != count:
            raise ValueError("truncated archive index range")
    return raw


def bounds(footer, total):
    if len(footer) != END.size:
        raise ValueError("invalid ZIP footer size")
    magic, disk, index_disk, entries_on_disk, entries, size, offset, comment = END.unpack(footer)
    if (magic != b"PK\x05\x06" or disk or index_disk or comment or entries_on_disk != entries
            or not 0 < entries < 5000 or not 0 < size <= INDEX_LIMIT or offset <= 0
            or offset + size != total - END.size):
        raise ValueError("ZIP index is outside the ordinary unsegmented format")
    return entries, size, offset


def entries_from_index(raw, count, offset):
    cursor = 0
    result = {}
    for _ in range(count):
        if cursor + ENTRY.size > len(raw):
            raise ValueError("truncated ZIP index")
        (magic, _, _, flags, method, _, _, crc, compressed, expanded, name_len, extra_len,
         comment_len, disk, _, attrs, local_header) = ENTRY.unpack_from(raw, cursor)
        cursor += ENTRY.size
        end = cursor + name_len + extra_len + comment_len
        if (magic != b"PK\x01\x02" or flags & 1 or disk or end > len(raw) or not 0 < name_len <= 1024
                or local_header + 30 + compressed > offset or method not in {0, 8}
                or stat.S_IFMT(attrs >> 16) not in {0, stat.S_IFDIR, stat.S_IFREG}):
            raise ValueError("unsupported or out-of-bounds ZIP index member")
        name = raw[cursor:cursor + name_len].decode("utf-8" if flags & 0x800 else "cp437")
        path = PurePosixPath(name)
        if (path.is_absolute() or path.as_posix() != name.rstrip("/") or ".." in path.parts
                or any(char in name for char in ("\0", "\\", ":")) or name in result):
            raise ValueError("noncanonical or repeated ZIP member")
        result[name] = Member(method, crc, compressed, expanded, local_header)
        cursor = end
    if cursor != len(raw):
        raise ValueError("ZIP index has trailing or undeclared records")
    return result


def manifest_data(name, member, header, index_start, body):
    (magic, _, flags, method, _, _, crc, compressed, expanded, name_len, extra_len) = LOCAL.unpack(header)
    expected = (member.crc, member.compressed, member.expanded)
    local_sizes = crc, compressed, expanded
    if (magic != b"PK\x03\x04" or flags & 1 or method != member.method
            or (local_sizes != expected and not (flags & 8 and local_sizes == (0, 0, 0)))
            or name_len != len(name) or extra_len > 1024
            or not 0 < member.compressed <= 64 * 1024 or not 0 < member.expanded <= 512 * 1024):
        raise ValueError("dataset manifest local header differs from its index")
    start = member.header_offset + LOCAL.size + name_len + extra_len
    if start + member.compressed > index_start:
        raise ValueError("dataset manifest crosses the ZIP index")
    region = body(member.header_offset + LOCAL.size, name_len + extra_len + member.compressed)
    if region[:name_len] != name.encode("utf-8"):
        raise ValueError("dataset manifest local member name differs")
    raw = region[name_len + extra_len:]
    if member.method == 8:
        inflater = zlib.decompressobj(wbits=-15)
        raw = inflater.decompress(raw, member.expanded + 1)
        if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
            raise ValueError("dataset manifest deflate stream is invalid")
    if len(raw) != member.expanded or binascii.crc32(raw) != member.crc:
        raise ValueError("dataset manifest differs from its indexed size or CRC")
    return raw


def task_manifest_summary(values, category, index):
    paths = {}
    ids = set()
    families = Counter()
    for row in values:
        identity = row.get("id")
        if not isinstance(identity, str) or not 0 < len(identity) <= 200 or identity in ids:
            raise ValueError("missing or repeated dataset case identity")
        ids.add(identity)
        files = []
        for key in ("spreadsheet_path", "golden_response_path"):
            raw = row.get(key)
            if not isinstance(raw, str):
                raise ValueError("missing workbook manifest member")
            path = PurePosixPath(raw)
            full = f"spreadsheetbench-v2/{category}/{raw}"
            if (not path.parts or path.as_posix() != raw or path.is_absolute() or ".." in path.parts
                    or path.parts[0] != "spreadsheet" or path.suffix.lower() != ".xlsx"
                    or full not in index):
                raise ValueError("workbook manifest member escaped or is absent from its archive")
            files.append(full)
        source, golden = files
        if source == golden or source in paths:
            raise ValueError("duplicate or self-referential workbook task")
        paths[source] = golden
        families[golden] += 1
    return {
        "records": len(ids),
        "distinct_input_paths": len(paths),
        "distinct_golden_paths": len(families),
        "golden_path_group_sizes": dict(Counter(families.values())),
        "max_tasks_with_one_golden_path": max(families.values()),
    }


def workbook_manifests(archives, indexes, collect):
    archive = archives[LATEST]
    footer = (TARGET / (LATEST + ".footer")).read_bytes()
    _, _, index_start = bounds(footer, archive["bytes"])
    rows = {}
    for category in CATEGORIES:
        name = f"spreadsheetbench-v2/{category}/dataset.json"
        member = indexes[LATEST][name]
        destination = TARGET / (category + ".manifest.json")
        if collect:
            header_path = TARGET / (category + ".manifest-header.bin")
            if not header_path.exists():
                header = fetch_range(LATEST, archive, member.header_offset, LOCAL.size)
                with header_path.open("xb") as out:
                    out.write(header)
            header = header_path.read_bytes()

            def read_body(start, size):
                return fetch_range(LATEST, archive, start, size)

            if not destination.exists():
                data = manifest_data(name, member, header, index_start, read_body)
                with destination.open("xb") as out:
                    out.write(data)
        raw = destination.read_bytes()
        if len(raw) != member.expanded or binascii.crc32(raw) != member.crc:
            raise ValueError("retained manifest no longer matches its index")
        values = json.loads(raw)
        if not isinstance(values, list) or not values or not all(isinstance(row, dict) for row in values):
            raise ValueError("unexpected dataset manifest record structure")
        prior_member = indexes[PRIOR][name]
        header = (TARGET / (category + ".manifest-header.bin")).read_bytes()
        name_len, extra_len = LOCAL.unpack(header)[-2:]
        rows[category] = {
            "archive_member": name,
            "manifest_sha256": digest(raw),
            "manifest_bytes": len(raw),
            "private_range_payload_bytes": LOCAL.size + name_len + extra_len + member.compressed,
            "older_index_advertises_same_crc_and_size": (
                prior_member.crc, prior_member.expanded
            ) == (member.crc, member.expanded),
            **task_manifest_summary(values, category, indexes[LATEST]),
        }
    return rows


def inspect(collect, manifests=False, collect_manifests=False):
    pinned = json.loads(SOURCE.read_bytes())["spreadsheetbench2"]
    if pinned["data_revision"] != REVISION or len(pinned["archives"]) != 2:
        raise ValueError("dataset pin changed")
    if collect:
        TARGET.mkdir(mode=0o700)
    verified = {}
    indexes = {}
    for filename, archive in pinned["archives"].items():
        footer_path = TARGET / (filename + ".footer")
        directory_path = TARGET / (filename + ".directory")
        total = archive["bytes"]
        if collect:
            tail = fetch_range(filename, archive, total - END.size, END.size)
            _, size, start = bounds(tail, total)
            directory = fetch_range(filename, archive, start, size)
            for path, data in ((footer_path, tail), (directory_path, directory)):
                with path.open("xb") as output:
                    output.write(data)
        footer = footer_path.read_bytes()
        count, size, start = bounds(footer, total)
        raw = directory_path.read_bytes()
        if len(raw) != size:
            raise ValueError("stored ZIP index length differs")
        rows = entries_from_index(raw, count, start)
        indexes[filename] = rows
        files = [PurePosixPath(name) for name in rows if not name.endswith("/")]
        verified[filename] = {
            "publisher_lfs_pin": archive,
            "footer_sha256": digest(footer),
            "directory_sha256": digest(raw),
            "metadata_bytes": len(raw) + len(footer),
            "entries": count,
            "file_extensions": dict(Counter(path.suffix.lower() or "(none)" for path in files)),
        }
    newer, prior = indexes[LATEST], indexes[PRIOR]
    names = newer.keys() & prior.keys()
    manifest_rows = (workbook_manifests(pinned["archives"], indexes, collect_manifests)
                     if manifests or collect_manifests else {})
    payload_bytes = sum(row["metadata_bytes"] for row in verified.values())
    return {
        "schema_version": "aeep.c13.spreadsheetbench-archive-index.v1",
        "publisher_revision": REVISION,
        "archives": verified,
        "index_comparison": {
            "same_paths": len(names), "newer_only_paths": len(newer.keys() - prior.keys()),
            "prior_only_paths": len(prior.keys() - newer.keys()),
            "common_paths_with_different_size_or_crc": sum(
                (newer[name].crc, newer[name].expanded) != (prior[name].crc, prior[name].expanded)
                for name in names
            ),
            "changed_files_by_category": dict(Counter(
                PurePosixPath(name).parts[1] for name in names
                if not name.endswith("/") and len(PurePosixPath(name).parts) > 2
                and (newer[name].crc, newer[name].expanded) != (prior[name].crc, prior[name].expanded)
            )),
        },
        "index_range_payload_bytes": payload_bytes,
        "dataset_manifests": manifest_rows,
        "payload_bytes_in_retained_ranges": payload_bytes + sum(
            row["private_range_payload_bytes"] for row in manifest_rows.values()
        ),
        **({
            "cell_graded_intake_rows": sum(manifest_rows[k]["records"] for k in CATEGORIES[:-1]),
            "initial_golden_path_groups_for_cell_rows": sum(
                manifest_rows[k]["distinct_golden_paths"] for k in CATEGORIES[:-1]
            ),
            "visualization_rows_outside_ordinary_offline_grading": manifest_rows["Visualization"]["records"],
            "recommended_archive_for_source_and_rights_review": LATEST,
            "recommendation_basis": "Later publisher upload with the same index paths and changed workbook entries.",
        } if manifest_rows else {}),
        "full_object_hashes_recomputed": False,
        "workbook_bodies_requested": False,
        "provider_disclosure_authorized": False,
        "graders_executed": 0,
        "formal_cases_adopted": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true", help="download only exact footer and directory ranges")
    parser.add_argument("--manifests", action="store_true", help="inspect the retained task manifests")
    parser.add_argument("--collect-manifests", action="store_true", help="download only the four task manifests")
    args = parser.parse_args()
    print(json.dumps(inspect(args.collect, args.manifests, args.collect_manifests),
                     indent=2, sort_keys=True, allow_nan=False))
