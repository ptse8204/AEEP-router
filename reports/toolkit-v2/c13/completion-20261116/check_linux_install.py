"""Review and run one new Linux compatibility check in a private container."""

import argparse
import json
import re
import shutil
import subprocess
import time
from datetime import timedelta
from pathlib import Path

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutionReceipt, ResourceVector, RouteEstimate, StrictModel, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / ".aeep/completion-20261116"
FROZEN = ROOT / ".aeep/sol-comparison-preflight-20261116/frozen-source"
HOST = Path("/private/tmp/aeep-c13-linux-install-package-bridge-20261116")
ARTIFACTS = HOST / "inputs"
OUTPUT = HOST / "output"
REVIEW = WORK / "linux-install-package-bridge-review.json"
RESULT = HERE / "linux-private-install-result.json"
IMAGE = "sha256:4474cf22f867c681aa6120ce2f98d809413f89755cf11a445444b1b993754ea1"
DOCKER = "/Applications/Docker.app/Contents/Resources/bin/docker"
SOCKET = str(Path.home() / ".docker/run/docker.sock")
NAME = "aeep-c13-linux-install-package-bridge-20261116"
ENV = {"HOME": str(HOST), "PATH": "/usr/bin:/bin", "LC_ALL": "C"}
LIMIT_SECONDS = 240


class Scope(StrictModel):
    review_sha256: str


def put(path: Path, value) -> None:
    with path.open("x") as file:
        file.write(json.dumps(value, indent=2) + "\n")


def get(path: Path):
    return json.loads(path.read_bytes())


def docker(*args: str, timeout: int = 20) -> str:
    return subprocess.run([DOCKER, "--host", f"unix://{SOCKET}", *args], env=ENV,
                          stdin=subprocess.DEVNULL, check=True, capture_output=True,
                          text=True, timeout=timeout).stdout.strip()


def inputs() -> dict[str, str]:
    entries = {}
    for entry in sorted(ARTIFACTS.rglob("*")):
        if entry.is_symlink() or not (entry.is_file() or entry.is_dir()):
            raise ValueError("unreviewable private input")
        if entry.is_file():
            entries[entry.relative_to(ARTIFACTS).as_posix()] = file_digest(entry)
    return entries


def verified_image() -> list[str]:
    info = json.loads(docker("image", "inspect", "--format", "{{json .}}", IMAGE))
    if (info["Id"] != IMAGE or info["Os"] != "linux" or info["Architecture"] != "arm64"
            or info["Config"].get("Volumes") or info["Config"].get("Healthcheck")):
        raise ValueError("retained Linux carrier differs")
    return info["RootFS"]["Layers"]


def create_argv() -> list[str]:
    return [
        "create", "--pull", "never", "--name", NAME, "--label", f"org.aeep.owned={NAME}", "--platform", "linux/arm64",
        "--network", "none", "--read-only", "--user", "65534:65534", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "96", "--memory", "768m", "--memory-swap", "768m",
        "--cpus", "1", "--log-driver", "none", "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=96m",
        "--workdir", "/scratch", "--env", "HOME=/scratch", "--env",
        "PYTHONPATH=/bootstrap:/input/wheels/packaging-24.2-py3-none-any.whl",
        "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "LC_ALL=C",
        "--mount", f"type=bind,src={ARTIFACTS},dst=/input,readonly",
        "--mount", f"type=bind,src={FROZEN / 'src'},dst=/bootstrap,readonly",
        "--mount", f"type=bind,src={OUTPUT},dst=/scratch",
        "--entrypoint", "python3", IMAGE, "-B", "/input/guest.py",
    ]


