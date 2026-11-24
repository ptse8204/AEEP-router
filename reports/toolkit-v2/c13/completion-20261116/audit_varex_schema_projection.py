"""Audit the pinned VAREX schemas using bounded Parquet column reads."""

import argparse
import hashlib
import io
import json
import os
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import pyarrow
import pyarrow.parquet as parquet

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / ".aeep/c13-cohort-runtime-20261124/varex"
MANIFEST = ROOT / ".aeep/c13-cohort-continuation-20261124/varex-source-metadata/manifest.json"
REV = "ff36b6cd232efd401b3f4a20272a07bf2b749914"
TREE_SHA = "587ab9762ea07d65c005451c7fbadde3b411fb0590e128c0a4c31e8dc3c64fee"
MANIFEST_SHA = "6acc717aca6a8ba8baf09ec84e1e73872d29a99657d28e365b6fe78c26b74ada"
CDN = "us.aws.cdn.hf.co"
COLUMNS = ("doc_id", "split", "schema")
MAX_BYTES = 10_000_000
MAX_REQUESTS = 160


def digest(body):
    return hashlib.sha256(body).hexdigest()


def pinned(path, expected):
    body = path.read_bytes()
    if digest(body) != expected:
        raise ValueError("retained publisher bytes differ")
    return body


def write(path, data):
    with path.open("x") as out:
        json.dump(data, out, ensure_ascii=True, indent=2, sort_keys=True)
        out.write("\n")


class BoundRedirect(HTTPRedirectHandler):
    def __init__(self, row):
        self.row = row
        self.observed = False

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if (
            self.observed
            or urlsplit(req.full_url).hostname != "huggingface.co"
            or target.scheme != "https"
            or target.hostname != CDN
            or target.port not in (None, 443)
            or headers.get("x-linked-etag", "").strip('"') != self.row["lfs"]["oid"]
            or headers.get("x-linked-size") != str(self.row["size"])
        ):
            raise ValueError("storage redirect has no matching publisher object")
        self.observed = True
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class RangeStore:
    def __init__(self, review, execute, *, work=WORK):
        self.review = review
        self.execute = execute
        self.work = work
        self.transfers = []
        self.requested = 0
        self.expected = {}
        if not execute:
            records = json.loads((self.work / "range-receipts.json").read_text())
            self.expected = {(r["object"], r["offset"], r["size"]): r for r in records}
            if len(self.expected) != len(records):
                raise ValueError("range receipt is duplicated")

    def read(self, row, start, size):
        end = start + size
        if not 0 <= start < end <= row["size"]:
            raise ValueError("column range lies outside its pinned object")
        self.requested += size
        if self.requested > self.review["max_bytes"] or len(self.transfers) >= MAX_REQUESTS:
            raise ValueError("bounded range acquisition exceeded its review")
        obj = row["lfs"]["oid"]
        path = self.work / "ranges" / f"{obj[:16]}-{start}-{size}.bin"
        if self.execute:
            url = f"https://huggingface.co/datasets/ibm-research/VAREX/resolve/{REV}/{row['path']}"
            request = Request(url, headers={"Range": f"bytes={start}-{end - 1}"})
            binding = BoundRedirect(row)
            with build_opener(binding).open(request, timeout=15) as response:
                if (
                    not binding.observed
                    or urlsplit(response.geturl()).hostname != CDN
                    or response.status != 206
                    or response.headers.get("Content-Range")
                    != f"bytes {start}-{end - 1}/{row['size']}"
                    or response.headers.get("Content-Encoding") not in (None, "identity")
                ):
                    raise ValueError("requested range was not served exactly")
                body = response.read(size + 1)
            if len(body) != size:
                raise ValueError("range body length differs")
            with path.open("xb") as out:
                out.write(body)
        else:
            body = pinned(path, self.expected[obj, start, size]["sha256"])
        self.transfers.append(
            {"object": obj, "offset": start, "size": size, "sha256": digest(body)}
        )
        return body


