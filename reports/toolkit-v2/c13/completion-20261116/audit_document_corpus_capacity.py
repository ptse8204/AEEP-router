"""Check pinned public document benchmark metadata without fetching task assets or running graders."""

import argparse
import json
from collections import Counter
from pathlib import Path

from audit_formal_inputs import digest

from aeep.assessment.models import content_digest
from aeep_toolkit.benchmarks import BenchmarkTask, relative_path

EXTRACT = "f9b910906cd7e73cc9eb5379a8d5d935c67b92c4"
WORKBOOK = "5a2215ed4121945ab09d8723df2995602090b042"
SCORER = "2f27f100730afc7c395602e26a2a87e07ea66b31"
SHEET_GRADER = "a7bdc2d358e052d35a94768e1f487c0d9e9c0011"
SAMPLES = (
    "short--00581-2011-p0050-2023b9ee84",
    "medium--baker-hughes-earnings-deck-q4fy25-56f3704b10",
    "long--sec-13f-0010-renaissance-technologies-5be683873c",
)
ROLES = {
    "instruction.md": "instruction",
    "environment/document.pdf": "input",
    "environment/schema.json": "input",
    "solution/expected.json": "oracle",
    "tests/reference.test.json": "oracle",
    "tests/verifier.py": "verifier",
}
REQUIRED = {"screening": 8, "training": 28, "holdout": 105}


def read(root, name):
    with (root / name).open("rb") as stream:
        document = stream.read(1_000_001)
    if len(document) > 1_000_000:
        raise ValueError("review file exceeds the observed metadata scope")
    return document


def pinned_documents(root):
    paths = {
        "extract-metadata": f"https://huggingface.co/api/datasets/llamaindex/ExtractBench/revision/{EXTRACT}",
        "extract-manifest": f"https://huggingface.co/datasets/llamaindex/ExtractBench/raw/{EXTRACT}/harbor-manifest.json",
        "extract-readme": f"https://huggingface.co/datasets/llamaindex/ExtractBench/raw/{EXTRACT}/README.md",
        "scorer-project": f"https://raw.githubusercontent.com/run-llama/ExtractBench/{SCORER}/pyproject.toml",
        "spreadsheet-metadata": f"https://huggingface.co/api/datasets/KAKA22/SpreadsheetBench-v2/revision/{WORKBOOK}",
        "spreadsheet-tree": f"https://huggingface.co/api/datasets/KAKA22/SpreadsheetBench-v2/tree/{WORKBOOK}",
        "spreadsheet-eval": f"https://raw.githubusercontent.com/RUCKBReasoning/SpreadsheetBench-2/{SHEET_GRADER}/evaluation/evaluation.py",
        "spreadsheet-recalc": f"https://raw.githubusercontent.com/RUCKBReasoning/SpreadsheetBench-2/{SHEET_GRADER}/evaluation/open_spreadsheet.py",
    }
    original = f"https://huggingface.co/datasets/llamaindex/ExtractBench/raw/{EXTRACT}/tasks/{SAMPLES[0]}/tests/"
    paths.update({
        "verifier.py": original + "verifier.py",
        "verifier.test.sh": original + "test.sh",
        "verifier.Dockerfile": original + "Dockerfile",
    })
    for sample in SAMPLES:
        paths[sample + ".tree.json"] = (
            f"https://huggingface.co/api/datasets/llamaindex/ExtractBench/tree/{EXTRACT}/tasks/{sample}"
            "?recursive=true&expand=false"
        )
    documents = {name: read(root, name) for name in paths}
    return documents, {
        name: {"url": paths[name], "sha256": digest(value), "bytes": len(value)}
        for name, value in documents.items()
    }


def sample_index(documents, records):
    selected = []
    for identity in SAMPLES:
        record = records[identity]
        files = {
            row["path"]: row
            for row in json.loads(documents[identity + ".tree.json"])
            if row["type"] == "file"
        }
        prefix = "tasks/" + identity + "/"
        if set(files) != {prefix + filename for filename in record["files"]}:
            raise ValueError("repository tree and publisher task manifest disagree")
        assets = []
        for path, role in ROLES.items():
            row = files[prefix + path]
            sha = record["files"][path]
            if row.get("lfs") and (row["lfs"]["oid"], row["lfs"]["size"]) != (sha, row["size"]):
                raise ValueError("publisher manifest and LFS digest disagree")
            assets.append({"path": relative_path(prefix + path), "sha256": sha, "bytes": row["size"], "role": role})
        task = BenchmarkTask.model_validate({
            "task_id": identity, "domain": "document-data", "difficulty": "unknown", "assets": assets,
            "output_paths": ["output.json"], "upstream_score": "native_reward",
        })
        data = task.model_dump(mode="json")
        selected.append({
            "task": data, "metadata_fingerprint": content_digest(data),
            "declared_input_bytes": sum(asset.bytes for asset in task.assets if asset.role in {"input", "instruction"}),
            "declared_protected_bytes": sum(asset.bytes for asset in task.assets if asset.role in {"oracle", "verifier"}),
            "published_artifact_hashes_verified_locally": False,
        })
    return selected


