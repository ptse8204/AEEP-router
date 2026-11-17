"""Bridge one protected ExtractBench observation to the v7 recipe reply."""

import argparse
import base64
import binascii
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path("/opt/aeep-extractbench")
OUTPUT_FIELD = "prediction_b64"
FAILURES = ("invalid_submission", "inexact_extraction")
MAX_PREDICTION = 200_000
MAX_ENCODED_PREDICTION = 4 * ((MAX_PREDICTION + 2) // 3)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def native_reply(observation):
    score = observation["value_f1"]
    perfect = observation["perfect"]
    status = observation["status"]
    if (
        type(observation["exit_code"]) is not int
        or observation["exit_code"] != 0
        or status not in ("scored", "invalid_submission")
        or type(score) not in (int, float)
        or not 0 <= score <= 1
        or type(perfect) is not int
        or perfect != int(score == 1)
        or (status == "invalid_submission" and score != 0)
    ):
        raise ValueError("ExtractBench verifier did not return a trustworthy task score")
    code = None if perfect else "invalid_submission" if status == "invalid_submission" else "inexact_extraction"
    return {"valid": [bool(perfect)], "failure_codes": [code], "quality_scores": [score]}


def prediction_bytes(output):
    if not isinstance(output, dict) or set(output) != {OUTPUT_FIELD}:
        return None
    encoded = output[OUTPUT_FIELD]
    if type(encoded) is not str or len(encoded) > MAX_ENCODED_PREDICTION:
        return None
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except binascii.Error:
        return None
    return decoded if len(decoded) <= MAX_PREDICTION else None


def evaluate(mode, request, bindings, root, observe):
    key = "examples" if mode == "grade" else "inputs"
    if set(request) != {key} or not isinstance(request[key], list) or len(request[key]) != 1:
        raise ValueError("expected a single reviewed ExtractBench case")
    record = request[key][0]
    if mode == "grade" and set(record) != {"input", "output", "expected"}:
        raise ValueError("unexpected ExtractBench grading fields")
    value = record["input"] if mode == "grade" else record
    identity = digest(value)
    binding = bindings[identity]
    if mode == "grade" and record["expected"] != {"input_sha256": identity}:
        raise ValueError("protected truth does not match the input")
    case_id = binding["case"]
    if not isinstance(case_id, str) or Path(case_id).name != case_id or case_id in (".", ".."):
        raise ValueError("protected case escaped the reviewed assets")
    support = root / "cases" / case_id
    reference = support / "verifier/reference.test.json"
    paths = {"reference": reference, "oracle": support / "controls/oracle.json"}
    verified = {}
    for role, path in paths.items():
        if not path.is_file() or any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError("protected ExtractBench input is missing")
        with path.open("rb") as stream:
            data = stream.read(800_001)
        if len(data) > 800_000 or hashlib.sha256(data).hexdigest() != binding[role + "_sha256"]:
            raise ValueError("protected ExtractBench input changed")
        verified[role] = data
    if mode == "reference":
        if len(verified["oracle"]) > MAX_PREDICTION:
            raise ValueError("protected reference exceeds the reviewed output bound")
        return {"outputs": [{OUTPUT_FIELD: base64.b64encode(verified["oracle"]).decode("ascii")}]}
    prediction = prediction_bytes(record["output"])
    with tempfile.TemporaryDirectory(prefix="extractbench-recipe-", dir="/tmp") as directory:
        work = Path(directory)
        destination = work / "output.json"
        if prediction is not None:
            destination.write_bytes(prediction)
        return native_reply(observe(support, root / "site", destination, reference, work))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("reference", "grade"))
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    from extractbench_harbor_observer import run_case

    bindings = json.loads((ROOT / "bindings.json").read_bytes())
    value = evaluate(args.mode, json.load(sys.stdin), bindings, ROOT, run_case)
    print(json.dumps(value, allow_nan=False))


if __name__ == "__main__":
    main()