class ColumnView(io.RawIOBase):
    """Expose only the byte ranges admitted from the pinned metadata."""

    def __init__(self, size, ranges):
        self.size = size
        self.ranges = ranges
        self.position = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.position, io.SEEK_END: self.size}[whence]
        if not 0 <= base + offset <= self.size or self.closed:
            raise OSError("unexpected Parquet seek")
        self.position = base + offset
        return self.position

    def read(self, size=-1):
        if size == 0:
            return b""
        if size < 0 or self.closed:
            raise OSError("unbounded Parquet read")
        end = self.position + size
        for start, data in self.ranges:
            if start <= self.position < end <= start + len(data):
                selected = data[self.position - start : end - start]
                self.position = end
                return selected
        raise OSError("Parquet attempted to read an unreviewed column")


def project(row, store, columns=COLUMNS):
    total = row["size"]
    tail = store.read(row, total - 8, 8)
    size = int.from_bytes(tail[:4], "little")
    if tail[-4:] != b"PAR1" or not 1 <= size <= 131_072:
        raise ValueError("unexpected Parquet footer")
    footer = store.read(row, total - 8 - size, size)
    metadata = parquet.read_metadata(io.BytesIO(b"PAR1" + footer + tail))
    if not (1 <= metadata.num_row_groups <= 24 and 1 <= metadata.num_rows <= 600):
        raise ValueError("unexpected publication row count")
    bounds = []
    for i in range(metadata.num_row_groups):
        group = metadata.row_group(i)
        selected = {
            col.path_in_schema: col
            for j in range(group.num_columns)
            if (col := group.column(j)).path_in_schema in columns
        }
        if set(selected) != set(columns):
            raise ValueError("published Parquet columns differ")
        for name in columns:
            col = selected[name]
            offset = col.dictionary_page_offset or col.data_page_offset
            count = col.total_compressed_size
            if not (
                col.physical_type == "BYTE_ARRAY"
                and col.file_path in ("", None)
                and 4 <= offset < offset + count <= total - size - 8
            ):
                raise ValueError("projected column references an unsupported range")
            bounds.append((offset, count))
    ranges = [(start, store.read(row, start, size)) for start, size in sorted(bounds)]
    with ColumnView(total, ranges) as view:
        reader = parquet.ParquetFile(view, metadata=metadata, pre_buffer=False, buffer_size=0)
        table = reader.read(columns=list(columns), use_threads=False)
    if table.num_rows != metadata.num_rows or set(table.column_names) != set(columns):
        raise ValueError("projected Parquet rows differ")
    yield from table.to_pylist()


def collection_paths(schema):
    def walk(node, path, references, depth):
        if not isinstance(node, dict):
            return set()
        if depth >= 32 or "$dynamicRef" in node:
            raise ValueError("schema nesting or dynamic reference is unsupported")
        paths = set()
        if "$ref" in node:
            ref = node["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/") or ref in references:
                raise ValueError("recursive or nonlocal schema reference")
            resolved = schema
            for part in unquote(ref[2:]).split("/"):
                key = part.replace("~1", "/").replace("~0", "~")
                if isinstance(resolved, list) and key.isdecimal() and int(key) < len(resolved):
                    resolved = resolved[int(key)]
                elif isinstance(resolved, dict) and key in resolved:
                    resolved = resolved[key]
                else:
                    raise ValueError("missing local schema reference")
            paths |= walk(resolved, path, (*references, ref), depth + 1)
        value = node.get("type")
        if value == "array" or (isinstance(value, list) and "array" in value):
            paths.add(path)
        for name, child in node.get("properties", {}).items():
            paths |= walk(child, (*path, name), references, depth + 1)
        paths |= walk(node.get("items"), (*path, "[]"), references, depth + 1)
        for keyword in ("allOf", "anyOf", "oneOf"):
            for option in node.get(keyword, []):
                paths |= walk(option, path, references, depth + 1)
        return paths

    return walk(schema, (), (), 0)


