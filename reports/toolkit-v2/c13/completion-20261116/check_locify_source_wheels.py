"""Build Locify's two missing source distributions in the retained offline carrier."""

import argparse
import asyncio
import json
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from stage_repository_transport import HERE, ROOT, WORK, digest, encode, write

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.execution import ExecutionEvidence, persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import (
    ActionRequest,
    ExecutionReceipt,
    ExecutorSpec,
    ResourceVector,
    StrictModel,
    utc_now,
)
from aeep.store import ReceiptStore

HOME_DIR = WORK / "locify-source-build-20261119"
CONTEXT = HOME_DIR / "context"
REVIEW = HOME_DIR / "operation-review.json"
AFLOW = HERE.parent / "proposal-optimizer-preparation-20261105"
AUTHORITY = HERE.parent / "pipeline-standing-authority-20261104.json"
BASE = "aeep-toolkit-v2/aflow:3f457218-cp312-arm64-20261105"
BASE_ID = "sha256:4e3cb7fa008c768c5d5c56d823a291a37add169eecb81c2f89ede3fd86723d8d"
TAG = "aeep-toolkit-v2/locify-source-wheels:fb523b79-20261119"
LABEL = "c13-locify-source-wheels-20261119"
PYTHON = "/opt/portable/python/bin/python3.12"
EXPECTED = ("fire-0.7.0-py3-none-any.whl", "litellm-1.50.1-py3-none-any.whl")
BUILD = """import io, hashlib, json, subprocess, sys
from pathlib import Path
from zipfile import ZipFile

root = Path('/opt/locify-input')
tools = root / 'build-dependencies'
backends = sorted(tools.glob('*.whl'))
assert len(backends) == 3
site = Path('/tmp/c13-locify-build-site')
out = Path('/opt/locify-wheels')
env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
       'PYTHONPATH': str(site), 'PYTHONNOUSERSITE': '1', 'PIP_NO_INDEX': '1'}
pip = [sys.executable, '-B', '-s', '-m', 'pip', '--isolated',
       '--disable-pip-version-check', '--no-input', '--no-cache-dir']
subprocess.run([*pip, 'install', '--no-index', '--no-deps', '--no-compile',
                '--target', str(site), *map(str, backends)], env=env, check=True, timeout=60)
fire = tools / 'fire-0.7.0.tar.gz'
subprocess.run([*pip, 'wheel', '--no-index', '--no-deps', '--no-build-isolation',
                '--wheel-dir', str(out), str(fire), str(root/'litellm')],
               env=env, check=True, timeout=130)
report = []
for package in sorted(out.glob('*.whl')):
    raw = package.read_bytes()
    assert len(raw) <= 20_000_000
    with ZipFile(io.BytesIO(raw)) as file:
        assert not any(name.startswith(('enterprise/', 'litellm/proxy/enterprise/')) for name in file.namelist())
        assert any(name.endswith('.dist-info/METADATA') for name in file.namelist())
    report.append({'filename': package.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
assert [row['filename'] for row in report] == ['fire-0.7.0-py3-none-any.whl', 'litellm-1.50.1-py3-none-any.whl']
(out/'inventory.json').write_text(json.dumps(report, sort_keys=True) + '\\n')
"""


class Scope(StrictModel):
    review_sha256: str


def doc(path):
    return json.loads(path.read_bytes())


def fingerprint(path):
    return digest(path.read_bytes())


def inventory():
    result = {}
    for path in sorted(CONTEXT.rglob("*")):
        if path.is_symlink():
            raise ValueError("build context cannot contain symlinks")
        if path.is_file():
            result[str(path.relative_to(CONTEXT))] = fingerprint(path)
    return result


def docker_settings():
    old = doc(AFLOW / "aflow-runtime-build-review.json")
    env = {name: old["environment"][name] for name in ("PATH", "LC_ALL", "DOCKER_BUILDKIT")}
    return old["docker"], env


def docker_pins(docker):
    old = doc(AFLOW / "aflow-runtime-build-review.json")
    plugin, = [Path(name) for name in old["assets"] if Path(name).name == "docker-buildx"]
    return {str(path): fingerprint(path) for path in (Path(docker[0]), plugin, Path(docker[2]) / "config.json")}


