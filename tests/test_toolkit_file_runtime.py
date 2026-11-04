"""Synthetic local file lifecycle; never executes an upstream binary or service."""

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest
from test_toolkit_installation import manifest, policy
from test_toolkit_runtime_install import installer_fixture_capacity as installer_fixture_capacity

from aeep_toolkit import file_runtime, install_runtime
from aeep_toolkit.cli import main
from aeep_toolkit.installation import preview
from aeep_toolkit.models import ExtensionRegistry

pytestmark = pytest.mark.usefixtures("installer_fixture_capacity")


def installation(tmp_path):
    tmp_path = tmp_path.resolve()
    source = tmp_path / "artifacts"
    source.mkdir()
    binary = source / "tool"
    binary.write_bytes(b"first-party inert executable fixture; never launched\n")
    license_file = source / "LICENSE"
    license_file.write_text("first-party test data only\n")
    sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    platform = sorted(install_runtime.host_platforms())[0]
    item = manifest(
        platforms=(platform,), source=manifest().source.model_dump() | {"artifact_sha256": sha}
    )
    rules = policy(item, platform=platform)
    selected = preview(ExtensionRegistry(extensions=(item,)), ("engine",), rules)
    files = tuple(
        file_runtime.RuntimeFile(
            extension_id="engine",
            source=name,
            destination=destination,
            sha256=hashlib.sha256((source / name).read_bytes()).hexdigest(),
            size_bytes=(source / name).stat().st_size,
            primary=primary,
            executable=primary,
        )
        for name, destination, primary in [
            ("tool", "bin/tool", True),
            ("LICENSE", "licenses/engine.txt", False),
        ]
    )
    return file_runtime.prepare_files(selected, rules, tmp_path / "runtime", source, files)


def test_owned_file_lifecycle_never_executes_and_preserves_edits(tmp_path, monkeypatch):
    monkeypatch.setattr(
        install_runtime.subprocess,
        "Popen",
        lambda *a, **kw: pytest.fail("file setup ran a process"),
    )
    plan = installation(tmp_path)
    before = install_runtime.snapshot(tmp_path.resolve())
    again = file_runtime.prepare_files(
        plan.preview, plan.policy, Path(plan.destination), Path(plan.artifact_root), plan.files
    )
    assert again == plan and install_runtime.snapshot(tmp_path.resolve()) == before
    state = install_runtime.apply(plan, install_runtime.digest(plan))
    assert (
        state["status"] == "installed" and state["qualified"] is False and state["enabled"] is False
    )
    assert install_runtime.apply(plan, install_runtime.digest(plan)) == state
    root = Path(plan.destination)
    assert (root / "bin/tool").read_bytes() == (Path(plan.artifact_root) / "tool").read_bytes()
    assert stat.S_IMODE((root / "bin/tool").stat().st_mode) == 0o555
    assert stat.S_IMODE((root / "licenses/engine.txt").stat().st_mode) == 0o444
    (root / "user-note").write_text("preserve this edit")
    with pytest.raises(ValueError, match="preserved"):
        install_runtime.remove(plan, install_runtime.digest(plan))
    assert (root / "user-note").read_text() == "preserve this edit"
    (root / "user-note").unlink()
    removed = install_runtime.remove(plan, install_runtime.digest(plan))
    assert removed["status"] == "removed" and not root.exists()
    assert install_runtime.remove(plan, install_runtime.digest(plan)) == removed
    assert install_runtime.paths(plan)[1].exists()
    with pytest.raises(ValueError, match="no automatic retry"):
        install_runtime.apply(plan, install_runtime.digest(plan))


@pytest.mark.parametrize(
    "path",
    [
        ".",
        "/absolute",
        "a/../b",
        "a//b",
        "a\\b",
        ".codex/auth.json",
        ".ssh/id_rsa",
        ".docker/config.json",
        "auth.json",
        "credentials.json",
        ".env.local",
    ],
)
def test_file_paths_exclude_escape_and_credential_state(path):
    with pytest.raises(ValueError):
        file_runtime.RuntimeFile(
            extension_id="engine",
            source=path,
            destination="bin/tool",
            sha256="a" * 64,
            size_bytes=1,
            primary=True,
        )


