"""Screen every page in the staged VAREX pack for undiscovered form families."""

import argparse
import itertools
import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from audit_extractbench_source_groups import partition
from audit_varex_source_families import POPPLER, POPPLER_SHA
from review_varex_balanced_capacity import packing
from stage_varex_calibration import REV, WORK, pinned, write

STAGED = WORK.parent / "varex-protected-reference-intake" / "balanced-prospects"
STAGED_SHA = "bb803986188f579e09b1e188273236dbe0f14af5f8cdfdc21f306b8ea54e4798"
CAPACITY_SHA = "a7eca5939be12d832c2112f58de5bff09f321a1451ce4c69f06c8d1a4a7423e1"


def pages(path):
    text = subprocess.run(
        [str(POPPLER), "-layout", str(path), "-"],
        capture_output=True,
        check=True,
        timeout=10,
        env={"PATH": os.defpath, "LC_ALL": "C"},
    ).stdout
    if len(text) > 1_000_000:
        raise ValueError("full-text output exceeds the review cap")
    output = []
    for page in text.decode().split("\f"):
        if not page.strip():
            continue
        words = re.findall(r"[a-z]{2,}", page.casefold())
        output.append(frozenset(zip(words, words[1:], words[2:], strict=False)))
    return output


def matches(features, prior):
    """Compare whole documents and substantial repeated pages without retaining text."""
    all_features = {key: frozenset().union(*value) for key, value in features.items()}
    for left, right in itertools.combinations(sorted(features), 2):
        if prior[left] == prior[right]:
            continue
        a, b = all_features[left], all_features[right]
        total = len(a & b) / max(1, len(a | b))
        page = max(
            (
                len(x & y) / len(x | y)
                for x in features[left]
                for y in features[right]
                if min(len(x), len(y)) >= 120
            ),
            default=0,
        )
        if total >= 0.70 or page >= 0.82:
            yield {
                "forms": [left, right],
                "full_text_overlap": round(total, 4),
                "strongest_page_overlap": round(page, 4),
            }


def audit():
    pinned(POPPLER, POPPLER_SHA)
    scope = json.loads(pinned(STAGED / "staged.json", STAGED_SHA))
    manifest = json.loads(pinned(STAGED / "benchmark-pack.json", scope["manifest_file_sha256"]))
    capacity = json.loads(
        pinned(Path(__file__).parent / "varex-balanced-capacity-20261124.json", CAPACITY_SHA)
    )
    assets = {entry["task_id"]: entry["assets"] for entry in manifest["tasks"]}
    known = {
        name: i for i, group in enumerate(capacity["provisional_source_groups"]) for name in group
    }
    features, inputs, uncertain, shapes = {}, {}, [], defaultdict(set)
    for name, entry in sorted(scope["cases"].items()):
        task = entry["input"]
        (pdf,) = [
            item for item in assets[task["task_id"]] if item["path"].endswith("/document.pdf")
        ]
        path = STAGED / "pack" / pdf["path"]
        data = pinned(path, pdf["sha256"])
        if (
            len(data) != pdf["bytes"]
            or pdf["sha256"] != task["document_sha256"]
            or name not in known
        ):
            raise ValueError("staged asset differs from the reviewed pack and grouping")
        inputs[name] = pdf["sha256"]
        shapes[task["family"]].add(name)
        text = pages(path)
        if not text or max(map(len, text)) < 40:
            uncertain.append(name)
        else:
            features[name] = text
    if len(inputs) != 246 or len(set(inputs.values())) != 246:
        raise ValueError("staged cohort contains duplicate or missing PDFs")
    leads = list(matches(features, known))
    links = [(name, ("previous", known[name])) for name in sorted(features)]
    for i, pair in enumerate(leads):
        links.extend((name, ("page overlap", i)) for name in pair["forms"])
    merged = partition(sorted(features), links)
    high, low = shapes["multiple-collections"], shapes["at-most-one-collection"]
    return {
        "schema_version": "aeep.c13.varex-staged-lineage-screen.v1",
        "revision": REV,
        "staging_sha256": STAGED_SHA,
        "capacity_sha256": CAPACITY_SHA,
        "pdftotext_sha256": POPPLER_SHA,
        "input_pdf_sha256": inputs,
        "usable_full_text": len(features),
        "unresolved_text": uncertain,
        "additional_review_leads": leads,
        "packs_without_splitting_flagged_families": packing(merged, high, low),
        "groups_with_multiple_cases": [list(group) for group in merged if len(group) > 1],
        "method": "Lowercase word trigrams over each full document and each page. Jaccard >=0.70 for full text or >=0.82 for pages with at least 120 trigrams each.",
        "scope": "Screen for additional lineage review. Unmatched forms do not establish independence.",
        "formal_assignments": 0,
        "models": 0,
        "cash_usd": 0,
        "provider_disclosure": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    write(parser.parse_args().out, audit())
