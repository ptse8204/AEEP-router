# MIT-licensed source excerpts from SWE-rebench/SWE-bench-fork
# Commit: 980d0cca8aa4e73f1d9f894e906370bef8c4de8a
# Exact function/class bodies; orchestration imports omitted. See LICENSE.upstream.
from __future__ import annotations
from enum import Enum
from typing import Any
FAIL_TO_PASS="FAIL_TO_PASS"
FAIL_TO_FAIL="FAIL_TO_FAIL"
PASS_TO_PASS="PASS_TO_PASS"
PASS_TO_FAIL="PASS_TO_FAIL"
class ResolvedStatus(Enum):
    NO = "RESOLVED_NO"
    PARTIAL = "RESOLVED_PARTIAL"
    FULL = "RESOLVED_FULL"

class TestStatus(Enum):
    FAILED = "FAILED"
    PASSED = "PASSED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    XFAIL = "XFAIL"

class EvalType(Enum):
    PASS_AND_FAIL = "pass_and_fail"
    FAIL_ONLY = "fail_only"
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
def test_passed(case: str, sm: dict[str, str]) -> bool:
    return case in sm and sm[case] in [TestStatus.PASSED.value, TestStatus.XFAIL.value]

def test_failed(case: str, sm: dict[str, str]) -> bool:
    return case not in sm or sm[case] in [TestStatus.FAILED.value, TestStatus.ERROR.value]

def get_eval_tests_report(
    eval_status_map: dict[str, str],
    gold_results: dict[str, str],
    calculate_to_fail: bool = False,
    eval_type: EvalType = EvalType.PASS_AND_FAIL,
) -> dict[str, dict[str, list[str]]]:
    """
    Create a report based on failure/pass change from gold results to eval results.

    Args:
        eval_sm (dict): evaluation status map
        gold_results (dict): gold results
        calculate_to_fail (bool): whether to calculate metrics for "x to fail" tests
    Returns:
        report (dict): report of metrics

    Metric Definitions (Gold Result Pair + Eval Result):
    - Fail-Pass (F2P) + P: Success (Resolution)
    - Pass-Pass (P2P) + P: Success (Maintenance)
    - Fail-Pass (F2P) + F: Failure
    - Pass-Pass (P2P) + F: Failure

    Miscellaneous Definitions
    - Fail-Fail (F2F) + F: Failure Maintenance
    - Pass-Fail (P2F) + F: Not considered
    - Fail-Fail (F2F) + P: Success (Extra Credit)
    - Pass-Fail (P2F) + P: Not considered
    """

    def check_pass_and_fail(test_case, eval_status_map, success, failed):
        if test_passed(test_case, eval_status_map):
            # Assume silent success for now (test case not in eval_sm)
            success.append(test_case)
        elif test_failed(test_case, eval_status_map):
            failed.append(test_case)

    def check_fail_only(test_case, eval_status_map, success, failed):
        if (
            test_case in eval_status_map
            and eval_status_map[test_case] == TestStatus.FAILED.value
        ):
            failed.append(test_case)
        else:
            success.append(test_case)

    check_test_case = (
        check_pass_and_fail if eval_type == EvalType.PASS_AND_FAIL else check_fail_only
    )

    # Calculate resolution metrics
    f2p_success = []
    f2p_failure = []
    for test_case in gold_results[FAIL_TO_PASS]:
        check_test_case(test_case, eval_status_map, f2p_success, f2p_failure)

    # Calculate maintenance metrics
    p2p_success = []
    p2p_failure = []
    for test_case in gold_results[PASS_TO_PASS]:
        check_test_case(test_case, eval_status_map, p2p_success, p2p_failure)

    results = {
        FAIL_TO_PASS: {
            "success": f2p_success,
            "failure": f2p_failure,
        },
        PASS_TO_PASS: {
            "success": p2p_success,
            "failure": p2p_failure,
        },
    }

    f2f_success = []
    f2f_failure = []
    p2f_success = []
    p2f_failure = []
    if calculate_to_fail:
        # Calculate "extra credit" metrics
        for test_case in gold_results[FAIL_TO_FAIL]:
            check_test_case(test_case, eval_status_map, f2f_success, f2f_failure)

        # Calculate not considered metrics
        for test_case in gold_results[PASS_TO_FAIL]:
            check_test_case(test_case, eval_status_map, p2f_success, p2f_failure)

    results.update(
        {
            FAIL_TO_FAIL: {
                "success": f2f_success,
                "failure": f2f_failure,
            },
            PASS_TO_FAIL: {
                "success": p2f_success,
                "failure": p2f_failure,
            },
        }
    )
    return results

def compute_fail_to_pass(report: dict[str, dict[str, Any]]) -> float:
    """
    Compute fail-to-pass metric. Accepts single report as argument.
    """
    total = len(report[FAIL_TO_PASS]["success"]) + len(report[FAIL_TO_PASS]["failure"])
    if total == 0:
        return 1
    return len(report[FAIL_TO_PASS]["success"]) / total

def compute_pass_to_pass(report: dict[str, dict[str, Any]]) -> float:
    """
    Compute pass-to-pass metric. Accepts single report as argument.
    """
    total = len(report[PASS_TO_PASS]["success"]) + len(report[PASS_TO_PASS]["failure"])
    if total == 0:
        # TODO: Don't factor in p2p metrics
        return 1
    return len(report[PASS_TO_PASS]["success"]) / total

def get_resolution_status(report: dict[str, dict[str, Any]]) -> str:
    """
    Determine resolved status of an evaluation instance

    Criteria:
        - If fail-to-pass (Resolution) = 1 and pass-to-pass (Maintenance) = 1 -> FULL
        - If (fail-to-pass (Resolution) < 1 and > 0) and pass-to-pass (Maintenance) = 1 -> PARTIAL
        - Otherwise -> NO
    """
    f2p = compute_fail_to_pass(report)
    p2p = compute_pass_to_pass(report)

    if f2p == 1 and p2p == 1:
        return ResolvedStatus.FULL.value
    elif f2p < 1 and f2p > 0 and p2p == 1:
        return ResolvedStatus.PARTIAL.value
    else:
        return ResolvedStatus.NO.value
