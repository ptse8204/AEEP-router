"""Observe the exact pytest scope of one protected repository fixture."""

import hashlib
import json
import os
import runpy
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SHARED = Path(__file__).resolve().parent


def valid_observation(binding, observed, exit_code, statuses, unexpected_failure):
    expected = binding["outcomes"]
    return (
        len(observed) == len(expected)
        and set(observed) == expected.keys()
        and statuses == expected
        and exit_code == binding["exit_code"]
        and not unexpected_failure
    )


def main(directory, bootstrap):
    role_dir = Path(directory)
    binding = json.loads((role_dir / "binding.json").read_bytes())
    if (os.geteuid(), os.getegid()) != (65534, 65534) or sys.version_info[:3] != (3, 13, 15):
        raise ValueError("unexpected repository grader identity")
    sys.path[:0] = [str(SHARED / "support"), bootstrap]
    from aeep.assessment.repository_suites import archive_files

    archive = (role_dir / "fixture.tar.gz").read_bytes()
    if hashlib.sha256(archive).hexdigest() != binding["archive_sha256"]:
        raise ValueError("protected repository fixture changed")
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ.pop("PYTEST_ADDOPTS", None)
    os.environ.pop("PYTEST_PLUGINS", None)
    Capture = runpy.run_path(str(SHARED / "capture.py"))["NativeCapture"]

    class CaptureWithFailureCheck(Capture):
        unexpected_failure = False

        def pytest_runtest_logreport(self, report):
            super().pytest_runtest_logreport(report)
            signature = binding.get("required_original_failure")
            if (
                signature
                and report.when == "call"
                and report.failed
                and signature not in report.longreprtext
            ):
                self.unexpected_failure = True

    with tempfile.TemporaryDirectory(dir="/tmp") as workspace:
        target = Path(workspace)
        for name, data in archive_files(archive, large=True).items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        os.environ["HOME"] = workspace
        observe = CaptureWithFailureCheck()
        with open(os.devnull, "w") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
            import pytest
            import pytest_asyncio.plugin

            if (
                pytest.__version__ != "8.4.1"
                or "a2a" in sys.modules
                or any(
                    not Path(module.__file__).is_relative_to(SHARED / "support")
                    for module in (pytest, pytest_asyncio.plugin)
                )
            ):
                raise ValueError("unexpected pytest runtime or preloaded source")
            os.chdir(target)
            sys.path[:0] = [str(target / "src"), str(target)]
            opts = [
                "-p",
                "no:cacheprovider",
                "-o",
                "addopts=-ra --strict-markers",
                "--rootdir",
                workspace,
                "-q",
                *binding["outcomes"],
            ]
            code = int(pytest.main(opts, plugins=[pytest_asyncio.plugin, observe]))
            statuses = observe.export()["statuses"]
            loaded = sys.modules.get("a2a")
            correct_source = loaded is not None and Path(loaded.__file__).is_relative_to(
                target / "src"
            )
    print(
        json.dumps(
            {
                "case_id": binding["case_id"],
                "role": binding["role"],
                "exit_code": code,
                "collected": len(observe.selected_ids),
                "statuses": statuses,
                "source_verified": correct_source,
                "archive_sha256": binding["archive_sha256"],
                "passed": correct_source
                and valid_observation(
                    binding, observe.selected_ids, code, statuses, observe.unexpected_failure
                ),
            }
        )
    )


if __name__ == "__main__":
    main(*sys.argv[1:])
