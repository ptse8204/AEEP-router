"""Synthetic pinned-interface fixtures are not executable upstream conformance."""
import hashlib
import json
import socket
import subprocess
from copy import deepcopy

import pytest

from aeep_toolkit.cli import main
from aeep_toolkit.external import PINS, import_result, render_import


def waza():
    return {'schemaVersion': '1.4', 'eval_id': 'private-evaluation', 'tasks': [
        {'test_id': 'private-task', 'status': 'passed', 'runs': [
            {'run_number': 1, 'attempts': 1, 'status': 'passed', 'duration_ms': 1250,
             'prompt': 'PRIVATE_PROMPT', 'final_output': '<script>PRIVATE_OUTPUT</script>',
             'session_digest': {'usage': {'input_tokens': 900}}, 'usage': {'input_tokens': 12, 'cache_read_tokens': 3}}
        ]}]}


def scanner():
    return {'skill_name': 'private-name', 'skill_path': '/private/candidate', 'is_safe': True,
            'findings_count': 1, 'findings': [{'id': 'private-id', 'severity': 'HIGH', 'snippet': 'PRIVATE_CODE'}],
            'suppressed_findings': [{'id': 'suppressed', 'severity': 'CRITICAL'}],
            'analyzers_used': ['static'], 'analyzers_failed': [{'error': 'PRIVATE_KEY'}]}


def imported(data, backend='waza'):
    return import_result(json.dumps(data).encode(), backend, revision=PINS[backend], candidate_sha256='a'*64)


def test_waza_preserves_missingness_and_does_not_sum_duplicate_session_usage():
    data = waza()
    data['baseline_outcome'] = {**deepcopy(data), 'is_baseline': True}
    result = imported(data)
    observed = result['observations']
    run = observed['runs'][0]
    assert run['reported_duration_seconds'] == 1.25
    assert run['reported_usage']['input_tokens'] == 12
    assert run['reported_usage']['output_tokens'] is None
    assert run['candidate_exposed'] is None
    assert run['verified_outcome'] == 'unknown'
    assert observed['baseline']['role_claim'] == 'baseline'
    assert observed['token_total'] is None and observed['actual_cash'] is None
    assert result['outcome'] == 'NOT_ASSESSED'
    assert result['artifact_sha256'] == hashlib.sha256(json.dumps(data).encode()).hexdigest()
    for format in ('json', 'markdown', 'html'):
        rendered = render_import(result, format)
        assert 'PRIVATE_' not in rendered and 'private-task' not in rendered
        assert '<script>' not in rendered


@pytest.mark.parametrize('mutation', ['version', 'negative', 'boolean', 'duplicate', 'nested', 'nan'])
def test_waza_rejects_ambiguous_or_invalid_observations(mutation):
    data = waza()
    run = data['tasks'][0]['runs'][0]
    if mutation == 'version':
        data['schemaVersion'] = '2.0'
    elif mutation == 'negative':
        run['duration_ms'] = -1
    elif mutation == 'boolean':
        run['usage']['input_tokens'] = True
    elif mutation == 'duplicate':
        data['tasks'].append(deepcopy(data['tasks'][0]))
    elif mutation == 'nested':
        data['baseline_outcome'] = {**deepcopy(data), 'is_baseline': True, 'baseline_outcome': {}}
    else:
        run['ignored'] = float('nan')
    with pytest.raises(ValueError):
        imported(data)


def test_error_and_cached_records_cannot_become_independent_successes():
    data = waza()
    data['tasks'][0]['cached'] = True
    data['tasks'][0]['runs'][0] = {'run_number': 1, 'status': 'error'}
    result = imported(data)['observations']['runs'][0]
    assert result['cached'] is True
    assert result['reported_status'] == 'error'
    assert result['verified_outcome'] == 'unknown'
    assert result['attempts'] is None and result['reported_usage'] is None
    assert result['reported_duration_seconds'] is None


def test_scanner_does_not_promote_safe_flag_or_ignore_incomplete_coverage():
    result = imported(scanner(), 'cisco-skill-scanner')
    assert result['observations']['safety_verdict'] == 'NOT_ESTABLISHED'
    assert result['observations']['coverage'] == 'incomplete'
    assert result['observations']['findings_by_severity'] == {'HIGH': 1}
    assert result['observations']['suppressed_by_severity'] == {'CRITICAL': 1}
    assert result['observations']['reported_duration_seconds'] is None
    assert 'PRIVATE_' not in json.dumps(result) and '/private' not in json.dumps(result)
    data = scanner()
    data['findings_count'] = 0
    with pytest.raises(ValueError):
        imported(data, 'cisco-skill-scanner')


def test_zero_findings_does_not_establish_safety():
    data = scanner()
    data.update(findings_count=0, findings=[], analyzers_failed=[], analyzers_used=[])
    result = imported(data, 'cisco-skill-scanner')['observations']
    assert result['safety_verdict'] == 'NOT_ESTABLISHED' and result['coverage'] == 'incomplete'


def test_cli_import_no_effects_and_pinned_identity(tmp_path, monkeypatch, capsys):
    path = tmp_path/'result.json'
    path.write_text(json.dumps(waza()))
    def forbidden(*args, **kwargs):
        pytest.fail('report import attempted execution or network')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    args = ['import-report', 'waza', '--input', str(path), '--revision', PINS['waza'], '--candidate-sha256', 'a'*64]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)['execution_performed'] is False
    assert list(tmp_path.iterdir()) == [path]
    for raw, revision, candidate in [(b'{"tasks":[],"tasks":[]}', PINS['waza'], 'a'*64),
                                    (b'{}', 'b'*40, 'a'*64), (b'{}', PINS['waza'], 'bad')]:
        with pytest.raises(ValueError):
            import_result(raw, 'waza', revision=revision, candidate_sha256=candidate)