def prepare() -> None:
    if REVIEW.exists() or shutil.disk_usage(HOST.parent).free < 52 * 1024**3:
        raise ValueError("review already exists or host reserve is insufficient")
    layers = verified_image()
    source = verification_source_digest(FROZEN)
    beta = get(HERE / "beta-package-audit.json")
    if source != beta["implementation_source"]:
        raise ValueError("retained execution source changed")
    HOST.mkdir(mode=0o700)
    ARTIFACTS.mkdir(mode=0o755)
    (ARTIFACTS / "wheels").mkdir(mode=0o755)
    (ARTIFACTS / "candidate").mkdir(mode=0o755)
    OUTPUT.mkdir(mode=0o700)
    OUTPUT.chmod(0o777)  # Only this fresh mount is writable by the unprivileged guest.
    pin_document = get(WORK / "linux-private-install-preflight.json")
    wheel_fields = ("extension_id", "filename", "name", "version", "sha256")
    for item in pin_document["pins"]:
        path = Path(item["artifact"])
        if file_digest(path) != item["sha256"]:
            raise ValueError("Linux wheel changed")
        shutil.copyfile(path, ARTIFACTS / "wheels" / item["filename"])
    put(ARTIFACTS / "linux-wheels.json",
        [{key: item[key] for key in wheel_fields} for item in pin_document["pins"]])
    for src, dest in (
        (HERE / "linux_install_guest.py", "guest.py"), (WORK / "beta-installation.json", "mac-installation.json"),
        (WORK / "beta-check/evidence.json", "evidence.json"), (WORK / "beta-check/candidate/SKILL.md", "candidate/SKILL.md"),
    ):
        shutil.copyfile(src, ARTIFACTS / dest)
    inspect = get(WORK / "beta-inspect.json")
    if file_digest(ARTIFACTS / "candidate/SKILL.md") != inspect["files"]["SKILL.md"]:
        raise ValueError("synthetic candidate fixture changed")
    put(ARTIFACTS / "expected.json", {
        "candidate": inspect["candidate_sha256"], "skill": inspect["files"]["SKILL.md"],
        "installed_source": beta["verified_installed_source"],
        "reports": {format: beta["archived_working_evidence"]["beta-report." + ext]
                    for format, ext in (("markdown", "md"), ("html", "html"))},
    })
    for entry in ARTIFACTS.rglob("*"):
        entry.chmod(0o555 if entry.is_dir() else 0o444)
    ARTIFACTS.chmod(0o555)
    review = {
        "authority_record": "reports/toolkit-v2/c13/pipeline-standing-authority-20261104.json",
        "purpose": "Verify the Linux installation workflow with the exact missing bootstrap dependency",
        "source": source, "carrier": IMAGE, "layers": layers, "inputs": inputs(),
        "launcher": file_digest(Path(__file__)), "docker": file_digest(Path(DOCKER)),
        "create": create_argv(), "expires_at": (utc_now() + timedelta(days=1)).isoformat(),
        "max_operations": 1, "max_model_turns": 0, "max_wall_seconds": LIMIT_SECONDS,
        "cash_usd": 0, "downloads": 0, "existing_resources_removed": 0,
        "prior_bootstrap_result": file_digest(HERE / "linux-private-install-bootstrap-result.json"),
        "prior_correction": file_digest(HERE / "linux-private-install-bootstrap-correction-result.json"),
        "carrier_inventory": file_digest(HERE / "linux-carrier-inventory.json"),
    }
    put(REVIEW, review)
    print(file_digest(REVIEW))


def checked_container(container: str, review: dict) -> None:
    found = json.loads(docker("inspect", "--format", "{{json .}}", container))
    config, host = found["Config"], found["HostConfig"]
    mounts = {(p["Source"], p["Destination"], p["RW"]) for p in found["Mounts"] if p["Type"] == "bind"}
    expected = {(str(ARTIFACTS), "/input", False), (str(FROZEN / "src"), "/bootstrap", False),
                (str(OUTPUT), "/scratch", True)}
    if (found["Image"] != review["carrier"] or found["State"]["Status"] != "created"
            or config["Labels"].get("org.aeep.owned") != NAME or config["User"] != "65534:65534"
            or config["Entrypoint"] != ["python3"] or config["Cmd"] != ["-B", "/input/guest.py"]
            or config["WorkingDir"] != "/scratch"
            or host["NetworkMode"] != "none" or not host["ReadonlyRootfs"] or host["Privileged"]
            or host["CapDrop"] != ["ALL"] or host.get("CapAdd") or not host["SecurityOpt"]
            or not any(opt.startswith("no-new-privileges") for opt in host["SecurityOpt"])
            or host["PidsLimit"] != 96 or host["Memory"] != 768 * 1024**2 or host["NanoCpus"] != 10**9
            or host["MemorySwap"] != host["Memory"] or host["LogConfig"]["Type"] != "none"
            or host["Tmpfs"] != {"/tmp": "rw,nosuid,nodev,noexec,size=96m"} or host.get("PortBindings")
            or mounts != expected or any(p["Type"] != "bind" and
                (p["Type"], p["Destination"]) != ("tmpfs", "/tmp") for p in found["Mounts"])):
        raise ValueError("effective container policy differs")


