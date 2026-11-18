"""Summarize protected ExtractBench markers with only reviewed CFPB field names.

Use inside a reviewed diagnostic scope before the grader's scratch is removed.
This reader performs no grading, calls no model, and changes no receipt.
"""

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_SHA256 = "867d30ab6d4d656810e93b69ea7524c8d5d0be528198455235dda6eed471925a"
METRIC = "extract_unified_value_f1"
MARKER_BYTES = 800_000
MAX_GROUPS = 64
INDEX = re.compile(r"\[(?:0|[1-9][0-9]{0,5})\]")
FIELD = re.compile(r"[a-z][a-z0-9_]{0,63}")


def bounded_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("expected a regular protected input")
    with path.open("rb") as source:
        raw = source.read(MARKER_BYTES + 1)
    if len(raw) > MARKER_BYTES:
        raise ValueError("protected input exceeds the reviewed bound")
    return raw


def field_names(raw_schema: bytes) -> frozenset[str]:
    if hashlib.sha256(raw_schema).hexdigest() != SCHEMA_SHA256:
        raise ValueError("public CFPB schema differs from the reviewed bytes")
    schema = json.loads(raw_schema)

    def visit(node: dict[str, Any], prefix: str):
        if "$ref" in node:
            yield from visit(schema["$defs"][node["$ref"].removeprefix("#/$defs/")], prefix)
        elif "anyOf" in node:
            for variant in node["anyOf"]:
                yield from visit(variant, prefix)
        elif "properties" in node:
            for name, child in node["properties"].items():
                if not FIELD.fullmatch(name):
                    raise ValueError("reviewed schema contains an unsupported field name")
                yield from visit(child, f"{prefix}.{name}" if prefix else name)
        elif "items" in node:
            yield from visit(node["items"], prefix + "[]")
        elif prefix and node.get("type") != "null":
            yield prefix

    return frozenset(visit(schema, ""))


def confirmed_field(raw_path: str | None, allowed: frozenset[str]) -> str | None:
    if raw_path is None:
        return None
    normalized = INDEX.sub("[]", raw_path.removeprefix("$."))
    # Return only a schema path and discard all row indices and unknown names.
    return normalized if normalized in allowed else None


def summarize(feedback: dict[str, Any], metrics: dict[str, Any], raw_schema: bytes) -> dict[str, Any]:
    allowed = field_names(raw_schema)
    if type(feedback.get("schema_version")) is not int or feedback["schema_version"] != 1:
        raise ValueError("unsupported protected feedback version")
    score = metrics.get("value_f1")
    if (type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1
            or type(metrics.get("perfect")) is not int or metrics["perfect"] != int(score == 1)):
        raise ValueError("invalid protected score markers")
    status = metrics.get("status")
    if status == feedback.get("status") == "invalid_submission":
        if score != 0 or feedback.get("cells") != []:
            raise ValueError("inconsistent invalid submission markers")
        return {"schema_version": 1, "status": status, "value_f1": score,
                "counts": None, "field_mismatches": [], "omitted_mismatches": None}
    if status != "scored" or feedback.get("status") != status:
        raise ValueError("no trustworthy scored feedback")
    if (feedback.get("path_space") != "normalized_scoring_inputs"
            or metrics.get("metrics", {}).get(METRIC) != score):
        raise ValueError("feedback and metric identity differ")

    counts = feedback.get("counts")
    cells = feedback.get("cells")
    if (not isinstance(counts, dict) or set(counts) != {"expected", "predicted", "matched"}
            or any(type(value) is not int or value < 0 for value in counts.values())
            or not counts["expected"] or not isinstance(cells, list)):
        raise ValueError("invalid protected cell counts")
    seen = dict.fromkeys(counts, 0)
    groups: Counter[tuple[str, str, str]] = Counter()
    omitted = 0
    total = counts["expected"] + counts["predicted"]
    for item in cells:
        if not isinstance(item, dict) or set(item) != {"reference_path", "output_path", "outcome", "f1_credit"}:
            raise ValueError("invalid protected cell record")
        reference, output = item["reference_path"], item["output_path"]
        if ((reference is None and output is None)
                or any(path is not None and (type(path) is not str or not 0 < len(path) <= 384)
                       for path in (reference, output))):
            raise ValueError("invalid protected path shape")
        outcome = item["outcome"]
        expected_outcomes = ({"prediction_only"} if reference is None
                             else {"reference_only"} if output is None
                             else {"value_differs", "matched"})
        if type(outcome) is not str or outcome not in expected_outcomes:
            raise ValueError("protected outcome disagrees with its two paths")
        credit = item["f1_credit"]
        if type(credit) not in (float, int) or not math.isclose(
            credit, 2 / total if outcome == "matched" else 0, rel_tol=0, abs_tol=1e-12
        ):
            raise ValueError("inconsistent protected credit")
        seen["expected"] += reference is not None
        seen["predicted"] += output is not None
        if outcome == "matched":
            seen["matched"] += 1
            continue
        reference_field = confirmed_field(reference, allowed)
        output_field = confirmed_field(output, allowed)
        if ((reference is not None and reference_field is None)
                or (output is not None and output_field is None)):
            omitted += 1
        else:
            groups[(reference_field or "", output_field or "", outcome)] += 1

    if seen != counts or not math.isclose(score, 2 * seen["matched"] / total, rel_tol=0, abs_tol=1e-12):
        raise ValueError("protected score does not reconcile to the cells")
    ordered = sorted(groups.items())
    omitted += sum(count for _, count in ordered[MAX_GROUPS:])
    return {
        "schema_version": 1,
        "status": status,
        "value_f1": score,
        "counts": counts,
        "field_mismatches": [
            {"reference_field": reference or None, "output_field": output or None,
             "outcome": outcome, "count": count}
            for (reference, output, outcome), count in ordered[:MAX_GROUPS]
        ],
        "omitted_mismatches": omitted,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("schema", "metrics", "feedback"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    result = summarize(json.loads(bounded_file(args.feedback)), json.loads(bounded_file(args.metrics)),
                       bounded_file(args.schema))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
