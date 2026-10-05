"""Synthetic multi-domain stack fixtures. These produce no real media or research."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from aeep.models import (
    ExecutorKind,
    ExecutorSpec,
    Locality,
    Manifest,
    ResourceVector,
    RouteEstimate,
    SideEffect,
)
from aeep.stack_models import ArtifactContract, GoalSpec, StackBinding, TaskNode


def synthetic_artifact(values: dict[str, Any]) -> dict[str, str]:
    return {'artifact': hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()}


def fixture(family: str, *, database: str = ':memory:') -> tuple[Manifest, GoalSpec, dict[str, dict[str, Any]]]:
    graphs = {
        'media': [('brief', []), ('music', ['brief']), ('storyboard', ['brief']),
                  ('keyframes', ['storyboard']), ('clips', ['keyframes']), ('timing', ['music']),
                  ('compose', ['clips', 'timing']), ('verify', ['compose']), ('export', ['verify'])],
        'data': [('ingest', []), ('transform', ['ingest']), ('summarize', ['transform']),
                 ('verify', ['summarize'])],
        'research': [('retrieve', []), ('extract', ['retrieve']), ('synthesize', ['extract']),
                     ('verify', ['synthesize'])],
    }
    graph = graphs[family]
    contract = ArtifactContract(semantic_type='synthetic-artifact', media_type='text/plain',
                                value_schema={'type': 'string'}, locality='local', confidentiality='public')
    specs, nodes = [], []
    for name, deps in graph:
        inputs = {dep: contract for dep in deps}
        if not deps:
            inputs = {'seed': contract}
        nodes.append(TaskNode(node_id=name, capability=f'fixture.{family}.{name}@1',
            inputs=inputs, outputs={'artifact': contract},
            bindings=[StackBinding(source_node=dep, source_port='artifact', target_port=dep) for dep in deps]))
        specs.append(ExecutorSpec(id=f'{family}.{name}', capability=nodes[-1].capability,
            kind=ExecutorKind.PYTHON, description='Synthetic offline stack fixture',
            input_schema={'type': 'object', 'properties': {key: {'type': 'string'} for key in inputs},
                          'required': list(inputs), 'additionalProperties': False},
            output_schema={'type': 'object', 'properties': {'artifact': {'type': 'string'}},
                           'required': ['artifact'], 'additionalProperties': False},
            estimate=RouteEstimate(resources=ResourceVector(monetary_usd=0, latency_ms=1)),
            side_effect=SideEffect.NONE, locality=Locality.IN_PROCESS, idempotent=True,
            safe_to_auto_execute=True,
            config={'callable': 'aeep.examples.stack_fixtures:domain_artifact', 'argument_mode': 'request',
                    'stack': {'inputs': {key: contract.model_dump() for key in inputs},
                              'outputs': {'artifact': contract.model_dump()}}}))
    goal = GoalSpec(goal_id=f'fixture.{family}', nodes=nodes, deliverables=[nodes[-1].node_id], propose_only=False)
    return Manifest(database=database, executors=specs), goal, {nodes[0].node_id: {'seed': f'synthetic-{family}'}}


def domain_artifact(request: Any) -> dict[str, str]:
    """Exercise domain operations on fixed public/synthetic inputs, without I/O."""
    _, family, operation = request.capability.partition('@')[0].split('.')
    values = {key: json.loads(value) for key, value in request.input.items() if key != 'seed'}
    artifact: Any
    if family == 'media':
        if operation == 'brief':
            artifact = {'style': 'Windows XP', 'seconds': 12, 'fps': 24, 'size': [640, 480]}
        elif operation == 'music':
            artifact = {'bpm': 120, 'beats': 24, 'seconds': values['brief']['seconds'], 'audio': 'fixture-tone'}
        elif operation == 'storyboard':
            artifact = {'shots': ['green hill', 'blue desktop', 'start menu'], 'seconds': values['brief']['seconds']}
        elif operation == 'keyframes':
            artifact = {'frames': [{'scene': shot, 'palette': ['#245edb', '#3c9f35']} for shot in values['storyboard']['shots']], 'seconds': values['storyboard']['seconds']}
        elif operation == 'clips':
            frames = values['keyframes']['frames']
            artifact = {'clips': [{'scene': frame['scene'], 'seconds': values['keyframes']['seconds'] / len(frames)} for frame in frames]}
        elif operation == 'timing':
            music = values['music']
            artifact = {'beat_times': [n * 60 / music['bpm'] for n in range(music['beats'])], 'seconds': music['seconds']}
        elif operation == 'compose':
            clips = values['clips']['clips']
            start = 0.0
            timeline = []
            for clip in clips:
                timeline.append({**clip, 'start': start, 'end': start + clip['seconds']})
                start += clip['seconds']
            artifact = {'timeline': timeline, 'duration': start, 'audio_duration': values['timing']['seconds']}
        elif operation == 'verify':
            composition = values['compose']
            if composition['duration'] != 12 or composition['audio_duration'] != 12:
                raise ValueError('fixture duration mismatch')
            if any(a['end'] != b['start'] for a, b in zip(composition['timeline'], composition['timeline'][1:], strict=False)):
                raise ValueError('fixture timeline gap')
            artifact = {**composition, 'verified': True}
        else:
            artifact = {**values['verify'], 'format': 'offline-edit-decision-list', 'encoded_video': False}
    elif family == 'data':
        if operation == 'ingest':
            artifact = {'rows': [{'category': 'A', 'amount': 12}, {'category': 'B', 'amount': 8}, {'category': 'A', 'amount': 5}]}
        elif operation == 'transform':
            totals: dict[str, int] = {}
            for row in values['ingest']['rows']:
                totals[row['category']] = totals.get(row['category'], 0) + row['amount']
            artifact = {'totals': totals, 'row_count': len(values['ingest']['rows'])}
        elif operation == 'summarize':
            artifact = {**values['transform'], 'grand_total': sum(values['transform']['totals'].values())}
        else:
            artifact = values['summarize']
            if artifact != {'totals': {'A': 17, 'B': 8}, 'row_count': 3, 'grand_total': 25}:
                raise ValueError('fixture report validation failed')
            artifact = {**artifact, 'verified': True}
    else:
        sources = [{'url': 'https://example.org/fixture/alpha', 'text': 'Alpha has 3 records.'},
                   {'url': 'https://example.org/fixture/beta', 'text': 'Beta has 2 records.'}]
        if operation == 'retrieve':
            artifact = {'sources': sources, 'offline_fixture': True}
        elif operation == 'extract':
            artifact = {'facts': [{'name': source['text'].split()[0], 'count': int(source['text'].split()[2]), 'citation': source['url']} for source in values['retrieve']['sources']]}
        elif operation == 'synthesize':
            facts = values['extract']['facts']
            artifact = {'facts': facts, 'total': sum(fact['count'] for fact in facts)}
        else:
            artifact = values['synthesize']
            if artifact['total'] != 5 or {fact['citation'] for fact in artifact['facts']} != {source['url'] for source in sources}:
                raise ValueError('fixture reference validation failed')
            artifact = {**artifact, 'verified': True}
    return {'artifact': json.dumps(artifact, sort_keys=True)}


def pass_artifact(source: str) -> dict[str, str]:
    """Identity mapping for testing a reviewed converter's workflow bindings."""
    return {'artifact': source}
