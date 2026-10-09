"""Synthetic installer metadata; no package is installed or qualified here."""

import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from aeep_toolkit.cli import main, read_json
from aeep_toolkit.installation import (
    InstalledObservation,
    PreviewPolicy,
    manifest_digest,
    preview,
    require_compatible,
)
from aeep_toolkit.models import ExtensionManifest, ExtensionRegistry

D = 'a' * 64


def manifest(identity='engine', **changes):
    return ExtensionManifest.model_validate(dict(
        extension_id=identity, purpose='Synthetic offline fixture', role='evaluator',
        source={'repository': 'https://example.org/fixture', 'revision': 'b' * 40,
                'artifact_sha256': D, 'license_expression': 'MIT', 'data_rights': 'fixture-only'},
        hosts=['codex'], platforms=['darwin-arm64'], dependencies=[],
        permissions={'network_destinations': [], 'filesystem_scope': 'none',
                     'authentication': 'none', 'financial_exposure': 'none'},
        disk_bytes=10, memory_bytes=20, install_effects=['Fixture only; no executable installer'],
        rollback='No change has been applied', status='experimental',
    ) | changes)


def policy(*manifests, **changes):
    return PreviewPolicy.model_validate(dict(
        host='codex', platform='darwin-arm64', allowed_licenses=['MIT'],
        allowed_data_rights=['fixture-only'], free_disk_bytes=100 * 1024**3,
        reviewed_dependency_manifests=[manifest_digest(item) for item in manifests],
    ) | changes)


def test_complete_preview_matches_golden_and_preserves_unknown_installed_state():
    child = manifest('helper', role='support')
    parent = manifest(dependencies=[{'extension_id': 'helper', 'manifest_sha256': manifest_digest(child)}])
    result = preview(ExtensionRegistry(extensions=(parent, child)), ('engine',), policy(parent, child))
    assert json.loads(result.model_dump_json()) == json.loads(Path('tests/fixtures/toolkit/preview.json').read_text())
    require_compatible(result)
    assert result.items[0].selection == 'dependency'
    assert result.items[0].observation.installed is None
    assert result.execution_authorized is False