@pytest.mark.parametrize(
    "change", ["hash", "size", "source-link", "source-hardlink", "existing", "review", "installer"]
)
def test_drift_stops_before_installation_effects(tmp_path, change):
    plan = installation(tmp_path)
    binary = Path(plan.artifact_root) / "tool"
    review = install_runtime.digest(plan)
    if change == "hash":
        binary.write_bytes(b"different")
    elif change == "size":
        plan.files[0].size_bytes += 1
        review = install_runtime.digest(plan)
    elif change == "source-link":
        binary.unlink()
        binary.symlink_to(Path(plan.artifact_root) / "LICENSE")
    elif change == "source-hardlink":
        os.link(binary, binary.with_name("alias"))
    elif change == "existing":
        Path(plan.destination).mkdir()
        (Path(plan.destination) / "user").write_text("preserve")
    elif change == "review":
        review = "0" * 64
    else:
        plan.installer_python_sha256 = "0" * 64
        review = install_runtime.digest(plan)
    with pytest.raises((ValueError, OSError)):
        install_runtime.apply(plan, review)
    assert not install_runtime.paths(plan)[1].exists()
    if change == "existing":
        assert (Path(plan.destination) / "user").read_text() == "preserve"


def test_file_failure_is_durable_without_automatic_retry(tmp_path, monkeypatch):
    plan = installation(tmp_path)
    chmod = Path.chmod

    def fail_after_copy(path, mode, **kwargs):
        if str(path).endswith("runtime/bin/tool"):
            raise OSError("first-party interrupted setup fixture")
        return chmod(path, mode, **kwargs)

    monkeypatch.setattr(Path, "chmod", fail_after_copy)
    with pytest.raises(OSError):
        install_runtime.apply(plan, install_runtime.digest(plan))
    assert install_runtime.load_state(install_runtime.paths(plan)[1])[1]["status"] == "failed"
    assert (Path(plan.destination) / "bin/tool").exists()
    with pytest.raises(ValueError, match="no automatic retry"):
        install_runtime.apply(plan, install_runtime.digest(plan))
    with pytest.raises(ValueError, match="preserved"):
        install_runtime.remove(plan, install_runtime.digest(plan))


def test_file_manifest_requires_primary_identity_and_unique_targets(tmp_path):
    plan = installation(tmp_path)
    value = plan.model_dump(mode="json")
    value["files"][0]["primary"] = False
    with pytest.raises(ValueError, match="primary"):
        file_runtime.FileRuntimeInstallation.model_validate(value)
    value = plan.model_dump(mode="json")
    value["files"][1]["destination"] = "BIN/tool"
    with pytest.raises(ValueError, match="collide"):
        file_runtime.FileRuntimeInstallation.model_validate(value)


def test_cli_prepares_and_installs_file_plan_without_new_commands(tmp_path, capsys):
    plan = installation(tmp_path)
    for name, value in [
        ("preview", plan.preview.model_dump(mode="json")),
        ("policy", plan.policy.model_dump(mode="json")),
        ("files", [f.model_dump(mode="json") for f in plan.files]),
    ]:
        (tmp_path / (name + ".json")).write_text(json.dumps(value))
    assert (
        main(
            [
                "install-files-plan",
                "--preview",
                str(tmp_path / "preview.json"),
                "--policy",
                str(tmp_path / "policy.json"),
                "--files",
                str(tmp_path / "files.json"),
                "--artifact-root",
                plan.artifact_root,
                "--destination",
                plan.destination,
            ]
        )
        == 0
    )
    document = json.loads(capsys.readouterr().out)
    assert document["installation"] == plan.model_dump(mode="json")
    path = tmp_path / "installation.json"
    path.write_text(json.dumps(document))
    assert (
        main(
            ["install", "--installation", str(path), "--reviewed-digest", document["review_sha256"]]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "installed"
    assert (
        main(
            ["remove", "--installation", str(path), "--reviewed-digest", document["review_sha256"]]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "removed"
