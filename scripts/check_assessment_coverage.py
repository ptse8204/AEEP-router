#!/usr/bin/env python3
"""Enforce 90% branch coverage for the new assessment authority boundaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TARGETS = {
    "configured setup scope": ("src/aeep/assessment/onboarding.py", "prepare_setup"),
    "current grant validity": ("src/aeep/assessment/repository.py", "AssessmentRepository.current_grant"),
    "reviewed grader diagnostics": ("src/aeep/assessment/extensions.py", "grader_results"),
    "paired inspection authority": ("src/aeep/hosts/codex_pair_inspection.py", "authorize_pair"),
    "worker inspection authority": ("src/aeep/hosts/codex_inspection.py", "execute"),
    "worker inspection cleanup": ("src/aeep/hosts/codex_inspection.py", "execute.invoke"),
    "operator sign-in authority": ("src/aeep/hosts/codex_signin.py", "signin_worker"),
    "pilot cost lineage": ("src/aeep/assessment/pilot.py", "require_linked_pilot"),
    "pilot calibration scope": ("src/aeep/assessment/pilot.py", "_require_calibrated_mapping"),
    "conformance bootstrap authority": ("src/aeep/assessment/boundary.py", "run_boundary_probe"),
    "pilot holdout separation": ("src/aeep/assessment/pilot.py", "require_separation"),
    "differential environment": ("src/aeep/assessment/boundary.py", "require_differential"),
    "budget amendment": ("src/aeep/assessment/repository.py", "AssessmentRepository._approve_budget_amendment"),
    "incremental utility": ("src/aeep/assessment/reporting.py", "incremental_utility"),
    "utility measurements": ("src/aeep/assessment/reporting.py", "incremental_utility.value"),
    "paired utility decisions": ("src/aeep/assessment/reporting.py", "incremental_utility.compare"),
    "boundary verification": ("src/aeep/assessment/boundary.py", "require_conformance"),
    "production worker binding": ("src/aeep/assessment/boundary.py", "require_managed_boundaries"),
    "scope amendment transaction": ("src/aeep/assessment/repository.py", "AssessmentRepository.approve_bundle"),
    "capability eligibility": ("src/aeep/execution.py", "ExecutorCapabilities.require"),
    "applicability": ("src/aeep/assessment/applicability.py", None),
    "authorization": ("src/aeep/assessment/repository.py", "AssessmentRepository.authorize"),
    "durable budget reservation": (
        "src/aeep/assessment/repository.py",
        "AssessmentRepository.reserve",
    ),
    "budget completion": (
        "src/aeep/assessment/repository.py",
        "AssessmentRepository.finish_operation",
    ),
    "atomic admission": ("src/aeep/assessment/service.py", "AssessmentService.admit"),
}


def main() -> int:
    files = {
        path.replace("\\", "/"): data
        for path, data in json.loads(Path(sys.argv[1]).read_text())["files"].items()
    }
    failed = False
    for label, (path, function) in TARGETS.items():
        entry = files[path]["functions"][function] if function else files[path]
        summary = entry["summary"]
        total, covered = summary["num_branches"], summary["covered_branches"]
        percentage = 100 * covered / total if total else 100
        print(f"{label}: {covered}/{total} branches ({percentage:.2f}%)")
        failed |= percentage < 90
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
