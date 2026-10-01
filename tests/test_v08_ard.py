from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from typer.testing import CliRunner

from aeep.cli import app
from aeep.discovery import ARDRegistryAdapter, FixtureRegistryAdapter, RegistryQuery
from aeep.errors import ConfigurationError, ExecutorError, ProtocolError
from aeep.models import Manifest

pytestmark = pytest.mark.assessment_contract


async def test_ard_search_is_bounded_inert_and_keeps_untrusted_provenance(monkeypatch):
    requests = []

    async def validate(*args, **kwargs):
        assert args[0] == 'https://registry.test/search'

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'results': [
            {'identifier': 'urn:air:skill:one', 'displayName': 'Sheet helper', 'score': 100,
             'url': 'https://untrusted.test/install.sh', 'type': 'skill', 'vendor': {'verified': True}},
            {'identifier': 'urn:air:skill:two'},
            {'identifier': 'urn:air:skill:three', '@context': {'url': 'https://evil.test'}},
            {'identifier': 'urn:air:skill:four', 'url': 'x', 'data': {}},
            'invalid'], 'referrals': ['https://other.test'], 'pageToken': 'next'})

    monkeypatch.setattr('aeep.discovery.validate_http_url', validate)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = ARDRegistryAdapter('https://registry.test', client=client)
        results = await adapter.search(RegistryQuery(query='spreadsheet', limit=5, cursor='prior'))
    assert len(requests) == 1 and len(results) == 2
    assert json.loads(requests[0].content) == {
        'query': {'text': 'spreadsheet'}, 'pageSize': 5, 'federation': 'none', 'pageToken': 'prior'}
    assert all(item.package_locator is None and item.remote_endpoint is None for item in results)
    assert results[0].provenance['trust_verified'] is False
    assert results[0].provenance['entry']['score'] == 100
    assert results[1].name == 'urn:air:skill:two'
    assert len(adapter.warnings) == 4
    assert not hasattr(results[0], 'qualified')


@pytest.mark.parametrize('failure', ['dns', 'redirect', 'oversize', 'invalid_json', 'shape', 'private'])
async def test_ard_failures_use_explicit_local_fallback_without_following_links(tmp_path, monkeypatch, failure):
    fixture = tmp_path / 'local.json'
    await asyncio.to_thread(fixture.write_text, json.dumps({'candidates': [
        {'registry_candidate_id': 'known', 'name': 'local sheet'}]}))
    requests = []

    async def validate(*args, **kwargs):
        if failure == 'dns':
            raise ExecutorError('cannot resolve private diagnostic')
        if failure == 'private':
            raise ConfigurationError('private endpoint')

    def handler(request):
        requests.append(request)
        if failure == 'redirect':
            return httpx.Response(302, headers={'location': 'https://other.test'})
        if failure == 'oversize':
            return httpx.Response(200, content=b' ' * 1_000_001)
        if failure == 'invalid_json':
            return httpx.Response(200, content=b'invalid')
        return httpx.Response(200, json={'unexpected': []})

    monkeypatch.setattr('aeep.discovery.validate_http_url', validate)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        adapter = ARDRegistryAdapter('https://registry.test', client=client, fallback=FixtureRegistryAdapter(fixture))
        assert [item.registry_candidate_id for item in await adapter.search(RegistryQuery(query='sheet'))] == ['known']
        assert adapter.warnings == ['ARD unavailable or unsupported; returning configured local candidates']
        adapter.fallback = None
        with pytest.raises(ProtocolError, match='no candidates activated'):
            await adapter.search(RegistryQuery(query='sheet'))
    assert all(request.url.host == 'registry.test' for request in requests)


async def test_ard_rejects_implicit_queries_and_filters_locally(monkeypatch):
    async def validate(*args, **kwargs):
        pass

    def handler(request):
        assert json.loads(request.content)['query']['filter'] == {'type': ['skill']}
        return httpx.Response(200, json={'results': [
            {'identifier': 'urn:air:other', 'type': 'server'},
            {'identifier': 'urn:air:skill', 'type': 'skill'}]})

    monkeypatch.setattr('aeep.discovery.validate_http_url', validate)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = ARDRegistryAdapter('https://registry.test', client=client, allowed_types=('skill',))
        with pytest.raises(ConfigurationError, match='explicit public'):
            await adapter.search(RegistryQuery())
        assert len(await adapter.search(RegistryQuery(query='sheet'))) == 1
        assert adapter.warnings == ['Malformed or unsupported ARD entry omitted']
        adapter.base_url += '?token=not-sent'
        with pytest.raises(ProtocolError):
            await adapter.search(RegistryQuery(query='sheet'))


def test_ard_cli_stores_only_inert_local_fallback(tmp_path, monkeypatch):
    fixture = tmp_path / 'local.json'
    fixture.write_text(json.dumps({'candidates': [{'registry_candidate_id': 'known', 'name': 'sheet'}]}))
    manifest = tmp_path / 'aeep.json'
    manifest.write_text(Manifest(database=str(tmp_path / 'state.db')).model_dump_json())

    async def unavailable(*args, **kwargs):
        raise ExecutorError('fixture unavailable')

    monkeypatch.setattr('aeep.discovery.validate_http_url', unavailable)
    runner = CliRunner()
    args = ['registry', 'search', 'sheet', '--registry', 'ard', '--fixture', str(fixture), '-m', str(manifest)]
    result = runner.invoke(app, [*args, '--base-url', 'https://registry.test'])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]['registry_candidate_id'] == 'known'
    assert 'returning configured local' in result.stderr
    assert runner.invoke(app, args).exit_code != 0
