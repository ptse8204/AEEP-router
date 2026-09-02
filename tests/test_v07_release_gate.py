from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_critical_module_branch_coverage():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_critical_coverage.py"),
            str(ROOT / "reports" / "v07" / "coverage.json"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_fault_injection_report_is_complete():
    report = json.loads(
        (ROOT / "reports" / "v07" / "fault-injection.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["result"] == "PASS"
    assert {case["fault"] for case in report["cases"]} == {
        "before claim",
        "after claim",
        "after cash reservation",
        "after capacity reservation",
        "before external invocation",
        "immediately after App Server turn start",
        "during streamed output",
        "after terminal result but before validation",
        "during settlement",
        "after partial release",
        "during recovery",
    }
    assert all(case["status"] == "PASS" and case["test_id"] for case in report["cases"])
