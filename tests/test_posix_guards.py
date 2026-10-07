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
