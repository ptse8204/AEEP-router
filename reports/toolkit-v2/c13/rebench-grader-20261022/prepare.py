"""Prepare an inert upstream compatibility review. Never import external code."""
import ast
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (AssessmentEnvironment, AssessmentScopeAmendment,
    AssessmentSubject, ExecutableRecipeExtension, RecipeDefinition, RecipeFeatureRule,
    RecipeLiteralFixture, RecipeMaterializationRequest, RecipeRuntimeBinding, content_digest)
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorKind, ExecutorSpec

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PRIVATE = ROOT / '.aeep/repository-cohort-20261022'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_source(path, names):
    text = path.read_text()
    nodes = {node.name: ast.get_source_segment(text, node) for node in ast.parse(text).body
             if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names}
    assert set(nodes) == set(names)
    return '\n\n'.join(nodes[name] for name in names) + '\n'


def archive_tree(path):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for item in sorted(path.rglob('*')):
            assert not item.is_symlink()
            if item.is_file():
                data = item.read_bytes()
                info = tarfile.TarInfo(item.relative_to(path).as_posix())
                info.size, info.mode = len(data), 0o444
                archive.addfile(info, io.BytesIO(data))
    return gzip.compress(stream.getvalue(), mtime=0)


def main():
    assert not (HERE / 'operation-review.json').exists()
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3
    task = json.loads((PRIVATE / 'development-task.json').read_text())
    provenance = json.loads((ROOT / 'reports/toolkit-v2/c13/repository-cohort-20261022/development-source-review.json').read_text())
    assert task['instance_id'] == 'delgan__loguru-1451'
    assert sha(PRIVATE / 'development-repo.tar.gz') == provenance['archive_sha256']
    pin = json.loads((ROOT / 'reports/toolkit-v2/c13/repository-cohort-20261022/upstream-harness-source-audit.json').read_text())
    source_root = PRIVATE / 'upstream-source'
    for name, item in pin['files'].items():
        if 'sha256' in item:
            assert sha(source_root / name) == item['sha256']
    constants = ['ResolvedStatus', 'TestStatus', 'EvalType']
    functions = ['test_passed', 'test_failed', 'get_eval_tests_report',
                 'compute_fail_to_pass', 'compute_pass_to_pass', 'get_resolution_status']
    attribution = ('# MIT-licensed source excerpts from SWE-rebench/SWE-bench-fork\n'
        '# Commit: ' + pin['revision'] + '\n'
        '# Exact function/class bodies; orchestration imports omitted. See LICENSE.upstream.\n')
    upstream = (attribution + 'from __future__ import annotations\nfrom enum import Enum\nfrom typing import Any\n'
        + 'FAIL_TO_PASS="FAIL_TO_PASS"\nFAIL_TO_FAIL="FAIL_TO_FAIL"\nPASS_TO_PASS="PASS_TO_PASS"\nPASS_TO_FAIL="PASS_TO_FAIL"\n'
        + selected_source(source_root / 'swebench/harness/constants/__init__.py', constants)
        + selected_source(source_root / 'swebench/harness/log_parsers/python.py', ['parse_log_pytest'])
        + selected_source(source_root / 'swebench/harness/grading.py', functions))
    compile(upstream, '<upstream-source-review>', 'exec')  # Parse only; never execute on host.
    (HERE / 'upstream-grading.py').write_text(upstream)
    (HERE / 'LICENSE.upstream').write_bytes((source_root / 'LICENSE').read_bytes())
    wheels_review = json.loads((ROOT / 'reports/toolkit-v2/c13/repository-cohort-20261022/wheel-source-review.json').read_text())
    wheels = []
    for item in wheels_review['pins']:
        path = PRIVATE / 'wheels' / item['filename']
        assert sha(path) == item['sha256']
        wheels.append({key: item[key] for key in ('filename', 'sha256')} | {'data': base64.b64encode(path.read_bytes()).decode()})
    workspace = PRIVATE / 'prepared'
    workspace.mkdir(exist_ok=False)
    base = workspace / 'base'
    base.mkdir()
    with tarfile.open(PRIVATE / 'development-repo.tar.gz') as archive:
        for item in archive.getmembers():
            if item.isdir():
                continue
            assert item.isfile()
            path = PurePosixPath(item.name)
            assert not path.is_absolute() and '..' not in path.parts
            relative = Path(*path.parts[1:])
            target = base / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(item).read())
    # Keep git from discovering the enclosing user checkout or its configuration.
    git_env = {'PATH': '/usr/bin:/bin', 'GIT_CEILING_DIRECTORIES': str(PRIVATE),
               'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
    discovery = subprocess.run(['/usr/bin/git', 'rev-parse', '--show-toplevel'], cwd=base,
                               env=git_env, capture_output=True, check=False)
    assert discovery.returncode != 0

    def apply(directory, patch):
        subprocess.run(['/usr/bin/git', 'apply', '--no-index', '--check', '-'], cwd=directory,
                       env=git_env, input=patch.encode(), check=True)
        subprocess.run(['/usr/bin/git', 'apply', '--no-index', '-'], cwd=directory,
                       env=git_env, input=patch.encode(), check=True)

    apply(base, task['test_patch'])
    gold = workspace / 'gold'
    shutil.copytree(base, gold)
    apply(gold, task['patch'])
    assert '_make_key_error' in (gold / 'loguru/_handler.py').read_text()
    assert '_make_key_error' not in (base / 'loguru/_handler.py').read_text()
    assert 'def test_invalid_format_key_error_message_content' in (base / 'tests/test_add_option_format.py').read_text()
    broken = workspace / 'regression'
    shutil.copytree(gold, broken)
    path = broken / 'loguru/_handler.py'
    text = path.read_text()
    assert text.count('self._sink.write(str_record)') == 1
    path.write_text(text.replace('self._sink.write(str_record)', 'self._sink.write(str_record.upper())'))
    test_file = 'tests/test_add_option_format.py'
    assert len({sha(path / test_file) for path in (base, gold, broken)}) == 1
    assert all(sha(base / path.relative_to(base)) == sha(gold / path.relative_to(base))
               for path in base.rglob('*') if path.is_file() and path.relative_to(base).as_posix() != 'loguru/_handler.py')
    variants = []
    test_argv = ['--no-header', '-rA', '--tb=line', '--color=no', '-p', 'no:cacheprovider', test_file]
    for name, directory, expected in [('unchanged', base, 'RESOLVED_NO'), ('published_repair', gold, 'RESOLVED_FULL'),
                                      ('introduced_regression', broken, 'RESOLVED_NO')]:
        archive = archive_tree(directory)
        payload = {'mode': 'repository', 'archive': base64.b64encode(archive).decode(),
                   'archive_sha256': hashlib.sha256(archive).hexdigest(), 'wheels': wheels,
                   'upstream_grading': upstream, 'upstream_grading_sha256': hashlib.sha256(upstream.encode()).hexdigest(),
                   'test_argv': test_argv, 'expected': {key: task[key] for key in ('FAIL_TO_PASS', 'PASS_TO_PASS')}}
        output = workspace / (name + '.json')
        output.write_text(json.dumps(payload, separators=(',', ':')))
        assert output.stat().st_size < 1_800_000
        variants.append({'name': name, 'payload': str(output.relative_to(ROOT)), 'payload_sha256': sha(output),
                         'payload_bytes': output.stat().st_size, 'archive_sha256': payload['archive_sha256'],
                         'expected_resolution': expected})
    program = (HERE / 'probe.py').read_text()
    spec = ExecutorSpec(id='swe-rebench-development-grader', capability='swe_rebench.development',
        kind=ExecutorKind.COMMAND, description='Pinned upstream repository development tests; not a model trial.',
        config={'argv': ['python3', '-B', '-c', program], 'argv_literal': True, 'stdin_json': True,
                'max_stdin_bytes': 1_800_000, 'max_output_bytes': 500_000,
                'timeout_seconds': 30, 'output': {'type': 'json'}})
    # This scope authorizes fixed probes only. It supplies no case generator or campaign acceptance.
    literal = lambda name: RecipeLiteralFixture(input={'mode': name}, output={'development_only': True})
    recipe = RecipeDefinition(schema_version='assessment.recipe.v2', recipe_id='swe-rebench-grader-development-20261022',
        capability=spec.capability, description='Fixed upstream grader compatibility probes only; not a validated campaign recipe.',
        input_schema={'type': 'object'}, output_schema={'type': 'object'}, generator='contained_json:1',
        grader='contained_json:1', extractor='structural_json:1', variations=['development'],
        exclusions=['model execution', 'qualification', 'admission', 'full upstream runtime equivalence'],
        extension=ExecutableRecipeExtension(generator=spec, grader=spec, reference=spec,
            independent_fixtures=[literal('boundary'), literal('fresh_read')], transformed_fixtures=[literal('fresh_write')],
            fault_outputs=[{}], feature_rules={'mode': RecipeFeatureRule(path='/mode', operation='type')},
            variation_features={'development': {'mode': 'str'}}, template_families=['development']))
    environment = AssessmentEnvironment(environment_id='rebench-offline-development-20261022', kind='container', identity={},
        container_image='sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7',
        container_runtime='/usr/local/bin/docker', container_socket='/Users/edwintse/.docker/run/docker.sock', network=False)
    subject = AssessmentSubject(kind='command', location=str(workspace), dependency_digests={str(workspace / (item['name']+'.json')): item['payload_sha256'] for item in variants},
        description='Development-only Loguru issue with pinned upstream tests and grading functions; excluded from holdout.')
    runtime = RecipeRuntimeBinding(dependencies=runtime_dependencies())
    request = RecipeMaterializationRequest(schema_version='assessment.recipe-materialization.v2',
        subject_digest=content_digest(subject), recipe_digest=content_digest(recipe), mapping_digest=content_digest(recipe),
        environment_digest=content_digest(environment), authorization_id='onboarding', seed=29,
        definition_digests=[content_digest(recipe), content_digest(environment), content_digest(runtime)], runtime_dependencies=runtime.dependencies)
    documents = {}
    for kind, identity, value in [('subject', subject.subject_id, subject), ('recipe', recipe.recipe_id, recipe),
        ('environment', environment.environment_id, environment), ('recipe_runtime', content_digest(runtime), runtime),
        ('recipe_materialization_request', request.plan_id, request)]:
        documents[content_digest(value)] = {'kind': kind, 'id': identity, 'document': value.model_dump(mode='json')}
    auth = '7cf37077213dd84d02ffb6c8c1106930ecec04d4337780454f6ac308b0bef659'
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=auth,
        subject_digests=[content_digest(subject)], recipe_digests=[content_digest(recipe)],
        environment_digests=[content_digest(environment)], reviewed_digests=list(documents))
    review = {'purpose': 'One offline upstream grader compatibility attempt; no qualification or benefit claim.',
        'source_digest': verification_source_digest(ROOT), 'runner_sha256': sha(HERE / 'run.py'),
        'probe_sha256': sha(HERE / 'probe.py'), 'upstream_grading_sha256': sha(HERE / 'upstream-grading.py'),
        'dataset_revision': provenance['dataset_revision'], 'instance_id': task['instance_id'], 'base_commit': task['base_commit'],
        'development_exclusion': [task['instance_id'], 'pgmpy__pgmpy-3137'],
        'upstream_harness_revision': pin['revision'], 'upstream_source_functions': functions + constants + ['parse_log_pytest'],
        'runtime_deviation': 'Use pytest 8.3.5 instead of the upstream task dev extra 8.4.1, avoiding an unused Pygments dependency so exact wheel bytes and the full repository fit the existing 2 MB container transport. This tests the adapted runtime only; official upstream image/runtime conformance remains unknown.',
        'wheels': [{key: value for key, value in item.items() if key != 'data'} for item in wheels_review['pins']],
        'variants': variants, 'expected_fail_to_pass': task['FAIL_TO_PASS'], 'expected_pass_to_pass': task['PASS_TO_PASS'],
        'request': request.model_dump(mode='json'), 'recipe': recipe.model_dump(mode='json'), 'documents': documents,
        'definitions': {key: item['document'] for key, item in documents.items()}, 'amendment': amendment.model_dump(mode='json'),
        'authorization_digest': auth, 'image': environment.container_image, 'docker': environment.container_runtime,
        'socket': 'unix://' + environment.container_socket,
        'host_canary': '.aeep/repository-cohort-20261022/host-only-canary',
        'maximum_contained_calls': 6, 'maximum_operations': 8, 'maximum_reserved_seconds': 360,
        'maximum_model_turns': 0, 'cash_usd': 0, 'network': False, 'automatic_retry': False,
        'effects': ['Run three fresh boundary/state probes and three full-repository upstream test runs in existing image.',
            'Load seven exact cached pure-Python wheels privately from stdin with zipimport; no pip/build backend, downloads, image builds/pulls, models, credentials, activation or release.',
            'Reuse existing AssessmentService authorization, atomic reservations, Router, ContainerExecutor and durable receipts. Record the finite scope amendment under standing operator delegation. Preserve all grant usage.',
            'Expected test identities and published patch stay outside model workers; there are no model workers in this check. Fixed development fixtures are excluded from all future holdouts.',
            'Retain payloads, logs, receipts and ledger. Remove only attempt-owned containers and the unchanged owned synthetic canary. No images, retained runtimes, backups or unrelated work are removed.'],
        'limitations': ['Upstream pytest log parsing is not a proof against adversarial log forgery or incomplete tests.',
            'One inspected public issue establishes neither broad workload validity nor model usefulness nor selection quality.',
            'No full SWE-bench environment, installer or official x86 image is executed; only pinned grading functions and real task tests are reused.'],
        'approval_reason': 'The pasted continuation excludes untrusted software execution; CONTINUATION.md requires applicable authority for new contained execution. The preceding approved correction bundle is terminal and does not cover external repository tests or these wheels.'}
    (HERE / 'operation-review.json').write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps({'review_sha256': sha(HERE / 'operation-review.json'), 'variants': variants,
                      'source_digest': review['source_digest'], 'execution_started': False}))


if __name__ == '__main__':
    main()
