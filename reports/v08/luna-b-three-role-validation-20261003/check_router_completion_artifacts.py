"""Read-only lock-digest half of router-complete; no project imports or tests."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

REPORT = Path(__file__).resolve().parent
ROOT = REPORT.parents[2]
PROFILES = {"core", "openai", "marketplace_contract"}


def main() -> int:
    source = ROOT / "src/aeep/verification.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    assignment = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_CHECKS" for target in node.targets)
    )
    calls = [
        node for node in ast.walk(assignment.value)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_CheckSpec"
    ]
    selected = [tuple(ast.literal_eval(arg) for arg in call.args) for call in calls]
    selected = [item for item in selected if item[1] in PROFILES]
    artifacts = sorted({item[3] for item in selected})
    lock = json.loads((ROOT / "reports/v08/verification-lock.json").read_text(encoding="utf-8"))
    results = []
    for relative in artifacts:
        path = ROOT / relative
        expected = lock["artifacts"].get(relative)
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        results.append({"path": relative, "expected": expected, "actual": actual, "match": expected == actual})
    output = {
        "selected_check_specs": len(selected),
        "unique_test_ids": len({item[2] for item in selected}),
        "unique_locked_artifacts": len(artifacts),
        "all_match": all(item["match"] for item in results),
        "results": results,
    }
    print(json.dumps(output, sort_keys=True))
    return 0 if output["all_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
