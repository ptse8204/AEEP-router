"""Run exact A2A transport assertions in an isolated, disposable checkout."""

import hashlib
import json
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class Observation:
    def __init__(self):
        self.collected = []
        self.outcomes = {}
        self.unexpected = 0

    def pytest_collection_finish(self, session):
        self.collected = [item.nodeid for item in session.items]

    def pytest_runtest_logreport(self, report):
        if report.when != "call":
            self.unexpected += int(report.outcome != "passed")
            return
        if report.nodeid in self.outcomes or getattr(report, "wasxfail", None):
            self.unexpected += 1
        self.outcomes[report.nodeid] = report.outcome
        if report.failed and "does not support the asynchronous context manager protocol" not in report.longreprtext:
            self.unexpected += 1


def passed(role, failures, preservation, observed, code):
    expected = {node: "passed" for node in [*failures, *preservation]}
    if role == "original":
        expected.update({node: "failed" for node in failures})
    return (
        role in {"reference", "original"}
        and sorted(observed.collected) == sorted(expected)
        and observed.outcomes == expected
        and not observed.unexpected
        and code == (0 if role == "reference" else 1)
    )


def main(role):
    expected = json.loads((ROOT / "required.json").read_bytes())
    failures, preservation = expected["fail_to_pass"], expected["pass_to_pass"]
    if len(failures) != 2 or len(preservation) != 5 or len(set(failures + preservation)) != 7:
        raise ValueError("required test scope drift")
    if role not in {"reference", "original"} or sys.version_info[:3] != (3, 13, 15):
        raise ValueError("unexpected protected role or interpreter")
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ.pop("PYTEST_ADDOPTS", None)
    os.environ.pop("PYTEST_PLUGINS", None)
    with tempfile.TemporaryDirectory(dir="/tmp") as scratch:
        target = Path(scratch)
        trees = ("source", "tests", "reference") if role == "reference" else ("source", "tests")
        for tree in trees:
            parent = ROOT / tree
            for source in parent.rglob("*"):
                if source.is_file():
                    path = target / source.relative_to(parent)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(source.read_bytes())
        home = target / ".fixture-home"
        home.mkdir()
        os.environ["HOME"] = str(home)
        os.chdir(target)
        sys.path[:0] = [str(target / "src"), str(ROOT / "support")]
        observed = Observation()
        with open(os.devnull, "w") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
            import pytest

            code = int(pytest.main(["-p", "no:cacheprovider", "-p", "pytest_asyncio.plugin",
                "-o", "addopts=-ra --strict-markers", "-q", *failures, *preservation], plugins=[observed]))
            module = sys.modules.get("a2a.client.base_client")
            plugin = sys.modules.get("pytest_asyncio.plugin")
            from_checkout = module is not None and Path(module.__file__).is_relative_to(target / "src")
            from_support = plugin is not None and all(Path(m.__file__).is_relative_to(ROOT / "support")
                                                      for m in (pytest, plugin))
    print(json.dumps({"role": role, "verified": from_checkout and from_support and
        passed(role, failures, preservation, observed, code), "exit_code": code,
        "collected": len(observed.collected), "identity_digest": hashlib.sha256(
            "\n".join(sorted(observed.collected)).encode()).hexdigest(),
        "test_outcomes": observed.outcomes, "unexpected_phases_or_failures": observed.unexpected}))


if __name__ == "__main__":
    main(sys.argv[1])
