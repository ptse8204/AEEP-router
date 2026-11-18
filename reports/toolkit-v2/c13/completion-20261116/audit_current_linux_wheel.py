"""Check cached inputs for the current Linux lifecycle without installing them."""

import json
from email.parser import BytesParser
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

import linux_install_guest
from check_linux_install import HERE, ROOT, WORK, get
from prepare_current_essentials import installed_identity

from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import (
    RuntimeInstallation,
    Wheel,
    check_wheel,
    digest,
    file_digest,
)

REMOVED_DEV_PIN = 'pydantic==2.12.0; extra == "dev"'


def pin(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": file_digest(path)}


def application_metadata(path: Path):
    dist = "aeep_agent_router-0.8.2.dist-info/"
    with ZipFile(path) as archive:
        headers = BytesParser().parsebytes(archive.read(dist + "METADATA"), headersonly=True)
        tags = BytesParser().parsebytes(archive.read(dist + "WHEEL"), headersonly=True)
    return (
        sorted(headers.get_all("Requires-Python", [])),
        sorted(headers.get_all("Requires-Dist", [])),
        sorted(tags.get_all("Tag", [])),
    )


def audit() -> dict:
    native = HERE / "current-wheel-lifecycle-result-20261117.json"
    historical = HERE / "linux-private-install-result.json"
    mac, linux = get(native), get(historical)
    assert mac["status"] == "PASSED" and linux["passed"]
    current = WORK / "formal-document-native-20261117"
    wheel = current / "dist/aeep_agent_router-0.8.2-py3-none-any.whl"
    assert file_digest(wheel) == mac["wheel_sha256"]
    assert installed_identity(wheel) == mac["installed_source"]
    assert verification_source_digest(current / "committable-source") == mac["application_source"]
    plan_path = WORK / "current-wheel-native-20261117/macos/installation.json"
    document = get(plan_path)
    plan = RuntimeInstallation.model_validate(document["installation"])
    assert document["review_sha256"] == digest(plan) == mac["installation_plan_ref"]

    prior_pins = WORK / "linux-private-install-preflight.json"
    mac_wheels = {item.extension_id: item for item in plan.wheels}
    wheels = []
    for row in get(prior_pins)["pins"]:
        old_artifact = Path(row["artifact"])
        original = Wheel.model_validate({key: row[key] for key in (
            "extension_id", "filename", "name", "version", "sha256",
        )})
        mac_wheel = mac_wheels[original.extension_id]
        assert (original.name, original.version) == (mac_wheel.name, mac_wheel.version)
        check_wheel(old_artifact, original)
        if original.extension_id == "aeep-agent-router":
            assert mac_wheel.filename == original.filename == wheel.name
            check_wheel(wheel, mac_wheel)
            old_python, old_requirements, old_tags = application_metadata(old_artifact)
            new_python, new_requirements, new_tags = application_metadata(wheel)
            assert old_python == new_python and old_tags == new_tags
            assert old_requirements == sorted([*new_requirements, REMOVED_DEV_PIN])
            wheels.append((wheel, mac_wheel))
        else:
            wheels.append((old_artifact, original))
    assert len(wheels) == len(mac_wheels) == 33

    with TemporaryDirectory(prefix="aeep-c13-linux-inputs-") as directory:
        staging = Path(directory)
        (staging / "mac-installation.json").write_bytes(plan_path.read_bytes())
        (staging / "linux-wheels.json").write_text(json.dumps([
            item.model_dump(mode="json") for _, item in wheels
        ]))
        with patch.object(linux_install_guest, "INPUT", staging), patch.object(linux_install_guest, "OUTPUT", staging):
            preview, policy = linux_install_guest.linux_preview()
    assert not preview.blockers and policy.platform == "linux-aarch64"
    assert {row.manifest.extension_id: row.manifest.source.artifact_sha256 for row in preview.items} == {
        item.extension_id: item.sha256 for _, item in wheels
    }
    for fmt in ("markdown", "html"):
        assert pin(ROOT / mac["phases"][fmt]["path"]) == mac["phases"][fmt]
        assert mac["phases"][fmt]["sha256"] == linux["reports_equal_macos"][fmt]

    return {
        "schema_version": "aeep.c13.current-linux-wheel-preflight.v1",
        "status": "INPUTS_VERIFIED_RUNTIME_UNSTARTED",
        "target": {"system": "Linux", "machine": "aarch64", "python": linux["python"], "image": linux["image"]},
        "application_source": mac["application_source"],
        "expected_installed_source": mac["installed_source"],
        "current_macos_lifecycle": pin(native),
        "prior_linux_lifecycle": pin(historical),
        "current_macos_installation_plan": pin(plan_path),
        "cached_linux_dependency_pins": pin(prior_pins),
        "existing_linux_guest": pin(HERE / "linux_install_guest.py"),
        "audit_script": pin(Path(__file__).resolve()),
        "selected_wheels": [{"filename": item.filename, "artifact": pin(artifact)} for artifact, item in wheels],
        "linux_dependency_wheels_unchanged": 32,
        "sole_dependency_metadata_change_removes_dev_only_pin": REMOVED_DEV_PIN,
        "guest_manifest_preview_accepted": True,
        "fixture_report_hashes": linux["reports_equal_macos"],
        "verified_runtime_for_current_wheel": False,
        "execution_approval": None,
        "installations": 0,
        "docker_commands": 0,
        "downloads": 0,
        "model_turns": 0,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True, allow_nan=False))