def audit(root):
    text, document_pins = pinned_documents(root)
    meta, manifest = map(json.loads, (text["extract-metadata"], text["extract-manifest"]))
    sheets = json.loads(text["spreadsheet-metadata"])
    if (
        meta["sha"] != EXTRACT or sheets["sha"] != WORKBOOK or manifest["scorer_revision"] != SCORER
        or manifest["reward"] != "extract_unified_value_f1"
    ):
        raise ValueError("upstream pin or scoring contract changed")
    records = manifest["tasks"]
    paths = {entry["rfilename"] for entry in meta["siblings"]}
    if any(f"tasks/{name}/{file}" not in paths for name, data in records.items() for file in data["files"]):
        raise ValueError("publisher task manifest refers to missing files")
    digests = {
        key: Counter(item["files"][key] for item in records.values())
        for key in ("environment/document.pdf", "environment/schema.json", "instruction.md", "tests/reference.test.json")
    }
    lengths = Counter(identity.split("--", 1)[0] for identity in records)
    for path, filename in (
        ("tests/verifier.py", "verifier.py"),
        ("tests/test.sh", "verifier.test.sh"),
        ("tests/Dockerfile", "verifier.Dockerfile"),
    ):
        if {item["files"][path] for item in records.values()} != {digest(text[filename])}:
            raise ValueError("shared verifier source differs from its manifest")
    archives = {
        item["path"]: {"sha256": item["lfs"]["oid"], "bytes": item["size"]}
        for item in json.loads(text["spreadsheet-tree"])
        if item["path"] in {"spreadsheetbench-v2-09-10.zip", "spreadsheetbench-v2.zip"}
    }
    if len(archives) != 2:
        raise ValueError("expected two pinned official archives")
    return {
        "schema_version": "aeep.c13.document-corpus-metadata.v1",
        "documents": document_pins,
        "case_requirements": REQUIRED,
        "extractbench": {
            "data_revision": EXTRACT, "scorer_revision": SCORER, "declared_license": meta["cardData"]["license"],
            "metadata_records": len(records), "declared_length_counts": dict(lengths),
            "digest_groups": {
                name: {"distinct": len(counts), "largest": max(counts.values()), "singletons": sum(n == 1 for n in counts.values())}
                for name, counts in digests.items()
            },
            "holdout_target_per_length_if_balanced": REQUIRED["holdout"] // 3,
            "length_balancing_possible": min(lengths.values()) >= REQUIRED["holdout"] // 3,
            "scope": "The published Harbor reward measures value F1. It omits grounding from the selected prompt.",
            "sample_assets": sample_index(text, records),
            "remaining": [
                "Verify provenance and permitted use per source, including third-party records.",
                "Bind related source documents across stages even when PDF hashes differ.",
                "Lock the offline runtime and test the original reward on an oracle, a partial output and destructive controls.",
                "Keep upstream F1 in metrics and protect expected answers and verifier feedback from task workers.",
            ],
        },
        "spreadsheetbench2": {
            "data_revision": WORKBOOK, "scorer_repository_revision": SHEET_GRADER,
            "declared_dataset_card_license": sheets["cardData"]["license"], "paper_dataset_license": "CC BY-SA 4.0",
            "archives": archives, "archive_selection": None, "asset_use_status": "conflicting declarations",
            "scope": "Offline cell evaluation covers declared ranges. Visualization uses an external model in the published harness.",
            "remaining": [
                "Resolve the data license discrepancy and identify the matching archive before acquisition.",
                "Verify pinned offline formula recalculation and preservation outside declared answer ranges.",
            ],
        },
        "locally_acquired_task_assets": 0,
        "executed_graders": 0,
        "provider_disclosures": 0,
        "new_formal_assignments": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.metadata)
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
