"""Stage and verify one reviewed Linux lifecycle for the current Essentials wheel."""

import argparse
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import check_linux_install as runner

from aeep.assessment.verification import verification_source_digest
from aeep.models import utc_now
from aeep_toolkit.install_runtime import file_digest

HERE, ROOT, PREVIOUS_WORK = runner.HERE, runner.ROOT, runner.WORK
WORK = PREVIOUS_WORK / "current-linux-wheel-lifecycle-20261117"
HOST = Path("/private/tmp/aeep-c13-linux-wheel-20261117")
SOURCE = PREVIOUS_WORK / "formal-document-native-20261117/committable-source"
PREVIOUS_REVIEW = runner.REVIEW
PREVIOUS_INPUTS = runner.ARTIFACTS
PRIOR_RESULT = runner.RESULT
INPUTS = HERE / "current-linux-wheel-inputs-20261117.json"
REVIEW = HERE / "current-linux-wheel-operation-review-20261117.json"
RESULT = WORK / "result.json"
APPROVAL = WORK / "linux-install-package-bridge-approval.json"
EXECUTION = WORK / "linux-install-package-bridge-execution"
FLOOR = 52 * 1024**3
APP_WHEEL = "aeep_agent_router-0.8.2-py3-none-any.whl"


def select_attempt() -> None:
    runner.WORK, runner.FROZEN, runner.HOST = WORK, SOURCE, HOST
    runner.ARTIFACTS, runner.OUTPUT = HOST / "inputs", HOST / "output"
    runner.REVIEW, runner.RESULT = REVIEW, RESULT
    runner.NAME = HOST.name
    runner.ENV = runner.ENV | {"HOME": str(HOST)}


def checked_ref(ref: dict) -> Path:
    path = ROOT / ref["path"]
    if not path.is_relative_to(ROOT) or path.resolve() != path or file_digest(path) != ref["sha256"]:
        raise ValueError("retained installation input differs")
    return path


def review_fields() -> dict:
    record = runner.get(INPUTS)
    old = runner.get(PREVIOUS_REVIEW)
    prior = runner.get(PRIOR_RESULT)
    if (prior["review_sha256"] != file_digest(PREVIOUS_REVIEW) or not prior["passed"]
            or old["carrier"] != record["target"]["image"] or old["carrier"] != runner.IMAGE
            or old["layers"] != runner.verified_image()
            or verification_source_digest(SOURCE) != record["application_source"]):
        raise ValueError("prior run, carrier or current source binding changed")
    bootstrap = SOURCE / "src"
    if bootstrap.resolve() != bootstrap or any(
        path.is_symlink() or not (path.is_dir() or path.is_file())
        or path.name in {"__pycache__", "sitecustomize.py", "usercustomize.py", ".env", ".codex"}
        or path.suffix in {".pyc", ".pth"}
        for path in bootstrap.rglob("*")
    ):
        raise ValueError("unreviewed entry in read-only bootstrap")
    return old | {
        "schema_version": "aeep.c13.current-linux-wheel-review.v1",
        "purpose": "Install, reapply, inspect, report and remove the exact current Essentials wheel in one fresh offline Linux container",
        "source": record["application_source"],
        "expected_installed_source": record["expected_installed_source"],
        "wheel_sha256": runner.inputs()[f"wheels/{APP_WHEEL}"],
        "inputs": runner.inputs(),
        "input_preflight_sha256": file_digest(INPUTS),
        "launcher": file_digest(Path(runner.__file__)),
        "wrapper_sha256": file_digest(Path(__file__)),
        "docker": file_digest(Path(runner.DOCKER)),
        "create": runner.create_argv(),
        "previous_review_sha256": prior["review_sha256"],
        "previous_result_sha256": file_digest(PRIOR_RESULT),
        "max_reserved_seconds": runner.LIMIT_SECONDS + 30,
        "min_usable_space_bytes": FLOOR,
        "max_containers_created": 1,
        "max_private_install_attempts": 1,
        "automatic_retry": False,
        "owned_cleanup_only": True,
    }


