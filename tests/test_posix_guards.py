"""Unsupported hosts must reject protected operations before touching files or children."""
import os

import pytest

from aeep.connections import file_lock
from aeep.errors import ConfigurationError
from aeep.hosts.codex_metrics import relay
from aeep.hosts.codex_native_process import execute_single_process
from aeep.hosts.codex_project import _read, _replace_codex_bytes
from aeep.tasks import _read as read_overlay


@pytest.mark.parametrize('read', [_read, read_overlay])
def test_protected_reads_require_no_follow(tmp_path, monkeypatch, read):
    monkeypatch.delattr(os, 'O_NOFOLLOW', raising=False)
    with pytest.raises(ConfigurationError, match='macOS or Linux/WSL'):
        read(tmp_path / 'missing')


def test_protected_mutations_reject_unsupported_host(tmp_path, monkeypatch):
    monkeypatch.delattr(os, 'O_NOFOLLOW', raising=False)
    path = tmp_path / 'untouched' / 'config'
    with pytest.raises(ConfigurationError, match='macOS or Linux/WSL'), file_lock(path):
        pytest.fail('unsupported lock acquired')
    with pytest.raises(ConfigurationError, match='macOS or Linux/WSL'):
        _replace_codex_bytes(path, None, b'new')
    assert not path.parent.exists()


async def test_process_guards_reject_before_launch(monkeypatch):
    monkeypatch.delattr(os, 'killpg', raising=False)
    with pytest.raises(ValueError, match='POSIX'):
        relay([], 'unused')
    monkeypatch.delattr(os, 'getsid', raising=False)
    with pytest.raises(ConfigurationError, match='POSIX'):
        await execute_single_process(None, [], {}, None, 1, 100)


def test_worker_executable_uses_linux_paths_and_local_executable_uses_host_paths(monkeypatch):
    from pathlib import PureWindowsPath
    from types import SimpleNamespace

    import aeep.models as models

    windows_paths = SimpleNamespace(isabs=lambda value: PureWindowsPath(value).is_absolute())
    monkeypatch.setattr(models, 'os', SimpleNamespace(path=windows_paths))
    fields = {'adapter_id': 'fixture', 'instructions': 'fixture', 'argv': ['/opt/codex/codex']}
    worker = models.ManagedHostExecutorConfig(**fields, managed_worker={'worker_id': 'fixture'})
    assert worker.argv == ('/opt/codex/codex',)
    with pytest.raises(ValueError, match='absolute'):
        models.ManagedHostExecutorConfig(**fields)
    fields['argv'] = [r'C:\tools\codex.exe']
    assert models.ManagedHostExecutorConfig(**fields).argv == tuple(fields['argv'])
    with pytest.raises(ValueError, match='absolute'):
        models.ManagedHostExecutorConfig(**fields, managed_worker={'worker_id': 'fixture'})


def test_container_runtime_is_a_host_path_while_binary_and_socket_are_posix(monkeypatch):
    from pathlib import PureWindowsPath

    from test_v08_managed_workers import binding

    import aeep.hosts.workers as workers

    monkeypatch.setattr(workers, 'Path', PureWindowsPath)
    worker = binding(runtime=r'C:\tools\docker.exe')
    assert worker.binary == '/opt/codex' and worker.socket == '/tmp/docker.sock'
    with pytest.raises(ValueError, match='explicit absolute'):
        binding(runtime='/opt/docker')
