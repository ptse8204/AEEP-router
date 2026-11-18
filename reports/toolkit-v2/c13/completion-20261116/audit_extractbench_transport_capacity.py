"""Screen the retained ExtractBench task groups against the worker archive limits."""

import argparse
import json
import re
import urllib.request
from collections import Counter
from itertools import product
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qsl, urlsplit

from audit_extractbench_collection_shapes import (
    AT_MOST_ONE,
    MULTIPLE,
    collection_paths,
    eligible_groups,
    feasibility,
)
from audit_extractbench_schema_variations import (
    EXTRACT,
    MANIFEST_SHA,
    SCHEMA,
    NoRedirect,
    digest,
    metadata,
    read,
    unique_object,
)
from recover_extractbench_schemas import bound_inputs, write
from stage_repository_transport import ROOT, WORK

TREE = f"https://huggingface.co/api/datasets/llamaindex/ExtractBench/tree/{EXTRACT}/tasks"
FIRST = TREE + "?recursive=true&expand=false"
MAX_PAGES = 8
MAX_BODY = 2 * 1024 * 1024
ZIP_LIMIT = 4_000_000
UNPACK_LIMIT = 16_000_000
INSTRUCTION_LIMIT = 100_000
PUBLIC = ("instruction.md", "environment/document.pdf", SCHEMA)
RECOVERY = ROOT / ".aeep/c13-extractbench-collection-shape.suhrzT/schema-recovery-review.json"
RECOVERY_PIN = "5e323b110188cae6d32dbe9fbd241d41a1d398b99c564a5191998f8d8139bcdc"


def page_url(url):
    if len(url) > 4096:
        raise ValueError("publisher cursor is oversized")
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, strict_parsing=True, max_num_fields=4)
    query = dict(pairs)
    if (
        f"{parts.scheme}://{parts.netloc}{parts.path}" != TREE
        or parts.fragment
        or len(query) != len(pairs)
        or set(query) - {"recursive", "expand", "cursor", "limit"}
        or query.get("recursive", "true") != "true"
        or query.get("expand", "false") != "false"
        or query.get("limit", "1000") != "1000"
        or ("cursor" in query and not query["cursor"])
    ):
        raise ValueError("publisher cursor escaped the pinned metadata endpoint")
    return url


def next_page(link):
    if not link:
        return None
    matches = re.findall(r'<([^<>]+)>\s*;\s*rel="next"', link)
    if len(matches) != 1:
        raise ValueError("unexpected publisher pagination header")
    return page_url(matches[0])


def tree_rows(raw):
    rows = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(rows, list) or not rows or len(rows) > 1000:
        raise ValueError("publisher page is not a bounded tree listing")
    for row in rows:
        path = PurePosixPath(row["path"])
        if (
            path.parts[:1] != ("tasks",)
            or path.as_posix() != row["path"]
            or ".." in path.parts
            or row["type"] not in {"directory", "file"}
            or not re.fullmatch("[0-9a-f]{40}", row["oid"])
            or type(row["size"]) is not int
            or row["size"] < 0
        ):
            raise ValueError("invalid publisher tree entry")
    return rows


def first_page(prior_pin):
    prior = WORK / "extractbench-transport-metadata-20261118"
    record = json.loads(read(prior / "terminal.json", prior_pin))
    if record["state"] != "failed" or len(record["retained_pages"]) != 1:
        raise ValueError("expected a settled initial page and no later requests")
    (page,) = record["retained_pages"]
    if page["url"] != FIRST or page["path"] != "page-00.json":
        raise ValueError("retained page is outside the original endpoint")
    raw = read(prior / page["path"], page["sha256"])
    cursor = next_page(page["link"])
    if (
        len(raw) != page["bytes"]
        or len(raw) != record["body_bytes"]
        or len(tree_rows(raw)) != page["rows"]
        or cursor in {None, FIRST}
    ):
        raise ValueError("retained initial response or unstarted cursor changed")
    return page, raw, cursor