def inspect(docker, env, name):
    raw = subprocess.check_output([*docker, "image", "inspect", name, "--format", "{{json .}}"],
                                  env=env, timeout=15, text=True)
    actual = json.loads(raw)
    if actual["Architecture"] != "arm64" or actual["Os"] != "linux" or actual["Config"].get("Volumes"):
        raise ValueError("image differs from the reviewed architecture or mount boundary")
    return {"id": actual["Id"], "layers": actual["RootFS"]["Layers"]}


def prepare():
    if REVIEW.exists() or shutil.disk_usage(ROOT).free < 53 * 2**30:
        raise ValueError("first build review requires an unstarted scope and host space")
    inputs = doc(HOME_DIR / "input-binding.json")
    expected = {item["name"]: item["sha256"] for item in inputs["files"]}
    if inventory() != expected or len(expected) != 466:
        raise ValueError("publisher files or build inputs changed")
    docker, env = docker_settings()
    parent = inspect(docker, env, BASE)
    if parent["id"] != BASE_ID:
        raise ValueError("retained Python carrier changed")
    compile(BUILD, "<locify source build>", "exec")
    write(CONTEXT / "build.py", BUILD.encode())
    write(CONTEXT / "Dockerfile", ("\n".join([
        f"FROM {BASE}", "USER 0:0",
        'RUN ["install","-d","-m","0755","-o","65534","-g","65534","/opt/locify-wheels"]',
        "COPY input/ /opt/locify-input/", "COPY build.py /opt/build-locify.py",
        "USER 65534:65534", "WORKDIR /tmp",
        "RUN " + json.dumps([PYTHON, "-I", "-B", "/opt/build-locify.py"]), "",
    ])).encode())
    usage = subprocess.check_output([*docker, "system", "df"], env=env, timeout=30, text=True)
    build = [*docker, "build", "--pull=false", "--network=none", "--platform=linux/arm64",
             "--provenance=false", "--sbom=false", "--tag", TAG, str(CONTEXT)]
    write(REVIEW, encode({
        "schema_version": "aeep.c13.locify-first-source-wheel-build.v1",
        "scope": "Two offline source wheels via the retained Python carrier, followed by an inventory check.",
        "authority_sha256": fingerprint(AUTHORITY), "driver_sha256": fingerprint(Path(__file__).resolve()),
        "context": inventory(), "base": parent, "tag": TAG, "docker": docker, "environment": env,
        "build_argv": build, "docker_tool_pins": docker_pins(docker), "disk_usage": usage,
        "expires_at": (utc_now() + timedelta(hours=2)).isoformat(),
        "no_network": True, "models": 0, "cash_usd": 0, "max_operations": 2,
        "max_reserved_seconds": 355, "automatic_retry": False, "preserve_existing_resources": True,
    }))
    print(fingerprint(REVIEW))


async def run_operation(repo, store, request, argv, stage, timeout, exact, env):
    name = LABEL + ":" + stage
    repo.reserve(request, name, AssessmentLimits(max_operations=1, max_elapsed_seconds=timeout + 5), stage=stage)
    spec = ExecutorSpec(id=LABEL, capability="toolkit.upstream-engineering@1", kind="command", side_effect="write",
                        description="Bounded offline build or inventory read.",
                        config={"argv": argv, "argv_literal": True, "inherit_env": False, "env": env,
                                "cwd": str(HOME_DIR), "timeout_seconds": timeout,
                                "max_output_bytes": 100_000, "output": {"type": "text"}})
    executor = CommandExecutor()
    clock = time.monotonic()
    started = utc_now()
    raw = None
    proof = None
    try:
        with persist_execution_events(lambda key, event: repo.put("execution_event", f"{key}:{event.sequence}", event)):
            handle = await executor.start(ExecutionContext(
                request=ActionRequest(action_id=name, capability=spec.capability), spec=spec,
                estimate=spec.estimate, attempt=1, attempt_id=name, approved_side_effect=spec.side_effect,
                invocation_check=lambda: (repo.authorize(request), exact)[1],
            ))
            while not handle.task.done():
                await asyncio.wait({handle.task}, timeout=1)
                if shutil.disk_usage(ROOT).free < 50 * 2**30:
                    await executor.cancel(handle)
                    raise RuntimeError("host storage reserve crossed")
            raw = await handle.task
        evidence = ExecutionEvidence.model_validate(raw.metadata["execution_evidence"])
        if evidence.complete:
            proof = repo.put("execution_evidence", evidence.digest(), evidence)
        if not proof or raw.exit_code != 0:
            raise RuntimeError("reviewed command did not settle successfully")
        return raw
    finally:
        await executor.close()
        elapsed = time.monotonic() - clock
        receipt = ExecutionReceipt(
            decision_id=name, action_id=name, capability=spec.capability, executor_id=spec.id,
            executor_kind=spec.kind, status="success" if raw and proof and raw.exit_code == 0 else "failed",
            started_at=started, ended_at=utc_now(), estimated=spec.estimate, execution_success=bool(raw and proof and raw.exit_code == 0),
            actual_resources=ResourceVector(latency_ms=elapsed * 1000),
            metadata={"review_sha256": exact, "execution_evidence_ref": proof},
        )
        store.save_receipt(receipt)
        repo.finish_operation(name, elapsed_seconds=elapsed, resources=receipt.actual_resources)
        write(HOME_DIR / f"{stage}-receipt.json", encode(receipt.model_dump(mode="json")))
        if raw:
            write(HOME_DIR / f"{stage}.log", ((raw.stdout or "") + (raw.stderr or ""))[-16000:].encode())


