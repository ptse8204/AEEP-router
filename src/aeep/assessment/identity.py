"""Static executable identity without importing or running candidate modules."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path

from ..errors import ConfigurationError
from ..models import ExecutorKind, ExecutorSpec
from .models import AssessmentSubject


def protected_directory(path: Path) -> bool:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
    resolved = path.resolve()
    return Path.home().resolve().is_relative_to(resolved) or codex_home.is_relative_to(resolved) or (resolved.is_relative_to(codex_home) and not any(resolved.is_relative_to(codex_home / directory) for directory in ("plugins", "packages")))


def file_digest(path: Path) -> str:
    if protected_directory(path):
        raise ConfigurationError("Codex state is excluded from executable identity inspection")
    if (
        path.is_symlink()
        or path.absolute() != path.resolve()
        or not path.is_file()
        or path.name in {"auth.json", ".env", "credentials.json"}
    ):
        raise ConfigurationError("executable identity requires an explicit non-secret regular file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()


def local_dependencies(spec: ExecutorSpec) -> dict[str, str]:
    paths: set[Path] = set()
    if spec.kind == ExecutorKind.PYTHON:
        module = str(spec.config.get("callable", "")).split(":", 1)[0]
        if not module or not all(part.isidentifier() for part in module.split(".")):
            raise ConfigurationError("Python assessment requires an explicit module callable")
        for root in sys.path:
            base = Path(root).joinpath(*module.split("."))
            match = next(
                (
                    path
                    for path in (base.with_suffix(".py"), base / "__init__.py")
                    if path.is_file()
                ),
                None,
            )
            if match is not None:
                paths.add(match.absolute())
                break
        else:
            raise ConfigurationError(
                "Python source identity is unavailable; use a pinned container image"
            )
    if spec.kind in {ExecutorKind.COMMAND, ExecutorKind.MANAGED_HOST, ExecutorKind.MCP}:
        argv = spec.config.get("argv", [])
        if spec.kind == ExecutorKind.MCP and spec.config.get("transport") == "stdio":
            argv = [spec.config.get("command"), *spec.config.get("args", [])]
        if argv:
            executable = shutil.which(str(argv[0]))
            if executable:
                # Configured executable symlinks are resolved once; invocation identity also binds argv.
                paths.add(Path(executable).resolve())
            cwd = Path(spec.config.get("cwd") or ".")
            for arg in argv[1:]:
                if isinstance(arg, str) and "{" not in arg and not arg.startswith("-"):
                    path = Path(arg) if Path(arg).is_absolute() else cwd / arg
                    if path.is_file():
                        paths.add(path.absolute())
    return {str(path): file_digest(path) for path in sorted(paths)}


def verify_dependencies(dependencies: dict[str, str]) -> None:
    for name, digest in dependencies.items():
        if file_digest(Path(name)) != digest:
            raise ConfigurationError(
                "assessment executable dependency changed; renewed review is required"
            )


def verify_subject(subject: AssessmentSubject) -> None:
    location = Path(subject.location)
    for name, digest in subject.dependency_digests.items():
        if file_digest(location / name if location.is_dir() else location) != digest:
            raise ConfigurationError("assessment subject changed; renewed review is required")


def runtime_dependencies() -> dict[str, str]:
    """Freeze the AEEP code that evaluates evidence and runs reviewed mappings."""
    root = Path(__file__).resolve().parents[1]
    return {str(path): file_digest(path) for path in sorted(root.rglob("*.py"))}
