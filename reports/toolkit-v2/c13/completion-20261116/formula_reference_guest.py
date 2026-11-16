"""Run the selected protected formula role in a disposable Chromium container."""

import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class Observation:
    def __init__(self):
        self.identities = []
        self.outcomes = {}
        self.renderer_timeouts = set()
        self.unexpected = 0

    def pytest_collection_finish(self, session):
        self.identities = [item.nodeid for item in session.items]

    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            if report.nodeid in self.outcomes or hasattr(report, "wasxfail"):
                self.unexpected += 1
            self.outcomes[report.nodeid] = report.outcome
        elif report.outcome != "passed":
            if report.when == "setup" and report.failed:
                self.outcomes[report.nodeid] = "error"
                if "TimeoutError" in report.longreprtext:
                    self.renderer_timeouts.add(report.nodeid)
            else:
                self.unexpected += 1


def classify(defined, role, observed, exit_code):
    identities = defined["identities"]
    expected = {node: "passed" for node in identities}
    policy = defined["roles"][role]
    expected.update({node: "failed" for node in policy["must_fail"]})
    errors = set()
    if policy["infrastructure_failure"]:
        errors.add(policy["affected_test"])
        expected[policy["affected_test"]] = "error"
    correct = (len(identities) == len(set(identities)) == 7
        and sorted(observed.identities) == sorted(identities)
        and observed.outcomes == expected and observed.renderer_timeouts == errors
        and observed.unexpected == 0 and exit_code == (0 if role == "reference" else 1))
    grade = None if not correct or policy["infrastructure_failure"] else int(role == "reference")
    return correct, grade


def main(role):
    if (os.geteuid(), os.getegid()) != (65534, 65534) or sys.version_info[:2] != (3, 12):
        raise ValueError("protected identity or interpreter does not match the reviewed renderer")
    fixtures = ROOT / "protected-fixtures"
    lock = json.loads((fixtures / "protected-fixture-lock.json").read_bytes())
    policy = lock["roles"][role]
    support = ROOT / "support"
    sys.path.insert(0, str(support))
    os.environ.update({"PLAYWRIGHT_BROWSERS_PATH": str(ROOT / "browsers"),
                       "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
    os.environ.pop("PYTEST_ADDOPTS", None)
    os.environ.pop("PYTEST_PLUGINS", None)
    with tempfile.TemporaryDirectory(dir="/tmp") as scratch:
        target = Path(scratch)
        os.chdir(target)
        os.environ["HOME"] = str(target)
        for name in ("latex_paper.pdf", "test_outputs.py"):
            shutil.copyfile(fixtures / name, target / name)
        if not policy.get("omit_local_mathjax"):
            shutil.copyfile(fixtures / "tex-svg.js", target / "tex-svg.js")
        artifact = role + ".md" if role in {"wrong-value", "incomplete"} else "reference.md"
        shutil.copyfile(fixtures / artifact, target / "latex_formula_extraction.md")
        observed = Observation()
        with open(os.devnull, "w") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
            import PIL
            import playwright
            import pytest

            if (not all(Path(mod.__file__).is_relative_to(support) for mod in (playwright, pytest, PIL))
                    or version("playwright") != "1.57.0" or PIL.__version__ != "10.4.0"
                    or pytest.__version__ != "8.4.1"):
                raise ValueError("protected runtime resolved an unreviewed dependency")
            code = int(pytest.main(["-q", "-c", "/dev/null", "--rootdir", str(target),
                                    "-p", "no:cacheprovider", str(target / "test_outputs.py")],
                                   plugins=[observed]))
    correct, grade = classify(lock, role, observed, code)
    print(json.dumps({"role": role, "verified_role": correct, "grade": grade,
        "exit_code": code, "collected": len(observed.identities), "outcomes": observed.outcomes,
        "unexpected_count": observed.unexpected, "renderer_timeout_count": len(observed.renderer_timeouts)}))


if __name__ == "__main__":
    main(sys.argv[1])