def acquire(directory, review_pin, prior_pin):
    if directory.parent != WORK or directory.resolve() != directory or directory.exists():
        raise ValueError("use a fresh canonical private directory")
    page, raw, url = first_page(prior_pin)
    directory.mkdir(mode=0o700)
    write(
        directory / "started.json",
        {"review_sha256": review_pin, "reused_initial_page_sha256": page["sha256"]},
    )
    with (directory / page["path"]).open("xb") as output:
        output.write(raw)
    client = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))
    pages, seen, total = [page], {FIRST}, page["bytes"]
    try:
        for index in range(1, MAX_PAGES):
            if total >= MAX_BODY or url in seen:
                raise ValueError("publisher tree hit the byte limit or repeated a page")
            seen.add(url)
            request = urllib.request.Request(
                page_url(url), headers={"Accept": "application/json", "Accept-Encoding": "identity"}
            )
            with client.open(request, timeout=15) as reply:
                if reply.status != 200 or reply.headers.get_content_type() != "application/json":
                    raise ValueError("publisher response is not a successful JSON page")
                if reply.headers.get("Content-Encoding", "identity") != "identity":
                    raise ValueError("encoded response cannot use the reviewed byte limit")
                raw = reply.read(MAX_BODY - total + 1)
                link = reply.headers.get("Link")
            total += len(raw)
            if total > MAX_BODY:
                raise ValueError("tree response exceeded reviewed aggregate byte limit")
            filename = f"page-{index:02d}.json"
            with (directory / filename).open("xb") as output:
                output.write(raw)
            pages.append(
                {
                    "path": filename,
                    "sha256": digest(raw),
                    "bytes": len(raw),
                    "url": url,
                    "link": link,
                    "rows": len(tree_rows(raw)),
                }
            )
            url = next_page(link)
            if url is None:
                break
        else:
            raise ValueError("publisher tree hit the reviewed page ceiling")
    except (OSError, ValueError, KeyError, TypeError) as error:
        write(
            directory / "terminal.json",
            {
                "state": "failed",
                "error_type": type(error).__name__,
                "retained_pages": pages,
                "body_bytes": total,
            },
        )
        raise
    record = {"state": "complete", "pages": pages, "body_bytes": total, "review_sha256": review_pin}
    write(directory / "terminal.json", record)
    return record


def acquisition(directory, review_pin):
    terminal = directory / "terminal.json"
    record = json.loads(terminal.read_bytes())
    if record["state"] != "complete" or record["review_sha256"] != review_pin:
        raise ValueError("no completed acquisition for this exact review")
    pages = record["pages"]
    if (
        not 1 <= len(pages) <= MAX_PAGES
        or sum(page["bytes"] for page in pages) != record["body_bytes"]
        or record["body_bytes"] > MAX_BODY
    ):
        raise ValueError("retained pages exceed the review")
    entries = {}
    url = FIRST
    for index, page in enumerate(pages):
        if page["path"] != f"page-{index:02d}.json" or url != page_url(page["url"]):
            raise ValueError("retained pages or pagination order changed")
        raw = read(directory / page["path"], page["sha256"])
        rows = tree_rows(raw)
        if len(raw) != page["bytes"] or len(rows) != page["rows"]:
            raise ValueError("retained page inventory changed")
        for row in rows:
            if row["path"] in entries:
                raise ValueError("tree repeated an entry")
            entries[row["path"]] = row
        url = next_page(page["link"])
    if url is not None:
        raise ValueError("retained tree is incomplete")
    return record, entries


def file_sizes(rows, entries):
    files = {name: row for name, row in entries.items() if row["type"] == "file"}
    expected = {f"tasks/{case}/{name}" for case, row in rows.items() for name in row["files"]}
    if set(files) != expected:
        raise ValueError("pinned tree inventory differs from the publisher manifest")
    inventory, lfs_count = {}, 0
    for case, manifest_row in rows.items():
        sizes = {}
        for name, sha in manifest_row["files"].items():
            entry = files[f"tasks/{case}/{name}"]
            lfs = entry.get("lfs")
            if lfs:
                if (lfs["oid"], lfs["size"]) != (sha, entry["size"]):
                    raise ValueError("publisher LFS metadata does not match the manifest")
                lfs_count += 1
            sizes[name] = entry["size"]
        inventory[case] = sizes
    return inventory, lfs_count


