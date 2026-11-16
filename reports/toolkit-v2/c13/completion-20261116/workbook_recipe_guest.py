"""Protected ordinary recipe for the pinned workbook recovery task."""

import base64
import binascii
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from xml.etree.ElementTree import ParseError

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from observe import Observation  # noqa: E402
from workbook_preservation import preserves_unaffected_values  # noqa: E402

INPUT_NAME = "nasa_budget_incomplete.xlsx"
OUTPUT_NAME = "nasa_budget_recovered.xlsx"
MAX_ARTIFACT = 128_000


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def output_bytes(value):
    if not isinstance(value, dict) or set(value) != {"workbook_b64"}:
        return None
    encoded = value["workbook_b64"]
    if type(encoded) is not str or len(encoded) > 4 * ((MAX_ARTIFACT + 2) // 3):
        return None
    try:
        data = base64.b64decode(encoded, validate=True)
        if not 0 < len(data) <= MAX_ARTIFACT:
            return None
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            names = {item.filename for item in entries}
            if (
                len(names) != len(entries) or len(entries) > 128
                or not {"[Content_Types].xml", "xl/workbook.xml"} <= names
                or sum(item.file_size for item in entries) > 6_000_000
                or any(item.flag_bits & 1 or item.filename.startswith(("xl/externalLinks/", "xl/vba"))
                       for item in entries)
            ):
                return None
    except (binascii.Error, zipfile.BadZipFile):
        return None
    return data


def reply(code=None):
    return {"valid": [code is None], "failure_codes": [code]}


def select(request, binding, mode):
    key = "inputs" if mode == "reference" else "examples"
    if (not isinstance(request, dict) or set(request) != {key}
            or not isinstance(request[key], list) or len(request[key]) != 1):
        raise ValueError("workbook recipe requires one reviewed task")
    item = request[key][0]
    if mode == "grade":
        if (
            not isinstance(item, dict) or set(item) != {"input", "output", "expected"}
            or item["expected"] != {"task_archive_sha256": binding["archive_sha256"]}
        ):
            raise ValueError("workbook grading truth changed")
        value, output = item["input"], item["output"]
    else:
        value, output = item, None
    if digest(value) != binding["input_digest"]:
        raise ValueError("workbook task input changed")
    return output


def classify(observed, exit_code, identities):
    collected = observed.collected
    if (
        len(collected) != 19 or len(set(collected)) != 19
        or hashlib.sha256("\n".join(collected).encode()).hexdigest() != identities
        or observed.errors or set(observed.outcomes) - {"passed", "failed"}
        or sum(observed.outcomes.values()) != 19
        or exit_code != int(bool(observed.outcomes["failed"]))
    ):
        raise ValueError("upstream verifier did not complete its reviewed checks")
    return reply("upstream_rejected") if observed.outcomes["failed"] else reply()


def run(mode, request, binding):
    if mode not in {"reference", "grade"}:
        raise ValueError("unreviewed workbook mode")
    output = select(request, binding, mode)
    raw = output_bytes(output) if mode == "grade" else None
    if mode == "grade" and raw is None:
        return reply("output_contract")
    pins = json.loads((ROOT / "pins.json").read_bytes())
    for name, identity in pins.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != identity:
            raise ValueError("protected workbook runtime file changed")
    sys.path[:0] = sorted(str(wheel) for wheel in (ROOT / "wheels").glob("*.whl"))
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ.pop("PYTEST_ADDOPTS", None)
    os.environ.pop("PYTEST_PLUGINS", None)
    with open(os.devnull, "w") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
        import openpyxl
        import pytest
        from openpyxl.utils.exceptions import InvalidFileException

        if (
            openpyxl.__version__ != "3.1.2" or pytest.__version__ != "8.4.1"
            or not all(".whl/" in str(mod.__file__) and Path(mod.__file__).is_relative_to(ROOT)
                       for mod in (openpyxl, pytest))
        ):
            raise ValueError("protected workbook parser or test runner changed")

        with tempfile.TemporaryDirectory(dir="/tmp") as scratch, chdir(scratch):
            shutil.copyfile(ROOT / INPUT_NAME, INPUT_NAME)
            output_file = Path(OUTPUT_NAME)
            if mode == "reference":
                _, body = (ROOT / "solve.sh").read_text().split("python3 << 'PYTHON'\n", 1)
                program, end = body.rsplit("\nPYTHON\n", 1)
                if end:
                    raise ValueError("upstream oracle envelope changed")
                exec(compile(program, "protected upstream oracle", "exec"), {})
                artifact = {"workbook_b64": base64.b64encode(output_file.read_bytes()).decode("ascii")}
                if output_bytes(artifact) is None:
                    raise ValueError("protected reference produced an invalid workbook")
                return {"outputs": [artifact]}
            output_file.write_bytes(raw)
            original = openpyxl.load_workbook(INPUT_NAME, keep_links=False)
            try:
                recovered = openpyxl.load_workbook(output_file, keep_links=False)
            except (InvalidFileException, ParseError, zipfile.BadZipFile, ValueError, KeyError, IndexError):
                return reply("output_contract")
            if not preserves_unaffected_values(original, recovered):
                return reply("preservation_rejected")
            observed = Observation()
            code = int(pytest.main([
                "-c", "/dev/null", "-p", "no:cacheprovider", "--rootdir", str(ROOT),
                str(ROOT / "test_outputs.py"), "-q",
            ], plugins=[observed]))
            return classify(observed, code, binding["identities_sha256"])


if __name__ == "__main__":
    if (os.geteuid(), os.getegid()) != (65534, 65534) or sys.version_info[:3] != (3, 13, 15):
        raise ValueError("protected workbook runtime identity changed")
    data = sys.stdin.buffer.read(750_001)
    if len(data) > 750_000:
        raise ValueError("ordinary workbook request exceeds its bound")
    print(json.dumps(run(sys.argv[1], json.loads(data), json.loads((ROOT / "binding.json").read_bytes()))))
