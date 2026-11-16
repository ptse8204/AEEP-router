"""Run the frozen workbook reference or control in a protected verifier guest."""

import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class Observation:
    def __init__(self) -> None:
        self.collected = []
        self.outcomes = Counter()
        self.errors = 0

    def pytest_collection_finish(self, session) -> None:
        self.collected = [item.nodeid for item in session.items]

    def pytest_runtest_logreport(self, report) -> None:
        if report.when == "call":
            self.outcomes["xfail" if hasattr(report, "wasxfail") else report.outcome] += 1
        elif report.skipped:
            self.outcomes["skipped"] += 1
        elif report.failed:
            self.errors += 1


def verify(phase: str) -> dict:
    from contextlib import redirect_stderr, redirect_stdout

    wheels = list((ROOT / "wheels").glob("*.whl"))
    sys.path[:0] = sorted(str(wheel) for wheel in wheels)
    pins = json.loads((ROOT / "pins.json").read_bytes())
    for name, digest in pins.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError("protected guest asset drift")
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ.pop("PYTEST_ADDOPTS", None)
    os.environ.pop("PYTEST_PLUGINS", None)
    with open(os.devnull, "w") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
        import openpyxl
        import pytest

        if openpyxl.__version__ != "3.1.2" or pytest.__version__ != "8.4.1":
            raise ValueError("protected verifier dependency drift")
        if not all(".whl/" in str(module.__file__) for module in (openpyxl, pytest)):
            raise ValueError("protected verifier dependency origin drift")

        original = Path.cwd()
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            os.chdir(tmp)
            try:
                source = Path("nasa_budget_incomplete.xlsx")
                result = Path("nasa_budget_recovered.xlsx")
                shutil.copyfile(ROOT / source, source)
                if phase == "reference":
                    oracle = (ROOT / "solve.sh").read_text()
                    _, body = oracle.split("python3 << 'PYTHON'\n", 1)
                    python, end = body.rsplit("\nPYTHON\n", 1)
                    if end:
                        raise ValueError("upstream oracle envelope changed")
                    exec(compile(python, "protected upstream oracle", "exec"), {})
                elif phase == "incomplete":
                    shutil.copyfile(source, result)
                elif phase == "invalid":
                    result.write_bytes(b"not a workbook")
                elif phase != "missing":
                    raise ValueError("unknown protected verifier phase")

                observed = Observation()
                exit_code = int(pytest.main([
                    "-c", "/dev/null", "-p", "no:cacheprovider", "--rootdir", str(ROOT),
                    str(ROOT / "test_outputs.py"), "-q",
                ], plugins=[observed]))
            finally:
                os.chdir(original)
    return {"phase": phase, "exit_code": exit_code, "collected": len(observed.collected),
            "distinct": len(set(observed.collected)),
            "identity_sha256": hashlib.sha256("\n".join(observed.collected).encode()).hexdigest(),
            "passed": observed.outcomes["passed"], "failed": observed.outcomes["failed"],
            "skipped": observed.outcomes["skipped"], "xfail": observed.outcomes["xfail"],
            "errors": observed.errors}


if __name__ == "__main__":
    print(json.dumps(verify(sys.argv[1])))