@pytest.mark.parametrize(('changes', 'message'), [
    ({'platform': 'linux-amd64'}, 'unsupported host or platform'),
    ({'host': 'unsupported'}, 'unsupported host or platform'),
    ({'allowed_licenses': []}, 'license not accepted'),
    ({'allowed_data_rights': []}, 'data rights not accepted'),
    ({'reviewed_dependency_manifests': []}, 'inventory has not been reviewed'),
    ({'free_disk_bytes': None}, 'free disk space unknown'),
    ({'free_disk_bytes': 50 * 1024**3}, '50 GiB'),
])
def test_policy_blocks_before_any_installer_effect(changes, message, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('preview attempted an effect')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(Path, 'write_text', forbidden)
    item = manifest()
    result = preview(ExtensionRegistry(extensions=(item,)), ('engine',), policy(item, **changes))
    with pytest.raises(ValueError, match=message):
        require_compatible(result)


@pytest.mark.parametrize('permission', [
    {'network_destinations': ['https://example.org']},
    {'filesystem_scope': 'user'}, {'authentication': 'operator_setup'},
    {'financial_exposure': 'metered'}, {'financial_exposure': 'unknown'},
])
def test_permission_expansion_blocked(permission):
    item = manifest(permissions=manifest().permissions.model_dump() | permission)
    result = preview(ExtensionRegistry(extensions=(item,)), ('engine',), policy(item))
    assert result.status == 'blocked'
    assert any('preview policy' in text for text in result.blockers)


def test_profiles_do_not_implicitly_select_or_enable_extensions():
    item = manifest(role='router')
    registry = ExtensionRegistry(extensions=(item,))
    assert preview(registry, (), policy(item), profile='full').items == ()
    assert preview(registry, ('engine',), policy(item)).status == 'blocked'
    observation = InstalledObservation(extension_id='engine', installed=True, enabled=False,
                                       manifest_sha256=manifest_digest(item), source_ref=D)
    result = preview(registry, ('engine',), policy(item), profile='full', observations=(observation,))
    assert any('disabled' in text for text in result.blockers)
    assert result.items[0].observation.enabled is False
    changed = observation.model_copy(update={'manifest_sha256': 'c' * 64, 'enabled': True})
    assert any('installed manifest differs' in text for text in preview(
        registry, ('engine',), policy(item), profile='full', observations=(changed,)).blockers)


def test_missing_dependencies_mismatched_digests_and_cycle_are_blocked():
    item = manifest(dependencies=[{'extension_id': 'missing', 'manifest_sha256': D}])
    missing = preview(ExtensionRegistry(extensions=(item,)), ('engine',), policy(item))
    assert not missing.disk_complete
    assert any('manifest unavailable' in text for text in missing.blockers)
    child = manifest('missing', dependencies=[{'extension_id': 'engine', 'manifest_sha256': D}])
    result = preview(ExtensionRegistry(extensions=(item, child)), ('engine',), policy(item, child))
    assert any('cycle' in text for text in result.blockers)
    assert any('manifest mismatch' in text for text in result.blockers)


def test_unknown_resources_and_blocked_metadata_stay_blocked():
    item = manifest(disk_bytes=None, memory_bytes=None, status='blocked', blockers=['No artifact review'])
    result = preview(ExtensionRegistry(extensions=(item,)), ('engine',), policy(item))
    assert not result.disk_complete
    assert result.known_disk_bytes == 0
    assert len(result.blockers) == 3


def test_ambiguous_or_unbacked_inventory_rejected():
    item = manifest()
    registry = ExtensionRegistry(extensions=(item,))
    with pytest.raises(ValueError, match='duplicate selected'):
        preview(registry, ('engine', 'engine'), policy(item))
    observation = InstalledObservation(extension_id='engine')
    with pytest.raises(ValueError, match='duplicate installation'):
        preview(registry, ('engine',), policy(item), observations=(observation, observation))
    for change in [{'installed': True}, {'installed': False}, {'enabled': True},
                   {'installed': True, 'source_ref': D}]:
        with pytest.raises(ValidationError):
            InstalledObservation(extension_id='engine', **change)


def test_cli_dry_run_preserves_tree_and_does_not_echo_bad_secret(tmp_path, capsys, monkeypatch):
    item = manifest()
    (tmp_path/'registry.json').write_text(ExtensionRegistry(extensions=(item,)).model_dump_json())
    (tmp_path/'policy.json').write_text(policy(item).model_dump_json())
    (tmp_path/'host-config.json').write_text('{"secret":"canary-must-not-appear"}')
    monkeypatch.setenv('AEEP_CONFIG_HOME', str(tmp_path/'uncreated-config'))
    def snapshot():
        return {str(p.relative_to(tmp_path)): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else 'directory'
                for p in tmp_path.rglob('*')}
    before = snapshot()
    assert main(['plan', '--registry', str(tmp_path/'registry.json'), '--policy', str(tmp_path/'policy.json'), '--select', 'engine']) == 0
    output = capsys.readouterr().out
    assert 'canary-must-not-appear' not in output
    assert snapshot() == before
    assert not (tmp_path/'uncreated-config').exists()
    with pytest.raises(SystemExit) as exc:
        main(['plan', '--policy', str(tmp_path/'host-config.json')])
    assert exc.value.code == 2
    assert 'canary-must-not-appear' not in capsys.readouterr().err
    assert snapshot() == before


def test_cli_full_catalog_is_inert_and_lists_pinned_sources(capsys):
    assert main(['list', 'full']) == 0
    output = json.loads(capsys.readouterr().out)
    assert len(output['catalog']) == 20
    assert output['selected'] == []
    entries = {item['id']: item for item in output['catalog']}
    assert entries['agent-skill-eval']['status'] == 'experimental'
    assert entries['agent-skill-eval']['qualification'] == 'scripted_engineering_only'
    assert entries['aeep-evaluator']['qualification'] == 'software_tests_only'
    assert all(item['status'] == 'blocked' for item in output['catalog'] if item['id'] not in {'agent-skill-eval', 'aeep-evaluator'})
    assert all(len(item['source_revision']) == 40 for item in output['catalog'])


def test_real_cli_import_excludes_legacy():
    result = subprocess.run([sys.executable, '-B', '-c',
        "import sys; from aeep_toolkit.cli import main, read_json; main(['list']); assert 'aeep' not in sys.modules"],
        capture_output=True, text=True, check=False,
        env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')})
    assert result.returncode == 0, result.stderr


def test_metadata_reader_excludes_authentication_and_symlinks_before_open(tmp_path, monkeypatch):
    private = tmp_path / 'private-codex'
    private.mkdir()
    secret = private / 'anything.json'
    secret.write_text('{"canary": "synthetic"}')
    named = tmp_path / 'auth.json'
    named.write_text('{}')
    link = tmp_path / 'metadata.json'
    link.symlink_to(secret)
    monkeypatch.setenv('CODEX_HOME', str(private))
    def forbidden(*args, **kwargs):
        pytest.fail('protected file opened')
    monkeypatch.setattr(os, 'open', forbidden)
    for path in (secret, named, link):
        with pytest.raises(ValueError):
            read_json(path)


def test_dependency_order_is_stable_across_hash_seeds():
    program = """from aeep_toolkit.models import ExtensionRegistry
from aeep_toolkit.installation import preview,manifest_digest
from test_toolkit_installation import manifest,policy
children=[manifest(name,role='support') for name in ('left','right','middle')]
parent=manifest(dependencies=[{'extension_id':x.extension_id,'manifest_sha256':manifest_digest(x)} for x in children])
items=[parent,*children]
print(preview(ExtensionRegistry(extensions=tuple(items)),('engine',),policy(*items)).model_dump_json())
"""
    root = Path(__file__).resolve().parents[1]
    results = []
    for seed in ('1', '2', '3'):
        result = subprocess.run([sys.executable, '-B', '-c', program],
            capture_output=True, text=True, check=True,
            env={**os.environ, 'PYTHONPATH': os.pathsep.join([str(root/'src'), str(root/'tests')]), 'PYTHONHASHSEED': seed})
        results.append(result.stdout)
    assert len(set(results)) == 1


def test_credential_case_aliases_are_rejected_before_open(tmp_path, monkeypatch):
    protected = tmp_path / 'CustomHome'
    protected.mkdir()
    (protected/'metadata.json').write_text('{}')
    upper = tmp_path/'AUTH.JSON'
    upper.write_text('{}')
    monkeypatch.setenv('CODEX_HOME', str(protected))
    def forbidden(*args, **kwargs):
        pytest.fail('reserved metadata alias opened')
    monkeypatch.setattr(os, 'open', forbidden)
    with pytest.raises(ValueError):
        read_json(upper)
    alias = tmp_path/'customhome'/'metadata.json'
    if alias.exists():
        with pytest.raises(ValueError):
            read_json(alias)


def test_essentials_can_disclose_required_isolation_dependency():
    worker = manifest('worker', role='isolation')
    engine = manifest(dependencies=[{'extension_id': 'worker', 'manifest_sha256': manifest_digest(worker)}])
    result = preview(ExtensionRegistry(extensions=(worker, engine)), ('engine',), policy(worker, engine))
    assert result.status == 'ready_for_review'
    assert [item.manifest.extension_id for item in result.items] == ['worker', 'engine']
    assert not result.execution_authorized


def test_metadata_reader_rejects_hardlinked_input(tmp_path):
    source = tmp_path / 'input.json'
    source.write_text('{"synthetic":true}')
    os.link(source, tmp_path / 'alias.json')
    with pytest.raises(ValueError, match='hard links'):
        read_json(source)


def test_unknown_memory_needs_explicit_policy_and_remains_unknown():
    item = manifest(memory_bytes=None)
    registry = ExtensionRegistry(extensions=(item,))
    ordinary = policy(item)
    assert 'allow_unknown_memory' not in ordinary.model_dump(mode='json')
    rejected = preview(registry, ('engine',), ordinary)
    assert any('memory requirement unknown' in reason for reason in rejected.blockers)
    accepted = preview(registry, ('engine',), ordinary.model_copy(update={'allow_unknown_memory': True}))
    assert not accepted.blockers and accepted.items[0].manifest.memory_bytes is None
    assert any('accepts unknown memory' in reason for reason in accepted.limitations)
    assert not accepted.execution_authorized
    assert ordinary.model_copy(update={'allow_unknown_memory': True}).model_dump()['allow_unknown_memory'] is True


def test_unknown_memory_acknowledgement_does_not_relax_disk_or_permissions():
    item = manifest(memory_bytes=None, disk_bytes=None)
    result = preview(ExtensionRegistry(extensions=(item,)), ('engine',), policy(item, allow_unknown_memory=True))
    assert any('disk requirement unknown' in reason for reason in result.blockers)


@pytest.mark.parametrize('value', ['true', 1, None])
def test_unknown_memory_acknowledgement_requires_an_actual_boolean(value):
    item = manifest()
    with pytest.raises(ValueError):
        policy(item, allow_unknown_memory=value)
