"""Build only the local worker overlays approved in the Sol comparison design."""

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from aeep.assessment.verification import verification_source_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LOCAL = ROOT / ".aeep"
WORK = LOCAL / "sol-comparison-preflight-20261116"
DESIGN = HERE / "sol-comparison-design.json"
DESIGN_SHA256 = "08613f4efd26fbf6ee10e6713acaf74adb7bafb8b8c721e00de8d526825ac0a6"
DOCKER_PATH = "/Applications/Docker.app/Contents/Resources/bin/docker"
CONFIG = LOCAL / "skillsbench-contained-graders-20261105/buildx-docker-config"
SOCKET = "/Users/edwintse/.docker/run/docker.sock"
DOCKER = [DOCKER_PATH, "--config", str(CONFIG), "--host", "unix://" + SOCKET]
ENV = {"HOME": str(WORK), "PATH": "/usr/bin:/bin", "LC_ALL": "C", "DOCKER_BUILDKIT": "1"}
DOCUMENT = "aeep-skillsbench-worker:sales-control-20261105"
SOFTWARE = "aeep-skillsbench-worker:react-sol-path-20261109-control"
SPREADSHEET = "aeep-csv-reusable-reviewed-base-treatment:1745a3204bb108c6"
DOC_CONTROL = "aeep-sol-comparison:20261116-document-control"
DOC_TREATMENT = "aeep-sol-comparison:20261116-document-treatment"
SOFT_TREATMENT = "aeep-sol-comparison:20261116-software-treatment"
GIB = 1024**3


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def docker(*args, timeout=20):
    return subprocess.check_output([*DOCKER, *args], text=True, timeout=timeout, env=ENV).strip()


def metadata(ref):
    item = json.loads(docker("image", "inspect", "--format", "{{json .}}", ref))
    config = item["Config"]
    if (item["Os"], item["Architecture"], config["User"]) != (
        "linux",
        "arm64",
        "65534:65534",
    ) or config.get("Volumes"):
        raise ValueError("worker platform, owner, or anonymous volume differs")
    return {
        "id": item["Id"],
        "layers": item["RootFS"]["Layers"],
        "size": item["Size"],
        "platform": "linux/arm64",
        "user": config["User"],
    }


def require_reserve(free=52):
    if shutil.disk_usage(WORK).free < free * GIB:
        raise RuntimeError("usable space is below the local packaging reserve")


def copy_sol(design, ctx):
    inputs = design["worker_inputs"]
    manifest = ROOT / inputs["sol_runtime_inventory"]["path"]
    assert sha(manifest) == inputs["sol_runtime_inventory"]["sha256"]
    original = manifest.parent / "sol-client-context"
    inventory = {k: v for k, v in read(manifest).items() if k.startswith("runtime/")}
    actual = {
        p.relative_to(original).as_posix() for p in (original / "runtime").rglob("*") if p.is_file()
    }
    assert actual == inventory.keys()
    for name, pin in inventory.items():
        src = original / name
        assert src.is_file() and not src.is_symlink()
        assert src.stat().st_size == pin["bytes"] and sha(src) == pin["sha256"]
        assert os.access(src, os.X_OK) == pin["executable"]
        dst = ctx / name
        dst.parent.mkdir(exist_ok=True, parents=True)
        shutil.copy2(src, dst)
    return inventory


