"""Fresh operator composition, independent file checks, and scoped lifecycle."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from aeep.assessment.repository import AssessmentRepository
from aeep.errors import ConfigurationError
from aeep.models import Manifest
from aeep.router import Router
from aeep.tasks import activate, change_state, inspect
from aeep.validators import ValidationContext

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'examples/native_website/task_service.py'
spec = importlib.util.spec_from_file_location('website_composition', MODULE)
assert spec is not None and spec.loader is not None
website = importlib.util.module_from_spec(spec)
spec.loader.exec_module(website)
CODEX = Path(os.environ.get('AEEP_NATIVE_CODEX', '/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'))


def definition(tmp_path):
    return website.prepare(tmp_path / 'website', CODEX, Path(sys.executable))


def invoke(record, activation, mode, *, messages=None, operation='build'):
    args = [sys.executable, str(MODULE), mode, '--manifest', record['manifest'], '--activation', activation]
    if mode == 'call':
        args.append(operation)
    environment = {**os.environ, 'PYTHONPATH': str(ROOT / 'src')}
    return subprocess.run(args, input=''.join(json.dumps(x) + '\n' for x in messages or []),
        text=True, capture_output=True, timeout=45, env=environment)


@pytest.mark.assessment_boundary
@pytest.mark.native_boundary
@pytest.mark.skipif(sys.platform != 'darwin' or not CODEX.is_file(), reason='pinned native macOS fixture required')
def test_fresh_cli_and_mcp_verify_files_and_preserve_lifecycle(tmp_path):
    record = definition(tmp_path)
    manifest = Path(record['manifest'])
    root = manifest.parent
    router = Router.from_manifest(manifest)
    repository = AssessmentRepository(router.store)
    repository.review(record['scope_digest'])
    repository.review(record['recipe_digest'])
    activation = activate(router, record['scope_id'])
    try:
        built = invoke(record, activation.activation_id, 'call')
        assert built.returncode == 0, built.stderr
        first = json.loads(built.stdout)['structuredContent']
        assert first['ok'] and first['receipts'][0]['task_valid'] is True
        assert any(c['kind'] == 'callback' and c['valid'] is True and c['trust'] == 'verified'
                   for c in first['receipts'][0]['checks'])
        (root / 'data/later-note.txt').write_text(website.LATER_NOTE)
        messages = [{'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                     'params': {'name': website.TOOL, 'arguments': {'operation': 'edit'}}},
                    {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                     'params': {'name': 'aeep_website_publish', 'arguments': {}}}]
        edited = invoke(record, activation.activation_id, 'mcp', messages=messages)
        assert edited.returncode == 0, edited.stderr
        replies = [json.loads(line) for line in edited.stdout.splitlines()]
        tool = replies[0]['result']['tools'][0]['name']
        assert tool == website.TOOL
        second = replies[1]['result']['structuredContent']
        assert second['ok'] and second['receipts'][0]['task_valid'] is True
        assert replies[2].get('error') or replies[2]['result']['isError']
        oracle = root / '.aeep/website-oracle.json'
        original_oracle = oracle.read_bytes()
        oracle.write_bytes(original_oracle + b' ')
        drifted = invoke(record, activation.activation_id, 'call', operation='edit')
        assert drifted.returncode != 0 and 'differs from reviewed' in drifted.stderr
        oracle.write_bytes(original_oracle)
        assert inspect(router, activation.activation_id)['attempts_used'] == 2
        assert router.store.get_receipt(first['receipts'][0]['receipt_id'])
        assert router.store.get_receipt(second['receipts'][0]['receipt_id'])
        change_state(router, activation.activation_id, 'pause')
        paused = invoke(record, activation.activation_id, 'call', operation='edit')
        assert paused.returncode != 0 or not json.loads(paused.stdout)['structuredContent']['ok']
        change_state(router, activation.activation_id, 'resume')
        assert inspect(router, activation.activation_id)['attempts_used'] == 2
        assert change_state(router, activation.activation_id, 'uninstall')['overlay'] == 'absent'
        assert (root / 'data/later-note.txt').read_text() == website.LATER_NOTE
        assert (root / 'data/note.txt').read_text() == website.NOTE
        assert (root / 'data/style.css').read_text() == website.STYLE
    finally:
        asyncio.run(router.close())


@pytest.mark.assessment_contract
@pytest.mark.skipif(not CODEX.is_file(), reason='fixture needs existing binary metadata only')
def test_pinned_oracle_and_module_drift_rejected_before_service(tmp_path):
    record = definition(tmp_path)
    manifest = Path(record['manifest'])
    oracle = manifest.parent / '.aeep/website-oracle.json'
    original = oracle.read_bytes()
    oracle.write_bytes(original + b' ')
    with pytest.raises(ConfigurationError, match='differs from reviewed'):
        website.compose(manifest, 'task_never_activated')
    oracle.write_bytes(original)
    model = Manifest.model_validate_json(manifest.read_bytes())
    model.executors[0].validators[0].config['module_sha256'] = '0' * 64
    manifest.write_text(model.model_dump_json())
    with pytest.raises(ConfigurationError, match='differs from reviewed'):
        website.compose(manifest, 'task_never_activated')


@pytest.mark.assessment_contract
@pytest.mark.skipif(not CODEX.is_file(), reason='fixture needs existing binary metadata only')
def test_independent_callback_rejects_success_shaped_output_without_files(tmp_path, monkeypatch):
    record = definition(tmp_path)
    manifest = Path(record['manifest'])
    # Observe the exact callback registered before activation; no child execution in this unit check.
    def captured(router, **kwargs):
        return router
    monkeypatch.setattr(website, 'AEEPToolService', captured)
    router = website.compose(manifest, 'task_fixture')
    try:
        verify = router.validator_callbacks[website.NAME]
        context = ValidationContext({'operation': 'build'}, {'operation': 'build', 'updated': 'index.html'})
        assert verify(context) is False
        (manifest.parent / 'data/index.html').write_text(website.HTML.replace('<h1>Draft</h1>', '<h1>Verified local website</h1>'))
        assert verify(context) is True
        (manifest.parent / 'data/style.css').write_text('corrupted')
        assert verify(context) is False
        (manifest.parent / 'data/style.css').unlink()
        (manifest.parent / 'data/style.css').symlink_to(manifest.parent / '.aeep/website-oracle.json')
        assert verify(context) is False
    finally:
        asyncio.run(router.close())