def audit(execute, *, write_prospects=False):
    if pyarrow.__version__ != "21.0.0":
        raise ValueError("reviewed local Arrow version differs")
    tree = json.loads(pinned(WORK / "publisher-tree.json", TREE_SHA))
    manifest = json.loads(pinned(MANIFEST, MANIFEST_SHA))
    expected_paths = [f"data/benchmark-{i:05d}-of-00004.parquet" for i in range(4)]
    if [row["path"] for row in tree] != expected_paths:
        raise ValueError("pinned shard names differ")
    review = {
        "revision": REV,
        "tree_sha256": TREE_SHA,
        "manifest_sha256": MANIFEST_SHA,
        "driver_sha256": digest(Path(__file__).read_bytes()),
        "arrow": pyarrow.__version__,
        "cdn": CDN,
        "columns": list(COLUMNS),
        "objects": [{k: row[k] for k in ("path", "size", "oid", "lfs")} for row in tree],
        "max_bytes": MAX_BYTES,
        "max_requests": MAX_REQUESTS,
        "models": 0,
        "cash_usd": 0,
        "provider_disclosure": False,
    }
    review_path = WORK / "schema-projection-review.json"
    if execute:
        (WORK / "ranges").mkdir(mode=0o700)
        write(review_path, review)
    else:
        saved = json.loads(review_path.read_text())
        if saved["driver_sha256"] != review["driver_sha256"]:
            pinned(WORK / "acquisition-driver.py", saved["driver_sha256"])
        if saved != review | {"driver_sha256": saved["driver_sha256"]}:
            raise ValueError("range review drift")
    store = RangeStore(review, execute)
    rows = {}
    try:
        for shard in tree:
            for row in project(shard, store):
                key = row["doc_id"]
                if key in rows or row["split"] not in {"Flat", "Nested", "Table"}:
                    raise ValueError("duplicate document or unknown publisher split")
                body = row["schema"].encode()
                if len(body) > 131_072:
                    raise ValueError("schema exceeds the reviewed limit")
                schema = json.loads(body)
                try:
                    collections = len(collection_paths(schema))
                except ValueError:
                    collections = None
                rows[key] = {
                    "split": row["split"],
                    "collections": collections,
                    "schema_sha256": digest(body),
                    "shard_sha256": shard["lfs"]["oid"],
                }
    finally:
        if execute:
            write(WORK / "range-receipts.json", store.transfers)
    if set(rows) != set(manifest["doc_ids"]) or len(rows) != manifest["document_count"]:
        raise ValueError("projected IDs differ from the publisher manifest")
    groups = Counter(
        "unknown" if x["collections"] is None else str(x["collections"]) for x in rows.values()
    )
    prospects = {
        key: meta for key, meta in rows.items() if meta["collections"] and meta["collections"] > 1
    }
    if write_prospects:
        write(
            WORK / "multiple-collection-prospects.json",
            {"dataset_revision": REV, "cases": prospects, "formal_assignments": 0},
        )
    return {
        "schema_version": "aeep.c13.varex-projected-schemas.v1",
        "documents": len(rows),
        "publisher_splits": dict(Counter(item["split"] for item in rows.values())),
        "collections": dict(groups),
        "multiple_collections": len(prospects),
        "multiple_collection_schema_hashes": len(
            {row["schema_sha256"] for row in prospects.values()}
        ),
        "projected_catalog_sha256": digest(json.dumps(rows, sort_keys=True).encode()),
        "actual_range_bytes": sum(row["size"] for row in store.transfers),
        "range_requests": len(store.transfers),
        "review_sha256": digest(review_path.read_bytes()),
        "analysis_driver_sha256": review["driver_sha256"],
        "formal_assignments": 0,
        "protected_grades": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--acquire", action="store_true", help="Fetch the scoped footer and column ranges once"
    )
    parser.add_argument(
        "--write-prospects", action="store_true", help="Write the private eligibility queue"
    )
    args = parser.parse_args()
    os.umask(0o077)
    print(
        json.dumps(
            audit(args.acquire, write_prospects=args.write_prospects), indent=2, sort_keys=True
        )
    )
