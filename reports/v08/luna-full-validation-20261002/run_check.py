"""Run one validation command, preserve its full log and enforce local bounds."""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


REPORT_DIR = Path(__file__).resolve().parent
REPO_ROOT = REPORT_DIR.parents[2]
TEMP_ROOT = Path(
    "/private/var/folders/_g/bvzl9cms7cx1d0wdpc981n9w0000gn/T/"
    "aeep-luna-full-validation-20261002"
)
SOURCE_MANIFEST = Path(
    os.environ.get("LUNA_SOURCE_MANIFEST", REPORT_DIR / "source-before.sha256")
)
MAX_TEMP_BYTES = 30 * 1024**3
MIN_IMPORTANT_BYTES = 80 * 1024**3


def source_manifest() -> str:
    rows = []
    for root_name in ("src", "examples", "tests"):
        root = REPO_ROOT / root_name
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rows.append(f"{digest}  {path.relative_to(REPO_ROOT)}")
    return "\n".join(rows) + "\n"


def directory_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    result = subprocess.run(
        ["du", "-sk", str(path)], check=True, capture_output=True, text=True
    )
    return int(result.stdout.split()[0]) * 1024


def capacities() -> dict[str, int]:
    result = subprocess.run(
        [sys.executable, str(REPORT_DIR / "storage_probe.py")],
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        key: int(value)
        for line in result.stdout.splitlines()
        for key, value in [line.split("=", 1)]
    }


def tail(path: Path, count: int = 80) -> str:
    with path.open(encoding="utf-8", errors="replace") as stream:
        lines = stream.readlines()
    return "".join(lines[-count:])


def main() -> int:
    if "--" not in sys.argv:
        raise SystemExit("usage: run_check.py LOG_STEM -- COMMAND [ARGS...]")
    separator = sys.argv.index("--")
    if separator != 2 or len(sys.argv) <= separator + 1:
        raise SystemExit("usage: run_check.py LOG_STEM -- COMMAND [ARGS...]")
    log_stem = sys.argv[1]
    command = sys.argv[separator + 1 :]
    log_path = REPORT_DIR / f"{log_stem}.log"
    if log_path.exists():
        raise SystemExit(f"refusing to overwrite existing log: {log_path}")
    if not SOURCE_MANIFEST.exists():
        raise SystemExit(f"source baseline is unavailable: {SOURCE_MANIFEST}")

    environment = os.environ.copy()
    monitored = {
        key: environment[key]
        for key in (
            "AEEP_VERIFY_OFFLINE",
            "PYTEST_ADDOPTS",
            "TMPDIR",
            "COVERAGE_FILE",
            "LUNA_SOURCE_MANIFEST",
        )
        if key in environment
    }
    with log_path.open("x", encoding="utf-8") as log:
        log.write(f"COMMAND: {' '.join(command)}\n")
        for key, value in sorted(monitored.items()):
            log.write(f"ENV {key}={value}\n")
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        started = time.monotonic()
        next_sample = started + 30
        interrupted_reason = None
        while process.poll() is None:
            try:
                process.wait(timeout=min(1, max(0.1, next_sample - time.monotonic())))
            except subprocess.TimeoutExpired:
                pass
            if process.poll() is not None:
                break
            if time.monotonic() < next_sample:
                continue
            temp_bytes = directory_bytes(TEMP_ROOT)
            report_bytes = directory_bytes(REPORT_DIR)
            important_bytes = capacities()[
                "NSURLVolumeAvailableCapacityForImportantUsageKey_bytes"
            ]
            elapsed = int(time.monotonic() - started)
            sample = (
                f"MONITOR elapsed_seconds={elapsed} temp_bytes={temp_bytes} "
                f"report_bytes={report_bytes} combined_bytes={temp_bytes + report_bytes} "
                f"important_usage_bytes={important_bytes}\n"
            )
            log.write(sample)
            log.flush()
            print(sample, end="", flush=True)
            next_sample = time.monotonic() + 30
            if temp_bytes + report_bytes > MAX_TEMP_BYTES:
                interrupted_reason = "temporary root plus retained logs/data exceeded 30 GiB"
            elif important_bytes < MIN_IMPORTANT_BYTES:
                interrupted_reason = "important-usage free capacity fell below 80 GiB"
            elif source_manifest() != SOURCE_MANIFEST.read_text(encoding="utf-8"):
                interrupted_reason = "source changed while validation was running"
            if interrupted_reason:
                log.write(f"RESOURCE_GUARD: {interrupted_reason}\n")
                log.flush()
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                break

        result = process.wait()
        log.write(f"EXIT_CODE: {result}\n")
        if interrupted_reason:
            log.write(f"STOP_REASON: {interrupted_reason}\n")
        log.flush()

    print(f"LOG: {log_path}")
    print(f"EXIT_CODE: {result}")
    if interrupted_reason:
        print(f"STOP_REASON: {interrupted_reason}")
    print("--- log tail ---")
    print(tail(log_path), end="")
    return 125 if interrupted_reason else result


if __name__ == "__main__":
    raise SystemExit(main())
