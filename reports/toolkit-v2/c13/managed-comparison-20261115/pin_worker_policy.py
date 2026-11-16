"""Bind the one task-tool read path each pair needs, under the same policy in both arms."""

import subprocess
import time

from prepare_runtime import (
    DOC_CONTROL,
    DOC_TREATMENT,
    DOCKER,
    ENV,
    SOFT_TREATMENT,
    SOFTWARE,
    WORK,
    docker,
    metadata,
    read,
    require_reserve,
    sha,
    write,
)

POLICY = "/etc/codex/requirements.toml"


def build():
    original = read(WORK / "worker-images.json")
    target = WORK / "paired-permissions"
    target.mkdir(mode=0o700)
    result = {}
    for domain, tags, root in (
        ("document_data", (DOC_CONTROL, DOC_TREATMENT), "/opt/aeep-task-tools"),
        ("software_engineering", (SOFTWARE, SOFT_TREATMENT), "/opt/aeep-specialists"),
    ):
        context = target / domain
        context.mkdir()
        policy = None
        images = {}
        for arm, parent in zip(("control", "treatment"), tags, strict=True):
            previous = original[domain][arm]
            assert metadata(parent) == previous
            current = (
                docker(
                    "run",
                    "--rm",
                    "--pull=never",
                    "--network",
                    "none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--user",
                    "65534:65534",
                    "--entrypoint",
                    "/bin/cat",
                    previous["id"],
                    POLICY,
                )
                + "\n"
            )
            if policy is None:
                policy = current
            assert (
                policy == current
                and root not in current
                and current.count("[permissions.aeep.network]") == 1
            )
            assert '"\x3aroot" = "deny"' in current and '"\x2fworker/auth" = "deny"' in current
            assert "enabled = false" in current
            config = context / "requirements.toml"
            if not config.exists():
                config.write_text(
                    current.replace(
                        "[permissions.aeep.network]",
                        f'"{root}" = "read"\n[permissions.aeep.network]',
                    )
                )
            assert metadata(parent) == previous
            tag = f"aeep-sol-comparison:20261116-{domain.replace('_', '-')}-{arm}-policy"
            df = context / f"Dockerfile.{arm}"
            df.write_text(f"FROM {parent}\nCOPY --chmod=0444 requirements.toml {POLICY}\n")
            command = [
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
            started = time.monotonic()
            log = context / f"{arm}.log"
            with log.open("xb") as stream:
                process = subprocess.run(
                    command, env=ENV, stdout=stream, stderr=subprocess.STDOUT, timeout=150
                )
            facts = {
                "command": command,
                "exit_code": process.returncode,
                "parent": previous["id"],
                "policy_sha256": sha(config),
                "new_read_root": root,
                "dockerfile_sha256": sha(df),
                "elapsed_seconds": time.monotonic() - started,
                "log_sha256": sha(log),
                "model_turns": 0,
            }
            write(context / f"{arm}-build.json", facts)
            if process.returncode != 0:
                raise RuntimeError("paired policy layer did not build")
            image = metadata(tag)
            assert image["layers"][: len(previous["layers"])] == previous["layers"]
            images[arm] = image | {"policy_sha256": sha(config)}
        result[domain] = images
    write(WORK / "final-worker-images.json", result)


if __name__ == "__main__":
    build()