def run(exact: str) -> None:
    from datetime import datetime

    if file_digest(REVIEW) != exact:
        raise ValueError("exact first Linux review required")
    review = get(REVIEW)
    if (RESULT.exists() or review["create"] != create_argv() or review["inputs"] != inputs()
            or review["launcher"] != file_digest(Path(__file__)) or review["docker"] != file_digest(Path(DOCKER))
            or review["source"] != verification_source_digest(FROZEN) or review["layers"] != verified_image()
            or datetime.fromisoformat(review["expires_at"]) <= utc_now()
            or shutil.disk_usage(HOST).free < 52 * 1024**3 or list(OUTPUT.iterdir())
            or docker("ps", "-aq", "--filter", f"name=^/{NAME}$")):
        raise ValueError("execution input, image, ownership, expiration or storage changed")
    if review["prior_bootstrap_result"] != file_digest(HERE / "linux-private-install-bootstrap-result.json"):
        raise ValueError("prior failure evidence changed")
    if (review["prior_correction"] != file_digest(HERE / "linux-private-install-bootstrap-correction-result.json")
            or review["carrier_inventory"] != file_digest(HERE / "linux-carrier-inventory.json")):
        raise ValueError("bootstrap evidence changed")
    approval = get(WORK / "linux-install-package-bridge-approval.json")
    if approval["approved"] is not True or approval["review_sha256"] != exact:
        raise ValueError("operator approval required before repeating the Linux compatibility check")
    out = WORK / "linux-install-package-bridge-execution"
    out.mkdir(mode=0o700)
    scope = Scope(review_sha256=exact)
    scope_ref = content_digest(scope)
    grant = AssessmentAuthorization(
        authorization_id=NAME, subject_digests=[scope_ref], recipe_digests=[scope_ref],
        environment_digests=[scope_ref], limits=AssessmentLimits(max_operations=1, max_model_turns=0,
                                                               max_elapsed_seconds=LIMIT_SECONDS + 30),
        expires_at=datetime.fromisoformat(review["expires_at"]), allowed_destinations=["local"], remote_disclosure=False,
    )
    request = RecipeMaterializationRequest(plan_id=NAME, authorization_id=NAME, subject_digest=scope_ref,
        recipe_digest=scope_ref, environment_digest=scope_ref, mapping_digest=scope_ref, definition_digests=[scope_ref], seed=0)
    operation = NAME + ":compatibility"
    result = {"review_sha256": exact, "passed": False, "model_turns": 0, "cash_usd": 0}
    with ReceiptStore(out / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("toolkit_c13_linux_install_scope", scope_ref, scope)
        repo.approve_bundle(grant, {scope_ref: scope.model_dump(mode="json")})
        repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=LIMIT_SECONDS + 30),
                     stage="linux_private_install")
        started = utc_now()
        clock = time.monotonic()
        container = None
        try:
            candidate = docker(*review["create"])
            if not re.fullmatch(r"[0-9a-f]{64}", candidate):
                raise ValueError("container identity unknown")
            container = candidate
            checked_container(container, review)
            docker("start", "-a", container, timeout=LIMIT_SECONDS)
            status = docker("inspect", "--format", "{{.State.ExitCode}}", container)
            guest = get(OUTPUT / "result.json")
            if status != "0" or guest["passed"] is not True:
                raise ValueError("Linux workload did not complete")
            result.update(guest)
        except subprocess.CalledProcessError as error:
            result.update(failure=type(error).__name__, error=error.stderr[-1300:])
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            result.update(failure=type(error).__name__, error=str(error)[:1300])
        finally:
            if container:
                owner = docker("inspect", "--format", '{{index .Config.Labels "org.aeep.owned"}}', container)
                if owner != NAME:
                    raise RuntimeError("container ownership is uncertain")
                if docker("inspect", "--format", "{{.State.Running}}", container) == "true":
                    docker("stop", "--time", "3", container)
                docker("rm", container)
            if docker("ps", "-aq", "--filter", f"name=^/{NAME}$"):
                raise RuntimeError("container absence is unverified; reservation remains open")
            elapsed = time.monotonic() - clock
            put(out / "terminal-observation.json", result | {"observed_seconds": elapsed, "container_absent": True})
            resources = ResourceVector(latency_ms=elapsed * 1000)
            receipt = ExecutionReceipt(
                decision_id=operation, action_id=operation, capability="toolkit.private-install@1",
                executor_id="toolkit.linux-private-install", executor_kind="command",
                status="success" if result["passed"] else "failed", started_at=started, ended_at=utc_now(),
                estimated=RouteEstimate(), actual_resources=resources, execution_success=result["passed"],
                error_type=result.get("failure"),
                metadata={"review_sha256": exact, "container_absent": True, "operating_system": "linux",
                          "observed_resource_dimensions": ["latency_ms"]},
            )
            store.save_receipt(receipt)
            repo.finish_operation(operation, elapsed_seconds=elapsed, resources=resources)
            put(out / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))
            put(out / "receipt.json", receipt.model_dump(mode="json"))
            put(RESULT, result | {"receipt_id": receipt.receipt_id, "wall_seconds": elapsed, "image": IMAGE,
                                  "operations": 1, "container_absent": True})
    if not result["passed"]:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        run(args.exact_review)


if __name__ == "__main__":
    main()
