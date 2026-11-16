"""Use the public Toolkit CLI for the reviewed Linux private-runtime check."""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from aeep_toolkit.installation import PreviewPolicy, manifest_digest, preview
from aeep_toolkit.models import ExtensionManifest, ExtensionRegistry

INPUT = Path("/input")
OUTPUT = Path("/scratch")


def read(path: Path):
    return json.loads(path.read_bytes())


def write(name: str, value) -> Path:
    path = OUTPUT / name
    with path.open("x") as file:
        json.dump(value, file, indent=2)
    return path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def execute(argv: list[str], seconds: int = 30) -> bytes:
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                            timeout=seconds, check=False)
    if result.returncode:
        # The fixture commands can echo only scoped, synthetic inputs and paths.
        raise RuntimeError(f"{Path(argv[0]).name} failed ({result.returncode}): {result.stderr[-500:]!r}")
    return result.stdout


def linux_preview():
    baseline = read(INPUT / "mac-installation.json")["installation"]
    wheels = read(INPUT / "linux-wheels.json")
    by_id = {wheel["extension_id"]: wheel for wheel in wheels}
    manifests = []
    migrated = {}
    for item in baseline["preview"]["items"]:
        data = item["manifest"]
        wheel = by_id[data["extension_id"]]
        before = manifest_digest(ExtensionManifest.model_validate(data))
        if before != item["manifest_sha256"]:
            raise ValueError("retained macOS manifest changed")
        data["platforms"] = ["linux-aarch64"]
        data["source"]["artifact_sha256"] = wheel["sha256"]
        for dependency in data["dependencies"]:
            original, adapted = migrated[dependency["extension_id"]]
            if dependency["manifest_sha256"] != original:
                raise ValueError("retained macOS dependency edge changed")
            dependency["manifest_sha256"] = adapted
        manifest = ExtensionManifest.model_validate(data)
        manifests.append(manifest)
        migrated[data["extension_id"]] = (before, manifest_digest(manifest))
    policy = PreviewPolicy.model_validate(baseline["policy"] | {
        "platform": "linux-aarch64", "free_disk_bytes": shutil.disk_usage(OUTPUT).free,
        "reviewed_dependency_manifests": [manifest_digest(m) for m in manifests],
    })
    proposal = preview(ExtensionRegistry(extensions=tuple(manifests)), ("aeep-agent-router",), policy,
                       profile="essentials")
    if proposal.blockers or {row.manifest.extension_id for row in proposal.items} != set(by_id):
        raise ValueError("Linux preview did not accept the exact adapted dependency closure")
    return proposal, policy


def main() -> None:
    import packaging

    if (sys.platform, platform.machine(), sys.version_info[:2]) != ("linux", "aarch64", (3, 13)):
        raise ValueError("unexpected Linux ABI")
    if not os.confstr("CS_GNU_LIBC_VERSION").startswith("glibc "):
        raise ValueError("glibc runtime required")
    if (packaging.__version__ != "24.2"
            or not str(packaging.__file__).startswith("/input/wheels/packaging-24.2-py3-none-any.whl/")):
        raise ValueError("reviewed packaging wheel must supply bootstrap imports")
    if list(OUTPUT.iterdir()) or shutil.disk_usage(OUTPUT).free < 52 * 1024**3:
        raise ValueError("unexpected initial workspace or storage reserve")
    os.umask(0o077)
    canary = write("neighbor.json", {"keep": True})
    canary_before = canary.read_bytes()
    proposal, policy = linux_preview()
    plan = write("preview.json", proposal.model_dump(mode="json"))
    policy_path = write("policy.json", policy.model_dump(mode="json"))
    runtime = OUTPUT / "runtime"
    command = [sys.executable, "-B", "-m", "aeep_toolkit"]
    installation = json.loads(execute([*command, "install-plan", "--preview", str(plan), "--policy",
                                       str(policy_path), "--wheels", str(INPUT / "linux-wheels.json"),
                                       "--wheelhouse", str(INPUT / "wheels"), "--destination", str(runtime)]))
    exact = write("installation.json", installation)
    args = ["--installation", str(exact), "--reviewed-digest", installation["review_sha256"]]
    first = json.loads(execute([*command, "install", *args], seconds=90))
    if first["status"] != "installed" or not runtime.is_dir():
        raise ValueError("unexpected first install state")
    again = json.loads(execute([*command, "install", *args], seconds=90))
    if again != first:
        raise ValueError("idempotent installation changed its journal")
    python = str(runtime / "bin/python")
    installed = execute([python, "-I", "-B", "-c",
        "from pathlib import Path; import aeep.assessment.verification as v; "
        "print(v.verification_source_digest(Path(v.__file__).resolve().parents[3]))"]).decode().strip()
    expected = read(INPUT / "expected.json")
    if installed != expected["installed_source"]:
        raise ValueError("installed package source or integration assets differ")
    cli = [python, "-I", "-B", "-m", "aeep_toolkit"]
    candidate = json.loads(execute([*cli, "candidate", str(INPUT / "candidate"), "--stage",
                                   str(OUTPUT / "staged-candidate")]))
    if candidate["candidate_sha256"] != expected["candidate"] or candidate["executed"]:
        raise ValueError("synthetic candidate preview changed identity or executed content")
    report_digests = {}
    for fmt in ("markdown", "html"):
        report = execute([*cli, "report", "--evidence", str(INPUT / "evidence.json"), "--format", fmt])
        if sha(report) != expected["reports"][fmt]:
            raise ValueError(f"{fmt} report differs from the equivalent macOS fixture")
        report_digests[fmt] = sha(report)
    removed = json.loads(execute([*command, "remove", *args]))
    journal = OUTPUT / "runtime.aeep-install.json"
    if (runtime.exists() or removed.get("status") != "removed" or read(journal) != removed
            or canary.read_bytes() != canary_before):
        raise ValueError("private removal or preservation failed")
    if sha((OUTPUT / "staged-candidate/SKILL.md").read_bytes()) != expected["skill"]:
        raise ValueError("staged synthetic candidate changed during removal")
    write("result.json", {
        "passed": True, "host": platform.platform(), "python": platform.python_version(),
        "plan_sha256": installation["review_sha256"], "installed_source": installed,
        "idempotent_install": True, "private_runtime_removed": True, "neighbor_preserved": True,
        "candidate_sha256": candidate["candidate_sha256"], "reports_equal_macos": report_digests,
        "removal_journal_sha256": sha(journal.read_bytes()), "model_turns": 0, "cash_usd": 0,
    })


if __name__ == "__main__":
    main()
