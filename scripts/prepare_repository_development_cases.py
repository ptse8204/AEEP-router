"""Extract pinned local maintenance examples; no imports of historical source."""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.repository_tasks import RepositoryCase

ROOT = Path(__file__).resolve().parents[1]
REVISION = '77077562e1a63d45791c478066affba35dd8d10d'


def source(path: str, revision: str = REVISION) -> str:
    return subprocess.check_output(['git', 'show', revision + ':' + path], cwd=ROOT).decode()


def function(text: str, name: str) -> str:
    node = next(item for item in ast.parse(text).body if isinstance(item, ast.FunctionDef) and item.name == name)
    segment = ast.get_source_segment(text, node)
    assert segment is not None
    return segment + '\n'


def build() -> list[dict]:
    cases = []

    def add(task_id, family, task, files, editable, changes, checks, path, provenance):
        value = dict(task_id=task_id, task=task, family=family, files=files, editable_paths=editable)
        digest = content_digest(value)
        faulty = {path: ''.join('def ' + call + '(*args, **kwargs):\n    return None\n'
            for call in sorted({check['probe']['call'] for check in checks if check['probe']['module'] == path}))
            for path in editable}
        case = RepositoryCase(input=value, truth={'input_sha256': digest, 'checks': checks},
            reference_patch={'base_sha256': digest, 'files': changes},
            fault_patches=[{'base_sha256': digest, 'files': faulty}],
            source_repository='https://github.com/ptse8204/AEEP-router', source_revision=REVISION,
            source_path=path, source_sha256=hashlib.sha256(source(path).encode()).hexdigest(),
            license='Apache-2.0', provenance=provenance, independent_case_id=task_id, template_family=task_id)
        cases.append(case.model_dump(mode='json'))

    launch_path = 'src/aeep/hosts/codex_metrics.py'
    before = source(launch_path, '44bdad98c1a6b2d845c4e084afe07bbf96a0073e')
    assert "command = [*argv, *(part for option in options for part in ('-c', option))]" in before
    old = "def command(argv, options):\n    return [*argv, *(part for option in options for part in ('-c', option))]\n"
    fixed = ("def command(argv, options):\n"
        "    boundary = argv.index('app-server') if 'app-server' in argv else len(argv)\n"
        "    return [*argv[:boundary], *(part for option in options for part in ('-c', option)), *argv[boundary:]]\n")
    add('aeep-cli-override-placement', 'regression-repair',
        'Repair global configuration option placement: append telemetry -c overrides after existing global options, before app-server when present. Preserve all argv elements and override order. Support commands with no app-server.',
        {'launch.py': old, 'README.txt': 'Extracted CLI argv construction; no process launching or network.\n'},
        ['launch.py'], {'launch.py': fixed}, [
            {'name': 'policy_and_telemetry', 'probe': {'module': 'launch.py', 'call': 'command',
                'args': [['codex', '-c', 'policy=locked', 'app-server', '--listen', 'stdio://'], ['metrics=local']]},
             'expected': ['codex', '-c', 'policy=locked', '-c', 'metrics=local', 'app-server', '--listen', 'stdio://']},
            {'name': 'no_subcommand', 'probe': {'module': 'launch.py', 'call': 'command', 'args': [['codex'], ['a=1', 'b=2']]},
             'expected': ['codex', '-c', 'a=1', '-c', 'b=2']},
            {'name': 'no_overrides', 'probe': {'module': 'launch.py', 'call': 'command', 'args': [['codex', 'app-server'], []]},
             'expected': ['codex', 'app-server']}], launch_path,
        'Known October 21 incident. Narrow function extraction/adaptation of the command expression before 7707756 and its repair; public development example, never independent holdout. Full pre-repair source pin: 44bdad98c1a6b2d845c4e084afe07bbf96a0073e; source SHA-256 ' + hashlib.sha256(before.encode()).hexdigest())

    report_path = 'src/aeep_toolkit/reporting.py'
    counts = 'from __future__ import annotations\n' + function(source(report_path), 'token_total')
    wrapper = ('from types import SimpleNamespace\nimport counts\n'
        'def total(value):\n    return counts.token_total(None if value is None else SimpleNamespace(**value)) or 0\n')
    tokens = dict(input_tokens=10, output_tokens=4, cached_input_tokens=5, reasoning_output_tokens=2,
                  cached_semantics='included_in_input', reasoning_semantics='included_in_output')
    add('aeep-token-unknown-propagation', 'contract-propagation',
        'Preserve the token_total contract through the public total API: unavailable counts must remain None; measured zero must remain zero. Do not double count included token categories. Preserve the core accounting implementation.',
        {'counts.py': counts, 'api.py': wrapper}, ['api.py'], {'api.py': wrapper.replace(' or 0', '')}, [
            {'name': 'unknown_input', 'probe': {'module': 'api.py', 'call': 'total', 'args': [None]}, 'expected': None},
            {'name': 'included_categories', 'probe': {'module': 'api.py', 'call': 'total', 'args': [tokens]}, 'expected': 14},
            {'name': 'unknown_semantics', 'probe': {'module': 'api.py', 'call': 'total', 'args': [{**tokens, 'cached_semantics': 'unknown'}]}, 'expected': None},
            {'name': 'measured_zero', 'probe': {'module': 'api.py', 'call': 'total', 'args': [{**tokens, 'input_tokens': 0, 'output_tokens': 0, 'cached_input_tokens': 0, 'reasoning_output_tokens': 0}]}, 'expected': 0},
            {'name': 'separate_categories', 'probe': {'module': 'api.py', 'call': 'total', 'args': [{**tokens, 'cached_semantics': 'separate', 'reasoning_semantics': 'separate'}]}, 'expected': 21}], report_path,
        'Actual pinned token_total source with a newly authored faulty cross-file caller. Seeded development reproduction of the repository accounting contract, not a historical bug claim or independently sourced benchmark.')

    callback_path = 'src/aeep/assessment/extensions.py'
    helper = ('import hashlib, json\n'
        'def content_digest(value):\n    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()\n')
    callback = 'from __future__ import annotations\nfrom digest import content_digest\n' + function(source(callback_path), 'grader_name')
    add('aeep-callback-binding-audit', 'adjacent-no-change',
        'Audit grader_name: it must bind both the input and expected result with the canonical content digest. Preserve working behavior; make no change if this contract is already met.',
        {'callbacks.py': callback, 'digest.py': helper}, ['callbacks.py'], {}, [
            {'name': name, 'probe': {'module': 'callbacks.py', 'call': 'grader_name', 'args': [value, expected]},
             'expected': 'contained_recipe_' + content_digest({'input': value, 'expected': expected})}
            for name, value, expected in [('literal', {'text': 'one'}, {'answer': 1}),
                ('changed_input', {'text': 'two'}, {'answer': 1}), ('changed_expected', {'text': 'one'}, {'answer': 2})]],
        callback_path, 'Actual pinned grader_name with an equivalent stdlib digest helper. Known contract audit/negative control; no repair needed. Development example, not a fresh holdout.')
    return cases


if __name__ == '__main__':
    print(json.dumps(build(), indent=2, ensure_ascii=False))
