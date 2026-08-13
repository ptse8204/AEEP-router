from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_checked_in_schemas_are_current():
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    completed = subprocess.run(
        [sys.executable, "scripts/generate_schemas.py", "--check"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
