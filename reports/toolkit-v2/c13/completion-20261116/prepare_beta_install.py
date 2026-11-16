"""Prepare the first private Essentials install of the current C13 wheel."""

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import RuntimeInstallation, check_closure, file_digest
from aeep_toolkit.installation import PreviewPolicy, manifest_digest, preview
from aeep_toolkit.models import ExtensionManifest, ExtensionRegistry

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / ".aeep/completion-20261116"
FROZEN = ROOT / ".aeep/sol-comparison-preflight-20261116/frozen-source"
EXPECTED = "4e673a6d324c6a72c4444ae55e736c1516acd03cb34d2a3401ecb8073f17c9f5"


def write(path: Path, value) -> None:
    with path.open("x") as output:
        output.write(json.dumps(value, indent=2) + "\n")


def inspect_wheel(wheel: Path) -> tuple[int, str, int]:
    groups: dict[str, bytes] = {}
    checked = set()
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            if name.startswith(("aeep/", "aeep_toolkit/")):
                source = FROZEN / "src" / name
                data = archive.read(name)
                if data != source.read_bytes():
                    raise ValueError(f"wheel/source mismatch: {name}")
                checked.add(name)
                groups[name] = data
            prefix = "aeep_agent_router-0.8.2.data/data/share/aeep/"
            if name.startswith(prefix + "integrations/"):
                groups[name.removeprefix(prefix)] = archive.read(name)
        expanded = sum(entry.file_size for entry in archive.infolist())
    expected = {path.relative_to(FROZEN / "src").as_posix()
                for name in ("aeep", "aeep_toolkit")
                for path in (FROZEN / "src" / name).rglob("*.py")}
    if expected - checked or not any(name.startswith("integrations/") for name in groups):
        raise ValueError("required package source or integration assets are missing")
    fingerprint = hashlib.sha256(b"aeep.installed-source.v1\0")
    for name, data in sorted(groups.items()):
        fingerprint.update(name.encode() + b"\0" + hashlib.sha256(data).digest())
    return len(checked), fingerprint.hexdigest(), expanded


def main() -> None:
    if verification_source_digest(FROZEN) != EXPECTED:
        raise ValueError("frozen execution source changed")
    old = RuntimeInstallation.model_validate_json(
        (HERE.parent / "workflow-sponsors-20261104/package-installation.json").read_bytes()
    )
    target = WORK / "beta-wheels"
    wheel = WORK / "dist/aeep_agent_router-0.8.2-py3-none-any.whl"
    package_files, expected_installed, expanded = inspect_wheel(wheel)
    entries = []
    for pin in old.wheels:
        source = wheel if pin.extension_id == "aeep-agent-router" else Path(old.wheelhouse) / pin.filename
        artifact = file_digest(source)
        if pin.extension_id != "aeep-agent-router" and artifact != pin.sha256:
            raise ValueError(f"reviewed dependency changed: {pin.filename}")
        entries.append((source, pin.model_copy(update={"sha256": artifact})))
    target.mkdir(mode=0o700)
    for source, pin in entries:
        shutil.copyfile(source, target / pin.filename)
    wheels = tuple(pin for _, pin in entries)
    closure_bytes = check_closure(target, wheels, old.policy.platform)
    manifests = [item.manifest for item in old.preview.items]
    core = next(manifest for manifest in manifests if manifest.extension_id == "aeep-agent-router")
    updated = core.model_dump(mode="json")
    updated["source"].update(artifact_sha256=file_digest(wheel), revision=EXPECTED)
    updated["disk_bytes"] = expanded
    manifests = tuple(ExtensionManifest.model_validate(updated)
                      if manifest.extension_id == core.extension_id else manifest
                      for manifest in manifests)
    policy = PreviewPolicy.model_validate(old.policy.model_dump(mode="json") | {
        "free_disk_bytes": shutil.disk_usage(WORK).free,
        "reviewed_dependency_manifests": [manifest_digest(manifest) for manifest in manifests],
    })
    plan = preview(ExtensionRegistry(extensions=manifests), (core.extension_id,), policy, profile="essentials")
    write(WORK / "beta-preview.json", plan.model_dump(mode="json"))
    write(WORK / "beta-policy.json", policy.model_dump(mode="json"))
    write(WORK / "beta-wheel-inventory.json", [pin.model_dump(mode="json") for pin in wheels])
    write(WORK / "beta-package-audit.json", {
        "implementation_source": EXPECTED, "wheel_sha256": file_digest(wheel),
        "package_files_matching_frozen_source": package_files,
        "anticipated_installed_source": expected_installed, "wheels": len(wheels),
        "archive_bytes": sum(path.stat().st_size for path, _ in entries),
        "conservative_closure_bytes": closure_bytes,
        "selected_components": list(plan.selected),
    })


if __name__ == "__main__":
    main()
