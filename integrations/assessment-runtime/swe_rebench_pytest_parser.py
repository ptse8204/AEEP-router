# MIT source: SWE-rebench/SWE-bench-fork, 980d0cca8aa4e73f1d9f894e906370bef8c4de8a
# Exact class/function bodies; see LICENSE.swe-rebench.
from __future__ import annotations

from enum import Enum
from typing import Any as TestSpec


class TestStatus(Enum):
    FAILED = "FAILED"
    PASSED = "PASSED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    XFAIL = "XFAIL"

def parse_log_pytest(log: str, test_spec: TestSpec) -> dict[str, str]:
    """
    Parser for test logs generated with PyTest framework

    Args:
        log (str): log content
    Returns:
        dict: test case to test status mapping
    """
    test_status_map = {}
    for line in log.split("\n"):
        if any([line.startswith(x.value) for x in TestStatus]):
            # Additional parsing for FAILED status
            if line.startswith(TestStatus.FAILED.value):
                line = line.replace(" - ", " ")
            test_case = line.split()
            if len(test_case) <= 1:
                continue
            test_status_map[test_case[1]] = test_case[0]
    return test_status_map
