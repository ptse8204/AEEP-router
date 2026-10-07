from __future__ import annotations

import asyncio
import json
import sys

import pytest
from typer.testing import CliRunner

from aeep.access import adopt_filter, change_access
from aeep.catalogs import defaults, read_catalogs, save_source, search_catalogs
from aeep.cli import app
from aeep.connections import connection_path
from aeep.discovery import RegistryQuery
from aeep.discovery_service import DiscoveryConfig, DiscoverySourceConfig
from aeep.errors import ConfigurationError
from aeep.marketplaces import MarketplaceAdapter
from aeep.mcp.server import AEEPToolService
from aeep.onboarding import connect, disconnect, initialize
from aeep.recommendations import RecommendationRequest, recommend
from aeep.router import Router

pytestmark = pytest.mark.skipif(sys.platform == 'win32', reason='onboarding targets macOS and Linux/WSL')

@pytest.fixture(autouse=True)
def offline_setup_probe(monkeypatch):
    monkeypatch.setattr('aeep.onboarding.probe_catalogs', lambda: {'catalog_checks': [], 'scope': 'mocked catalog check'})


def prepare(tmp_path, monkeypatch):
    monkeypatch.setenv('AEEP_CONFIG_HOME', str(tmp_path / 'config'))
    project = tmp_path / 'project'
    project.mkdir()
    initialize()
    return project


def test_setup_rerun_preserves_edits_and_disconnect_revokes(tmp_path, monkeypatch):
    project = prepare(tmp_path, monkeypatch)
    config = project / '.codex/config.toml'
    config.parent.mkdir()
    config.write_text('model = "existing-model"\n')
    first = connect('writer', 'codex', project)
    assert connect('writer', 'codex', project).host_applied == first.host_applied
    assert config.read_text().count('[mcp_servers.aeep_writer]') == 1
    config.write_text(config.read_text() + '\n# user note\n')
    disconnect('writer')
    assert 'existing-model' in config.read_text() and '# user note' in config.read_text()
    assert not json.loads(connection_path('writer').read_text())['enabled']
    connect('writer', 'codex', project)
    config.write_text(config.read_text().replace('"serve"', '"changed"'))
    with pytest.raises(ConfigurationError, match='revoked'):
        disconnect('writer')
    assert 'changed' in config.read_text()


def test_claude_adoption_restores_only_owned_rule(tmp_path, monkeypatch):
    project = prepare(tmp_path, monkeypatch)
    (project / '.mcp.json').write_text(json.dumps({'mcpServers': {'existing': {'url': 'https://example.org/mcp'}}}))
    connect('claude', 'claude', project)
    adopt_filter('claude', 'existing', 'write', deny=True)
    settings = project / '.claude/settings.json'
    data = json.loads(settings.read_text())
    data['permissions']['deny'].append('Bash(rm:*)')
    settings.write_text(json.dumps(data))
    adopt_filter('claude', 'existing', 'write', deny=False)
    assert json.loads(settings.read_text())['permissions']['deny'] == ['Bash(rm:*)']
    disconnect('claude')
    assert 'existing' in json.loads((project / '.mcp.json').read_text())['mcpServers']


def test_call_and_routing_denials_follow_changes_and_fingerprints(tmp_path, monkeypatch):
    project = prepare(tmp_path, monkeypatch)
    c = connect('reader', 'deepseek-api', project)
    router = Router.from_manifest(c.manifest)
    service = AEEPToolService(router, connection=connection_path('reader'))
    try:
        assert 'aeep_execute_action' not in {t['name'] for t in service.list_tools()}
        assert asyncio.run(service.call('aeep_execute_action', {'capability': 'text.stats', 'input': {'text': 'hi'}}))['isError']
        change_access('reader', 'builtin.text-stats', True)
        result = asyncio.run(service.call('aeep_execute_action', {'capability': 'text.stats', 'input': {'text': 'hi'}}))
        assert not result.get('isError'), result
        change_access('reader', 'aeep_execute_action', False)
        assert router.route({'capability': 'text.stats', 'input': {'text': 'hi'}}).selected_executor_id is None
        change_access('reader', 'builtin.text-stats', False)
        decision = router.route({'capability': 'text.stats', 'input': {'text': 'hi'}})
        assert decision.selected_executor_id is None
        change_access('reader', 'aeep_stack_propose', False)
        assert 'aeep_stack_propose' not in {t['name'] for t in service.list_tools()}
        assert asyncio.run(service.call('aeep_stack_propose', {}))['isError']
        disconnect('reader')
        assert asyncio.run(service.call('aeep_list_capabilities', {}))['isError']
    finally:
        asyncio.run(router.close())


