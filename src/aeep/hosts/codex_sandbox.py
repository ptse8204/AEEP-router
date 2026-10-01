"""Native command containment; no model invocation or persistent host configuration."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ..errors import ConfigurationError
from ..models import StrictModel


@lru_cache(maxsize=1)
def native_policy_digest() -> str:
    """Bind route review to the installed adapter that compiles containment."""
    command = Path(__file__).parents[1] / 'executors' / 'command.py'
    from .codex_native_process import guard_digest
    helper = Path(__file__).with_name('codex_native_process.py')
    transport = Path(__file__).with_name('codex_app_server.py')
    return hashlib.sha256(Path(__file__).read_bytes() + b'\0' + command.read_bytes()
                          + helper.read_bytes() + transport.read_bytes() + guard_digest().encode()).hexdigest()


def native_backend_digest(boundary: NativeSandboxConfig) -> str:
    payload = {'boundary': boundary.model_dump(mode='json'), 'policy_digest': native_policy_digest()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class NativeSandboxConfig(StrictModel):
    schema_version: Literal['codex.native-sandbox.v1'] = 'codex.native-sandbox.v1'
    binary: str
    binary_sha256: str = Field(pattern=r'^sha256:[a-f0-9]{64}$')
    project_root: str
    read_roots: list[str] = Field(default_factory=list, max_length=32)
    write_roots: list[str] = Field(default_factory=list, max_length=16)
    deny_roots: list[str] = Field(default_factory=list, max_length=32)
    network: Literal[False] = False
    single_process: bool = False
    python_binary: str | None = None
    python_sha256: str | None = Field(default=None, pattern=r'^sha256:[a-f0-9]{64}$')

    def validate_single_process(self) -> None:
        if not self.single_process:
            return
        if sys.platform != "darwin" or os.geteuid() == 0:
            raise ConfigurationError("single-process native commands require nonroot macOS")
        if not self.python_binary or not self.python_sha256:
            raise ConfigurationError("single-process native commands require pinned Python")
        path = Path(self.python_binary)
        if not path.is_absolute() or path.resolve() != path or not any(path.is_relative_to(root) for root in self.read_roots):
            raise ConfigurationError("single-process Python requires a canonical permitted read path")
        try:
            with path.open("rb") as stream:
                digest = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError as exc:
            raise ConfigurationError("single-process Python is unavailable") from exc
        if digest != self.python_sha256:
            raise ConfigurationError("single-process Python changed")

    def validate_environment(self, configured: object) -> dict[str, str]:
        """Only literal scratch variables scoped to an existing reviewed write root."""
        if not isinstance(configured, dict):
            raise ConfigurationError('native sandbox environment must be a mapping')
        result: dict[str, str] = {}
        for key, value in configured.items():
            if key not in {'TMPDIR', 'TMP', 'TEMP'} or not isinstance(value, str):
                raise ConfigurationError('native sandbox environment supports only literal temporary paths')
            path = Path(value)
            if not path.is_absolute() or path.resolve() != path or value not in self.write_roots or not path.is_dir():
                raise ConfigurationError('native temporary path requires an existing reviewed write root')
            result[key] = value
        return result

    @model_validator(mode='after')
    def bounded_paths(self) -> NativeSandboxConfig:
        for value in [self.binary, self.project_root, *self.read_roots, *self.write_roots, *self.deny_roots]:
            path = Path(value)
            if not path.is_absolute() or '..' in path.parts or path.resolve() != path:
                raise ValueError('native sandbox paths must be absolute, canonical and symlink-free')
        project = Path(self.project_root)
        for value in self.write_roots:
            if Path(value) == project or not Path(value).is_relative_to(project):
                raise ValueError('native writes require explicit project subdirectories')
        for denied in self.deny_roots:
            if any(Path(value).is_relative_to(denied) for value in [*self.read_roots, *self.write_roots]):
                raise ValueError('native allows must not reopen denied paths')
        return self

    def argv(self, command: list[str]) -> list[str]:
        overrides = self.permission_overrides()
        if sys.platform != 'darwin':
            raise ConfigurationError('native sandbox v1 is supported only on macOS')
        try:
            with Path(self.binary).open('rb') as stream:
                digest = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
        except OSError as exc:
            raise ConfigurationError('native sandbox executable is unavailable') from exc
        if digest != self.binary_sha256:
            raise ConfigurationError('native sandbox executable changed')
        return [self.binary, 'sandbox', '--permission-profile', 'aeep-native-task',
                '--include-managed-config', '--cd', self.project_root, *overrides, '--', *command]

    def permission_overrides(self) -> list[str]:
        """Validate/compile policy offline; argv() verifies the launcher at dispatch."""
        if any(character in value for value in [self.binary, self.project_root, *self.read_roots,
                                                 *self.write_roots, *self.deny_roots]
               for character in '*?[]{}\\'):
            raise ConfigurationError('native sandbox path contains unsupported glob characters')
        # Codex's macOS :minimal rules grant writable system temp directories.
        # Exact path denies do not carve these grants out on this launcher;
        # recursive glob denies do. Do not promise narrower access inside them.
        implicit_temp = tuple(sorted({Path('/tmp').resolve(), Path('/var/tmp').resolve()}))
        if any(Path(value).is_relative_to(temp) for temp in implicit_temp
               for value in [self.project_root, *self.read_roots, *self.write_roots]):
            raise ConfigurationError('native sandbox scope cannot allow system temporary directories')
        filesystem = {':root': 'deny', ':minimal': 'read'}
        filesystem.update(dict.fromkeys(self.read_roots, 'read'))
        filesystem.update(dict.fromkeys(self.write_roots, 'write'))
        filesystem.update(dict.fromkeys(self.deny_roots, 'deny'))
        protected = [Path.home() / '.codex', Path(self.project_root) / '.aeep',
                     Path(self.project_root) / '.codex', Path(self.project_root) / 'aeep.yaml',
                     Path(self.project_root) / 'aeep.yml', Path(self.project_root) / 'aeep.json']
        for root in protected:
            filesystem[str(root)] = 'deny'
            # More-specific allows must never reopen a protected control path.
            if any(Path(path).is_relative_to(root) for path in [*self.read_roots, *self.write_roots]):
                raise ConfigurationError('native sandbox scope overlaps protected control files')
        for root in [*implicit_temp, *map(Path, self.deny_roots), *protected]:
            filesystem[str(root)] = 'deny'
            filesystem[str(root / '**')] = 'deny'
            # On this macOS launcher an exact deny can lose to :minimal's
            # platform allow; this glob covers the root itself as well.
            filesystem[f'{root}{{,/**}}'] = 'deny'
        profile = 'aeep-native-task'
        argv = ['-c', f'permissions.{profile}.network.enabled=false']
        rules = ', '.join(f'{json.dumps(path, ensure_ascii=False)} = {json.dumps(permission, ensure_ascii=False)}'
                          for path, permission in filesystem.items())
        argv.extend(['-c', f'permissions.{profile}.filesystem={{ {rules} }}'])
        return argv
