"""Ordinary protected Formula Extraction reference and Markdown grading command."""

import base64
import binascii
import hashlib
import json
import os
import shutil
import sys
from contextlib import chdir, redirect_stderr, redirect_stdout
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "protected-fixtures"
OUTPUT = "latex_formula_extraction.md"
MAX_ARTIFACT = 32_768
MAX_ENCODED = 4 * ((MAX_ARTIFACT + 2) // 3)


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def response(code=None):
    return {"valid": [code is None], "failure_codes": [code]}


def select(request, binding, mode):
    key = {"reference": "inputs", "grade": "examples"}[mode]
    if (
        not isinstance(request, dict)
        or set(request) != {key}
        or not isinstance(request[key], list)
        or len(request[key]) != 1
    ):
        raise ValueError("the formula recipe requires one bound task")
    entry = request[key][0]
    if mode == "grade":
        if (
            not isinstance(entry, dict)
            or set(entry) != {"input", "output", "expected"}
            or entry["expected"] != {"task_archive_sha256": binding["archive_sha256"]}
        ):
            raise ValueError("formula grading truth changed")
        value, output = entry["input"], entry["output"]
    else:
        value, output = entry, None
    if digest(value) != binding["input_digest"]:
        raise ValueError("formula task input changed")
    return output


def markdown_bytes(value):
    if not isinstance(value, dict) or set(value) != {"markdown_b64"}:
        return None
    encoded = value["markdown_b64"]
    if type(encoded) is not str or len(encoded) > MAX_ENCODED:
        return None
    try:
        data = base64.b64decode(encoded, validate=True)
        data.decode("utf-8")
    except (binascii.Error, UnicodeError):
        return None
    if not 0 < len(data) <= MAX_ARTIFACT or b"\0" in data:
        return None
    return data


def classify(expected, observation, exit_code):
    if (
        len(expected) != 7
        or len(set(expected)) != 7
        or sorted(observation.identities) != sorted(expected)
        or set(observation.outcomes) != set(expected)
        or set(observation.outcomes.values()) - {"passed", "failed"}
        or observation.renderer_timeouts
        or observation.unexpected
        or exit_code != int("failed" in observation.outcomes.values())
    ):
        raise ValueError("protected formula verifier did not complete all seven checks")
    return response("upstream_rejected") if exit_code else response()


def observe(data, identities):
    # The original observer remains byte-identical in this image.
    sys.path.insert(0, str(ROOT))
    from guest import Observation

    support = ROOT / "support"
    sys.path.insert(0, str(support))
    os.environ.update(
        PLAYWRIGHT_BROWSERS_PATH=str(ROOT / "browsers"),
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
    )
    os.environ.pop("PYTEST_ADDOPTS", None)
    os.environ.pop("PYTEST_PLUGINS", None)
    with TemporaryDirectory(dir="/tmp") as scratch, chdir(scratch):
        os.environ["HOME"] = scratch
        for name in ("latex_paper.pdf", "tex-svg.js", "test_outputs.py"):
            shutil.copyfile(FIXTURES / name, name)
        Path(OUTPUT).write_bytes(data)
        observation = Observation()
        with open(os.devnull, "w") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
            import PIL
            import playwright
            import pytest

            if (
                sys.version_info[:2] != (3, 12)
                or not all(
                    Path(module.__file__).is_relative_to(support)
                    for module in (playwright, pytest, PIL)
                )
                or version("playwright") != "1.57.0"
                or PIL.__version__ != "10.4.0"
                or pytest.__version__ != "8.4.1"
            ):
                raise ValueError("protected formula renderer dependency changed")
            code = int(
                pytest.main(
                    [
                        "-q",
                        "-c",
                        "/dev/null",
                        "--rootdir",
                        scratch,
                        "-p",
                        "no:cacheprovider",
                        str(Path(scratch) / "test_outputs.py"),
                    ],
                    plugins=[observation],
                )
            )
    return classify(identities, observation, code)


def run(mode, request, binding):
    output = select(request, binding, mode)
    if mode == "reference":
        data = (FIXTURES / "reference.md").read_bytes()
        if hashlib.sha256(data).hexdigest() != binding["reference_sha256"]:
            raise ValueError("protected reference output changed")
        return {"outputs": [{"markdown_b64": base64.b64encode(data).decode("ascii")}]}
    data = markdown_bytes(output)
    if data is None:
        return response("output_contract")
    return observe(data, binding["identities"])


if __name__ == "__main__":
    if (os.geteuid(), os.getegid()) != (65534, 65534):
        raise ValueError("protected formula command requires its nonroot worker")
    print(
        json.dumps(
            run(
                sys.argv[1],
                json.load(sys.stdin),
                json.loads((ROOT / "ordinary-binding.json").read_bytes()),
            )
        )
    )