def preflight(exact):
    review = doc(REVIEW)
    started = HOME_DIR / "started.json"
    if (
        fingerprint(REVIEW) != exact or started.exists()
        or fingerprint(AUTHORITY) != review["authority_sha256"]
        or fingerprint(Path(__file__).resolve()) != review["driver_sha256"] or inventory() != review["context"]
        or shutil.disk_usage(ROOT).free < 53 * 2**30
        or utc_now() >= datetime.fromisoformat(review["expires_at"])
    ):
        raise ValueError("first build scope or storage drifted")
    docker, env = docker_settings()
    if (docker != review["docker"] or env != review["environment"]
            or docker_pins(docker) != review["docker_tool_pins"] or inspect(docker, env, BASE) != review["base"]):
        raise ValueError("Docker tool or base identity changed")
    if subprocess.run([*docker, "image", "inspect", TAG], env=env, timeout=10, capture_output=True).returncode == 0:
        raise ValueError("reviewed output tag already exists")
    write(started, encode({"review_sha256": exact, "authority": str(AUTHORITY.relative_to(ROOT)), "first_attempt": True}))
    return review, docker, env


async def execute(exact, review, docker, env):
    scope = Scope(review_sha256=exact)
    bind = content_digest(scope)
    expiry = datetime.fromisoformat(review["expires_at"])
    grant = AssessmentAuthorization(
        authorization_id=LABEL, subject_digests=[bind], recipe_digests=[bind], environment_digests=[bind],
        limits=AssessmentLimits(max_operations=2, max_elapsed_seconds=355), expires_at=expiry,
        allowed_destinations=["local"], remote_disclosure=False,
    )
    request = RecipeMaterializationRequest(plan_id=LABEL, authorization_id=LABEL,
        subject_digest=bind, recipe_digest=bind, mapping_digest=bind, environment_digest=bind,
        definition_digests=[bind], seed=0)
    result = {"review_sha256": exact, "passed": False, "models": 0, "cash_usd": 0}
    with ReceiptStore(HOME_DIR / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("c13_locify_source_build_scope", bind, scope)
        repo.approve_bundle(grant, {bind: scope.model_dump(mode="json")})
        try:
            await run_operation(repo, store, request, review["build_argv"], "build", 300, exact, env)
            image = inspect(docker, env, TAG)
            if image["layers"][:len(review["base"]["layers"])] != review["base"]["layers"]:
                raise ValueError("built image did not retain the verified parent")
            cmd = [*docker, "run", "--rm", "--pull=never", "--name", LABEL,
                   "--network=none", "--read-only", "--user", "65534:65534", "--cap-drop=ALL",
                   "--security-opt=no-new-privileges", "--memory=256m", "--pids-limit=32",
                   "--entrypoint", "/bin/cat", image["id"], "/opt/locify-wheels/inventory.json"]
            reply = await run_operation(repo, store, request, cmd, "inventory", 40, exact, env)
            actual = json.loads(reply.stdout)
            if tuple(row["filename"] for row in actual) != EXPECTED:
                raise ValueError("actual wheel inventory differs")
            result.update(passed=True, image=image, wheels=actual)
        finally:
            write(HOME_DIR / "ledger.json", encode(repo.operation_ledger(LABEL).model_dump(mode="json")))
            write(HOME_DIR / "result.json", encode(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--first-review")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        asyncio.run(execute(args.first_review, *preflight(args.first_review)))


if __name__ == "__main__":
    main()
