"""Reviewed, offline wheel installation into an exclusively owned private runtime."""
from __future__ import annotations

import configparser
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import venv
import zipfile
from datetime import UTC, datetime
from email.parser import BytesParser
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import parse_tag, sys_tags
from packaging.utils import parse_wheel_filename
from packaging.version import Version
from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from .installation import InstallationPreview, PreviewPolicy, preview, require_compatible
from .models import ContractModel, Digest, ExtensionRegistry, Identifier
from .storage import StorageReserveException

if TYPE_CHECKING:
    from .file_runtime import FileRuntimeInstallation


class Wheel(ContractModel):
    extension_id: Identifier
    filename: str = Field(pattern=r'^[A-Za-z0-9_.+!-]+\.whl$')
    name: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
    version: str = Field(pattern=r'^[0-9][A-Za-z0-9.+!_-]*$')
    sha256: Digest


class RuntimeInstallation(ContractModel):
    schema_version: Literal['aeep.toolkit.runtime-installation.v1', 'aeep.toolkit.runtime-installation.v2'] = 'aeep.toolkit.runtime-installation.v1'
    storage_exception: StorageReserveException | None = None
    preview: InstallationPreview
    policy: PreviewPolicy
    destination: str
    wheelhouse: str
    interpreter: str
    interpreter_sha256: Digest
    python_version: str
    system: str
    machine: str
    wheels: tuple[Wheel, ...] = Field(min_length=1, max_length=256)
    effects: tuple[str, ...] = (
        'Create a new private Python environment and sibling installation journal/lock.',
        'Install only reviewed local wheels; no index, source builds, host activation or sign-in.',
        'Reserve staged/expanded wheel bytes and 500 MiB bootstrap headroom above the 50 GiB host reserve.',
        'Keep failed/interrupted state; no automatic retry. Preserve the journal on removal.',
        'Remove only a completely unchanged owned runtime; preserve conflicts for inspection.',
    )

    @model_validator(mode='after')
    def exact_closure(self) -> RuntimeInstallation:
        if self.schema_version.endswith('.v2') != (self.storage_exception is not None):
            raise ValueError('temporary storage exceptions require runtime installation v2')
        if self.storage_exception is not None:
            exception = self.storage_exception
            if (self.destination != exception.destination
                    or digest([w.model_dump(mode='json') for w in self.wheels]) != exception.wheel_set_sha256
                    or storage_effect(exception) not in self.effects):
                raise ValueError('storage exception differs from the exact destination, wheels or effects')
        original = self.preview
        rebuilt = preview(ExtensionRegistry(extensions=tuple(i.manifest for i in original.items)),
                          original.selected, self.policy, profile=original.profile,
                          observations=tuple(i.observation for i in original.items),
                          storage_exception=self.storage_exception)
        if rebuilt != original:
            raise ValueError('preview differs from resolved policy/manifest closure')
        require_compatible(rebuilt)
        items = {i.manifest.extension_id: i.manifest for i in rebuilt.items}
        if (len(self.wheels) != len(items) or {w.extension_id for w in self.wheels} != set(items)
                or len({normalize(w.name) for w in self.wheels}) != len(self.wheels)
                or len({w.filename for w in self.wheels}) != len(self.wheels)):
            raise ValueError('every selected dependency requires one unique wheel')
        for wheel in self.wheels:
            if wheel.sha256 != items[wheel.extension_id].source.artifact_sha256:
                raise ValueError('wheel does not match selected manifest artifact')
        return self

    @model_serializer(mode='wrap')
    def preserve_v1(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if self.storage_exception is None:
            value.pop('storage_exception', None)
        return value


def storage_effect(exception: StorageReserveException) -> str:
    return (f'Temporary storage exception {exception.exception_id}: reserve '
            f'{exception.minimum_free_bytes} bytes, maximum additional reservation '
            f'{exception.maximum_additional_bytes} bytes, expires {exception.expires_at.isoformat()}.')


class StorageReserveError(ValueError):
    def __init__(self, observation: dict[str, Any]) -> None:
        super().__init__('temporary storage exception expired, changed filesystem or insufficient real capacity')
        self.observation = observation


def exception_space(plan: RuntimeInstallation, required: int, *, baseline_free: int | None = None) -> dict[str, Any]:
    """Measure actual host capacity; a reviewed exception never fabricates free space."""
    exception = plan.storage_exception
    if exception is None:
        raise ValueError('no scoped storage exception')
    parent = canonical(plan.destination).parent
    now = datetime.now(UTC)
    free = shutil.disk_usage(parent).free
    observation = {'observed_at': now.isoformat(), 'available_free_bytes': free,
                   'required_additional_bytes': required, 'minimum_free_bytes': exception.minimum_free_bytes,
                   'exception_sha256': exception.digest(), 'host_delta_is_not_task_attribution': True}
    if (not exception.issued_at <= now < exception.expires_at
            or parent.stat().st_dev != exception.filesystem_device
            or required > exception.maximum_additional_bytes
            or free - required < exception.minimum_free_bytes
            or (baseline_free is not None and baseline_free - free > exception.maximum_additional_bytes)):
        raise StorageReserveError(observation | {'accepted': False})
    return observation | {'accepted': True}


def normalize(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def digest(value: Any) -> str:
    if isinstance(value, ContractModel):
        value = value.model_dump(mode='json')
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def canonical(path: str) -> Path:
    result = Path(path)
    protected = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).resolve()
    if (not result.is_absolute() or result.resolve() != result or result.is_relative_to(protected)
            or any(p.casefold() == '.codex' for p in result.parts)):
        raise ValueError('installation paths must be canonical and outside Codex state')
    return result


def file_digest(path: Path) -> str:
    # Read with no-follow/nonblocking checks before hashing binaries or package bytes.
    if not hasattr(os, 'O_NOFOLLOW'):
        raise ValueError('private runtime installation requires macOS or Linux/WSL')
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 512 * 1024**2:
            raise ValueError('expected a bounded, unlinked regular file')
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def wheel_commands(path: Path, wheel: Wheel) -> tuple[str, ...]:
    """Inventory private venv scripts; reject bootstrap overrides and collisions."""
    names: list[str] = []
    prefix = f'{normalize(wheel.name).replace("-", "_")}-{wheel.version}.data/scripts/'
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.startswith(prefix) and not name.endswith('/'):
                names.append(name.removeprefix(prefix))
            if name.endswith('.dist-info/entry_points.txt'):
                if archive.getinfo(name).file_size > 1024**2:
                    raise ValueError('wheel command metadata exceeds bounds')
                parser = configparser.ConfigParser(interpolation=None)
                parser.optionxform = str  # type: ignore[method-assign, assignment]
                try:
                    parser.read_string(archive.read(name).decode('utf-8'))
                except configparser.Error as exc:
                    raise ValueError('invalid wheel command metadata') from exc
                for group in ('console_scripts', 'gui_scripts'):
                    if parser.has_section(group):
                        names.extend(parser[group])
    for name in names:
        if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', name)
                or name.casefold().startswith(('python', 'pip', 'activate', 'deactivate'))):
            raise ValueError('unsupported wheel command: bootstrap override or unsafe name')
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError('wheel command names collide')
    return tuple(sorted(names))