def run():
    assert sha(DESIGN) == DESIGN_SHA256
    approved = read(DESIGN)
    source = verification_source_digest(ROOT)
    assert source == approved["implementation_source"]
    WORK.mkdir(mode=0o700)
    require_reserve(55)
    assert docker("buildx", "version")
    inputs = approved["worker_inputs"]
    candidates = approved["candidate_arms"]
    parents = {
        DOCUMENT: metadata(DOCUMENT),
        SOFTWARE: metadata(SOFTWARE),
        SPREADSHEET: metadata(SPREADSHEET),
    }
    assert [parents[ref]["id"] for ref in parents] == [
        inputs["document_baseline_parent"],
        inputs["software_baseline_parent"],
        candidates["document-data"]["source_image"],
    ]
    for tag in (DOC_CONTROL, DOC_TREATMENT, SOFT_TREATMENT):
        status = subprocess.run([*DOCKER, "image", "inspect", tag], capture_output=True, env=ENV)
        assert status.returncode == 1 and b"No such image" in status.stderr
    context = WORK / "build"
    context.mkdir()
    runtime = copy_sol(approved, context)
    soft = candidates["software-engineering"]
    skill = ROOT / soft["candidate_skill"]["path"]
    assert sha(skill) == soft["candidate_skill"]["sha256"]
    shutil.copy2(skill, context / "libcst-migrate.md")
    (context / "wheels").mkdir()
    for wheel in soft["local_wheels"]:
        path = LOCAL / "stack-candidate-review-20261030" / wheel["filename"]
        assert path.stat().st_size == wheel["bytes"] and sha(path) == wheel["sha256"]
        shutil.copy2(path, context / "wheels" / path.name)

    dockerfiles = {
        DOC_CONTROL: (
            DOCUMENT,
            f"FROM {DOCUMENT}\n"
            "COPY runtime/ /opt/codex/0.159.1/\n"
            "ENV PATH=/opt/codex/0.159.1/codex-path:/opt/codex/0.159.1/bin:/usr/local/bin:/usr/bin:/bin\n",
        ),
        DOC_TREATMENT: (
            DOC_CONTROL,
            f"FROM {SPREADSHEET} AS candidate\nFROM {DOC_CONTROL}\n"
            "COPY --from=candidate /opt/dependencies/runtime/ /opt/dependencies/runtime/\n"
            "COPY --from=candidate /opt/dependencies/plugin/skills/spreadsheets/ "
            "/opt/dependencies/plugin/skills/spreadsheets/\n"
            "USER root\n"
            "RUN mkdir -p /etc/codex/skills && ln -s "
            "/opt/dependencies/plugin/skills/spreadsheets /etc/codex/skills/spreadsheets\n"
            "USER 65534:65534\n",
        ),
        SOFT_TREATMENT: (
            SOFTWARE,
            f"FROM {SOFTWARE} AS offline-dependencies\n"
            "USER root\nCOPY wheels/ /wheels/\n"
            "RUN python3 -m pip install --no-index --no-deps --no-compile "
            "--disable-pip-version-check --target /opt/aeep-specialists /wheels/*.whl\n"
            f"FROM {SOFTWARE}\n"
            "COPY --from=offline-dependencies /opt/aeep-specialists/ /opt/aeep-specialists/\n"
            "COPY --chmod=0444 libcst-migrate.md /opt/dependencies/libcst-migrate/SKILL.md\n"
            "USER root\n"
            "RUN mkdir -p /etc/codex/skills && ln -s "
            "/opt/dependencies/libcst-migrate /etc/codex/skills/libcst-migrate\n"
            "USER 65534:65534\n",
        ),
    }
    builds = {}
    for index, (tag, (parent, definition)) in enumerate(dockerfiles.items(), start=1):
        df = context / f"Dockerfile.{index}"
        df.write_text(definition)
        builds[tag] = {
            "parent": parent,
            "file": str(df),
            "sha256": sha(df),
            "argv": [
                *DOCKER,
                "buildx",
                "build",
                "--builder",
                "default",
                "--platform",
                "linux/arm64",
                "--network=none",
                "--pull=false",
                "--provenance=false",
                "--load",
                "-f",
                str(df),
                "-t",
                tag,
                str(context),
            ],
        }
    write(
        WORK / "offline-build-scope.json",
        {
            "approved_design_sha256": DESIGN_SHA256,
            "source": source,
            "parent_bindings": parents,
            "docker_sha256": sha(Path(DOCKER_PATH)),
            "private_docker_config_sha256": sha(CONFIG / "config.json"),
            "runtime_inventory": runtime,
            "specialist_wheels": soft["local_wheels"],
            "builds": builds,
            "maximum_builds": 3,
            "timeout_seconds_per_build": 600,
            "model_turns": 0,
            "cash_usd": "0",
        },
    )
    retained = dict(parents)
    for tag, build in builds.items():
        require_reserve()
        assert metadata(build["parent"]) == retained[build["parent"]]
        assert sha(Path(build["file"])) == build["sha256"]
        began = time.monotonic()
        prefix = WORK / tag.rsplit("-", 2)[-2]
        log = WORK / (tag.split(":")[1] + ".log")
        status = None
        try:
            with log.open("xb") as stream:
                status = subprocess.run(
                    build["argv"], stdout=stream, stderr=subprocess.STDOUT, env=ENV, timeout=600
                ).returncode
            if status != 0:
                raise RuntimeError("offline image build failed")
            meta = metadata(tag)
            layers = retained[build["parent"]]["layers"]
            assert meta["layers"][: len(layers)] == layers
            retained[tag] = meta
        finally:
            write(
                prefix.with_name(tag.split(":")[1] + ".json"),
                {
                    "tag": tag,
                    "exit_code": status,
                    "elapsed_seconds": time.monotonic() - began,
                    "image": retained.get(tag),
                    "log_sha256": sha(log),
                    "model_turns": 0,
                },
            )
    require_reserve()
    write(
        WORK / "worker-images.json",
        {
            "document_data": {
                "control": retained[DOC_CONTROL],
                "treatment": retained[DOC_TREATMENT],
            },
            "software_engineering": {
                "control": retained[SOFTWARE],
                "treatment": retained[SOFT_TREATMENT],
            },
        },
    )


if __name__ == "__main__":
    run()
