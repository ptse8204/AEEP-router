"""Observe original economic-task assertions and a separate precision rule."""

import hashlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IDS = (
    "test_answer_file_exists",
    "test_answer_format",
    "test_answer_is_valid_number",
    "test_correlation_value_correct",
)
_FORMAT = re.compile(rb"-?[01]\.[0-9]{5}")


def precise_answer(answer: bytes | None, expected: Decimal) -> bool:
    if answer is None or len(answer) > 128:
        return False
    value = answer.strip(b" \r\n\t")
    if _FORMAT.fullmatch(value) is None:
        return False
    number = Decimal(value.decode("ascii"))
    return -1 <= number <= 1 and number == expected


class Observation(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.passes = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passes.append(test)


def observe(verifier: Path, answer: bytes | None, expected: Decimal) -> dict:
    """Invoke one exact unittest module in disposable scratch. Caller owns isolation."""
    with tempfile.TemporaryDirectory(prefix="economic-grade-", dir="/tmp") as directory:
        scratch = Path(directory)
        if answer is not None:
            (scratch / "answer.txt").write_bytes(answer)
        with (
            chdir(scratch),
            io.StringIO() as hidden,
            redirect_stdout(hidden),
            redirect_stderr(hidden),
        ):
            spec = spec_from_file_location("protected_economic_verifier", verifier)
            if spec is None or spec.loader is None:
                raise ValueError("protected verifier entry point was unavailable")
            module = module_from_spec(spec)
            spec.loader.exec_module(module)
            suite = unittest.TestLoader().loadTestsFromTestCase(module.TestEconomicsTask)
            result = Observation()
            suite.run(result)
    outcomes = [("passed", test) for test in result.passes]
    outcomes += [("failed", test) for test, _ in result.failures]
    outcomes += [("skipped", test) for test, _ in result.skipped]
    statuses = {test.id().rsplit(".", 1)[-1]: name for name, test in outcomes}
    known = (
        result.testsRun == len(outcomes) == len(statuses)
        and set(statuses) == set(IDS)
        and not result.errors
        and not result.unexpectedSuccesses
        and not result.expectedFailures
    )
    upstream = known and all(status == "passed" for status in statuses.values())
    precision = precise_answer(answer, expected)
    return {
        "protocol_verified": known,
        "upstream_valid": upstream if known else None,
        "protected_grade": int(upstream and precision) if known else None,
        "precision_valid": precision if known else None,
        "observations": statuses if known else None,
    }


def main():
    if (os.geteuid(), os.getegid()) != (65534, 65534) or sys.version_info[:3] != (3, 13, 15):
        raise ValueError("unexpected protected grader identity")
    lock = json.loads((ROOT / "fixtures.json").read_bytes())
    upstream = ROOT / "upstream_test.py"
    if hashlib.sha256(upstream.read_bytes()).hexdigest() != lock["verifier_sha256"]:
        raise ValueError("protected verifier drift")
    if os.path.exists("/root/answer.txt"):
        raise ValueError("grader cannot prefer a global answer")
    result = {
        name: observe(
            upstream, None if text is None else text.encode("ascii"), Decimal(lock["expected"])
        )
        for name, text in lock["artifacts"].items()
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
