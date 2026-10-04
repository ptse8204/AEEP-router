"""Focused acceptance tests for the staged docx:1 WorkerPairInspection delta.

Run after applying worker-pair-docx-profile.patch with:
  PYTHONPATH=src:tests python3 -m pytest -q reports/v08/luna-docx-stage/test_docx_profile.py
"""
from __future__ import annotations

import pytest

from aeep.assessment.models import content_digest
from aeep.errors import ConfigurationError
from aeep.hosts import codex_pair_inspection as paired
from test_v08_pair_inspection import definition as base_definition

DOCX_SKILL_SHA256 = '65c3442f51953a6b987e8aefa9abcb458f110344e80cc16c7c7efb931a13efea'


def docx_definition() -> paired.WorkerPairInspection:
    value = base_definition(task_profile=True).model_dump(mode='json')
    value.update(schema_version='assessment.worker-pair-inspection.v3', profile='docx:1')
    skill, alias, directory, names = paired.SKILL_PROFILES['docx:1']
    digest = DOCX_SKILL_SHA256
    differential = value['differential']
    differential.update(candidate_paths=sorted([skill, alias, directory]), candidate_aliases=['docx'],
        control_inventory={'python': 'd' * 64}, candidate_inventory={'skill:docx': digest},
        treatment_inventory={'python': 'd' * 64, 'skill:docx': digest})
    value['candidate_skill_digest'] = digest
    value['shared_versions'] = {'pandas': '2.3.2', 'openpyxl': '3.1.5', 'python-docx': '1.1.2'}
    for role in ('control', 'treatment'):
        config = value[role]['config']
        value[role]['capability'] = 'assessment.offer_letter@1'
        worker = config['managed_worker']
        worker['reviewed_files'] = {skill: digest} if role == 'treatment' else None
        config['artifact'] = {'input_field': 'template_b64', 'output_field': 'document_b64',
            'input_name': 'offer_letter_template.docx', 'output_name': 'offer_letter.docx', 'max_bytes': 150000}
        target = config['invocation']
        if role == 'treatment':
            target.update(skill_name='docx', skill_path=skill, skill_sha256=digest)
    return paired.WorkerPairInspection.model_validate(value)


def test_docx_profile_reuses_v3_inventory_and_candidate_access_probes():
    definition = docx_definition()
    assert definition.profile == 'docx:1'
    assert set(definition.shared_versions) == {'pandas', 'openpyxl', 'python-docx'}
    expected = paired.expected_probes(definition, 'treatment')
    assert set(expected) == {'allowed_tool', 'denied_tool', 'cross_worker', 'answers', 'configuration',
        'candidate_network', 'credential_canary', 'resource_limits', 'cleanup', 'events', 'candidate_access'}
    assert expected['candidate_access'] == {
        'definition_digest': content_digest(definition.differential), 'candidate_available': True}
    assert paired.expected_probes(definition, 'control')['candidate_access']['candidate_available'] is False
    program = paired.CHECK.replace('PATHS', repr({'own_workspace': '/workspace/own'})).replace('DOCX_PROBE', 'True')
    assert 'Document(io.BytesIO(docx_buffer.getvalue()))' in program
    compile(program, '<docx-boundary-probe>', 'exec')


def test_docx_profile_rejects_missing_shared_version_or_legacy_schema():
    value = docx_definition().model_dump(mode='json')
    value['shared_versions'].pop('python-docx')
    with pytest.raises(ValueError):
        paired.WorkerPairInspection.model_validate(value)
    value = docx_definition().model_dump(mode='json')
    value['schema_version'] = 'assessment.worker-pair-inspection.v2'
    with pytest.raises(ValueError):
        paired.WorkerPairInspection.model_validate(value)


def test_docx_filesystem_observation_enforces_shape_and_pair_predicates():
    observed = {'own_workspace': 'readable', 'other_workspace': 'absent', 'credential_canary': 'denied',
        'external_answer': 'absent', 'shared_workbook_roundtrip': True, 'candidate_alias': True,
        'candidate_runtime': True, 'python_docx_roundtrip': True, 'pandas': '2.3.2',
        'openpyxl': '3.1.5', 'python-docx': '1.1.2', 'candidate_skill_sha256': DOCX_SKILL_SHA256}
    assert paired.filesystem_observation(observed, 'docx:1') == observed
    missing = dict(observed)
    missing.pop('python_docx_roundtrip')
    with pytest.raises(ConfigurationError, match='malformed filesystem observation'):
        paired.filesystem_observation(missing, 'docx:1')
    # Shape validation accepts observed values; the pair predicate compares them
    # against the reviewed exact dependency and rejects an unsuccessful roundtrip.
    for role in ('control', 'treatment'):
        definition = docx_definition()
        worker = paired.binding_from_config(getattr(definition, role).managed_host_config().managed_worker)
        assert worker is not None
        candidate = role == 'treatment'
        skill_path = paired.SKILL_PROFILES['docx:1'][0]
        base = dict(observed, candidate_skill_sha256=DOCX_SKILL_SHA256 if candidate else None,
            candidate_alias=candidate, candidate_runtime=candidate)
        inspection = {'inspection_complete': True,
            'advertised_inventory': {'apps': [], 'servers': [], 'skills': ([{'name': 'docx', 'path': skill_path, 'enabled': True}] if candidate else [])},
            'sandbox_command': {'workspace_write': True, 'proxy': 'denied', 'direct': 'denied'},
            'config/read': {key: {'matches': True} for key in ('config/web_search', 'config/mcp_servers',
                'config/features/apps', 'config/features/memories', 'config/features/multi_agent',
                'config/features/browser_use', 'config/features/computer_use')},
            'configRequirements/read': {str(i): {'matches': True} for i in range(3)}}
        facts = {'inspection': inspection, 'filesystem': base,
            'cgroups': {'cpu.max': f'{int(worker.cpu_count * 100000)} 100000',
                'memory.max': str(worker.memory_mb * 1024 * 1024), 'pids.max': str(worker.process_limit)},
            'container': {'image': worker.image, 'readonly': True, 'network': worker.network_id,
                'mounts': [{'Type': 'volume', 'Name': worker.credential_volume, 'Destination': '/worker/auth'}]},
            'active_policy': {'profile_matches': True, 'approval_never': True, 'cwd_matches': True},
            'canary_seeded': True, 'canary_removed': True, 'cleanup_confirmed': True,
            'command_stopped': True, 'collection_complete': True}
        for broken in ('version', 'roundtrip'):
            facts['filesystem'] = dict(base)
            if broken == 'version':
                facts['filesystem']['python-docx'] = '1.1.3'
            else:
                facts['filesystem']['python_docx_roundtrip'] = False
            facts['filesystem'] = paired.filesystem_observation(facts['filesystem'], 'docx:1')
            result = paired.observations(definition, role, worker, facts)
            assert result['allowed_tool']['dependencies'] is False
