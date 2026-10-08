"""Read actual project configuration fixtures without starting any service."""

import hashlib
import json
import os
import socket
import subprocess

import pytest

from aeep.router import Router
from aeep.store import ReceiptStore
from aeep_toolkit.cli import doctor, main

pytestmark = pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="Project configuration inspection requires POSIX")


@pytest.mark.parametrize(('host', 'name', 'text'), [
    ('codex', '.codex/config.toml', '[mcp_servers.aeep_fixture]\nenabled = false\ncommand = "SECRET_ARG"\n[mcp_servers.aeep_fixture.env]\nTOKEN = "SECRET_TOKEN"\n'),
    ('claude', '.mcp.json', '{"mcpServers":{"aeep_fixture":{"enabled":false,"env":{"TOKEN":"SECRET_TOKEN"},"command":"SECRET_ARG"}}}'),
    ('deepseek-api', '.aeep/deepseek-connection.json', '{"mcpServers":{"aeep_fixture":{"enabled":false,"env":{"TOKEN":"SECRET_TOKEN"}}}}'),
    ('dsh', '.aeep/dsh-connection.json', '[{"insert":[{"id":"aeep_fixture","config":{"TOKEN":"SECRET_TOKEN"}}]}]'),
])
def test_doctor_reuses_inventory_without_effects_or_secret_values(tmp_path, monkeypatch, host, name, text):
    config = tmp_path / name
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(text)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}

    def forbidden(*args, **kwargs):
        pytest.fail('doctor attempted a process, network, or store effect')

    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(Router, '__init__', forbidden)
    monkeypatch.setattr(ReceiptStore, '__init__', forbidden)
    result = doctor(host, tmp_path)
    assert result['status'] == 'configuration_only'
    connection = result['connections'][0]
    assert connection == {'name': 'aeep_fixture', 'configured': True,
                          'enabled_in_configuration': None if host == 'dsh' else False,
                          'installed': None, 'live_exposure': None, 'qualified': None}
    assert 'SECRET_' not in json.dumps(result)
    facts = {k: v for k, v in result.items() if k not in {'observation_sha256', 'notice'}}
    assert result['observation_sha256'] == hashlib.sha256(json.dumps(facts, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_missing_configuration_stays_unknown_and_cli_does_not_create_it(tmp_path, capsys):
    assert main(['doctor', '--host', 'codex', '--project', str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['connections'] == []
    assert not list(tmp_path.iterdir())


def test_invalid_enabled_value_is_never_echoed(tmp_path):
    (tmp_path / '.mcp.json').write_text('{"mcpServers":{"fixture":{"enabled":{"TOKEN":"secret"}}}}')
    result = doctor('claude', tmp_path)
    assert result['connections'][0]['enabled_in_configuration'] is None
    assert 'secret' not in json.dumps(result)


@pytest.mark.parametrize('text', ['{invalid-secret', '{"mcpServers":[]}', '{"mcpServers":{"bad\\u001bname":{}}}'])
def test_bad_configuration_fails_without_echoing_contents(tmp_path, capsys, text):
    (tmp_path / '.mcp.json').write_text(text)
    with pytest.raises(SystemExit) as failure:
        main(['doctor', '--host', 'claude', '--project', str(tmp_path)])
    assert failure.value.code == 2
    assert 'secret' not in capsys.readouterr().err


def test_missing_project_does_not_create_directory(tmp_path):
    missing = tmp_path / 'absent'
    with pytest.raises(FileNotFoundError):
        doctor('codex', missing)
    assert not missing.exists()


def test_doctor_rejects_unknown_host_before_inventory(tmp_path):
    with pytest.raises(ValueError, match='unsupported host'):
        doctor('unknown', tmp_path)


def test_special_and_linked_configuration_files_fail_closed(tmp_path, capsys):
    config = tmp_path / '.mcp.json'
    os.mkfifo(config)
    with pytest.raises(SystemExit) as failure:
        main(['doctor', '--host', 'claude', '--project', str(tmp_path)])
    assert failure.value.code == 2
    config.unlink()
    secret = tmp_path / 'not-configuration.txt'
    secret.write_text('SENSITIVE_VALUE')
    config.symlink_to(secret)
    with pytest.raises(SystemExit):
        main(['doctor', '--host', 'claude', '--project', str(tmp_path)])
    assert 'SENSITIVE_VALUE' not in capsys.readouterr().err
