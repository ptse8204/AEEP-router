"""Run the original VAREX scorer on reference and fault outputs in private scratch."""

import copy
import importlib
import json
import os
import runpy
import sys
import tempfile
from pathlib import Path

ROLES = ("reference", "reordered", "missing_row", "missing_output", "malformed")
VERSIONS = {"numpy": "2.4.3", "scipy": "1.17.1", "rapidfuzz": "3.14.3"}


def arrange(reference):
    def tables(node, path=()):
        if isinstance(node, dict):
            for key, value in node.items():
                yield from tables(value, (*path, key))
        elif isinstance(node, list) and len(node) > 1 and node != node[::-1]:
            yield path, len(node)

    path, _ = max(tables(reference), key=lambda entry: entry[1])

    def changed(remove):
        result = copy.deepcopy(reference)
        table = result
        for key in path:
            table = table[key]
        if remove:
            del table[-1]
        else:
            table.reverse()
        return json.dumps(result, allow_nan=False)

    return {
        "reference": json.dumps(reference, allow_nan=False),
        "reordered": changed(False),
        "missing_row": changed(True),
        "missing_output": None,
        "malformed": "{",
    }


def observe(score, exclusions, folder, doc_id, case):
    reference = json.loads((folder / case["reference"]).read_bytes())
    results = {}
    for role, prediction in arrange(reference).items():
        with tempfile.TemporaryDirectory(dir="/tmp") as scratch:
            root = Path(scratch)
            if prediction is None:
                # The upstream evaluator skips entirely empty prediction directories.
                # A prediction for a different ID exercises its actual missing-document branch.
                (root / "unrelated.pred.json").write_text("{}")
            else:
                (root / f"{doc_id}.pred.json").write_text(prediction)
            grade = score("calibration", role, root, {doc_id: reference},
                          {doc_id: case["split"]}, exclusions, root)["agg"]
        results[role] = {
            "docs": grade["docs"], "fields": grade["fields"],
            "exact_match_normalized": grade["exact_match_normalized"],
            "perfect_docs": grade["perfect_docs"],
        }
    return results


def boundary(dependencies, protected):
    if os.getuid() != 65534 or os.getgid() != 65534:
        raise ValueError("protected grader identity changed")
    mounts = {row.split()[1]: set(row.split()[3].split(","))
              for row in Path("/proc/mounts").read_text().splitlines()}
    if ("noexec" not in mounts["/tmp"] or "ro" not in mounts[str(dependencies)]
            or "ro" not in mounts[str(protected)]):
        raise ValueError("protected or dependency mount is writable, or scratch is executable")
    sys.path.insert(0, str(dependencies))
    versions = {}
    for name, version in VERSIONS.items():
        module = importlib.import_module(name)
        if module.__version__ != version or not Path(module.__file__).resolve().is_relative_to(dependencies):
            raise ValueError("native scoring dependency drift")
        versions[name] = version
    return versions


def main():
    dependencies, protected = (Path(name) for name in sys.argv[1:])
    stage = "boundary"
    try:
        versions = boundary(dependencies, protected)
        stage = "load_scorer"
        payload = json.load(sys.stdin)
        scorer = runpy.run_path(str(protected / "score.py"), run_name="varex_native")
        exclusions = scorer["load_field_exclusions"](protected / "field_exclusions.json")
        stage = "grade_cases"
        output = {doc_id: observe(scorer["score_model_mode"], exclusions, protected, doc_id, case)
                  for doc_id, case in payload["cases"].items()}
    except (OSError, ValueError, ImportError, KeyError, TypeError, OverflowError) as error:
        print(json.dumps({"stage": stage, "category": type(error).__name__}))
        return
    print(json.dumps({"versions": versions, "scores": output}, allow_nan=False))


if __name__ == "__main__":
    main()
