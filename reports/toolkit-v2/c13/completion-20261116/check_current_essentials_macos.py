"""Prepare and run one contained lifecycle rehearsal for the exact current Essentials wheel."""

import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from check_linux_install import HERE, WORK, get, put
from prepare_current_essentials import NATIVE, RESERVE, STAGING

from aeep.assessment.verification import verification_source_digest
from aeep.models import utc_now
from aeep_toolkit.install_runtime import RuntimeInstallation, digest, file_digest
from aeep_toolkit.stack_verification import ROOT

MAC = STAGING / "macos"
PLAN = MAC / "installation.json"
FIXTURE = MAC / "fixture"
RESULTS = STAGING / "macos-execution"
REVIEW = HERE / "current-essentials-macos-operation-review.json"
APPROVAL = STAGING / "macos-approval.json"
SANDBOX = Path("/usr/bin/sandbox-exec")
PROFILE = MAC / "sandbox.sb"
RUNTIME = NATIVE / "runtime"
ALLOWED_PHASES = (
    "install",
    "idempotent",
    "source",
    "candidate",
    "markdown",
    "html",
    "remove",
)
CAP_SECONDS = 740
PROBE = """
import os, socket, sys
from pathlib import Path
def denied(f):
    try:
        f()
    except PermissionError:
        return
    raise AssertionError('sandbox permitted a prohibited operation')
root, unrelated, forbidden = map(Path, sys.argv[1:])
assert root.resolve() == root
assert (root / 'canary').read_text() == 'keep'
with (root / 'allowed').open('x') as f:
    f.write('tested')
with socket.socket() as sock:
    denied(lambda: sock.bind(('127.0.0.1', 0)))
denied(unrelated.read_bytes)
denied(lambda: forbidden.write_text('fail'))
"""

REPORT_IDENTITY = (
    "from pathlib import Path; import aeep.assessment.verification as v; "
    "print(v.verification_source_digest(Path(v.__file__).resolve().parents[3]))"
)


def space():
    if shutil.disk_usage(NATIVE).free < RESERVE:
        raise ValueError("native lifecycle reached the host reserve")


def sandbox_policy():
    quoted = json.dumps
    lines = [
        "(version 1)",
        "(allow default)",
        "(deny network*)",
        "(deny file-write*)",
        '(allow file-write* (literal "/dev/null"))',
        f"(allow file-write* (subpath {quoted(str(NATIVE))}))",
        f"(deny file-read* (subpath {quoted(str(Path.home()))}) "
        '(subpath "/private/tmp") (subpath "/private/var/folders"))',
    ]
    for root in (NATIVE, MAC, ROOT):
        lines.append(f"(allow file-read* (subpath {quoted(str(root))}))")
        for path in root.parents:
            lines.append(f"(allow file-read-metadata (literal {quoted(str(path))}))")
    return "\n".join(lines) + "\n"


