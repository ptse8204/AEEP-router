"""Check the audited intake wheel using the established private Essentials lifecycle."""

import argparse
import io
import os
import shutil
import subprocess
import time
from datetime import timedelta
from pathlib import Path
from tarfile import open as open_tar
from zipfile import ZipFile

import check_current_essentials_macos as lifecycle
import check_linux_install as linux
from check_linux_install import get, put
from prepare_current_essentials import installed_identity, refresh_manifests
from rebind_current_stack import SOURCE_SCOPE
from rebind_intake_stack import COMMIT, CURRENT, CURRENT_SOURCE, REPO, WHEEL_HASH

from aeep.assessment.verification import verification_source_digest
from aeep.models import utc_now
from aeep_toolkit.install_runtime import (
    RuntimeInstallation,
    check_closure,
    digest,
    file_digest,
    prepare,
)
from aeep_toolkit.installation import PreviewPolicy, manifest_digest, preview
from aeep_toolkit.models import ExtensionRegistry
from aeep_toolkit.stack_verification import ROOT

WORK = lifecycle.WORK
STAGING = REPO / ".aeep/c13-intake-wheel-20261124"
NATIVE = Path("/private/tmp/aeep-c13-intake-native-20261124")
WHEEL = CURRENT / "corrected/dist/aeep_agent_router-0.8.2-py3-none-any.whl"
RESERVE = 52 * 2**30
AUTHORITY = WORK.parents[1] / "reports/toolkit-v2/c13/pipeline-standing-authority-20261104.json"


