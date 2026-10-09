"""Exercise the existing discovery service through the user-facing toolkit CLI."""
import json
import socket
import subprocess

import pytest

from aeep.router import Router
from aeep.store import ReceiptStore
from aeep_toolkit.cli import main


def test_local_discovery_records_provenance_without_router_or_candidate_execution(tmp_path, monkeypatch, capsys):
    catalog = tmp_path / 'catalog.json'
    catalog.write_text(json.dumps({'candidates': [{'registry_candidate_id': 'csv-helper', 'name': 'CSV helper',
        'description': 'fixture', 'package_locator': {'kind': 'https', 'value': 'https://example.invalid/candidate.zip'}}]}))
    config = tmp_path / 'discovery.json'
    config.write_text(json.dumps({'sources': [{'source_id': 'local', 'kind': 'fixture', 'path': catalog.name}]}))
    def forbidden(*args, **kwargs):
        pytest.fail('discovery executed a process, used network or initialized Router')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(Router, '__init__', forbidden)
    store = tmp_path / 'provenance.sqlite3'
    assert main(['discover', '--config', str(config), '--store', str(store), '--source', 'local', '--query', 'CSV']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['candidate_ids'] == ['csv-helper']
    db = ReceiptStore(store)
    try:
        from aeep.discovery_service import DiscoveryService
        assert DiscoveryService(db, {}).get(result['discovery_id']).candidate_ids == ['csv-helper']
        assert db._connection.execute('SELECT COUNT(*) FROM assessment_jobs').fetchone()[0] == 0
    finally:
        db.close()
    before = store.read_bytes()
    with pytest.raises(SystemExit):
        main(['discover', '--config', str(config), '--store', str(store), '--source', 'missing', '--query', 'CSV'])
    assert store.read_bytes() == before


def test_discovery_denies_remote_without_authority(tmp_path, capsys):
    config = tmp_path / 'discovery.json'
    config.write_text(json.dumps({'sources': [{'source_id': 'remote', 'kind': 'mcp', 'base_url': 'https://example.invalid'}]}))
    with pytest.raises(SystemExit) as failure:
        main(['discover', '--config', str(config), '--store', str(tmp_path/'db'), '--source', 'remote', '--query', 'CSV'])
    assert failure.value.code == 2
    assert 'Cannot read or validate' in capsys.readouterr().err
