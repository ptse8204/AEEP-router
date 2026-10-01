"""Offline observations supplement, and never authorize, authenticated conformance."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from test_v08_managed_workers import binding

from aeep.errors import ConfigurationError
from aeep.models import ExecutorSpec
from scripts.probe_managed_pair import offline_specs, probe

pytestmark = pytest.mark.assessment_boundary


def fixture_specs():
    result = []
    for role in ('control', 'treatment'):
        worker = binding().model_copy(update={'worker_id': role})
        result.append(ExecutorSpec(id=role, capability='offline', kind='host_managed', description='Offline fixture',
            resource_pool='fixture', config={'adapter_id':'codex-app-server', 'argv':[worker.binary,'app-server'],
                'instructions':'Never dispatched', 'managed_worker':worker.model_dump(mode='json')}).model_dump(mode='json'))
    return result


@pytest.mark.parametrize('field,value', [('credential_volume','aeep-auth-fixture'),('network_id','a'*64)])
async def test_pair_refuses_authenticated_or_networked_workers_before_launch(tmp_path, field, value):
    values = fixture_specs()
    values[0]['config']['managed_worker'][field] = value
    path = tmp_path/'workers.json'
    path.write_text(json.dumps(values))
    with pytest.raises(ValueError,match='refuses credentials'):
        await probe(path)


def test_offline_pair_requires_bounded_matching_definitions(tmp_path):
    path = tmp_path/'workers.json'
    values = fixture_specs()
    path.write_text(json.dumps(values))
    specs, digest = offline_specs(path)
    assert len(specs) == 2 and len(digest) == 64
    values[0]['config']['managed_worker']['memory_mb'] *= 2
    path.write_text(json.dumps(values))
    with pytest.raises(ConfigurationError,match='differ'):
        offline_specs(path)
    path.write_text('[]')
    with pytest.raises(ValueError,match='two offline'):
        offline_specs(path)
    path.write_bytes(b' '*262145)
    with pytest.raises(ValueError,match='bound'):
        offline_specs(path)
    forbidden = tmp_path/'auth.json'
    forbidden.write_text('synthetic; never read')
    with pytest.raises(ConfigurationError,match='non-secret'):
        offline_specs(forbidden)
    link = tmp_path/'alias'
    link.symlink_to(path)
    with pytest.raises(ConfigurationError,match='non-secret'):
        offline_specs(link)


@pytest.mark.real_container
@pytest.mark.skipif(not os.environ.get('AEEP_INSPECTION_FIXTURE_SPECS'), reason='requires explicit offline Codex pair')
async def test_actual_pair_separates_canaries_dependencies_and_interrupted_processes():
    result = await probe(Path(os.environ['AEEP_INSPECTION_FIXTURE_SPECS']))
    assert result['passed'], result
    assert result['authenticated'] is False and result['full_conformance'] is False and result['model_turns'] == 0
    assert result['source_unchanged']
    assert set(result['workers']) == {'control','treatment'}
    assert all(item['cleanup_confirmed'] for item in result['workers'].values())
    assert all(item['observed']['private_input_tree'] for item in result['workers'].values())
    assert result['workers']['control']['observed']['candidate_skill_sha256'] is None
    assert result['workers']['treatment']['observed']['candidate_skill_sha256']


async def test_partial_probe_failure_remains_negative_and_closes_transport(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from scripts import probe_managed_pair

    path = tmp_path/'workers.json'
    path.write_text(json.dumps(fixture_specs()))
    adapter = SimpleNamespace(transport=SimpleNamespace(close=AsyncMock()),
                              _worker_process_id=None, _worker_security=None)
    monkeypatch.setattr(probe_managed_pair.CodexAppServerAdapter, 'from_executor', lambda *args, **kwargs: adapter)
    monkeypatch.setattr(probe_managed_pair, 'command', AsyncMock(side_effect=RuntimeError('synthetic failure')))
    result = await probe(path)
    assert result['passed'] is False and result['failed_stage'] == 'start'
    assert result['error_type'] == 'RuntimeError'
    assert result['workers']['control']['cleanup_confirmed'] is False
    adapter.transport.close.assert_awaited_once()