def check_macos():
    os.umask(0o077)
    free_before = min(shutil.disk_usage(path).free for path in (REPO, NATIVE.parent))
    if verification_source_digest(ROOT) != CURRENT_SOURCE or file_digest(WHEEL) != WHEEL_HASH:
        raise ValueError("current source or wheel has drifted")
    if free_before < RESERVE + 2**30 or STAGING.exists() or NATIVE.exists():
        raise ValueError("expected fresh paths and headroom for the pinned closure")

    lifecycle.ROOT = ROOT
    lifecycle.STAGING = STAGING
    lifecycle.NATIVE = NATIVE
    lifecycle.MAC = STAGING / "macos"
    lifecycle.PLAN = lifecycle.MAC / "installation.json"
    lifecycle.FIXTURE = lifecycle.MAC / "fixture"
    lifecycle.RESULTS = STAGING / "execution"
    lifecycle.REVIEW = STAGING / "operation-review.json"
    lifecycle.APPROVAL = STAGING / "delegated-launch-binding.json"
    lifecycle.PROFILE = lifecycle.MAC / "sandbox.sb"
    lifecycle.RUNTIME = NATIVE / "runtime"
    lifecycle.RESERVE = RESERVE

    STAGING.mkdir(mode=0o700)
    NATIVE.mkdir(mode=0o700)
    wheelhouse = lifecycle.MAC / "wheels"
    wheelhouse.mkdir(mode=0o700, parents=True)
    earlier = WORK / "current-essentials"
    original = RuntimeInstallation.model_validate(
        get(earlier / "macos/installation.json")["installation"]
    )
    if (
        len(original.wheels) != 33
        or file_digest(Path(original.interpreter)) != original.interpreter_sha256
    ):
        raise ValueError("retained platform closure or interpreter changed")
    wheels = []
    for pin in original.wheels:
        if pin.extension_id == "aeep-agent-router":
            source = WHEEL
            pin = pin.model_copy(update={"sha256": WHEEL_HASH})
        else:
            source = Path(original.wheelhouse) / pin.filename
        if file_digest(source) != pin.sha256:
            raise ValueError("pinned archive drift")
        shutil.copyfile(source, wheelhouse / pin.filename)
        wheels.append(pin)
    pins = tuple(wheels)
    closure = check_closure(wheelhouse, pins, original.policy.platform)
    with ZipFile(WHEEL) as wheel:
        application_bytes = sum(entry.file_size for entry in wheel.infolist())
    manifests = tuple(
        item.model_copy(update={"disk_bytes": application_bytes})
        if item.extension_id == "aeep-agent-router"
        else item
        for item in refresh_manifests(original, CURRENT_SOURCE, WHEEL_HASH)
    )
    policy = PreviewPolicy.model_validate(
        {
            **original.policy.model_dump(mode="json"),
            "free_disk_bytes": RESERVE,
            "reviewed_dependency_manifests": [manifest_digest(item) for item in manifests],
        }
    )
    selection = preview(
        ExtensionRegistry(extensions=manifests),
        original.preview.selected,
        policy,
        profile="essentials",
    )
    plan = prepare(selection, policy, lifecycle.RUNTIME, wheelhouse, pins)
    put(
        lifecycle.PLAN,
        {"review_sha256": digest(plan), "installation": plan.model_dump(mode="json")},
    )
    reports = get(earlier / "results.json")["fixture_reports_equal_retained"]
    put(
        STAGING / "results.json",
        {
            "implementation_source": CURRENT_SOURCE,
            "macos_plan_sha256": digest(plan),
            "wheel_sha256": WHEEL_HASH,
            "anticipated_installed_source": installed_identity(WHEEL),
            "fixture_reports_equal_retained": reports,
        },
    )

    # The established helper pins every command and checks the actual sandbox.
    lifecycle.prepare()
    exact = file_digest(lifecycle.REVIEW)
    review = lifecycle.preflight(exact)
    for format, expected in reports.items():
        completed = subprocess.run(
            [
                str(lifecycle.SANDBOX),
                "-f",
                str(lifecycle.PROFILE),
                plan.interpreter,
                "-B",
                "-m",
                "aeep_toolkit",
                "report",
                "--evidence",
                str(lifecycle.FIXTURE / "evidence.json"),
                "--format",
                format,
            ],
            env=review["environment"],
            cwd=NATIVE,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=True,
            timeout=30,
        )
        report = STAGING / f"source.{format}"
        report.write_bytes(completed.stdout)
        if file_digest(report) != expected:
            raise ValueError("current source report differs before private installation")

    put(
        STAGING / "execution-authority.json",
        {
            "review_sha256": exact,
            "standing_authority_path": str(AUTHORITY.relative_to(REPO)),
            "standing_authority_sha256": file_digest(AUTHORITY),
            "driver_sha256": file_digest(Path(__file__)),
            "scope": "First lifecycle check for the new committed first-party wheel, with the same reviewed cached dependency bytes. The operator directed completion of the remaining C13 work.",
            "previous_artifacts_preserved": True,
            "downloads": 0,
            "models": 0,
            "cash_usd": 0,
        },
    )
    put(lifecycle.APPROVAL, {"approved": True, "review_sha256": exact})
    started = time.monotonic()
    lifecycle.launch(exact)
    result = get(lifecycle.RESULTS / "result.json")
    put(
        STAGING / "summary.json",
        {
            **result,
            "wheel_sha256": WHEEL_HASH,
            "implementation_source": CURRENT_SOURCE,
            "plan_review_sha256": digest(plan),
            "phases": review["phases"],
            "unchanged_dependency_wheels": 32,
            "closure_bytes": closure,
            "before_free_bytes": free_before,
            "after_free_bytes": shutil.disk_usage(REPO).free,
            "wall_seconds": round(time.monotonic() - started, 3),
            "sandbox_preflight": get(STAGING / "macos-boundary-preflight.json"),
            "report_sha256": reports,
            "retained_install_journal_sha256": file_digest(NATIVE / "runtime.aeep-install.json"),
            "runtime_removed": not lifecycle.RUNTIME.exists(),
        },
    )


