"""Grade the reviewed WASDE tables with the ordinary document recipe envelope."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extractbench_recipe_guest import encode, evaluate


def unique_members(pairs):
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError("duplicate JSON properties")
    return value


def reject_constant(_name):
    raise ValueError("non-finite JSON value")


def strict_json(body):
    return json.loads(
        body.decode("utf-8"),
        object_pairs_hook=unique_members,
        parse_constant=reject_constant,
    )


def exact_match(_support, _dependencies, prediction, reference, _work):
    expected = encode(strict_json(reference.read_bytes()))
    try:
        actual = encode(strict_json(prediction.read_bytes()))
    except (FileNotFoundError, ValueError, RecursionError):
        return {"exit_code": 0, "status": "invalid_submission", "value_f1": 0.0, "perfect": 0}
    passed = int(expected == actual)
    # The envelope carries a binary score. No ExtractBench metric runs here.
    return {"exit_code": 0, "status": "scored", "value_f1": float(passed), "perfect": passed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("reference", "grade"))
    parser.add_argument("--support", required=True, type=Path)
    args = parser.parse_args()
    root = args.support
    binding_path = root / "bindings.json"
    if root.resolve() != root or binding_path.is_symlink():
        raise ValueError("protected binding path changed")
    bindings = strict_json(binding_path.read_bytes())
    body = sys.stdin.buffer.read(600_001)
    if len(body) > 600_000:
        raise ValueError("protected recipe request exceeds the reviewed bound")
    result = evaluate(args.mode, strict_json(body), bindings, root, exact_match)
    print(encode(result).decode("ascii"))


if __name__ == "__main__":
    main()
