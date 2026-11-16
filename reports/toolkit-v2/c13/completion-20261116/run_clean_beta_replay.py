"""Verify clean rollback of the approved private Essentials replay."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / ".aeep/completion-20261116"


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(path: Path, identity: str) -> dict:
    if sha(path) != identity:
        raise ValueError("exact replay review changed")
    review = json.loads(path.read_bytes())
    if any(sha(Path(name)) != digest for name, digest in review["pins"].items()):
        raise ValueError("reviewed source or journal changed")
    return review


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exact-review", required=True)
    args = parser.parse_args()
    review_path = WORK / "beta-clean-replay-operation-review.json"
    review = verify(review_path, args.exact_review)
    approval_path = WORK / "beta-clean-replay-approval.json"
    approval = json.loads(approval_path.read_bytes())
    if approval["approved"] is not True or approval["review_sha256"] != args.exact_review:
        raise ValueError("explicit operator approval is required for the repeated install")

    target = Path(review["target"])
    runtime = target / "runtime"
    original = WORK / "beta-runtime"
    canary = target / "canary"
    if (target.resolve() != target or target.parent != Path("/private/tmp") or not target.is_dir()
            or list(target.iterdir()) or not original.is_dir()
            or shutil.disk_usage(target).free < review["minimum_free_gib"] * 1024**3):
        raise ValueError("reviewed paths or free space changed")
    with (WORK / "beta-clean-replay-started.json").open("x") as stream:
        json.dump({"review_sha256": args.exact_review}, stream)
    canary.write_text("unrelated writable neighbor in the clean rollback rehearsal\n")
    canary_digest = sha(canary)
    environment = {"PATH": "/usr/bin:/bin", "HOME": str(target),
                   "TMPDIR": str(target), "PYTHONPATH": review["toolkit_source"], "LC_ALL": "C",
                   "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                   "PYTHONDONTWRITEBYTECODE": "1"}
    outputs = {}
    for phase, expected in (("install", "installed"), ("remove", "removed")):
        verify(review_path, args.exact_review)
        result = subprocess.run(review["commands"][phase], cwd=target, env=environment, timeout=340,
                                stdin=subprocess.DEVNULL, capture_output=True, check=False)
        for suffix, payload in (("json", result.stdout), ("log", result.stderr)):
            (WORK / ("beta-clean-replay-" + phase + "." + suffix)).write_bytes(payload)
        if result.returncode:
            raise RuntimeError("clean rollback rehearsal stopped with retained evidence")
        outputs[phase] = json.loads(result.stdout)
        if outputs[phase]["status"] != expected:
            raise ValueError("unexpected installer lifecycle state")
    if runtime.exists() or not original.is_dir() or sha(canary) != canary_digest:
        raise ValueError("expected install and removal states did not resolve")
    journal = target / "runtime.aeep-install.json"
    if json.loads(journal.read_bytes()) != outputs["remove"]:
        raise ValueError("removal state and ownership journal differ")
    verify(review_path, args.exact_review)
    with (WORK / "beta-clean-replay-result.json").open("x") as stream:
        json.dump({"passed": True, "review_sha256": args.exact_review,
                   "new_journal_sha256": sha(journal), "prior_runtime_preserved": True,
                   "neighbor_preserved": True, "model_turns": 0, "cash_usd": 0}, stream, indent=2)


if __name__ == "__main__":
    os.umask(0o077)
    main()
