"""Run one frozen-source validation command with bounded local resources."""

from __future__ import annotations

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
    "aeep-luna-full-validation-successor-20261002"
)
EXPECTED_SOURCE = "060fbefd55ff1c73256520a0c1e3d0de0e029755b75437cf7a93d7b68335e293"
MAX_TEMP_BYTES = 30 * 1024**3
MIN_IMPORTANT_BYTES = 80 * 1024**3

sys.path.insert(0, str(REPO_ROOT / "src"))
from aeep.assessment.verification import verification_source_digest


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

    initial_source = verification_source_digest(REPO_ROOT)
    if initial_source != EXPECTED_SOURCE:
        raise SystemExit(
            f"source digest mismatch before command: {initial_source} != {EXPECTED_SOURCE}"
        )

    environment = os.environ.copy()
    for key in (
        "AEEP_VERIFY_OFFLINE",
        "AEEP_INSPECTION_FIXTURE_SPECS",
        "AEEP_LIVE_MANIFEST",
        "AEEP_LIVE_ASSESSMENT_IDS",
        "AEEP_LIVE_RECEIPT_IDS",
        "AEEP_CONTAINER_IMAGE",
        "AEEP_CONTAINER_RUNTIME",
        "AEEP_CONTAINER_SOCKET",
        "AEEP_CATALOG_METRICS_IMAGE",
        "AEEP_NATIVE_CODEX",
        "AEEP_NATIVE_WORKBOOK_PYTHON",
        "AEEP_WORKBOOK_IMAGE",
        "AEEP_CODEX_EXECUTABLE",
    ):
        environment.pop(key, None)
    temp_run = TEMP_ROOT / f"tmp-{log_stem}"
    pytest_run = TEMP_ROOT / f"pytest-{log_stem}"
    temp_run.mkdir(parents=True, exist_ok=True)
    if "pytest" in command:
        pytest_run.mkdir(parents=True, exist_ok=True)
        cache_dir = REPORT_DIR / f"pytest-cache-{log_stem}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        environment["PYTEST_ADDOPTS"] = (
            f"--basetemp={pytest_run} -o cache_dir={cache_dir}"
        )
    else:
        environment.pop("PYTEST_ADDOPTS", None)
    environment["TMPDIR"] = str(temp_run)
    if "coverage" in command:
        environment["COVERAGE_FILE"] = str(REPORT_DIR / "coverage.data")

    with log_path.open("x", encoding="utf-8") as log:
        log.write(f"COMMAND: {' '.join(command)}\n")
        log.write(f"EXPECTED_VERIFICATION_SOURCE_DIGEST: {EXPECTED_SOURCE}\n")
        for key in (
            "AEEP_VERIFY_OFFLINE",
            "PYTEST_ADDOPTS",
            "TMPDIR",
            "COVERAGE_FILE",
        ):
            log.write(f"ENV {key}={environment.get(key, '<unset>')}\n")
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
            source_digest = verification_source_digest(REPO_ROOT)
            elapsed = int(time.monotonic() - started)
            sample = (
                f"MONITOR elapsed_seconds={elapsed} temp_bytes={temp_bytes} "
                f"report_bytes={report_bytes} combined_bytes={temp_bytes + report_bytes} "
                f"important_usage_bytes={important_bytes} "
                f"verification_source_digest={source_digest}\n"
            )
            log.write(sample)
            log.flush()
            print(sample, end="", flush=True)
            next_sample = time.monotonic() + 30
            if temp_bytes + report_bytes > MAX_TEMP_BYTES:
                interrupted_reason = "temporary root plus reports exceeded 30 GiB"
            elif important_bytes < MIN_IMPORTANT_BYTES:
                interrupted_reason = "important-usage capacity fell below 80 GiB"
            elif source_digest != EXPECTED_SOURCE:
                interrupted_reason = "verification source changed during validation"
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
        final_source = verification_source_digest(REPO_ROOT)
        log.write(f"EXIT_CODE: {result}\n")
        log.write(f"VERIFICATION_SOURCE_DIGEST_AFTER: {final_source}\n")
        if interrupted_reason:
            log.write(f"STOP_REASON: {interrupted_reason}\n")
        log.flush()

    print(f"LOG: {log_path}")
    print(f"EXIT_CODE: {result}")
    print(f"VERIFICATION_SOURCE_DIGEST_AFTER: {final_source}")
    if interrupted_reason:
        print(f"STOP_REASON: {interrupted_reason}")
        return 125
    if final_source != EXPECTED_SOURCE:
        return 125
    return result


if __name__ == "__main__":
    raise SystemExit(main())
