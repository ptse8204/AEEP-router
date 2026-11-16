"""Build the one local helper layer and check it through isolated App Server commands."""

import argparse
import asyncio
import hashlib
import secrets
import shutil
import subprocess
import time
from pathlib import Path

from prepare_runtime import (
    CONFIG,
    DOCKER,
    DOCKER_PATH,
    ENV,
    WORK,
    docker,
    metadata,
    read,
    require_reserve,
    sha,
    write,
)
from software_observer import HELPER, PREFIX
from verify_workers import REACT, command, make_spec

from aeep.hosts.codex_app_server import CodexAppServerAdapter

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "libcst_reviewed_helper.py"
PARENT = "aeep-sol-comparison:20261116-software-treatment-ready"
TAG = "aeep-sol-comparison:20261116-software-treatment-libcst-observed"
DIR = WORK / "software-observer-offline"
REVIEW = DIR / "review.json"
RESULT = DIR / "result.json"
IMAGES = WORK / "verified-image-bindings.json"
FIXTURE = r"""
import pathlib,sys,json
root = pathlib.Path('/workspace')
(root/'observed.py').write_text('from module import Old\n# preserve\nx = Old("Old")\n')
(root/'alias.py').symlink_to('observed.py')
print(json.dumps({'python':sys.executable,'helper':pathlib.Path('/opt/aeep-specialists/aeep_libcst_reviewed.py').is_file()}))
"""


def bindings():
    return {
        "source_sha256": sha(SOURCE),
        "driver_sha256": sha(Path(__file__)),
        "existing_image_bindings_sha256": sha(IMAGES),
        "local_parent": PARENT,
        "new_tag": TAG,
        "docker_sha256": sha(Path(DOCKER_PATH)),
        "docker_config_sha256": sha(CONFIG / "config.json"),
        "offline_only": True,
        "maximum_local_builds": 1,
        "maximum_offline_workers": 2,
        "model_turns": 0,
        "cash_usd": "0",
    }


def build(parent):
    require_reserve()
    assert metadata(PARENT)["id"] == parent["id"]
    tag_probe = subprocess.run(
        [*DOCKER, "image", "inspect", TAG], env=ENV, capture_output=True, timeout=20
    )
    assert tag_probe.returncode == 1 and b"No such image" in tag_probe.stderr
    shutil.copyfile(SOURCE, DIR / SOURCE.name)
    df = DIR / "Dockerfile"
    df.write_text(f"FROM {PARENT}\nCOPY --chmod=0444 {SOURCE.name} {HELPER}\n")
    with (DIR / "build.log").open("xb") as log:
        subprocess.run(
            [
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
                TAG,
                str(DIR),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            env=ENV,
            timeout=150,
        )
    built = metadata(TAG)
    assert len(built["layers"]) == len(parent["layers"]) + 1
    assert built["layers"][:-1] == parent["layers"]
    return built | {"policy_sha256": parent["policy_sha256"]}


async def worker_check(role, image):
    spec = make_spec(REACT, "software_engineering", role, image, offline=True)
    if role == "treatment":
        spec.config["managed_worker"]["reviewed_files"][HELPER] = sha(SOURCE)
    adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=secrets.token_bytes(32))
    assert adapter._worker_process_id
    name = "aeep-" + hashlib.sha256(adapter._worker_process_id.encode()).hexdigest()[:32]
    argv = adapter.transport.argv
    assert argv[argv.index("--network") + 1] == "none" and "--mount" not in argv
    assert not any("PROXY=" in arg for arg in argv)
    assert not docker("ps", "-aq", "--filter", "name=^/" + name + "$")
    started = time.monotonic()
    try:
        await adapter.transport.start()
        facts = await command(adapter.transport, FIXTURE)

        async def native(*args):
            return await adapter.transport.request(
                "command/exec",
                {
                    "command": [*PREFIX, *args],
                    "cwd": "/workspace",
                    "timeoutMs": 10000,
                    "outputBytesCap": 2000,
                },
                timeout=15,
            )

        if role == "treatment":
            assert facts["helper"]
            assert (await native("check", "observed.py"))["exitCode"] == 0
            renamed = await native("rename", "observed.py", "module.Old", "module.New")
            assert renamed["exitCode"] == 0
            assert renamed["stdout"] == 'from module import New\n# preserve\nx = New("Old")\n'
            assert (await native("rename", "observed.py", "module.Missing", "module.New"))[
                "exitCode"
            ] == 3
            assert (await native("check", "alias.py"))["exitCode"] != 0
            assert (await native("check", "../observed.py"))["exitCode"] != 0
        else:
            assert not facts["helper"]
            assert (await native("check", "observed.py"))["exitCode"] != 0
    finally:
        await adapter.close()
        assert not docker("ps", "-aq", "--filter", "name=^/" + name + "$")
    return {
        "image": image["id"],
        "expected_helper_available": role == "treatment",
        "import_parse_and_changed_transform_controls_passed": role == "treatment",
        "non_transform_and_path_escape_controls_passed": role == "treatment",
        "owned_worker_removed": True,
        "elapsed_seconds": time.monotonic() - started,
    }


async def execute(identity):
    assert sha(REVIEW) == identity and read(REVIEW) == bindings() and not RESULT.exists()
    images = read(IMAGES)["software_engineering"]
    images["treatment"] = build(images["treatment"])
    write(DIR / "images.json", images)
    records = {role: await worker_check(role, image) for role, image in images.items()}
    write(RESULT, {"review_sha256": identity, "workers": records, "model_turns": 0})
    print(sha(RESULT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--execute")
    args = parser.parse_args()
    if args.freeze:
        DIR.mkdir(mode=0o700)
        write(REVIEW, bindings())
        print(sha(REVIEW))
    else:
        asyncio.run(execute(args.execute))
