"""Synthetic storage observations; these do not measure a real installation."""

import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_toolkit_runtime_install import fake_install, installation

from aeep_toolkit import install_runtime as runtime
from aeep_toolkit.cli import main
from aeep_toolkit.installation import preview
from aeep_toolkit.models import ExtensionRegistry
from aeep_toolkit.storage import StorageReserveException

GIB = 1024**3
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="private runtime installation requires POSIX no-follow paths")


class FixtureDisk:
    def __init__(self, free):
        self.free = free

    def disk_usage(self, _path):
        return SimpleNamespace(free=self.free)

    def __getattr__(self, name):
        return getattr(shutil, name)


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    disk = FixtureDisk(60 * GIB)
    monkeypatch.setattr(runtime, "shutil", disk)
    legacy = installation(tmp_path)
    exception = StorageReserveException(
        exception_id="synthetic-test-only", destination=legacy.destination,
        filesystem_device=tmp_path.stat().st_dev,
        wheel_set_sha256=runtime.digest([w.model_dump(mode="json") for w in legacy.wheels]),
        minimum_free_bytes=42 * GIB, maximum_additional_bytes=GIB,
        issued_at=datetime.now(UTC) - timedelta(minutes=1),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    disk.free = 43 * GIB
    return legacy, exception, disk


def prepare(inputs, exception=None):
    legacy, original, _disk = inputs
    policy = legacy.policy.model_copy(update={"free_disk_bytes": 43 * GIB})
    selection = preview(ExtensionRegistry(extensions=tuple(i.manifest for i in legacy.preview.items)),
                        legacy.preview.selected, policy)
    assert selection.status == "blocked"
    return runtime.prepare(selection, policy, Path(legacy.destination), Path(legacy.wheelhouse),
                           legacy.wheels, storage_exception=exception or original)


def test_v1_review_bytes_remain_unchanged():
    root = Path(__file__).resolve().parents[1]
    folder = root / "reports/toolkit-v2/c13/workflow-scanner-20261102"
    value = json.loads((folder / "package-installation.json").read_bytes())
    plan = runtime.RuntimeInstallation.model_validate(value)
    assert plan.model_dump(mode="json") == value
    old_review = json.loads((folder / "operation-review.json").read_bytes())
    assert runtime.digest(plan) == old_review["package"]["installation_digest"]


def test_scoped_preview_retains_real_declared_free_space(inputs):
    plan = prepare(inputs)
    assert plan.schema_version.endswith(".v2")
    assert plan.preview.schema_version.endswith(".v2")
    assert plan.policy.free_disk_bytes == 43 * GIB
    assert plan.preview.storage_exception_sha256 == plan.storage_exception.digest()
    assert not Path(plan.destination).exists()
    assert not runtime.paths(plan)[1].exists()


@pytest.mark.parametrize("change", ["destination", "wheels", "filesystem", "expiry", "budget"])
def test_wrong_scope_and_expired_exception_prevent_effects(inputs, change):
    legacy, exception, _disk = inputs
    data = exception.model_dump(mode="json")
    if change == "destination":
        data["destination"] += "-other"
    elif change == "wheels":
        data["wheel_set_sha256"] = "0" * 64
    elif change == "filesystem":
        data["filesystem_device"] += 1
    elif change == "budget":
        data["maximum_additional_bytes"] = 100
    else:
        data["issued_at"] = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        data["expires_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError):
        prepare(inputs, StorageReserveException.model_validate(data))
    assert not Path(legacy.destination).exists()
    assert not runtime.paths(legacy)[1].exists()


def test_default_policy_still_refuses_below_fifty(inputs):
    legacy, _exception, _disk = inputs
    with pytest.raises(ValueError, match="50 GiB"):
        runtime.prepare(legacy.preview, legacy.policy, Path(legacy.destination),
                        Path(legacy.wheelhouse), legacy.wheels)


def test_low_real_capacity_and_wrong_review_refuse_before_effects(inputs, monkeypatch):
    plan = prepare(inputs)
    _legacy, _exception, disk = inputs
    fake_install(monkeypatch)
    with pytest.raises(ValueError, match="exact installation review"):
        runtime.apply(plan, "f" * 64)
    disk.free = 42 * GIB + 100
    with pytest.raises(ValueError, match="insufficient real capacity"):
        runtime.apply(plan, runtime.digest(plan))
    assert not Path(plan.destination).exists()
    assert not runtime.paths(plan)[1].exists()


@pytest.mark.parametrize(("initial_free", "free_after_create"), [
    (43 * GIB, 42 * GIB - 1), (44 * GIB, 42 * GIB + GIB // 2),
])
def test_capacity_loss_retains_failed_journal_and_refuses_replay(inputs, monkeypatch, initial_free, free_after_create):
    plan = prepare(inputs)
    _legacy, _exception, disk = inputs
    disk.free = initial_free
    fake_install(monkeypatch)

    def create(_builder, target):
        (target / "payload.txt").write_text("owned fixture")
        disk.free = free_after_create

    monkeypatch.setattr(runtime.venv.EnvBuilder, "create", create)
    with pytest.raises(ValueError, match="insufficient real capacity"):
        runtime.apply(plan, runtime.digest(plan))
    state = runtime.load_state(runtime.paths(plan)[1])[1]
    assert state["status"] == "failed" and state["storage_checks"]
    assert state["storage_checks"][-1]["accepted"] is False
    assert state["storage_checks"][-1]["available_free_bytes"] == free_after_create
    assert (Path(plan.destination) / "payload.txt").read_text() == "owned fixture"
    disk.free = 43 * GIB
    with pytest.raises(ValueError, match="no automatic retry"):
        runtime.apply(plan, runtime.digest(plan))


def test_success_keeps_measurements_and_expiry_does_not_prevent_removal(inputs, monkeypatch):
    plan = prepare(inputs)
    fake_install(monkeypatch)
    state = runtime.apply(plan, runtime.digest(plan))
    assert state["status"] == "installed"
    assert all(row["available_free_bytes"] == 43 * GIB for row in state["storage_checks"])
    assert runtime.apply(plan, runtime.digest(plan)) == state
    import datetime as std_datetime

    class FutureClock:
        @staticmethod
        def now(_tz):
            return std_datetime.datetime.now(UTC) + timedelta(hours=2)

    monkeypatch.setattr(runtime, "datetime", FutureClock)
    assert runtime.remove(plan, runtime.digest(plan))["status"] == "removed"


def test_permission_and_version_guards_are_preserved(inputs):
    legacy, exception, _disk = inputs
    invalid = legacy.model_dump(mode="json") | {"storage_exception": exception.model_dump(mode="json")}
    with pytest.raises(ValueError, match="v2"):
        runtime.RuntimeInstallation.model_validate(invalid)
    policy = legacy.policy.model_copy(update={"allowed_licenses": ()})
    with pytest.raises(ValueError, match="installation blocked"):
        runtime.prepare(legacy.preview, policy, Path(legacy.destination), Path(legacy.wheelhouse),
                        legacy.wheels, storage_exception=exception)
    long_window = exception.model_dump(mode="json") | {
        "expires_at": (exception.issued_at + timedelta(days=2)).isoformat(),
    }
    with pytest.raises(ValueError, match="24 hours"):
        StorageReserveException.model_validate(long_window)


def test_cli_prepares_exception_without_installing(inputs, tmp_path, capsys):
    legacy, exception, _disk = inputs
    for name, value in [("preview", legacy.preview.model_dump(mode="json")),
                        ("policy", legacy.policy.model_dump(mode="json")),
                        ("wheels", [w.model_dump(mode="json") for w in legacy.wheels]),
                        ("exception", exception.model_dump(mode="json"))]:
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    main(["install-plan", "--preview", str(tmp_path / "preview.json"),
          "--policy", str(tmp_path / "policy.json"), "--wheels", str(tmp_path / "wheels.json"),
          "--wheelhouse", legacy.wheelhouse, "--destination", legacy.destination,
          "--storage-exception", str(tmp_path / "exception.json")])
    value = json.loads(capsys.readouterr().out)
    assert value["installation"]["storage_exception"]["exception_id"] == exception.exception_id
    assert not Path(legacy.destination).exists()