def transport_class(sizes):
    public_bytes = sum(sizes[name] for name in PUBLIC)
    if not 0 < sizes["instruction.md"] <= INSTRUCTION_LIMIT or public_bytes > UNPACK_LIMIT:
        return "outside_current_instruction_or_unpack_limit"
    # A ZIP_STORED size calculation for the exact three standard entries.
    # ZIP_DEFLATED is measured separately on actual assets before dispatch.
    stored = public_bytes + 22 + sum(30 + 46 + 2 * len(name) for name in PUBLIC)
    if stored <= ZIP_LIMIT:
        return "stored_zip_size_within_limit"
    return "compressed_zip_size_needed"


def scopes(rows, groups, inventory, observed, unresolved):
    all_slots = {case for members in groups.values() for case in members}
    classes = {case: transport_class(inventory[case]) for case in all_slots}
    lengths = {}
    results = {}
    for key, allowed in (
        ("within_stored_zip_budget", {"stored_zip_size_within_limit"}),
        (
            "allows_unknown_zip_compression",
            {
                "stored_zip_size_within_limit",
                "compressed_zip_size_needed",
            },
        ),
    ):
        viable = {
            group: [case for case in cases if classes[case] in allowed]
            for group, cases in groups.items()
        }
        counts, _, _, existing = feasibility(rows, viable, observed)
        hypotheses = Counter()
        for conditional in product((1, 2), repeat=len(unresolved)):
            assumptions = dict(zip(unresolved, conditional, strict=True))
            _, _, _, witness = feasibility(rows, viable, observed | assumptions)
            hypotheses["capacity_witness_found" if witness else "no_capacity_witness_found"] += 1
            if witness and tuple(map(len, witness.values())) != (8, 28, 105, 105):
                raise ValueError("cohort witness changed required stage sizes")
        results[key] = {
            "slot_counts_by_variant": {
                name: counts[name] for name in (AT_MOST_ONE, MULTIPLE, "unresolved")
            },
            "conditional_schema_classifications": dict(hypotheses),
            "witness_from_verified_schemas_only": existing is not None,
        }
    for case in all_slots:
        name = classes[case]
        lengths.setdefault(name, Counter())[case.split("--", 1)[0]] += 1
    return results, lengths