def check_linux():
    os.umask(0o077)
    mac = get(STAGING / "summary.json")
    previous = linux.HERE / "current-linux-wheel-operation-review-20261117.json"
    prior = get(previous)
    previous_result = get(WORK / "current-linux-wheel-lifecycle-20261117/result.json")
    if (
        not mac["passed"]
        or mac["wheel_sha256"] != WHEEL_HASH
        or not previous_result["passed"]
        or previous_result["review_sha256"] != file_digest(previous)
        or prior["layers"] != linux.verified_image()
    ):
        raise ValueError("Linux baseline or matching current macOS check differs")
    work = STAGING / "linux"
    host = Path("/private/tmp/aeep-c13-intake-linux-20261124")
    if (
        work.exists()
        or host.exists()
        or min(shutil.disk_usage(path).free for path in (STAGING, host.parent)) < RESERVE + 2**30
        or file_digest(WHEEL) != WHEEL_HASH
    ):
        raise ValueError("expected fresh Linux paths and audited wheel with sufficient headroom")

    linux.WORK, linux.HOST = work, host
    linux.FROZEN = work / "source"
    linux.ARTIFACTS, linux.OUTPUT = host / "inputs", host / "output"
    linux.NAME = host.name
    linux.ENV = linux.ENV | {"HOME": str(host)}
    linux.REVIEW, linux.RESULT = work / "operation-review.json", work / "result.json"
    if linux.docker("ps", "-aq", "--filter", f"name=^/{linux.NAME}$"):
        raise ValueError("Linux test container name is occupied")

    linux.FROZEN.mkdir(mode=0o700, parents=True)
    archive = subprocess.check_output(
        ["git", "archive", COMMIT, *SOURCE_SCOPE], cwd=REPO, timeout=30
    )
    with open_tar(fileobj=io.BytesIO(archive)) as source:
        source.extractall(linux.FROZEN, filter="data")
    if verification_source_digest(linux.FROZEN) != CURRENT_SOURCE:
        raise ValueError("Linux bootstrap archive differs from the committed source")

    host.mkdir(mode=0o700)
    for path in (linux.ARTIFACTS, linux.ARTIFACTS / "wheels", linux.ARTIFACTS / "candidate"):
        path.mkdir(mode=0o755)
    linux.OUTPUT.mkdir(mode=0o700)
    linux.OUTPUT.chmod(0o777)
    inputs = {
        "guest.py": linux.HERE / "linux_install_guest.py",
        "evidence.json": STAGING / "macos/fixture/evidence.json",
        "candidate/SKILL.md": STAGING / "macos/fixture/candidate/SKILL.md",
    }
    retained_linux = WORK / "current-essentials/linux"
    wheels = get(retained_linux / "linux-wheels.json")
    for wheel in wheels:
        name = wheel["filename"]
        if wheel["extension_id"] == "aeep-agent-router":
            inputs[f"wheels/{name}"] = WHEEL
            wheel["sha256"] = WHEEL_HASH
        else:
            inputs[f"wheels/{name}"] = retained_linux / "wheels" / name
    for name, path in inputs.items():
        expected = WHEEL_HASH if path == WHEEL else prior["inputs"][name]
        if file_digest(path) != expected:
            raise ValueError(f"Linux input differs from its reviewed bytes: {name}")
        shutil.copyfile(path, linux.ARTIFACTS / name)

    shutil.copyfile(STAGING / "macos/installation.json", linux.ARTIFACTS / "mac-installation.json")
    put(linux.ARTIFACTS / "linux-wheels.json", wheels)
    put(
        linux.ARTIFACTS / "expected.json",
        {
            "installed_source": mac["installed_source"],
            "candidate": previous_result["candidate_sha256"],
            "skill": prior["inputs"]["candidate/SKILL.md"],
            "reports": mac["report_sha256"],
        },
    )
    if set(linux.inputs()) != set(prior["inputs"]):
        raise ValueError("Linux staged input inventory differs")
    for path in linux.ARTIFACTS.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    linux.ARTIFACTS.chmod(0o555)
    put(
        linux.REVIEW,
        prior
        | {
            "purpose": "First Linux ARM64 lifecycle of the reviewed intake wheel",
            "source": CURRENT_SOURCE,
            "expected_installed_source": mac["installed_source"],
            "wheel_sha256": WHEEL_HASH,
            "inputs": linux.inputs(),
            "input_preflight_sha256": file_digest(STAGING / "summary.json"),
            "launcher": file_digest(Path(linux.__file__)),
            "wrapper_sha256": file_digest(Path(__file__)),
            "docker": file_digest(Path(linux.DOCKER)),
            "create": linux.create_argv(),
            "expires_at": (utc_now() + timedelta(days=1)).isoformat(),
        },
    )
    exact = file_digest(linux.REVIEW)
    put(
        work / "execution-authority.json",
        {
            "review_sha256": exact,
            "standing_authority_sha256": file_digest(AUTHORITY),
            "scope": "First private Linux compatibility check of this exact wheel using the reviewed offline carrier and cached closure. Existing resources and previous outcomes are preserved.",
        },
    )
    put(
        work / "linux-install-package-bridge-approval.json",
        {"approved": True, "review_sha256": exact},
    )
    linux.run(exact)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=("macos", "linux"))
    args = parser.parse_args()
    if args.platform == "macos":
        check_macos()
    else:
        check_linux()