def test_marketplace_sources_search_descriptions_and_reject_unsafe_entries(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch)
    path = tmp_path / 'catalog/.claude-plugin/marketplace.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'name': 'media', 'plugins': [
        {'name': 'voice-one', 'source': './voice', 'description': 'narration audio'},
        {'name': 'escape', 'source': '../outside', 'description': 'narration'},
    ]}))
    adapter = MarketplaceAdapter(str(path.parent.parent), local=True)
    found = asyncio.run(adapter.search(RegistryQuery(query='narration')))
    assert [item.name for item in found] == ['voice-one']
    assert found[0].provenance['supported_hosts'] == ['claude']
    assert adapter.warnings
    source = DiscoverySourceConfig(source_id='local', kind='marketplace', path=str(path))
    save_source(source)
    assert len(read_catalogs().sources) == 3
    assert len(defaults().sources) == 2


def test_video_recommendation_names_candidates_without_admission(tmp_path, monkeypatch):
    project = prepare(tmp_path, monkeypatch)
    c = connect('video', 'deepseek-api', project)
    path = tmp_path / 'marketplace.json'
    names = ['inspect', 'storyboard', 'capture', 'narration', 'edit', 'captions', 'review']
    path.write_text(json.dumps({'name': 'video', 'plugins': [{'name': name, 'source': './' + name,
        'description': name + ' video'} for name in names]}))
    config = DiscoveryConfig(sources=[DiscoverySourceConfig(source_id='video', kind='marketplace', path=str(path))])
    router = Router.from_manifest(c.manifest)
    try:
        request = RecommendationRequest(host='claude', stages=[{'stage_id': name, 'purpose': name + ' educational video',
                                                               'search_terms': ['video', name]} for name in names])
        result = asyncio.run(recommend(router, request, config=config))
        assert all(stage.preferred for stage in result.stages)
        assert result.status == 'setup_required'
        assert all(option.quality.startswith('unknown') for stage in result.stages for option in stage.options)
        assert len(router.registry.all()) == 3
        record = router.store._connection.execute("SELECT payload_json FROM assessment_records WHERE kind='stack_recommendation'").fetchone()
        assert record and 'setup_required' in record[0]
        path.unlink()
        cached = asyncio.run(search_catalogs(router.store, ['video', 'inspect', 'storyboard', 'capture', 'narration', 'edit'], config=config))
        assert cached.stale and cached.candidates
    finally:
        asyncio.run(router.close())


def test_cli_setup_and_filtered_export(tmp_path, monkeypatch):
    monkeypatch.setenv('AEEP_CONFIG_HOME', str(tmp_path / 'config'))
    runner = CliRunner()
    result = runner.invoke(app, ['setup', '--agent', 'deepseek-api', '--project', str(tmp_path), '--yes'])
    assert result.exit_code == 0, result.output
    exported = runner.invoke(app, ['tools', 'export', 'deepseek', '--connection', str(connection_path('deepseek-api'))])
    assert exported.exit_code == 0, exported.output
    names = [t['function']['name'] for t in json.loads(exported.output)['tools']]
    assert 'aeep_stack_recommend' in names and 'aeep_execute_action' not in names
    assert runner.invoke(app, ['doctor', '--setup', '--json']).exit_code == 0


def test_codex_native_filter_preserves_unrelated_and_rejects_symlink(tmp_path, monkeypatch):
    project = prepare(tmp_path, monkeypatch)
    p = project / '.codex/config.toml'
    p.parent.mkdir()
    p.write_text('[mcp_servers.existing]\ncommand="demo"\ndisabled_tools=["old"]\n\n[other]\nx=1\n')
    connect('codex', 'codex', project)
    adopt_filter('codex', 'existing', 'write', deny=True)
    assert '"old", "write"' in p.read_text()
    adopt_filter('codex', 'existing', 'write', deny=False)
    assert '[other]\nx=1' in p.read_text()
    external = tmp_path / 'external'
    external.write_text('{}')
    connection_path('codex').unlink()
    connection_path('codex').symlink_to(external)
    with pytest.raises(ConfigurationError):
        change_access('codex', 'aeep_execute_action', True)


