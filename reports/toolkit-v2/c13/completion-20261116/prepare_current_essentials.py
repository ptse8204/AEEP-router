"""Plan private Essentials installation for the exact, current C13 wheel."""

import contextlib
import hashlib
import io
import json
import shutil
import socket
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import linux_install_guest
from check_linux_install import HERE, WORK, get, put
from rebind_current_stack import WHEEL, verify_delta

from aeep_toolkit.cli import main as toolkit
from aeep_toolkit.install_runtime import (
    RuntimeInstallation,
    Wheel,
    apply,
    check_wheel,
    digest,
    file_digest,
)
from aeep_toolkit.installation import PreviewPolicy, manifest_digest, preview
from aeep_toolkit.models import ExtensionManifest, ExtensionRegistry

STAGING = WORK / "current-essentials"
NATIVE = Path("/private/tmp/aeep-toolkit-c13-current-essentials")
APPLICATION = "aeep-agent-router"
RESERVE = 52 * 1024**3


def cli(arguments):
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        if toolkit(arguments) != 0:
            raise ValueError("ordinary Toolkit CLI refused the planned input")
    return stdout.getvalue().encode()


def installed_identity(path):
    prefix = "aeep_agent_router-0.8.2.data/data/share/aeep/"
    with ZipFile(path) as wheel:
        members = {
            name.removeprefix(prefix): hashlib.sha256(wheel.read(name)).digest()
            for name in wheel.namelist()
            if not name.endswith("/")
            and name.startswith(("aeep/", "aeep_toolkit/", prefix + "integrations/"))
        }
    identity = hashlib.sha256(b"aeep.installed-source.v1\0")
    for name, digest_bytes in sorted(members.items()):
        identity.update(name.encode() + b"\0" + digest_bytes)
    return identity.hexdigest()


def refresh_manifests(original, current, dependency_hash):
    values = []
    for inclusion in original.preview.items:
        manifest = inclusion.manifest.model_dump(mode="json")
        if manifest["extension_id"] == APPLICATION:
            manifest["source"].update(revision=current, artifact_sha256=dependency_hash)
        parsed = ExtensionManifest.model_validate(manifest)
        if parsed.extension_id != APPLICATION and digest(parsed) != digest(inclusion.manifest):
            raise ValueError("an unchanged dependency manifest drifted")
        values.append(parsed)
    return tuple(values)


def staged_wheels(platform, new_binary, original):
    folder = STAGING / platform / "wheels"
    folder.mkdir(mode=0o700, parents=True)
    wheels = []
    for artifact, wheel in original:
        if file_digest(artifact) != wheel.sha256:
            raise ValueError("a retained wheel differs from its pin")
        if wheel.extension_id == APPLICATION:
            artifact = new_binary
            wheel = wheel.model_copy(update={"sha256": file_digest(artifact)})
        target = folder / wheel.filename
        shutil.copyfile(artifact, target)
        check_wheel(target, wheel)
        wheels.append(wheel)
    folder.parent.chmod(0o700)
    put(folder.parent / "wheels.json", [wheel.model_dump(mode="json") for wheel in wheels])
    return folder, wheels


def check_fixture():
    original = WORK / "beta-check"
    recorded = get(WORK / "beta-inspect.json")
    beta = get(HERE / "beta-package-audit.json")
    source = original / "candidate"
    if file_digest(source / "SKILL.md") != recorded["files"]["SKILL.md"]:
        raise ValueError("synthetic candidate fixture changed")
    staged = STAGING / "staged-candidate"
    report = json.loads(cli(["candidate", str(source), "--stage", str(staged)]))
    if report["executed"] or report["candidate_sha256"] != recorded["candidate_sha256"]:
        raise ValueError("current source changed inert candidate inspection")
    result = {}
    for fmt, suffix in (("markdown", "md"), ("html", "html")):
        output = cli(["report", "--evidence", str(original / "evidence.json"), "--format", fmt])
        observed = hashlib.sha256(output).hexdigest()
        if observed != beta["archived_working_evidence"]["beta-report." + suffix]:
            raise ValueError("synthetic report changed on the current source")
        with (STAGING / ("fixture-report." + suffix)).open("xb") as stream:
            stream.write(output)
        result[fmt] = observed
    return result


