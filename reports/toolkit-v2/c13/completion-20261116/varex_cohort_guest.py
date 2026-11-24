"""Exercise the native VAREX grader on protected references and fixed rejection controls."""

import copy
import json
import runpy
import sys
import tempfile
from pathlib import Path

ROLES = ("reference", "missing_field", "missing_output", "malformed")


def branches(node, path=()):
    if isinstance(node, dict):
        for name, child in sorted(node.items()):
            yield (*path, name)
            yield from branches(child, (*path, name))


def missing_field(reference, scored):
    # A list is treated as a branch. Deleting one occurrence could change the
    # upstream array alignment before it exercises a missing scoreable field.
    for parts in sorted(branches(reference), key=lambda item: (-len(item), item)):
        parent = ".".join(parts)
        if not any(key == parent or key.startswith((parent + ".", parent + "[")) for key in scored):
            continue
        modified = copy.deepcopy(reference)
        node = modified
        for part in parts[:-1]:
            node = node[part]
        del node[parts[-1]]
        return modified
    raise ValueError("no scoreable field can be removed")


def observe(scorer, exclusions, folder, case, label):
    import jsonschema

    reference = json.loads((folder / case["reference"]).read_bytes())
    schema = json.loads((folder / case["schema"]).read_bytes())
    schema_validator = jsonschema.validators.validator_for(schema)
    schema_valid = False
    try:
        schema_validator.check_schema(schema)
        schema_valid = schema_validator(schema).is_valid(reference)
    except jsonschema.exceptions.SchemaError:
        pass
    fields = {
        key for key, value in scorer["flatten"](reference).items()
        if value not in (None, "", []) and key not in exclusions.get(label, set())
    }
    if not fields:
        return {"schema_valid": schema_valid, "scoreable_fields": 0, "status": "no_scoreable_fields"}
    predictions = {
        "reference": json.dumps(reference, allow_nan=False),
        "missing_field": json.dumps(missing_field(reference, fields), allow_nan=False),
        "missing_output": None, "malformed": "{",
    }
    results = {}
    for role, content in predictions.items():
        with tempfile.TemporaryDirectory(dir="/tmp") as scratch:
            root = Path(scratch)
            if content is None:
                (root / "other.pred.json").write_text("{}")
            else:
                (root / f"{label}.pred.json").write_text(content)
            outcome = scorer["score_model_mode"](
                "local", role, root, {label: reference}, {label: case["split"]}, exclusions, root,
            )
        if outcome is None:
            return {"schema_valid": schema_valid, "scoreable_fields": len(fields), "status": "missing_scorer_result"}
        row = outcome["agg"]
        if row["docs"] != 1 or row["fields"] != len(fields):
            return {"schema_valid": schema_valid, "scoreable_fields": len(fields), "status": "scorer_population_changed"}
        results[role] = row["exact_match_normalized"]
    return {"schema_valid": schema_valid, "scoreable_fields": len(fields), "status": "observed", "scores": results}


def main():
    dependencies, protected = (Path(value) for value in sys.argv[1:])
    boundary = runpy.run_path(str(protected / "guest_boundary.py"))["boundary"]
    versions = boundary(dependencies, protected)
    import jsonschema

    if not Path(jsonschema.__file__).resolve().is_relative_to(dependencies):
        raise ValueError("schema validation used an unreviewed dependency")
    scorer = runpy.run_path(str(protected / "score.py"), run_name="varex_native")
    exclusions = scorer["load_field_exclusions"](protected / "field_exclusions.json")
    result = {}
    for label, case in json.load(sys.stdin)["cases"].items():
        if Path(label).name != label:
            raise ValueError("case ID escapes the scratch directory")
        try:
            result[label] = observe(scorer, exclusions, protected, case, label)
        except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError) as error:
            result[label] = {"status": "case_error", "category": type(error).__name__}
    print(json.dumps({"versions": versions, "cases": result}, allow_nan=False))


if __name__ == "__main__":
    main()
