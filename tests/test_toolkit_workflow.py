"""Workflow assembly fixtures. No live worker, capability value or release claim."""

import asyncio
import hashlib
import json
import sqlite3

import pytest
from test_toolkit_managed import prepared, record

from aeep.assessment.service import AssessmentService
from aeep.router import Router
from aeep_toolkit import managed
from aeep_toolkit.cli import main
from aeep_toolkit.workflow import EvaluationWorkflow, prepare

pytestmark = pytest.mark.assessment_contract


def workflow(tmp_path, monkeypatch):
    router, service, adapter, campaign_path, _ = prepared(tmp_path, monkeypatch)
    files = {}
    for name, model in [('plan', adapter.plan), ('source', adapter.source)]:
        path = tmp_path / (name + '.json')
        path.write_text(model.model_dump_json())
        files[name] = {'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    definition = tmp_path / 'workflow.json'
    definition.write_text(EvaluationWorkflow(configurations={'csv': files, 'second-choice': files}).model_dump_json())
    return router, service, adapter, campaign_path, definition


def test_selected_plan_is_inert_and_does_not_infer_any_acceptance_gate(tmp_path, monkeypatch, capsys):
    router, _, _, _, definition = workflow(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr(Router, 'from_manifest', lambda *a: pytest.fail('preview started Router'))
        monkeypatch.setattr(sqlite3, 'connect', lambda *a, **k: pytest.fail('preview opened SQLite'))
        assert main(['workflow', 'plan', '--workflow', str(definition), '--configuration', 'csv']) == 0
        result = json.loads(capsys.readouterr().out)
        assert result['configuration'] == 'csv'
        assert result['gates'] == {'stack_integration': 'NOT_VERIFIED_BY_PREVIEW',
            'candidate_usefulness': 'NOT_ASSESSED', 'selection_usefulness': 'NOT_ASSESSED'}
        other, *_ = prepare(definition, 'second-choice')
        assert result['review_sha256'] != other['review_sha256']
    finally:
        asyncio.run(router.close())


@pytest.mark.parametrize('change', ['bytes', 'traversal', 'credential', 'symlink', 'parent-link', 'unknown', 'backend'])
def test_changed_or_unsafe_inputs_fail_before_service_initialization(tmp_path, monkeypatch, change):
    router, _, _, _, definition = workflow(tmp_path, monkeypatch)
    try:
        data = json.loads(definition.read_text())
        source = tmp_path / 'source.json'
        if change == 'bytes':
            source.write_text(source.read_text() + '\n')
        elif change == 'traversal':
            data['configurations']['csv']['source']['path'] = '../source.json'
        elif change == 'credential':
            data['configurations']['csv']['source']['path'] = 'auth.json'
        elif change == 'symlink':
            link = tmp_path / 'linked.json'
            link.symlink_to(source)
            data['configurations']['csv']['source']['path'] = link.name
        elif change == 'parent-link':
            link = tmp_path / 'linked'
            link.symlink_to(tmp_path, target_is_directory=True)
            data['configurations']['csv']['source']['path'] = 'linked/source.json'
        elif change == 'backend':
            data['backend'] = 'arbitrary-process'
        definition.write_text(json.dumps(data))
        monkeypatch.setattr(managed, 'main', lambda *a: pytest.fail('unsafe input reached backend'))
        with pytest.raises(SystemExit) as exc:
            main(['workflow', 'plan', '--workflow', str(definition),
                  '--configuration', 'missing' if change == 'unknown' else 'csv'])
        assert exc.value.code == 2
    finally:
        asyncio.run(router.close())


def test_run_requires_selection_review_and_delegates_without_retry(tmp_path, monkeypatch):
    router, _, _, _, definition = workflow(tmp_path, monkeypatch)
    try:
        preview, *_ = prepare(definition, 'csv')
        calls = []
        def denied(argv):
            calls.append(argv)
            raise SystemExit(2)
        monkeypatch.setattr(managed, 'main', denied)
        common = ['workflow', 'run', '--workflow', str(definition), '--configuration', 'csv',
                  '--manifest', str(tmp_path / 'manifest.json'), '--output', str(tmp_path / 'out')]
        with pytest.raises(SystemExit):
            main([*common, '--reviewed-digest', '0' * 64])
        assert calls == []
        with pytest.raises(SystemExit):
            main([*common, '--reviewed-digest', preview['review_sha256']])
        assert len(calls) == 1
        assert calls[0][-1] == preview['backend_review']['review_sha256']
        assert not (tmp_path / 'out').exists()
    finally:
        asyncio.run(router.close())


def test_workflow_exports_existing_canonical_fixture_without_dispatch(tmp_path, monkeypatch, capsys):
    router, service, adapter, campaign_path, definition = workflow(tmp_path, monkeypatch)
    report = record(service, adapter, campaign_path)
    preview, *_ = prepare(definition, 'csv')
    monkeypatch.setattr(Router, 'from_manifest', lambda *a: router)
    monkeypatch.setattr(AssessmentService, 'enqueue', lambda *a: pytest.fail('report dispatched work'))
    monkeypatch.setattr(managed, 'require_conformance', lambda *a, **k: None)
    output = tmp_path / 'export'
    assert main(['workflow', 'report', '--workflow', str(definition), '--configuration', 'csv',
                 '--reviewed-digest', preview['review_sha256'], '--manifest', str(tmp_path / 'fixture.json'),
                 '--directory', str(service.directory), '--output', str(output),
                 '--report-id', report.report_id]) == 0
    assert json.loads(capsys.readouterr().out)['normalized_trials'] == 2
    assert (output / 'report.html').is_file() and (output / 'report.md').is_file()
    assert json.loads((output / 'managed-evidence.json').read_text())['canonical_trials'] == 3


def test_bind_outputs_pins_without_writing_or_dispatching(tmp_path, monkeypatch, capsys):
    router, _, _, _, _definition = workflow(tmp_path, monkeypatch)
    try:
        before = {p.name for p in tmp_path.iterdir()}
        main(['workflow', 'bind', '--plan', str(tmp_path / 'plan.json'),
              '--source', str(tmp_path / 'source.json'), '--configuration', 'named'])
        bound = EvaluationWorkflow.model_validate_json(capsys.readouterr().out)
        assert list(bound.configurations) == ['named']
        assert {p.name for p in tmp_path.iterdir()} == before
        assert bound.configurations['named'].plan.sha256 == hashlib.sha256((tmp_path / 'plan.json').read_bytes()).hexdigest()
    finally:
        asyncio.run(router.close())