def environment():
    return {
        "HOME": str(NATIVE),
        "TMPDIR": str(NATIVE),
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PIP_NO_INDEX": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    }


def definitions():
    expected = get(STAGING / "results.json")
    outer = get(PLAN)
    plan = RuntimeInstallation.model_validate(outer["installation"])
    if (
        digest(plan) != outer["review_sha256"]
        or plan.destination != str(RUNTIME)
        or outer["review_sha256"] != expected["macos_plan_sha256"]
        or file_digest(Path(plan.interpreter)) != plan.interpreter_sha256
        or verification_source_digest(ROOT) != expected["implementation_source"]
        or PROFILE.read_text() != sandbox_policy()
    ):
        raise ValueError("current native installation changed")
    local = [str(SANDBOX), "-f", str(PROFILE)]
    operator = [*local, plan.interpreter, "-B", "-m", "aeep_toolkit"]
    installed = [*local, str(RUNTIME / "bin/python"), "-I", "-B"]
    commands = {
        "install": [
            *operator,
            "install",
            "--installation",
            str(PLAN),
            "--reviewed-digest",
            outer["review_sha256"],
        ],
        "remove": [
            *operator,
            "remove",
            "--installation",
            str(PLAN),
            "--reviewed-digest",
            outer["review_sha256"],
        ],
        "source": [*installed, "-c", REPORT_IDENTITY],
        "candidate": [
            *installed,
            "-m",
            "aeep_toolkit",
            "candidate",
            str(FIXTURE / "candidate"),
            "--stage",
            str(NATIVE / "staged-candidate"),
        ],
    }
    commands["idempotent"] = commands["install"]
    for fmt in ("markdown", "html"):
        commands[fmt] = [
            *installed,
            "-m",
            "aeep_toolkit",
            "report",
            "--evidence",
            str(FIXTURE / "evidence.json"),
            "--format",
            fmt,
        ]
    files = [
        Path(__file__),
        SANDBOX,
        PROFILE,
        PLAN,
        STAGING / "results.json",
        FIXTURE / "candidate/SKILL.md",
        FIXTURE / "evidence.json",
        HERE / "macos-private-rollback-result.json",
        HERE / "linux-private-install-result.json",
    ]
    pin = {str(path): file_digest(path) for path in files}
    for wheel in plan.wheels:
        artifact = Path(plan.wheelhouse) / wheel.filename
        if file_digest(artifact) != wheel.sha256:
            raise ValueError("a wheel differs from the reviewed closure")
        pin[str(artifact)] = wheel.sha256
    return {
        "implementation_source": expected["implementation_source"],
        "purpose": "Private macOS arm64 Essentials install, report and rollback on the exact current wheel",
        "wheel_sha256": expected["wheel_sha256"],
        "installation_plan_ref": outer["review_sha256"],
        "expected_installed_source": expected["anticipated_installed_source"],
        "expected_report_hashes": expected["fixture_reports_equal_retained"],
        "expected_candidate": get(WORK / "beta-inspect.json")["candidate_sha256"],
        "native_runtime": str(RUNTIME),
        "phases": list(ALLOWED_PHASES),
        "commands": commands,
        "environment": environment(),
        "pins": pin,
        "wall_seconds": CAP_SECONDS,
        "maximum_install_attempts": 1,
        "maximum_rollback_attempts": 1,
        "idempotent_apply_requires_completed_install": True,
        "models": 0,
        "cash_usd": 0,
        "downloads": 0,
        "existing_resources_removed": 0,
    }


def boundary_probe():
    # Synthetic local file outside the sandbox's read/write roots.
    unrelated = STAGING / "native-boundary-unrelated.txt"
    unrelated.write_text("unrelated synthetic file\n")
    outside = unrelated.with_suffix(".unwritable")
    probe = NATIVE / "sandbox-probe"
    probe.mkdir(mode=0o700)
    (probe / "canary").write_text("keep")
    plan = get(PLAN)["installation"]
    subprocess.run(
        [
            str(SANDBOX),
            "-f",
            str(PROFILE),
            plan["interpreter"],
            "-I",
            "-B",
            "-c",
            PROBE,
            str(probe),
            str(unrelated),
            str(outside),
        ],
        env=environment(),
        cwd=NATIVE,
        stdin=subprocess.DEVNULL,
        timeout=30,
        check=True,
    )
    if outside.exists() or unrelated.read_text() != "unrelated synthetic file\n":
        raise ValueError("boundary probe unexpectedly affected its neighboring file")
    return {
        "local_scratch": True,
        "outside_read_denied": True,
        "outside_write_denied": True,
        "network_bind_denied": True,
    }


def prepare():
    if REVIEW.exists() or RESULTS.exists() or list(NATIVE.iterdir()):
        raise ValueError("expected an unstarted native runtime destination")
    space()
    FIXTURE.mkdir(mode=0o700)
    (FIXTURE / "candidate").mkdir(mode=0o700)
    for path in ("evidence.json", "candidate/SKILL.md"):
        shutil.copyfile(WORK / "beta-check" / path, FIXTURE / path)
    with PROFILE.open("x") as out:
        out.write(sandbox_policy())
    boundary = boundary_probe()
    checked = definitions()
    put(STAGING / "macos-boundary-preflight.json", boundary)
    put(
        REVIEW,
        {
            **checked,
            "boundary_preflight_sha256": file_digest(STAGING / "macos-boundary-preflight.json"),
            "expires_at": (utc_now() + timedelta(days=4)).isoformat(),
        },
    )
    print(file_digest(REVIEW))


def preflight(exact):
    if file_digest(REVIEW) != exact:
        raise ValueError("exact native review differs")
    reviewed = get(REVIEW)
    expires = datetime.fromisoformat(reviewed.pop("expires_at"))
    boundary = reviewed.pop("boundary_preflight_sha256")
    if (
        expires <= utc_now()
        or reviewed != definitions()
        or boundary != file_digest(STAGING / "macos-boundary-preflight.json")
    ):
        raise ValueError("native runtime review expired or inputs changed")
    space()
    return reviewed


def launch(exact):
    if RESULTS.exists() or get(APPROVAL) != {"approved": True, "review_sha256": exact}:
        raise ValueError("native lifecycle requires its exact approval and an unstarted attempt")
    review = preflight(exact)
    if RUNTIME.exists() or (NATIVE / "runtime.aeep-install.json").exists():
        raise ValueError("native destination is occupied")
    RESULTS.mkdir(mode=0o700)
    expires = time.monotonic() + review["wall_seconds"]
    canary = NATIVE / "neighbor"
    with canary.open("x") as stream:
        stream.write("Keep this file through rollback.\n")
    retained = file_digest(canary)
    observations = {}
    for phase in review["phases"]:
        preflight(exact)
        if get(APPROVAL) != {"approved": True, "review_sha256": exact}:
            raise ValueError("native operation authorization changed")
        remaining = expires - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("reviewed lifecycle time elapsed")
        result = subprocess.run(
            review["commands"][phase],
            cwd=NATIVE,
            env=review["environment"],
            timeout=remaining,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        (RESULTS / f"{phase}.stdout").write_bytes(result.stdout)
        (RESULTS / f"{phase}.stderr").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError("native lifecycle stopped; preserve the owned runtime and journal")
        if phase in {"markdown", "html"}:
            if file_digest(RESULTS / f"{phase}.stdout") != review["expected_report_hashes"][phase]:
                raise ValueError("installed report differs from the retained evidence")
        elif phase == "source":
            if result.stdout.decode().strip() != review["expected_installed_source"]:
                raise ValueError("installed runtime source differs from the wheel")
        else:
            state = json.loads(result.stdout)
            if phase == "install" and state["status"] != "installed":
                raise ValueError("native install state is indeterminate")
            if phase == "idempotent" and state != observations["install"]:
                raise ValueError("re-applying an unchanged plan altered its journal")
            if phase == "candidate" and (
                state["executed"] or state["candidate_sha256"] != review["expected_candidate"]
            ):
                raise ValueError("installed candidate inspection changed")
            if phase == "remove" and (
                state["status"] != "removed"
                or RUNTIME.exists()
                or get(NATIVE / "runtime.aeep-install.json") != state
            ):
                raise ValueError("native removal state is indeterminate")
            observations[phase] = state
    if file_digest(canary) != retained:
        raise ValueError("rollback affected the neighboring file")
    put(
        RESULTS / "result.json",
        {
            "passed": True,
            "review_sha256": exact,
            "operations": 7,
            "installed_source": review["expected_installed_source"],
            "rollback_preserved_neighbor": True,
            "models": 0,
            "cash_usd": 0,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--preflight")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    os.umask(0o077)
    if args.prepare:
        prepare()
    elif args.exact_review:
        launch(args.exact_review)
    else:
        preflight(args.preflight)
        print(args.preflight)


if __name__ == "__main__":
    main()