@pytest.mark.parametrize('restore_order', [('first', 'second'), ('second', 'first')])
def test_codex_adoption_restore_allows_owned_connection_disconnect(tmp_path, monkeypatch, restore_order):
    project = prepare(tmp_path, monkeypatch)
    connect('codex', 'codex', project)
    config = project / '.codex/config.toml'
    original = config.read_bytes()
    for tool in ('first', 'second'):
        adopt_filter('codex', 'aeep_codex', tool, deny=True)
    for tool in restore_order:
        adopt_filter('codex', 'aeep_codex', tool, deny=False)
    assert config.read_bytes() == original
    disconnect('codex')
    assert config.read_bytes() == b''


@pytest.mark.parametrize('operator_edit', ['disabled_tools = [] # operator edit\n', ''])
def test_codex_adoption_restore_preserves_operator_removed_rule(tmp_path, monkeypatch, operator_edit):
    project = prepare(tmp_path, monkeypatch)
    config = project / '.codex/config.toml'
    config.parent.mkdir()
    config.write_text('[mcp_servers.existing]\ncommand="demo"\n')
    connect('codex', 'codex', project)
    adopt_filter('codex', 'existing', 'write', deny=True)
    config.write_text(config.read_text().replace('disabled_tools = ["write"]\n', operator_edit))
    edited = config.read_bytes()
    adopt_filter('codex', 'existing', 'write', deny=False)
    assert config.read_bytes() == edited


def test_disconnect_is_repeatable_and_identical_user_skill_survives(tmp_path, monkeypatch):
    from aeep.onboarding import INSTRUCTIONS
    project = prepare(tmp_path, monkeypatch)
    skill = project / '.agents/skills/aeep-planning/SKILL.md'
    skill.parent.mkdir(parents=True)
    skill.write_text(INSTRUCTIONS)
    connect('codex', 'codex', project)
    disconnect('codex')
    disconnect('codex')
    assert skill.read_text() == INSTRUCTIONS


def test_api_dispatch_and_dsh_patch_bind_current_connection(tmp_path, monkeypatch):
    from aeep.integrations.connected_tools import ConnectedTools
    project = prepare(tmp_path, monkeypatch)
    connect('api', 'deepseek-api', project)
    bridge = ConnectedTools(connection_path('api'))
    try:
        assert any(t['function']['name'] == 'aeep_stack_recommend' for t in bridge.declarations())
        change_access('api', 'aeep_stack_recommend', False)
        assert asyncio.run(bridge.call('aeep_stack_recommend', {}))['isError']
        assert not any(t['function']['name'] == 'aeep_stack_recommend' for t in bridge.declarations())
    finally:
        asyncio.run(bridge.close())
    c = connect('harness', 'dsh', project)
    patches = json.loads(__import__('pathlib').Path(c.host_configuration).read_text())
    args = patches[0]['insert'][0]['config']['args']
    assert args[args.index('--connection') + 1] == str(connection_path('harness'))
    assert len(json.loads(__import__('pathlib').Path(connect('harness', 'dsh', project).host_configuration).read_text())) == 1
    disconnect('harness')
    disconnect('harness')


def test_component_exact_review_interruption_and_argv_install(tmp_path, monkeypatch):
    from aeep.assessment.repository import AssessmentRepository
    from aeep.component_setup import ComponentSetup, apply, define
    from aeep.discovery import RegistryCandidate
    from aeep.models import utc_now
    project = prepare(tmp_path, monkeypatch)
    c = connect('claude', 'claude', project)
    router = Router.from_manifest(c.manifest)
    candidate = RegistryCandidate(registry_candidate_id='fixture', adapter_id='fixture', name='fixture',
        raw_metadata_digest='sha256:' + 'a' * 64, retrieved_at=utc_now())
    router.store.save_registry_candidate(candidate)
    plan = ComponentSetup(connection_id='claude', candidate_id='fixture', candidate_digest=candidate.raw_metadata_digest,
                          kind='npm', package='fixture', version='1.2.3', executable='fixture')
    result = define(router, plan)
    import aeep.component_setup as module
    calls = []
    def execute(argv, cwd):
        calls.append(argv)
        target = cwd / 'node_modules/.bin/fixture'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('fixture')
    monkeypatch.setattr(module, '_run', execute)
    monkeypatch.setattr(module, 'require_space', lambda *args: None)
    monkeypatch.setattr(module.shutil, 'which', lambda name: '/usr/bin/' + name)
    try:
        with pytest.raises(ConfigurationError, match='exact operator review'):
            apply(router, result['digest'])
        AssessmentRepository(router.store).review(result['digest'])
        assert apply(router, result['digest'])['status'] == 'installed'
        assert '--ignore-scripts' in calls[0] and calls[0][-1] == 'fixture@1.2.3'
        assert apply(router, result['digest'])['status'] == 'installed'
        assert len(calls) == 1
        entries = json.loads((project / '.mcp.json').read_text())['mcpServers']
        assert next(v for k, v in entries.items() if k.startswith('aeep_component'))['type'] == 'stdio'
        assert not json.loads(connection_path('claude').read_text())['executor_fingerprints']
        journal = tmp_path / 'config/installations' / (result['digest'] + '.json')
        journal.write_text(json.dumps({'status': 'installing'}))
        with pytest.raises(ConfigurationError, match='interrupted'):
            apply(router, result['digest'])
    finally:
        asyncio.run(router.close())


