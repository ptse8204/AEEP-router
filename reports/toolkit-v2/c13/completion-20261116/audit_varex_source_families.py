"""Verify candidate PDF bodies and screen their first pages for related form templates."""

import argparse
import itertools
import json
import os
import re
import subprocess
from pathlib import Path

from audit_extractbench_source_groups import partition
from stage_varex_calibration import CASES, METADATA, REV, WORK, digest, pinned, write

POPPLER = Path("/usr/local/Cellar/poppler/25.01.0/bin/pdftotext")
POPPLER_SHA = "7d507ea2df5ce2b8eac1f09ee085c88b2c3cce7a7c5687eef60acfeeb22184a2"
CATALOG = "7ed679a52a481e6d842658a1f28476eb75a9c40dcfa650485ed45b4f316b1d28"
GIT_PINS = {
    "varex-git-pdf-samples": "9a74e2de34530239cfd2acb84b86ae7914c31993f25855e7715ee38188f69b16",
    "varex-git-pdf-remaining": "3d28df59cc504bd6b13dc64aea3c4ecc57eb93fdb15db599e3a9f8d30ed37481",
}
PENDING_FORMS = (("SF1152-11", "sf1152"), ("SF1153-11", "sf1153"), ("SF85PS-17", "sf85ps"))


def verified_pdfs():
    import hashlib

    data = json.loads(pinned(METADATA / "pdf-metadata-result.json", CATALOG))
    catalog = {row["doc_id"]: row for row in data["prospects"] if row["doc_id"] not in CASES}
    active = "varex-lfs-pdf-remaining"
    known = GIT_PINS | {active: digest((WORK.parent / active / "result.json").read_bytes())}
    found, reports, unavailable = {}, {}, {}
    for name, sha in known.items():
        folder = WORK.parent / name
        result = json.loads(pinned(folder / "result.json", sha))
        review = json.loads(pinned(folder / "acquisition-review.json", result["review_sha256"]))
        if review["dataset_revision"] != REV or result["dataset_revision"] != REV:
            raise ValueError("download used another publication")
        for doc_id, row in result["files"].items():
            path = folder / f"{doc_id}.pdf"
            content = pinned(path, row["sha256"])
            source = catalog[doc_id]
            if (
                doc_id in found or len(content) != source["bytes"] or row["bytes"] != source["bytes"]
                or row["schema_sha256"] != source["schema_sha256"]
                or row["git_oid"] != source["git_oid"]
            ):
                raise ValueError("PDF differs from its reviewed manifest entry")
            if source["lfs_sha256"]:
                if row["sha256"] != source["lfs_sha256"]:
                    raise ValueError("PDF differs from its LFS digest")
            else:
                blob = hashlib.sha1(f"blob {len(content)}\0".encode() + content, usedforsecurity=False)
                if blob.hexdigest() != source["git_oid"]:
                    raise ValueError("PDF differs from its published Git object")
            found[doc_id] = (path, row["sha256"], len(content))
        unavailable.update(result.get("unverified_files", {}))
        reports[name] = {"result_sha256": sha, "review_sha256": result["review_sha256"]}
    if set(found) & unavailable.keys() or set(found) | unavailable.keys() != set(catalog):
        raise ValueError("candidate readback omitted a publisher PDF")
    return found, reports, unavailable


def first_page(path):
    text = subprocess.run(
        [str(POPPLER), "-f", "1", "-l", "1", "-layout", str(path), "-"],
        capture_output=True, check=True, timeout=10, env={"PATH": os.defpath, "LC_ALL": "C"},
    ).stdout
    if len(text) > 128_000:
        raise ValueError("first-page text exceeds the review envelope")
    words = re.findall(r"[a-z]{2,}", text.decode().casefold())
    return frozenset(itertools.pairwise(words))


def audit():
    pinned(POPPLER, POPPLER_SHA)
    documents, reports, unavailable = verified_pdfs()
    fingerprints = {}
    insufficient = []
    for doc_id, (path, _, _) in sorted(documents.items()):
        try:
            features = first_page(path)
        except (OSError, ValueError, subprocess.SubprocessError):
            insufficient.append(doc_id)
            continue
        if len(features) >= 40:
            fingerprints[doc_id] = features
        else:
            insufficient.append(doc_id)
    potential = []
    for left, right in itertools.combinations(fingerprints, 2):
        a, b = fingerprints[left], fingerprints[right]
        overlap = len(a & b) / len(a | b)
        if overlap >= 0.60:
            potential.append({"cases": [left, right], "first_page_bigram_jaccard": round(overlap, 4)})
    potential.sort(key=lambda row: (-row["first_page_bigram_jaccard"], row["cases"]))
    links = [
        (identity, index) for index, row in enumerate(potential) for identity in row["cases"]
    ]
    provisional_groups = partition(sorted(documents), links)
    return {
        "schema_version": "aeep.c13.varex-source-family-screen.v1",
        "dataset_revision": REV, "poppler_sha256": POPPLER_SHA, "acquisitions": reports,
        "files": {doc_id: {"sha256": sha, "bytes": size} for doc_id, (_, sha, size) in documents.items()},
        "verified_pdf_bodies": len(documents), "unavailable": unavailable,
        "verified_pdf_bytes": sum(size for _, _, size in documents.values()),
        "cases_with_usable_first_page_text": len(fingerprints), "insufficient_first_page_text": insufficient,
        "filename_variant_leads": [list(pair) for pair in PENDING_FORMS],
        "related_form_leads": potential,
        "connected_related_form_groups": [list(group) for group in provisional_groups if len(group) > 1],
        "capacity_if_one_case_per_provisional_group": len(provisional_groups),
        "method": "First-page lowercase word-bigram Jaccard, minimum 40 bigrams and 0.60 overlap. Retain identifiers and scores only.",
        "scope": "Related-form screening for manual source-family review. Unmatched pairs do not prove independence.",
        "formal_cases_assigned": 0, "new_grader_calls": 0, "model_turns": 0, "cash_usd": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    write(parser.parse_args().out, audit())
