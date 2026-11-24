"""Locate document-level rights notices before approving a VAREX batch."""

import argparse
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

from audit_varex_archive_lineage import POPPLER, POPPLER_SHA, STAGED, STAGED_SHA
from audit_varex_packing_witness import RIGHTS_SHA
from stage_repository_transport import HERE, ROOT, digest, read, write

MARKERS = {
    "rights_reserved": r"all rights reserved",
    "prior_permission": r"(?:(?:without|requires?) (?:the )?(?:prior |express |written ){1,3}(?:permission|consent))",
    "restricted_redistribution": r"(?:may not|must not|shall not) be (?:reproduced|redistributed|republished|distributed|copied)",
    "distribution_restricted": r"(?:unauthori[sz]ed|prohibit(?:ed|s)) (?:reproduction|redistribution|distribution)",
    "third_party_attribution": r"reproduced (?:by|with) (?:the )?permission",
    "limited_scope_license": r"(?:licensed|licen[sc]e) (?:for|to) (?:personal|internal|educational|noncommercial|non-commercial) use",
}


def audit():
    read(POPPLER, POPPLER_SHA)
    staging = json.loads(read(STAGED / "staged.json", STAGED_SHA))
    manifest = json.loads(read(STAGED / "benchmark-pack.json", staging["manifest_file_sha256"]))
    reviewed = json.loads(read(HERE / "varex-asset-use-inventory-20261124.json", RIGHTS_SHA))
    inventory = reviewed["draft_inventory"]
    drafts = json.loads(read(ROOT / inventory["path"], inventory["sha256"]))
    if (
        drafts["pack_sha256"] != staging["benchmark_pack_sha256"]
        or len(manifest["tasks"]) != len(drafts["drafts"])
        or len(drafts["drafts"]) != 246
        or drafts["local_execution_approvals"]
        or drafts["provider_disclosure_approvals"]
    ):
        raise ValueError("document and draft inventory scope changed")
    approval_files = {entry["task_id"]: entry["assets"] for entry in drafts["drafts"]}
    checked = {}
    flagged = []
    for task in manifest["tasks"]:
        task_id = task["task_id"]
        (asset,) = [entry for entry in task["assets"] if entry["path"].endswith("/document.pdf")]
        path = STAGED / "pack" / asset["path"]
        if (
            len(read(path, asset["sha256"])) != asset["bytes"]
            or approval_files[task_id][asset["path"]] != asset["sha256"]
        ):
            raise ValueError("staged input and unsigned rights record differ")
        data = subprocess.run(
            [str(POPPLER), "-layout", str(path), "-"],
            capture_output=True,
            check=True,
            timeout=10,
            env={"PATH": os.defpath, "LC_ALL": "C"},
        ).stdout
        if len(data) > 1_000_000 or not data.strip():
            raise ValueError("text extraction outside reviewed bounds")
        checked[task_id] = asset["sha256"]
        for i, page in enumerate(data.decode().casefold().split("\f"), start=1):
            normalized = " ".join(page.split())
            for kind, marker in MARKERS.items():
                if re.search(marker, normalized):
                    flagged.append({"task_id": task_id, "page": i, "marker": kind})
    return {
        "schema_version": "aeep.c13.document-notice-screen.v1",
        "staging_sha256": STAGED_SHA,
        "rights_inventory_sha256": RIGHTS_SHA,
        "pdftotext_sha256": POPPLER_SHA,
        "verified_input_count": len(checked),
        "input_hash_map_sha256": digest(json.dumps(checked, sort_keys=True).encode()),
        "flagged_document_count": len({row["task_id"] for row in flagged}),
        "notice_counts": dict(Counter(row["marker"] for row in flagged)),
        "flagged_pages": flagged,
        "scope": "Text-layer phrase screen to locate pages for rights review; no PDF text retained. Unflagged pages are not a rights determination.",
        "local_execution_approvals": 0,
        "provider_disclosure_approvals": 0,
        "formal_assignments": 0,
        "models": 0,
        "cash_usd": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proof", type=Path)
    options = parser.parse_args()
    write(options.proof, (json.dumps(audit(), indent=2, sort_keys=True) + "\n").encode())
