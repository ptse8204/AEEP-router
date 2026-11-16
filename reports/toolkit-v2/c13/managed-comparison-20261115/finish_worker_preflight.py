"""Finish offline verification with corrected synthetic checks and a readable LibCST skill."""

import asyncio
import subprocess

from prepare_runtime import (
    DOCKER,
    ENV,
    WORK,
    metadata,
    read,
    require_reserve,
    sha,
    write,
)
from verify_workers import REACT, SALES, make_spec, observe


def repair():
    previous = "aeep-sol-comparison:20261116-software-engineering-treatment-policy"
    image = read(WORK / "final-worker-images.json")["software_engineering"]["treatment"]
    initial = metadata(previous)
    assert initial == {key: image[key] for key in initial}
    context = WORK / "libcst-readable"
    context.mkdir(mode=0o700)
    df = context / "Dockerfile"
    df.write_text(
        f"FROM {previous}\nUSER root\n"
        "RUN /bin/chmod 0555 /opt/dependencies/libcst-migrate\nUSER 65534:65534\n"
    )
    tag = "aeep-sol-comparison:20261116-software-treatment-ready"
    argv = [
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
    ]
    require_reserve()
    log = context / "build.log"
    with log.open("xb") as stream:
        proc = subprocess.run(argv, env=ENV, stdout=stream, stderr=subprocess.STDOUT, timeout=150)
    facts = {
        "argv": argv,
        "reuses": initial["id"],
        "exit_code": proc.returncode,
        "dockerfile_sha256": sha(df),
        "log_sha256": sha(log),
        "model_turns": 0,
    }
    write(context / "build.json", facts)
    if proc.returncode != 0:
        raise RuntimeError("local file-mode correction failed")
    patched = metadata(tag)
    assert patched["layers"][: len(initial["layers"])] == initial["layers"]
    return patched | {"policy_sha256": image["policy_sha256"]}


async def main():
    images = read(WORK / "final-worker-images.json")
    images["software_engineering"]["treatment"] = repair()
    scope = WORK / "verified-image-bindings.json"
    write(scope, images)
    directory = WORK / "verified-worker-observations"
    directory.mkdir(mode=0o700)
    results = {}
    for domain, file in (("document_data", SALES), ("software_engineering", REACT)):
        pair = results[domain] = {}
        for role, image in images[domain].items():
            pair[role] = await observe(
                domain, role, image, make_spec(file, domain, role, image, offline=True), directory
            )
        assert (
            pair["control"]["runtime"]["shared_tools"]
            == pair["treatment"]["runtime"]["shared_tools"]
        )
    write(
        WORK / "verified-worker-pairs.json",
        {
            "pairs": results,
            "model_turns": 0,
            "provider_contact": False,
            "credential_mounts": 0,
            "shared_tools_matched": True,
            "passed": True,
            "image_bindings_sha256": sha(scope),
            "earlier_failures": {
                p.name: sha(p) for p in sorted((WORK / "worker-observations").glob("*.json"))
            },
            "scope": "Offline. Fresh authenticated boundary and collector checks precede live dispatch.",
        },
    )


if __name__ == "__main__":
    asyncio.run(main())
