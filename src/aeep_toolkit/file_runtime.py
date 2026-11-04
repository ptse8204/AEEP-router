"""Copy reviewed runtime artifacts using the existing owned-installation journal.

This module never downloads, builds, imports or executes an installed artifact.
Architecture/backend compatibility and functional permission remain separate.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import Field, model_validator

from .install_runtime import canonical, digest, file_digest, load_state, paths, snapshot
from .installation import InstallationPreview, PreviewPolicy, preview, require_compatible
from .models import ContractModel, Digest, ExtensionRegistry, Identifier


def _relative(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not path.parts
        or path.is_absolute()
        or str(path) != value
        or ".." in path.parts
        or "\\" in value
        or "\x00" in value
        or len(path.parts) > 16
        or any(
            part.casefold()
            in {
                ".codex",
                ".ssh",
                ".aws",
                ".azure",
                ".gnupg",
                ".config",
                ".docker",
                ".npm",
                "auth.json",
                "credentials.json",
            }
            or part.casefold().startswith(".env")
            for part in path.parts
        )
    ):
        raise ValueError("runtime file paths must be relative and exclude credential state")
    return value


class RuntimeFile(ContractModel):
    extension_id: Identifier
    source: str = Field(min_length=1, max_length=1024)
    destination: str = Field(min_length=1, max_length=1024)
    sha256: Digest
    size_bytes: int = Field(strict=True, ge=0, le=512 * 1024**2)
    executable: bool = Field(default=False, strict=True)
    primary: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def safe_paths(self) -> RuntimeFile:
        _relative(self.source)
        _relative(self.destination)
        return self


class FileRuntimeInstallation(ContractModel):
    schema_version: Literal["aeep.toolkit.file-runtime-installation.v1"] = (
        "aeep.toolkit.file-runtime-installation.v1"
    )
    preview: InstallationPreview
    policy: PreviewPolicy
    destination: str
    artifact_root: str
    files: tuple[RuntimeFile, ...] = Field(min_length=1, max_length=128)
    installer_python: str
    installer_python_sha256: Digest
    python_version: str
    system: str
    machine: str
    effects: tuple[str, ...] = (
        "Copy exact local artifacts into a new private owned tree; no download, build or execution.",
        "Write the existing sibling installation journal and lock; no host activation or service startup.",
        "Keep executable files at0555 and other files at0444; permissions confer no execution authority.",
        "Keep the normal50GiB actual host reserve and staged/allocated file headroom.",
        "Retain failed/interrupted state; remove only an unchanged owned runtime and preserve conflicts.",
    )

    @model_validator(mode="after")
    def exact_closure(self) -> FileRuntimeInstallation:
        rebuilt = preview(
            ExtensionRegistry(extensions=tuple(i.manifest for i in self.preview.items)),
            self.preview.selected,
            self.policy,
            profile=self.preview.profile,
            observations=tuple(i.observation for i in self.preview.items),
        )
        if rebuilt != self.preview:
            raise ValueError("preview differs from the reviewed file-runtime closure")
        require_compatible(rebuilt)
        items = {i.manifest.extension_id: i.manifest for i in rebuilt.items}
        if {f.extension_id for f in self.files} != set(items):
            raise ValueError("every selected component needs its exact runtime files")
        for identity, manifest in items.items():
            primary = [f for f in self.files if f.extension_id == identity and f.primary]
            if len(primary) != 1 or primary[0].sha256 != manifest.source.artifact_sha256:
                raise ValueError(
                    "each component needs one primary file matching its source artifact"
                )
        targets = [f.destination.casefold() for f in self.files]
        if sum(f.size_bytes for f in self.files) > 512 * 1024**2:
            raise ValueError("runtime file closure exceeds512MiB")
        if len(set(targets)) != len(targets) or any(
            a != b and b.startswith(a + "/") for a in targets for b in targets
        ):
            raise ValueError("runtime files collide with another file or parent directory")
        return self


def _root(value: str) -> Path:
    from aeep.assessment.identity import protected_directory

    result = canonical(value)
    if protected_directory(result):
        raise ValueError("file runtime roots must exclude home and filesystem roots")
    # Apply the same credential-directory exclusion to absolute roots and parents.
    _relative("/".join(result.parts[1:]))
    return result


def check_files(plan: FileRuntimeInstallation) -> int:
    source, target = _root(plan.artifact_root), _root(plan.destination)
    if (
        not source.is_dir()
        or source == target
        or source.is_relative_to(target)
        or target.is_relative_to(source)
    ):
        raise ValueError("artifact source and installation must be separate trees")
    allocated, total = 0, 0
    for entry in plan.files:
        path = canonical(str(source / entry.source))
        if file_digest(path) != entry.sha256:
            raise ValueError("reviewed runtime artifact changed")
        size = path.stat().st_size
        if size != entry.size_bytes:
            raise ValueError("reviewed artifact size changed")
        total += size
        allocated += (size // 4096 + 1) * 4096
    if total > 512 * 1024**2:
        raise ValueError("runtime file closure exceeds512MiB")
    return max(plan.preview.known_disk_bytes, 2 * allocated + 8 * 1024**2)


def prepare_files(
    selection: InstallationPreview,
    policy: PreviewPolicy,
    destination: Path,
    artifact_root: Path,
    files: tuple[RuntimeFile, ...],
) -> FileRuntimeInstallation:
    """Read metadata and exact bytes only; never write, import or execute artifacts."""
    target = _root(str(destination))
    if target.exists() or not target.parent.is_dir():
        raise ValueError("destination must be absent with an existing parent")
    python = Path(sys.executable).resolve(strict=True)
    result = FileRuntimeInstallation(
        preview=selection,
        policy=policy,
        destination=str(target),
        artifact_root=str(_root(str(artifact_root))),
        files=files,
        installer_python=str(python),
        installer_python_sha256=file_digest(python),
        python_version=platform.python_version(),
        system=sys.platform,
        machine=platform.machine(),
    )
    required = check_files(result)
    if shutil.disk_usage(target.parent).free - required < 50 * 1024**3:
        raise ValueError("runtime files would cross the50GiB host reserve")
    return result


def apply_files(plan: FileRuntimeInstallation, reviewed_digest: str) -> dict[str, Any]:
    from aeep.component_setup import require_space
    from aeep.connections import file_lock, write_json

    plan = FileRuntimeInstallation.model_validate(plan.model_dump(mode="json"))
    identity = digest(plan)
    if reviewed_digest != identity:
        raise ValueError("exact file-runtime installation review required")
    if (plan.system, plan.machine, plan.python_version, plan.installer_python) != (
        sys.platform,
        platform.machine(),
        platform.python_version(),
        str(Path(sys.executable).resolve()),
    ):
        raise ValueError("reviewed installer platform or Python changed")
    if file_digest(canonical(plan.installer_python)) != plan.installer_python_sha256:
        raise ValueError("reviewed installer Python bytes changed")
    root, journal = paths(plan)
    required = check_files(plan)
    require_space(root, required)
    if (root.exists() or root.is_symlink()) and not journal.exists():
        raise ValueError("destination already exists; preserved")
    with file_lock(journal):
        before, state = load_state(journal)
        if state:
            if (
                state.get("plan_sha256") == identity
                and state.get("status") == "installed"
                and snapshot(root) == state.get("applied_tree_sha256")
            ):
                return state
            raise ValueError(
                "existing installation changed, failed or interrupted; no automatic retry"
            )
        if root.exists() or root.is_symlink():
            raise ValueError("destination already exists; preserved")
        state = {
            "schema": "aeep.toolkit.installation-state.v1",
            "plan_sha256": identity,
            "destination": str(root),
            "original": "absent",
            "status": "installing",
            "automatic_retry": False,
        }
        write_json(journal, state, before=before)
        before, _ = load_state(journal)
        try:
            root.mkdir(mode=0o700)
            for entry in plan.files:
                require_space(root, 0)
                source = canonical(str(Path(plan.artifact_root) / entry.source))
                target = root / entry.destination
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                fd = os.open(source, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
                with os.fdopen(fd, "rb") as original, target.open("xb") as output:
                    info = os.fstat(original.fileno())
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or info.st_nlink != 1
                        or info.st_size != entry.size_bytes
                    ):
                        raise ValueError("artifact changed before staging")
                    remaining = entry.size_bytes
                    while remaining:
                        require_space(root, 0)
                        chunk = original.read(min(remaining, 1024**2))
                        if not chunk:
                            raise ValueError("artifact shortened during staging")
                        output.write(chunk)
                        remaining -= len(chunk)
                    if original.read(1):
                        raise ValueError("artifact grew during staging")
                if file_digest(target) != entry.sha256:
                    raise ValueError("copied artifact differs from the reviewed hash")
                target.chmod(0o555 if entry.executable else 0o444)
            state.update(
                status="installed",
                applied_tree_sha256=snapshot(root),
                enabled=False,
                qualified=False,
            )
        except BaseException:
            state["status"] = "failed"
            write_json(journal, state, before=before)
            raise
        write_json(journal, state, before=before)
        return state