def test_setup_json_is_single_document_and_marketplace_symlink_denied(tmp_path, monkeypatch):
    monkeypatch.setenv('AEEP_CONFIG_HOME', str(tmp_path / 'config'))
    output = CliRunner().invoke(app, ['setup', '--agent', 'deepseek-api', '--project', str(tmp_path), '--yes', '--json'])
    assert output.exit_code == 0, output.output
    assert json.loads(output.stdout)['connections'][0]['service'] == 'ready'
    outside = tmp_path / 'outside.json'
    outside.write_text('{"plugins":[]}')
    root = tmp_path / 'catalog/.agents/plugins'
    root.mkdir(parents=True)
    (root / 'marketplace.json').symlink_to(outside)
    with pytest.raises(ConfigurationError, match='escapes'):
        asyncio.run(MarketplaceAdapter(str(root.parent.parent), local=True).search(RegistryQuery(query='video')))


def test_upgrade_updates_owned_runtime_without_overwriting_project_settings(tmp_path, monkeypatch):
    project = prepare(tmp_path, monkeypatch)
    connect('editor', 'codex', project)
    config = project / '.codex/config.toml'
    config.write_text(config.read_text() + '\n[unrelated]\nvalue = 42\n')
    monkeypatch.setattr('aeep.onboarding.sys.executable', '/owned/new-runtime/bin/python')
    connect('editor', 'codex', project)
    assert config.read_text().count('[mcp_servers.aeep_editor]') == 1
    assert '/owned/new-runtime/bin/python' in config.read_text()
    assert '[unrelated]\nvalue = 42' in config.read_text()


def test_missing_connection_cli_returns_machine_error(tmp_path, monkeypatch):
    monkeypatch.setenv('AEEP_CONFIG_HOME', str(tmp_path / 'config'))
    result = CliRunner().invoke(app, ['access', 'show', 'missing', '--json'])
    assert result.exit_code == 4
    assert json.loads(result.stdout)['error_type'] == 'ValidationError'


def test_native_catalog_rejects_command_sources_and_metadata_drift(tmp_path):
    from aeep.component_setup import ComponentSetup, inspect_native_catalog
    from aeep.discovery import _metadata_digest
    catalog = tmp_path / '.claude-plugin/marketplace.json'
    catalog.parent.mkdir()
    (tmp_path / 'plugin').mkdir()
    entry = {'name': 'safe', 'source': './plugin'}
    plan = ComponentSetup(connection_id='test', candidate_id='candidate', candidate_digest=_metadata_digest(entry),
                          kind='marketplace', package='https://github.com/owner/repo', version='a' * 40,
                          plugin='safe', marketplace='demo')
    catalog.write_text(json.dumps({'name': 'demo', 'plugins': [entry]}))
    inspect_native_catalog(tmp_path, plan)
    catalog.write_text(json.dumps({'name': 'demo', 'plugins': [entry, {'name': 'bad', 'source': {'source': 'command', 'command': 'arbitrary'}}]}))
    with pytest.raises(ConfigurationError, match='command-based'):
        inspect_native_catalog(tmp_path, plan)
    catalog.write_text(json.dumps({'name': 'demo', 'plugins': [{**entry, 'description': 'changed'}]}))
    with pytest.raises(ConfigurationError, match='differs'):
        inspect_native_catalog(tmp_path, plan)


def test_claude_supported_marketplace_inventory_is_importable(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from aeep.onboarding import known_marketplaces
    monkeypatch.setattr('aeep.onboarding.shutil.which', lambda name: '/usr/bin/' + name)
    monkeypatch.setattr('subprocess.run', lambda *a, **k: SimpleNamespace(stdout=json.dumps([
        {'name': 'team', 'source': 'github', 'repo': 'team/plugins'},
        {'name': 'hosted', 'source': 'claudeai', 'marketplaceId': 'private-id'}]).encode()))
    assert known_marketplaces('claude') == [{'name': 'team', 'location': 'team/plugins'}]
