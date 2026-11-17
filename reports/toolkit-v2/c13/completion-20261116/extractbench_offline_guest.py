"""Populate one disposable grader workspace from the reviewed offline wheelhouse."""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from importlib.metadata import distributions
from pathlib import Path


def site_run(runtime, support, request):
    if sys.version_info[:3] != (3, 13, 15) or platform.machine() != "aarch64":
        raise ValueError("grader interpreter differs from the reviewed wheel platform")
    with tempfile.TemporaryDirectory(prefix="extractbench-site-", dir="/tmp") as directory:
        work = Path(directory)
        deps = work / "site"
        env = {"HOME": directory, "LC_ALL": "C", "PATH": os.defpath, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
        started = time.monotonic()
        result = subprocess.run([
            sys.executable, "-I", "-B", "-m", "pip", "--isolated", "install", "--no-index", "--no-deps", "--no-compile",
            "--only-binary=:all:", "--require-hashes", "--no-cache-dir", "--disable-pip-version-check", "--no-input",
            "--find-links", str(runtime / "wheels"), "--target", str(deps), "-r", str(runtime / "requirements.txt"),
        ], cwd=work, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=115, check=False)
        setup_seconds = time.monotonic() - started
        if result.returncode:
            return {"setup_status": "wheel_install_failed", "setup_exit_code": result.returncode, "setup_seconds": setup_seconds}
        packages = {dist.metadata["Name"].lower().replace("_", "-").replace(".", "-"): dist.version
                    for dist in distributions(path=[str(deps)])}
        if packages != request["packages"] or (deps / "fuzzysearch").exists():
            raise ValueError("installed wheel composition differs from its exact review")
        shutil.copytree(runtime / "fuzzysearch", deps / "fuzzysearch")
        footprint = sum(path.stat().st_size for path in deps.rglob("*") if path.is_file())
        result = subprocess.run([
            sys.executable, "-I", "-B", str(runtime / "extractbench_harbor_observer.py"),
            "--support", str(support), "--dependencies", str(deps),
        ], cwd=work, env=env, input=json.dumps({"roles": request["roles"]}), stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=185, check=False)
        return {
            "setup_status": "ready", "setup_seconds": setup_seconds, "installed_wheels": len(packages),
            "installed_file_bytes": footprint, "observer_exit_code": result.returncode,
            "grader": json.loads(result.stdout) if result.returncode == 0 and len(result.stdout) <= 10_000 else None,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--support", type=Path, required=True)
    opts = parser.parse_args()
    result = site_run(opts.runtime, opts.support, json.load(sys.stdin))
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
