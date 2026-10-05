from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import httpx
import pytest

from aeep.discovery import DiscoveryRequest, RegistryQuery
from aeep.discovery_service import (
    DiscoveryConfig,
    DiscoveryService,
    DiscoverySourceConfig,
    discovery_adapter,
)
from aeep.errors import ConfigurationError
from aeep.models import Manifest
from aeep.provider_setup import (
    HostManagedSetupAdapter,
    ProviderSetupDefinition,
    ProviderSetupService,
)
from aeep.router import Router


@pytest.mark.parametrize('source', [
    {'source_id': 'ard', 'kind': 'ard', 'base_url': 'http://invalid.example'},
    {'source_id': 'mcp', 'kind': 'mcp'},
    {'source_id': 'mcp', 'kind': 'mcp', 'base_url': 'https://user:pass@example.org'},
    {'source_id': 'fixture', 'kind': 'fixture', 'path': 'x.json', 'token_env': 'TOKEN'},
    {'source_id': 'docker', 'kind': 'docker'},
    {'source_id': 'smithery', 'kind': 'smithery'},
])
def test_source_config_rejects_ambiguous_authority(source):
    with pytest.raises(ValueError):
        DiscoverySourceConfig.model_validate(source)


async def test_mcp_factory_uses_pinned_contract_and_no_implicit_network(monkeypatch):
    source = DiscoverySourceConfig(source_id='official', kind='mcp', base_url='https://registry.modelcontextprotocol.io')
    router = Router(Manifest(database=':memory:'))
    try:
        service = DiscoveryService.from_config(router.store, DiscoveryConfig(sources=[source]))
        with pytest.raises(ConfigurationError, match='remote-query authority'):
            await service.search(DiscoveryRequest(public_query='filesystem', source_ids=['official']))
        adapter = discovery_adapter(source)
        import aeep.discovery as discovery
        async def validate(*args, **kwargs):
            return None
        monkeypatch.setattr(discovery, 'validate_http_url', validate)
        def handle(request):
            assert request.url.path == '/v0.1/servers'
            assert request.url.params['search'] == 'filesystem'
            return httpx.Response(200, json={'servers': [{'server': {'name': 'io.example/filesystem', 'version': '1.0', 'description': 'File tools'}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            adapter.client = client
            found = await adapter.search(RegistryQuery(query='filesystem'))
        assert len(found) == 1 and found[0].name == 'io.example/filesystem'
        assert not router.registry.all()
    finally:
        await router.close()


async def test_local_package_adapter_is_inert():
    router = Router(Manifest(database=':memory:'))
    source = DiscoverySourceConfig(source_id='package', kind='package', path='examples/provider_package/aeep-provider.yaml')
    try:
        service = DiscoveryService.from_config(router.store, DiscoveryConfig(sources=[source]))
        result = await service.search(DiscoveryRequest(public_query='fixture', source_ids=['package']))
        assert result.candidates and result.source_records[0].status == 'complete'
        assert not router.registry.all()
    finally:
        await router.close()


async def test_https_setup_preserves_only_readiness_and_no_secret(monkeypatch):
    import aeep.provider_setup as setup
    router = Router(Manifest(database=':memory:'))
    service = ProviderSetupService(router.store)
    definition = ProviderSetupDefinition(setup_id='metered', adapter='https-readiness',
        endpoint='https://provider.example/credits', secret_env='AEEP_FIXTURE_PROVIDER_TOKEN',
        billing_credit_pointer='/credits', required_checks=['connectivity', 'authentication', 'billing'], non_charging=True)
    service.repository.review(service.define(definition))
    monkeypatch.setenv('AEEP_FIXTURE_PROVIDER_TOKEN', 'secret-sentinel-never-persist')
    async def validate(*args, **kwargs):
        return None
    monkeypatch.setattr(setup, 'validate_http_url', validate)
    status = [200]
    original = httpx.AsyncClient
    def response(request):
        assert request.headers['authorization'] == 'Bearer secret-sentinel-never-persist'
        return httpx.Response(status[0], json={'credits': 4, 'account': 'private-account-sentinel'})
    monkeypatch.setattr(setup.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(response), **kwargs))
    try:
        result = await service.check('metered')
        assert result.checks['billing'] == 'ready' and service.ready('metered')
        dump = '\n'.join(router.store._connection.iterdump())
        assert 'secret-sentinel-never-persist' not in dump and 'private-account-sentinel' not in dump
        with monkeypatch.context() as context:
            context.setattr(setup, 'implementation_digest', lambda: 'sha256:' + 'f' * 64)
            assert not service.ready('metered')
            with pytest.raises(ConfigurationError, match='changed'):
                await service.check('metered')
        monkeypatch.delenv('AEEP_FIXTURE_PROVIDER_TOKEN')
        missing = await service.check('metered')
        assert missing.checks['authentication'] == 'blocked'
        monkeypatch.setenv('AEEP_FIXTURE_PROVIDER_TOKEN', 'secret-sentinel-never-persist')
        status[0] = 401
        result = await service.check('metered')
        assert result.checks['authentication'] == 'blocked' and not service.ready('metered')
    finally:
        await router.close()


async def test_setup_cancel_and_invalid_host_observations_are_not_ready():
    router = Router(Manifest(database=':memory:'))
    async def cancel(definition):
        raise asyncio.CancelledError
    service = ProviderSetupService(router.store, host_adapter=HostManagedSetupAdapter(cancel, revision='sha256:' + 'a' * 64))
    definition = ProviderSetupDefinition(setup_id='host', adapter='host-managed', non_charging=True)
    service.repository.review(service.define(definition))
    try:
        with pytest.raises(asyncio.CancelledError):
            await service.check('host')
        assert not service.ready('host')
        rows = router.store._connection.execute("SELECT payload_json FROM assessment_records WHERE kind='provider_setup_observation'").fetchall()
        assert json.loads(rows[0][0])['status'] == 'cancelled'
        async def invalid(definition):
            return {'connectivity': 'sensitive-sentinel'}
        service.adapters['host-managed'] = HostManagedSetupAdapter(invalid, revision='sha256:' + 'a' * 64)
        observed = await service.check('host')
        assert observed.status == 'failed' and not service.ready('host')
        assert 'sensitive-sentinel' not in '\n'.join(router.store._connection.iterdump())
    finally:
        await router.close()


async def test_actual_pinned_local_runtime_and_wrong_digest():
    router = Router(Manifest(database=':memory:'))
    executable = await asyncio.to_thread(Path(sys.executable).resolve)
    service = ProviderSetupService(router.store)
    definition = ProviderSetupDefinition(setup_id='python', adapter='local-runtime', executable=str(executable),
        executable_digest='sha256:' + hashlib.sha256(executable.read_bytes()).hexdigest(),
        version_args=['--version'], non_charging=True, required_checks=['runtime'])
    service.repository.review(service.define(definition))
    try:
        result = await service.check('python')
        assert result.checks['runtime'] == 'ready' and service.ready('python')
        changed = definition.model_copy(update={'setup_id': 'changed', 'executable_digest': 'sha256:' + 'a' * 64})
        service.repository.review(service.define(changed))
        result = await service.check('changed')
        assert result.checks['runtime'] == 'blocked'
    finally:
        await router.close()