def check_wheel(path: Path, wheel: Wheel) -> int:
    if file_digest(path) != wheel.sha256:
        raise ValueError('wheel artifact changed')
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if (len(names) != len({name.rstrip('/').casefold() for name in names}) or len(names) > 20000
                or sum(entry.file_size for entry in entries) > 512 * 1024**2):
            raise ValueError('wheel exceeds bounds or contains duplicate paths')
        for entry in entries:
            name = Path(entry.filename)
            # pip places this reviewed AEEP data below the private venv's share directory.
            owned_data = (
                wheel.name == 'aeep-agent-router'
                and name.parts[:4] == (f'aeep_agent_router-{wheel.version}.data', 'data', 'share', 'aeep')
                and not any(part.casefold().endswith('.data') for part in name.parts[1:])
            )
            private_script = (len(name.parts) == 3
                and name.parts[:2] == (f'{normalize(wheel.name).replace("-", "_")}-{wheel.version}.data', 'scripts'))
            if (not name.parts or str(name) != entry.filename.rstrip('/') or name.is_absolute() or '..' in name.parts or '\\' in entry.filename
                    or stat.S_ISLNK(entry.external_attr >> 16)
                    or (any(part.casefold().endswith('.data') for part in name.parts) and not (owned_data or private_script))
                    or name.suffix.casefold() == '.pth' or any(Path(part).stem.casefold() in {'sitecustomize', 'usercustomize', 'pip'} for part in name.parts)):
                raise ValueError('wheel contains unsupported paths or interpreter startup hooks')
        metadata = [name for name in names if len(Path(name).parts) == 2 and name.endswith('.dist-info/METADATA')]
        if len(metadata) != 1 or archive.getinfo(metadata[0]).file_size > 1024**2:
            raise ValueError('wheel metadata missing or oversized')
        headers = BytesParser().parsebytes(archive.read(metadata[0]), headersonly=True)
        if (headers.get_all('Name') != [wheel.name] or headers.get_all('Version') != [wheel.version]):
            raise ValueError('wheel metadata differs from reviewed identity')
        wheel_commands(path, wheel)
        # Include allocation rounding, staging and unpacking; manifest estimates cannot shrink this bound.
        return 3 * (path.stat().st_size + sum((e.file_size // 4096 + 1) * 4096 for e in entries))


def host_platforms() -> set[str]:
    system = 'macos' if sys.platform == 'darwin' else sys.platform
    machine = platform.machine()
    return {f'{sys.platform}-{machine}', f'{system}-{machine}-python{sys.version_info.major}.{sys.version_info.minor}'}


def check_closure(source: Path, wheels: tuple[Wheel, ...], selected_platform: str) -> int:
    if selected_platform not in host_platforms():
        raise ValueError('declared installation platform differs from this host')
    # packaging can launch a compatibility probe on legacy macOS or musl; preview must never do so.
    if sys.platform == 'darwin':
        mac_version = platform.mac_ver()[0]
        if not mac_version or mac_version.startswith('10.16'):
            raise ValueError('ambiguous macOS version; process-free compatibility preview unavailable')
    elif sys.platform == 'linux':
        try:
            libc = os.confstr('CS_GNU_LIBC_VERSION')
        except (OSError, ValueError):
            libc = None
        if not libc:
            raise ValueError('process-free wheel preview currently requires glibc on Linux')
    else:
        raise ValueError('private runtime installation requires macOS or glibc Linux')
    supported = set(sys_tags())
    versions = {normalize(w.name): Version(w.version) for w in wheels}
    required = 0
    commands: set[str] = set()
    for wheel in wheels:
        required += check_wheel(source / wheel.filename, wheel)
        selected_commands = {name.casefold() for name in wheel_commands(source / wheel.filename, wheel)}
        if commands & selected_commands:
            raise ValueError('selected wheels overwrite the same private runtime command')
        commands.update(selected_commands)
        name, version, _, tags = parse_wheel_filename(wheel.filename)
        if name != normalize(wheel.name) or version != versions[normalize(wheel.name)] or not tags & supported:
            raise ValueError('wheel filename identity or platform is incompatible')
        with zipfile.ZipFile(source / wheel.filename) as archive:
            metadata = next(n for n in archive.namelist() if len(Path(n).parts) == 2 and n.endswith('.dist-info/METADATA'))
            headers = BytesParser().parsebytes(archive.read(metadata), headersonly=True)
            wheel_metadata = metadata.removesuffix('METADATA') + 'WHEEL'
            if archive.getinfo(wheel_metadata).file_size > 1024**2:
                raise ValueError('wheel tag metadata exceeds bounds')
            wheel_headers = BytesParser().parsebytes(archive.read(wheel_metadata), headersonly=True)
            declared_tags = {tag for raw in wheel_headers.get_all('Tag', []) for tag in parse_tag(raw)}
            if wheel_headers.get_all('Wheel-Version') != ['1.0'] or declared_tags != tags:
                raise ValueError('wheel tag metadata differs from filename or has an unsupported version')
        python = headers.get_all('Requires-Python', [])
        if len(python) > 1 or (python and not SpecifierSet(python[0]).contains(platform.python_version(), prereleases=True)):
            raise ValueError('wheel requires a different Python version')
        for raw in headers.get_all('Requires-Dist', []):
            requirement = Requirement(raw)
            if requirement.marker and not requirement.marker.evaluate({'extra': ''}):
                continue
            if requirement.url or requirement.extras:
                raise ValueError('direct URL dependencies and dependency extras require a separate reviewed closure')
            dependency = versions.get(normalize(requirement.name))
            if dependency is None or not requirement.specifier.contains(dependency, prereleases=True):
                raise ValueError('wheel dependency is missing or incompatible with the selected closure')
    return required


def prepare(plan: InstallationPreview, policy: PreviewPolicy, destination: Path,
            wheelhouse: Path, wheels: tuple[Wheel, ...], *,
            storage_exception: StorageReserveException | None = None) -> RuntimeInstallation:
    """Read local inputs, producing an inert exact review document without writes."""
    target, source = canonical(str(destination)), canonical(str(wheelhouse))
    if not target.parent.is_dir() or target.exists() or not source.is_dir():
        raise ValueError('destination must be absent with an existing parent; wheelhouse must exist')
    interpreter = Path(sys.executable).resolve(strict=True)
    options: dict[str, Any] = {}
    if storage_exception is not None:
        plan = preview(ExtensionRegistry(extensions=tuple(i.manifest for i in plan.items)),
                       plan.selected, policy, profile=plan.profile,
                       observations=tuple(i.observation for i in plan.items), storage_exception=storage_exception)
        effects = list(RuntimeInstallation.model_fields['effects'].default)
        effects[2] = storage_effect(storage_exception)
        options = {'schema_version': 'aeep.toolkit.runtime-installation.v2',
                   'storage_exception': storage_exception, 'effects': tuple(effects)}
    result = RuntimeInstallation(preview=plan, policy=policy, destination=str(target), wheelhouse=str(source),
                                 interpreter=str(interpreter), interpreter_sha256=file_digest(interpreter),
                                 python_version=platform.python_version(), system=sys.platform, machine=platform.machine(),
                                 wheels=wheels, **options)
    required = max(plan.known_disk_bytes, 500 * 1024**2 + check_closure(source, wheels, policy.platform))
    if storage_exception is not None:
        exception_space(result, required)
    elif shutil.disk_usage(target.parent).free - required < 50 * 1024**3:
        raise ValueError('actual wheel closure would cross the 50 GiB free-space reserve')
    return result


def snapshot(root: Path) -> str:
    canonical(str(root))
    if not root.is_dir():
        raise ValueError('owned runtime missing')
    rows: dict[str, Any] = {'.': {'mode': stat.S_IMODE(root.stat().st_mode)}}
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(directory) / name
            if any(part.casefold() == '.codex' for part in path.parts) or name.casefold() in {'auth.json', 'credentials.json'} or name.casefold().startswith('.env'):
                raise ValueError('credential state is excluded from runtime inspection')
            info = path.lstat()
            entry: dict[str, Any] = {'mode': stat.S_IMODE(info.st_mode)}
            if stat.S_ISLNK(info.st_mode):
                entry.update(kind='link', target=os.readlink(path))
            elif stat.S_ISREG(info.st_mode):
                entry.update(kind='file', sha256=file_digest(path))
            elif stat.S_ISDIR(info.st_mode):
                entry.update(kind='directory')
            else:
                raise ValueError('special file in runtime; preserve for inspection')
            rows[str(path.relative_to(root))] = entry
            if len(rows) > 20000:
                raise ValueError('runtime inventory exceeds limit')
    return digest(rows)


def parse_installation(value: Any) -> RuntimeInstallation | FileRuntimeInstallation:
    if isinstance(value, dict) and value.get('schema_version') == 'aeep.toolkit.file-runtime-installation.v1':
        from .file_runtime import FileRuntimeInstallation

        return FileRuntimeInstallation.model_validate(value)
    return RuntimeInstallation.model_validate(value)


def paths(plan: RuntimeInstallation | FileRuntimeInstallation) -> tuple[Path, Path]:
    root = canonical(plan.destination)
    if not root.parent.is_dir():
        raise ValueError('runtime parent must already exist')
    return root, root.with_name(root.name + '.aeep-install.json')


def load_state(journal: Path) -> tuple[bytes | None, dict[str, Any]]:
    from .cli import read_bytes
    if not journal.exists() and not journal.is_symlink():
        return None, {}
    before = read_bytes(journal)
    return before, json.loads(before)


def run(argv: list[str], root: Path) -> None:
    env = {'PATH': os.defpath, 'HOME': str(root), 'PYTHONNOUSERSITE': '1',
           'PIP_CONFIG_FILE': os.devnull, 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'}
    # No child output is retained: installer errors can echo private local paths.
    with subprocess.Popen(argv, cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, start_new_session=True) as child:
        try:
            status = child.wait(timeout=300)
        except BaseException:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            raise
        if status:
            raise subprocess.CalledProcessError(status, argv)


def apply(plan: RuntimeInstallation | FileRuntimeInstallation, reviewed_digest: str) -> dict[str, Any]:
    """Operator CLI only; a model-facing call must never supply this review."""
    from .file_runtime import FileRuntimeInstallation, apply_files

    if isinstance(plan, FileRuntimeInstallation):
        return apply_files(plan, reviewed_digest)
    from aeep.component_setup import require_space
    from aeep.connections import file_lock, write_json

    plan = RuntimeInstallation.model_validate(plan.model_dump(mode='json'))
    identity = digest(plan)
    if reviewed_digest != identity:
        raise ValueError('exact installation review required')
    if (plan.system, plan.machine, plan.python_version, plan.interpreter) != (
            sys.platform, platform.machine(), platform.python_version(), str(Path(sys.executable).resolve())):
        raise ValueError('reviewed installation platform or interpreter changed')
    if file_digest(canonical(plan.interpreter)) != plan.interpreter_sha256:
        raise ValueError('reviewed interpreter bytes changed')
    root, journal = paths(plan)
    source = canonical(plan.wheelhouse)
    # Validate every artifact and reserve before any destination/journal effects.
    required = max(plan.preview.known_disk_bytes,
                   500 * 1024**2 + check_closure(source, plan.wheels, plan.policy.platform))
    storage_checks = [exception_space(plan, required)] if plan.storage_exception else []
    if plan.storage_exception is None:
        require_space(root, required)
    if (root.exists() or root.is_symlink()) and not journal.exists():
        raise ValueError('destination already exists; preserved')
    with file_lock(journal):
        before, state = load_state(journal)
        if state:
            if state.get('plan_sha256') == identity and state.get('status') == 'installed' and snapshot(root) == state.get('applied_tree_sha256'):
                return state
            raise ValueError('existing installation is changed, failed, removed or interrupted; no automatic retry')
        if root.exists() or root.is_symlink():
            raise ValueError('destination already exists; preserved')
        state = {'schema': 'aeep.toolkit.installation-state.v1', 'plan_sha256': identity,
                 'destination': str(root), 'original': 'absent', 'status': 'installing', 'automatic_retry': False}
        if storage_checks:
            state['storage_checks'] = storage_checks
        write_json(journal, state, before=before)
        before, _ = load_state(journal)
        try:
            def check_progress() -> None:
                if plan.storage_exception:
                    try:
                        observation = exception_space(plan, 0, baseline_free=storage_checks[0]['available_free_bytes'])
                    except StorageReserveError as error:
                        storage_checks.append(error.observation)
                        raise
                    storage_checks.append(observation)

            check_progress()
            root.mkdir(mode=0o700)
            venv.EnvBuilder(with_pip=False).create(root)
            check_progress()
            # Stage captured, rechecked wheel bytes; later wheelhouse edits cannot change pip input.
            stage = root / '.aeep-wheels'
            stage.mkdir(mode=0o700)
            for wheel in plan.wheels:
                fd = os.open(source / wheel.filename, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
                with os.fdopen(fd, 'rb') as src, (stage / wheel.filename).open('xb') as dst:
                    info = os.fstat(src.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 512 * 1024**2:
                        raise ValueError('wheel changed before staging')
                    shutil.copyfileobj(src, dst)
                check_wheel(stage / wheel.filename, wheel)
                check_progress()
            lock = root / '.aeep-requirements.txt'
            lock.write_text(''.join(f'{w.name}=={w.version} --hash=sha256:{w.sha256}\n' for w in plan.wheels))
            python = str(root / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))
            run([python, '-I', '-B', '-m', 'ensurepip', '--upgrade', '--default-pip'], root)
            check_progress()
            run([python, '-I', '-B', '-m', 'pip', '--isolated', '--disable-pip-version-check',
                 'install', '--no-deps', '--no-index', '--find-links', str(stage), '--no-cache-dir', '--only-binary=:all:',
                 '--require-hashes', '--no-compile', '-r', str(lock)], root)
            check_progress()
            run([python, '-I', '-B', '-m', 'pip', '--isolated', '--disable-pip-version-check', 'check'], root)
            check_progress()
            state.update(status='installed', applied_tree_sha256=snapshot(root), enabled=False, qualified=False)
        except BaseException:
            state['status'] = 'failed'
            write_json(journal, state, before=before)
            raise
        write_json(journal, state, before=before)
        return state


def remove(plan: RuntimeInstallation | FileRuntimeInstallation, reviewed_digest: str) -> dict[str, Any]:
    from aeep.connections import file_lock, write_json

    plan = parse_installation(plan.model_dump(mode='json'))
    identity = digest(plan)
    if reviewed_digest != identity:
        raise ValueError('exact installation review required for removal')
    root, journal = paths(plan)
    with file_lock(journal):
        before, state = load_state(journal)
        if state.get('plan_sha256') != identity or state.get('original') != 'absent':
            raise ValueError('no matching owned installation')
        if state.get('status') == 'removed' and not root.exists() and not root.is_symlink():
            return state
        if state.get('status') != 'installed' or snapshot(root) != state.get('applied_tree_sha256'):
            raise ValueError('runtime changed or incomplete; all contents preserved')
        state['status'] = 'removing'
        write_json(journal, state, before=before)
        before, _ = load_state(journal)
        # A second check catches edits during the durable transition. Interrupted removal is not replayed.
        if snapshot(root) != state['applied_tree_sha256']:
            raise ValueError('runtime changed during removal; preserved')
        shutil.rmtree(root)
        state['status'] = 'removed'
        write_json(journal, state, before=before)
        return state