def prepare() -> None:
    if REVIEW.exists() or WORK.exists() or HOST.exists() or min(
        shutil.disk_usage(parent).free for parent in (HOST.parent, PREVIOUS_WORK)
    ) < FLOOR + 32 * 1024**2:
        raise ValueError("fresh preparation paths and host headroom are required")
    record = runner.get(INPUTS)
    old = runner.get(PREVIOUS_REVIEW)
    expected = runner.get(PREVIOUS_INPUTS / "expected.json")
    for name in ("evidence.json", "candidate/SKILL.md", "guest.py", "expected.json", "linux-wheels.json"):
        path = PREVIOUS_INPUTS / name
        if path.resolve() != path or file_digest(path) != old["inputs"][name]:
            raise ValueError("previously executed fixture or guest differs")
    prior_result = checked_ref(record["prior_linux_lifecycle"])
    if prior_result != PRIOR_RESULT or expected["reports"] != record["fixture_report_hashes"]:
        raise ValueError("fixture or previous run differs from verified input record")
    selected = {row["filename"]: row["artifact"] for row in record["selected_wheels"]}
    wheels = runner.get(PREVIOUS_INPUTS / "linux-wheels.json")
    if len(selected) != 33 or set(selected) != {row["filename"] for row in wheels}:
        raise ValueError("exact 33-wheel closure required")
    if any(row["sha256"] != selected[row["filename"]]["sha256"]
           for row in wheels if row["filename"] != APP_WHEEL):
        raise ValueError("a dependency changed from the tested Linux closure")
    sources = {name: checked_ref(ref) for name, ref in selected.items()}
    mac_plan = checked_ref(record["current_macos_installation_plan"])
    mac = runner.get(checked_ref(record["current_macos_lifecycle"]))
    if mac["wheel_sha256"] != selected[APP_WHEEL]["sha256"] or mac["status"] != "PASSED":
        raise ValueError("app wheel lacks its retained macOS lifecycle result")
    if runner.docker("ps", "-aq", "--filter", f"name=^/{runner.NAME}$"):
        raise ValueError("reviewed container name is already occupied")

    WORK.mkdir(mode=0o700)
    HOST.mkdir(mode=0o700)
    for folder in (runner.ARTIFACTS, runner.ARTIFACTS / "wheels", runner.ARTIFACTS / "candidate"):
        folder.mkdir(mode=0o755)
    runner.OUTPUT.mkdir(mode=0o700)
    runner.OUTPUT.chmod(0o777)
    for name in ("guest.py", "evidence.json", "candidate/SKILL.md"):
        shutil.copyfile(PREVIOUS_INPUTS / name, runner.ARTIFACTS / name)
    shutil.copyfile(mac_plan, runner.ARTIFACTS / "mac-installation.json")
    for row in wheels:
        name = row["filename"]
        row["sha256"] = selected[name]["sha256"]
        shutil.copyfile(sources[name], runner.ARTIFACTS / "wheels" / name)
    runner.put(runner.ARTIFACTS / "linux-wheels.json", wheels)
    runner.put(runner.ARTIFACTS / "expected.json", expected | {
        "installed_source": record["expected_installed_source"],
    })
    wanted = old["inputs"] | {
        f"wheels/{APP_WHEEL}": selected[APP_WHEEL]["sha256"],
        "mac-installation.json": file_digest(mac_plan),
        "linux-wheels.json": file_digest(runner.ARTIFACTS / "linux-wheels.json"),
        "expected.json": file_digest(runner.ARTIFACTS / "expected.json"),
    }
    if runner.inputs() != wanted:
        raise ValueError("staged inputs differ from the reviewed closure")
    for path in runner.ARTIFACTS.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    runner.ARTIFACTS.chmod(0o555)
    runner.put(REVIEW, review_fields() | {"expires_at": (utc_now() + timedelta(days=7)).isoformat()})


def verify(exact: str) -> None:
    if file_digest(REVIEW) != exact:
        raise ValueError("exact review digest required")
    review = runner.get(REVIEW)
    expiry = review["expires_at"]
    if datetime.fromisoformat(expiry) <= utc_now() or review != (review_fields() | {"expires_at": expiry}):
        raise ValueError("review expired or an execution binding changed")
    if (EXECUTION.exists() or RESULT.exists() or not runner.OUTPUT.is_dir()
            or any(path.resolve() != path for path in (HOST, WORK, runner.ARTIFACTS, runner.OUTPUT))
            or any(runner.OUTPUT.iterdir())
            or shutil.disk_usage(HOST).free < FLOOR
            or runner.docker("ps", "-aq", "--filter", f"name=^/{runner.NAME}$")):
        raise ValueError("attempt state, space or container ownership prevents launch")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--verify")
    mode.add_argument("--execute-reviewed")
    args = parser.parse_args()
    select_attempt()
    if args.prepare:
        prepare()
        verify(file_digest(REVIEW))
    else:
        exact = args.verify or args.execute_reviewed
        verify(exact)
        if args.execute_reviewed:
            if not APPROVAL.is_file() or runner.get(APPROVAL) != {"approved": True, "review_sha256": exact}:
                raise ValueError("operator approval required for this exact lifecycle repeat")
            runner.run(exact)
    print(file_digest(REVIEW))


if __name__ == "__main__":
    main()