def main():
    if (
        STAGING.exists()
        or NATIVE.exists()
        or any(
            shutil.disk_usage(parent).free < RESERVE + 1024**3 for parent in (WORK, NATIVE.parent)
        )
    ):
        raise ValueError("expected fresh planning paths and storage headroom")
    _, current, _, _, (_, new_hash) = verify_delta()
    compatibility = get(HERE / "current-stack-source-binding.json")
    if compatibility["implementation_source"] != current or compatibility["accepted_checks"] != 37:
        raise ValueError("this packet requires the revalidated committed source")
    wheel = WORK / "selection-final-check.vuYku6/committed-dist" / WHEEL
    old = get(WORK / "beta-installation.json")
    previous = RuntimeInstallation.model_validate(old["installation"])
    if digest(previous) != old["review_sha256"]:
        raise ValueError("earlier macOS plan changed")
    linux = get(WORK / "linux-private-install-preflight.json")["pins"]
    variant = [
        (
            Path(row["artifact"]),
            Wheel.model_validate(
                {key: row[key] for key in ("extension_id", "filename", "name", "version", "sha256")}
            ),
        )
        for row in linux
    ]
    if {item.extension_id: (item.name, item.version) for _, item in variant} != {
        item.extension_id: (item.name, item.version) for item in previous.wheels
    }:
        raise ValueError("previous platform closures disagree")
    STAGING.mkdir(mode=0o700)
    NATIVE.mkdir(mode=0o700)
    mac_folder, mac_wheels = staged_wheels(
        "macos",
        wheel,
        ((Path(previous.wheelhouse) / item.filename, item) for item in previous.wheels),
    )
    linux_folder, linux_wheels = staged_wheels("linux", wheel, variant)
    manifests = refresh_manifests(previous, current, new_hash)
    policy = PreviewPolicy.model_validate(
        previous.policy.model_dump(mode="json")
        | {
            "free_disk_bytes": shutil.disk_usage(NATIVE).free,
            "reviewed_dependency_manifests": [manifest_digest(item) for item in manifests],
        }
    )
    mac_preview = preview(
        ExtensionRegistry(extensions=manifests), (APPLICATION,), policy, profile="essentials"
    )
    if mac_preview.blockers:
        raise ValueError("updated macOS graph failed preview")
    put(mac_folder.parent / "preview.json", mac_preview.model_dump(mode="json"))
    put(mac_folder.parent / "policy.json", policy.model_dump(mode="json"))
    target = NATIVE / "runtime"
    command = [
        "install-plan",
        "--preview",
        str(mac_folder.parent / "preview.json"),
        "--policy",
        str(mac_folder.parent / "policy.json"),
        "--wheels",
        str(mac_folder.parent / "wheels.json"),
        "--wheelhouse",
        str(mac_folder),
        "--destination",
        str(target),
    ]
    with patch.object(
        socket.socket, "connect", side_effect=AssertionError("network access denied")
    ):
        mac_installation = json.loads(cli(command))
        plan = RuntimeInstallation.model_validate(mac_installation["installation"])
        if mac_installation["review_sha256"] != digest(plan) or plan.wheels != tuple(mac_wheels):
            raise ValueError("ordinary macOS installation plan changed bindings")
        try:
            apply(plan, "0" * 64)
        except ValueError as error:
            if str(error) != "exact installation review required":
                raise
        else:
            raise ValueError("incorrect install digest was accepted")
        if list(NATIVE.iterdir()):
            raise ValueError("plan or refused install left runtime effects")
        put(mac_folder.parent / "installation.json", mac_installation)
        # The Linux guest uses the already verified graph mapper. Its preview
        # is inert on this host; check_closure will verify glibc tags in the guest.
        put(linux_folder.parent / "mac-installation.json", mac_installation)
        put(
            linux_folder.parent / "linux-wheels.json",
            [item.model_dump(mode="json") for item in linux_wheels],
        )
        with (
            patch.object(linux_install_guest, "INPUT", linux_folder.parent),
            patch.object(linux_install_guest, "OUTPUT", linux_folder.parent),
        ):
            linux_preview, linux_policy = linux_install_guest.linux_preview()
        put(linux_folder.parent / "preview.json", linux_preview.model_dump(mode="json"))
        put(linux_folder.parent / "policy.json", linux_policy.model_dump(mode="json"))
        reports = check_fixture()
    if list(NATIVE.iterdir()):
        raise ValueError("macOS lifecycle started during preparation")
    record = {
        "implementation_source": current,
        "wheel_sha256": new_hash,
        "anticipated_installed_source": installed_identity(wheel),
        "macos_plan_sha256": mac_installation["review_sha256"],
        "macos_preview_ref": digest(mac_preview),
        "linux_preview_ref": digest(linux_preview),
        "wheel_count_by_platform": {"macos": len(mac_wheels), "linux": len(linux_wheels)},
        "fixture_reports_equal_retained": reports,
        "rejected_digest_preserved_absent_destination": True,
        "native_command": command,
        "linux_preview_only": True,
        "private_staging_tree": str(STAGING),
        "new_runtime_creations": 0,
        "model_calls": 0,
    }
    put(STAGING / "results.json", record)
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
