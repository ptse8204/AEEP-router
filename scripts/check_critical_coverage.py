#!/usr/bin/env python3
"""Enforce the AEEP 0.7 critical-module branch-coverage floor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

FLOOR = 90.0
CRITICAL_MODULES = {
    "App Server transport": "src/aeep/hosts/codex_app_server.py",
    "capacity reservations": "src/aeep/capacity/reservations.py",
    "transferability": "src/aeep/capacity/policy.py",
    "unified attempt recovery": "src/aeep/attempts.py",
    "x402 conformance": "src/aeep/x402/conformance.py",
}


def main() -> int:
    report_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("reports/v07/coverage.json")
    files = json.loads(report_path.read_text(encoding="utf-8"))["files"]
    failed = False
    for label, path in CRITICAL_MODULES.items():
        summary = files[path]["summary"]
        total = summary["num_branches"]
        covered = summary["covered_branches"]
        percent = 100.0 if total == 0 else covered * 100.0 / total
        print(f"{label}: {covered}/{total} branches ({percent:.2f}%)")
        failed |= percent < FLOOR
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
