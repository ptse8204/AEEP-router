"""Observe the original Harbor verifier in an offline, reviewed grader mount."""

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

METRIC = "extract_unified_value_f1"
SCORE_LIMIT = 800_000
MARKERS = {"metrics.json", "reward.txt", "feedback.json"}
# The child executes the path-adapted upstream verifier with its normal CLI.
BOOTSTRAP = (
    "import runpy, sys; "
    "source, deps, verifier, *options = sys.argv[1:]; "
    "sys.path[:0] = [deps, source]; sys.argv[:] = [verifier, *options]; "
    "runpy.run_path(verifier, run_name='__main__')"
)


def bounded_bytes(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError("verifier marker is missing or is not a regular file")
    with path.open("rb") as stream:
        data = stream.read(SCORE_LIMIT + 1)
    if len(data) > SCORE_LIMIT:
        raise ValueError("verifier marker exceeds the protected bound")
    return data


def score_number(value):
    if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("invalid native score")
    return float(value)


def observe_markers(folder, exit_code):
    if exit_code != 0:
        if any((folder / name).exists() or (folder / name).is_symlink() for name in MARKERS):
            raise ValueError("failed verifier left ambiguous scoring artifacts")
        return {"status": "infrastructure_error", "value_f1": None, "perfect": None}
    raw = json.loads(bounded_bytes(folder / "metrics.json"))
    feedback = json.loads(bounded_bytes(folder / "feedback.json"))
    native_reward = score_number(raw["value_f1"])
    if score_number(float(bounded_bytes(folder / "reward.txt"))) != native_reward:
        raise ValueError("native reward and metrics disagree")
    if type(raw["perfect"]) is not int or raw["perfect"] != int(native_reward == 1.0):
        raise ValueError("native binary indicator disagrees with value F1")
    status = raw["status"]
    if feedback["schema_version"] != 1:
        raise ValueError("unsupported feedback version")
    if status == "invalid_submission":
        if native_reward != 0.0 or feedback["status"] != status or feedback["cells"]:
            raise ValueError("invalid submission has inconsistent score markers")
        return {"status": status, "value_f1": native_reward, "perfect": raw["perfect"]}
    if status != "scored" or feedback["status"] != "scored" or score_number(raw["metrics"][METRIC]) != native_reward:
        raise ValueError("unexpected native score contract")
    counts = feedback["counts"]
    if (set(counts) != {"expected", "predicted", "matched"}
            or any(type(value) is not int or value < 0 for value in counts.values())
            or not counts["expected"] or counts["matched"] > min(counts["expected"], counts["predicted"])):
        raise ValueError("invalid native feedback counts")
    # Retain the upstream counts alongside the score while withholding paths and cells.
    return {"status": status, "value_f1": native_reward, "perfect": raw["perfect"], "counts": counts}


def run_case(source, dependencies, prediction, reference, work):
    log = work / "score"
    log.mkdir(mode=0o700)
    wait = subprocess.run([
        sys.executable, "-I", "-S", "-B", "-c", BOOTSTRAP,
        str(source), str(dependencies), str(source / "verifier/harbor_on_carrier.py"),
        "--test-json", str(reference), "--prediction", str(prediction), "--log-dir", str(log),
    ], cwd=work, env={
        "HOME": str(work), "LC_ALL": "C", "PATH": os.defpath,
        "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
    }, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=25, check=False)
    return {"exit_code": wait.returncode, **observe_markers(log, wait.returncode)}


def local_input(root, filename, absent):
    if filename is None:
        return absent
    if Path(filename).name != filename or filename in {".", ".."}:
        raise ValueError("grader input escaped its protected directory")
    path = root / filename
    if not path.is_file() or path.is_symlink():
        raise ValueError("reviewed grader input is unavailable")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--support", type=Path, required=True)
    parser.add_argument("--dependencies", type=Path, required=True)
    args = parser.parse_args()
    request = json.load(sys.stdin)
    if set(request) != {"roles"} or len(request["roles"]) != 7:
        raise ValueError("expected the seven reviewed verifier roles")
    results = {}
    with tempfile.TemporaryDirectory(prefix="extractbench-grader-") as temporary:
        for index, (role, data) in enumerate(request["roles"].items()):
            if set(data) != {"prediction", "reference"}:
                raise ValueError("unexpected grader argument")
            directory = Path(temporary) / str(index)
            directory.mkdir(mode=0o700)
            prediction = local_input(args.support / "controls", data["prediction"], directory / "unavailable-output")
            reference = local_input(args.support / "verifier", data["reference"], directory / "unavailable-reference")
            try:
                results[role] = run_case(args.support, args.dependencies, prediction, reference, directory)
            except subprocess.TimeoutExpired:
                results[role] = {"status": "timeout", "value_f1": None, "perfect": None, "exit_code": None}
    print(json.dumps({"metric": METRIC, "observations": results}, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
