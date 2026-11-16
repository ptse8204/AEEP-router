"""Run the exact published assertions in a protected, disposable source tree."""

import hashlib
import json
import os
import re
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class Observation:
    def __init__(self) -> None:
        self.nodes: list[str] = []
        self.statuses: dict[str, str] = {}
        self.errors = 0
        self.failure_categories: dict[str, int] = {}

    def pytest_collection_finish(self, session) -> None:
        self.nodes = [item.nodeid for item in session.items]

    def pytest_runtest_logreport(self, report) -> None:
        if report.when == "call":
            self.statuses[report.nodeid] = "xfail" if hasattr(report, "wasxfail") else report.outcome
        elif report.failed or report.skipped:
            self.errors += 1
        if report.failed:
            lines = re.findall(r"(?m)^E\s+([A-Za-z][A-Za-z0-9_]*(?:Error|Exception)):", report.longreprtext)
            key = lines[-1] if lines else "UnclassifiedFailure"
            self.failure_categories[key] = self.failure_categories.get(key, 0) + 1


def main(phase: str, bootstrap: str) -> None:
    pins = json.loads((ROOT / "protected-inputs.json").read_bytes())
    packages = ROOT / "support"
    sys.path[:0] = [bootstrap, str(packages)]
    from aeep.assessment.repository_suites import archive_files

    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ.pop("PYTEST_ADDOPTS", None)
    os.environ.pop("PYTEST_PLUGINS", None)
    roles = ["original", "protected_tests"]
    if phase == "reference":
        roles.append("protected_reference")
    elif phase != "original":
        raise ValueError("unreviewed fixture role")
    files = {}
    for role in roles:
        meta = pins["assets"][role]
        payload = (ROOT / meta["file"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != meta["sha256"]:
            raise ValueError("protected fixture changed")
        files.update(archive_files(payload))
    expected = pins["test_selectors"]
    nodes = expected["fail_to_pass"] + expected["pass_to_pass"]
    if len(nodes) != 15 or len(set(nodes)) != len(nodes):
        raise ValueError("published test identities changed")
    with tempfile.TemporaryDirectory(dir="/tmp") as directory:
        target = Path(directory)
        scratch_home = target / ".fixture-home"
        scratch_home.mkdir()
        os.environ.update({
            "HOME": str(scratch_home),
            "XDG_CONFIG_HOME": str(scratch_home / "config"),
            "XDG_CACHE_HOME": str(scratch_home / "cache"),
            "XDG_DATA_HOME": str(scratch_home / "data"),
        })
        for name, data in files.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        os.chdir(target)
        sys.path.insert(0, str(target))
        with open(os.devnull, "w") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
            import pytest

            observer = Observation()
            code = int(pytest.main(["-p", "no:cacheprovider", "-q", *nodes], plugins=[observer]))
    counts = {status: sorted(node for node in observer.statuses if observer.statuses[node] == status)
              for status in ("passed", "failed")}
    exact = sorted(set(observer.nodes)) == sorted(nodes) and len(observer.nodes) == len(nodes)
    passed = counts["passed"] == sorted(nodes if phase == "reference" else expected["pass_to_pass"])
    failures = counts["failed"] == ([] if phase == "reference" else sorted(expected["fail_to_pass"]))
    print(json.dumps({
        "role": phase, "exit_code": code, "exact_test_identities": exact,
        "collected": len(observer.nodes), "passed": len(counts["passed"]),
        "failed": len(counts["failed"]), "setup_and_teardown_errors": observer.errors,
        "failure_categories": observer.failure_categories,
        "expected_outcome": exact and passed and failures and not observer.errors
        and code == (0 if phase == "reference" else 1),
    }))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
