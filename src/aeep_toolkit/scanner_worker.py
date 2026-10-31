"""Contained Cisco CLI bridge. Deploy in a reviewed offline image, never on host.

Only static/core analyzers are requested. The exact upstream artifact and image
must be reviewed separately; this program does not install or qualify either.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

SOURCE_REVISION = "c3d7fd9fee50cf2ea45f0b381eb61f857360f825"
SCANNER = "/opt/aeep-scanner/bin/skill-scanner"


def scan(request: dict[str, Any], workspace: Path) -> dict[str, Any]:
    required = {"files", "candidate_sha256", "implementation_source", "check"}
    if (
        set(request) != required
        or request["check"] not in {"static_scan", "findings_and_failures"}
        or not isinstance(request["files"], dict)
        or not 1 <= len(request["files"]) <= 512
    ):
        raise ValueError("invalid bounded static scanner request")
    for name in ("candidate_sha256", "implementation_source"):
        if (
            not isinstance(request[name], str)
            or len(request[name]) != 64
            or any(c not in "0123456789abcdef" for c in request[name])
        ):
            raise ValueError("invalid scanner source binding")
    captured, folded = {}, set()
    for name, encoded in request["files"].items():
        path = PurePosixPath(name)
        if (
            not isinstance(encoded, str)
            or not name
            or len(name) > 512
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or str(path) != name
            or name.casefold() in folded
            or any(
                part.casefold() in {".git", ".codex", ".aws", ".ssh", "evals", "__pycache__"}
                for part in path.parts
            )
            or path.name.casefold() in {"auth.json", "credentials.json"}
            or path.name.casefold().startswith(".env")
            or len(encoded) > 1_500_000
        ):
            raise ValueError("unsafe scanner candidate file")
        captured[name] = base64.b64decode(encoded, validate=True)
        folded.add(name.casefold())
    if "SKILL.md" not in captured or sum(map(len, captured.values())) > 8 * 1024**2:
        raise ValueError("scanner candidate exceeds its reviewed payload envelope")
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(captured.items())}
    identity = hashlib.sha256(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if identity != request["candidate_sha256"]:
        raise ValueError("candidate bytes differ inside scanner worker")
    with tempfile.TemporaryDirectory(prefix="aeep-static-scan-", dir=workspace) as directory:
        root = Path(directory) / "candidate"
        root.mkdir(mode=0o700)
        home = Path(directory) / "home"
        home.mkdir(mode=0o700)
        for name, raw in captured.items():
            target = root / name
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(raw)
        result = subprocess.run(
            [SCANNER, "scan", str(root), "--format", "json"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env={
                "HOME": str(home),
                "PATH": "/opt/aeep-scanner/bin:/usr/bin:/bin",
                "TMPDIR": str(workspace),
                "LANG": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            timeout=90,
            check=False,
        )
        if result.returncode not in (0, 1) or len(result.stdout) > 1024**2:
            raise ValueError("static scanner failed or exceeded its output envelope")
        data = json.loads(result.stdout)
        findings, failures, analyzers = (
            data["findings"],
            data.get("analyzers_failed", []),
            data["analyzers_used"],
        )
        if (
            not isinstance(findings, list)
            or type(data["findings_count"]) is not int
            or data["findings_count"] != len(findings)
            or not isinstance(failures, list)
            or not isinstance(analyzers, list)
            or not analyzers
            or not all(isinstance(name, str) for name in analyzers)
            or any(
                any(label in name.casefold() for label in ("llm", "aidefense", "virustotal"))
                for name in analyzers
            )
            or any(
                not isinstance(f, dict)
                or f.get("severity") not in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "SAFE"}
                for f in findings
            )
        ):
            raise ValueError("scanner returned unsupported or incomplete analyzer observations")
        # Ensure the scanner did not edit candidate bytes or introduce files.
        after = {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*")
            if path.is_file() and not path.is_symlink()
        }
        if after != hashes or any(path.is_symlink() for path in root.rglob("*")):
            raise ValueError("candidate bytes changed during static scanning")
        return {
            "component": "skill-scanner",
            "check": request["check"],
            "source_revision": SOURCE_REVISION,
            "implementation_source": request["implementation_source"],
            "mode": "upstream_functional",
            "candidate_sha256": identity,
            "findings_count": len(findings),
            "candidate_bytes_bound": True,
            "high_or_critical": sum(f["severity"] in {"HIGH", "CRITICAL"} for f in findings),
            "high_or_critical_detected": any(
                f["severity"] in {"HIGH", "CRITICAL"} for f in findings
            ),
            "failed_analyzers": len(failures),
            "analyzers_executed": len(analyzers),
            "findings": [
                {
                    key: finding.get(key)
                    for key in ("id", "rule_id", "category", "severity", "analyzer", "line_number")
                }
                for finding in findings
            ],
            "analyzer_failures": [
                {
                    "analyzer": failure.get("analyzer"),
                    "diagnostic_sha256": hashlib.sha256(
                        json.dumps(failure, sort_keys=True).encode()
                    ).hexdigest(),
                }
                for failure in failures
            ],
            "analyzers_used": analyzers,
            "upstream_report_sha256": hashlib.sha256(result.stdout).hexdigest(),
            "safety_verdict": "NOT_ESTABLISHED",
        }


def main() -> None:
    if sys.platform != "linux" or os.getuid() == 0 or not Path("/workspace").is_dir():
        raise ValueError("static scanner requires the reviewed nonroot Linux worker")
    raw = sys.stdin.buffer.read(12 * 1024**2 + 1)
    if len(raw) > 12 * 1024**2:
        raise ValueError("scanner input exceeds its envelope")
    print(json.dumps(scan(json.loads(raw), Path("/workspace")), allow_nan=False))


if __name__ == "__main__":
    main()