def audit(directory, review_pin):
    source = json.loads(read(RECOVERY, RECOVERY_PIN))
    rows, _, retained = bound_inputs(source, RECOVERY.parent)
    manifest_rows, _ = metadata()
    if rows != manifest_rows or any(
        name not in row["files"] for row in rows.values() for name in PUBLIC
    ):
        raise ValueError("manifest changed from schema recovery inputs")
    result, entries = acquisition(directory, review_pin)
    inventory, lfs_count = file_sizes(rows, entries)
    groups = eligible_groups(rows)
    all_slots = {case for cases in groups.values() for case in cases}
    observed = {sha: len(collection_paths(raw)) for sha, raw in retained.items()}
    unresolved = sorted(item["schema_sha256"] for item in source["requests"])
    envelopes, lengths = scopes(rows, groups, inventory, observed, unresolved)
    public_sizes = {case: sum(inventory[case][name] for name in PUBLIC) for case in all_slots}
    eligible = {
        case
        for case in all_slots
        if transport_class(inventory[case]) == "stored_zip_size_within_limit"
    }
    return {
        "schema_version": "aeep.c13.extractbench-transport-capacity.v1",
        "publisher_revision": EXTRACT,
        "manifest_sha256": MANIFEST_SHA,
        "metadata_public_files": len([row for row in entries.values() if row["type"] == "file"]),
        "metadata_lfs_entries_verified_against_manifest": lfs_count,
        "metadata_only_downloads_including_retained_page": len(result["pages"]),
        "new_metadata_only_downloads": len(result["pages"]) - 1,
        "retained_first_page_replayed": False,
        "metadata_response_bytes": result["body_bytes"],
        "metadata_acquisition_receipt": {
            "path": (directory / "terminal.json").relative_to(ROOT).as_posix(),
            "sha256": digest((directory / "terminal.json").read_bytes()),
        },
        "driver_sha256": digest(Path(__file__).read_bytes()),
        "local_schema_recovery_review_sha256": RECOVERY_PIN,
        "publisher_task_count": len(rows),
        "source_disjoint_metadata_slots_considered": len(all_slots),
        "total_public_bytes_before_deduplication": sum(public_sizes.values()),
        "total_public_bytes_in_stored_size_bucket": sum(public_sizes[case] for case in eligible),
        "maximum_single_task_public_bytes": max(public_sizes.values()),
        "metadata_slots_by_transport_and_length": lengths,
        "cohort_sensitivity_after_transport_screen": envelopes,
        "limits": {
            "instruction_bytes": INSTRUCTION_LIMIT,
            "archive_bytes": ZIP_LIMIT,
            "unpacked_bytes": UNPACK_LIMIT,
        },
        "limit_source_sha256": {
            name: digest((ROOT / name).read_bytes())
            for name in (
                "src/aeep/assessment/adapters.py",
                "src/aeep_toolkit/benchmarks.py",
            )
        },
        "scope": [
            "Public tree metadata supplies sizes and Git object IDs. Non-LFS task bytes are still unverified.",
            "Stored ZIP size is a size-only screen. Verify actual compressed archives and protected assets before use.",
            "Conditional classifications reuse the exact source exclusion and early-stage witness procedure.",
            "No rights determination, holdout assignment, grading or model transfer follows from this audit.",
        ],
        "task_file_bodies_downloaded": 0,
        "formal_cases_adopted": 0,
        "protected_grader_calls": 0,
        "model_turns": 0,
        "comparisons_paused": True,
        "waza_excluded": True,
    }


def check_review(path, expected):
    pins = json.loads(read(path, expected))
    helpers = {
        name: digest(Path(__file__).with_name(name).read_bytes())
        for name in (
            "audit_extractbench_collection_shapes.py",
            "audit_extractbench_schema_variations.py",
            "recover_extractbench_schemas.py",
            "audit_extractbench_source_groups.py",
        )
    }
    prior_pin = pins.get("retained_initial_receipt_sha256")
    page, _, cursor = first_page(prior_pin)
    if pins != {
        "schema_version": "aeep.c13.extractbench-tree-continuation.v1",
        "retained_initial_receipt_sha256": prior_pin,
        "remaining_initial_cursor_sha256": digest(cursor.encode()),
        "retained_initial_page_sha256": page["sha256"],
        "publisher_endpoint": TREE,
        "first_page": FIRST,
        "publisher_manifest_sha256": MANIFEST_SHA,
        "max_http_requests_including_retained_page": MAX_PAGES,
        "max_new_http_requests": MAX_PAGES - 1,
        "max_metadata_body_bytes": MAX_BODY + 1,
        "driver_sha256": digest(Path(__file__).read_bytes()),
        "helper_sha256": helpers,
        "authority": "Bounded read-only publisher metadata audit under CONTINUATION.md",
        "task_file_bodies": 0,
        "network_credentials": 0,
        "repeats": 0,
        "model_turns": 0,
        "cash_usd": 0,
    }:
        raise ValueError("metadata scope or executable changed")
    return prior_pin


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--fetch-unstarted-pages", action="store_true")
    args = parser.parse_args()
    prior_pin = check_review(args.review, args.digest)
    if args.fetch_unstarted_pages:
        acquire(args.directory, args.digest, prior_pin)
    print(json.dumps(audit(args.directory, args.digest), indent=2, sort_keys=True))
