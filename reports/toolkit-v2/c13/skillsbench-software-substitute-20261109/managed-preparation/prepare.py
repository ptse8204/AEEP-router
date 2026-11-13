"""Stage the reviewed Prefix Cache files and canonical recipe without running a worker."""

import base64
import hashlib
import json
import runpy
from pathlib import Path

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.extensions import bounded_batches, require_environment
from aeep.assessment.models import AssessmentEnvironment, RecipeDefinition, content_digest
from aeep.assessment.recipes import faulty_outputs
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest, ManagedHostArtifact
from aeep.registry import validate_json
from aeep_toolkit.benchmarks import BenchmarkPack, task_input

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
REPORTS = HERE.parents[1]
WORK = ROOT / '.aeep' / HERE.parent.name / 'managed-preparation'
IMAGE = REPORTS / 'skillsbench-react-managed-preparation-20261107'
CARRIER = REPORTS / 'skillsbench-contained-graders-20261105'
REFERENCE = REPORTS / 'skillsbench-invoice-fraud-20261106' / 'continuation' / 'reference-operation-review.json'
DESTINATION = '/opt/aeep-skillsbench-prefix-cache'
TASK = 'llm-prefix-cache-replay'
LIMIT = 262144


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    assert not any(parent.is_symlink() for parent in (path, *path.parents))
    if path.exists():
        assert path.read_bytes() == data
    else:
        with path.open('xb') as stream:
            stream.write(data)
        path.chmod(0o444)


def write(path, value):
    save(path, (json.dumps(value, indent=2) + '\n').encode())


def checks(grade, binding):
    ids = binding['test_identities']
    status = dict.fromkeys(ids, 'PASSED')
    assert grade['classify'](0, ids, status, ids)['valid'] == [True]
    status[ids[0]] = 'FAILED'
    assert grade['classify'](1, ids, status, ids)['failure_codes'] == ['upstream_rejected']
    for rejected in ('ERROR', 'SKIPPED'):
        status[ids[0]] = rejected
        try:
            grade['classify'](1, ids, status, ids)
        except ValueError:
            pass
        else:
            raise AssertionError('unexpected grade for incomplete verifier results')
    assert grade['decode_report']({'report_b64': 'e30='}, binding) == b'{}'
    assert grade['decode_report']({'report_b64': 'W10='}, binding) is None
    assert grade['decode_report']({'report_b64': 'not base64'}, binding) is None
    assert grade['decode_report']({'report_b64': base64.b64encode(b'x' * (LIMIT+1)).decode()}, binding) is None


def main():
    review_path = HERE.parent / 'runtime-support' / 'operation-review.json'
    audit_path = review_path.with_name('audit.json')
    review, audit = read(review_path), read(audit_path)
    assert audit['review_sha256'] == sha(review_path) and audit['cases']['reference']['upstream_binary_reward'] == 1
    pack_path = HERE.parent / 'task-pack.json'
    pack = BenchmarkPack.model_validate(read(pack_path))
    transport = read(HERE.parent / 'task-pack-transport.json')
    value = task_input(pack, Path(transport['pack_root']), TASK)
    assert value['task_archive_sha256'] == transport['public_archive_sha256']
    assert value['output_paths'] == ['report.json']
    assert not read(HERE.parent / 'local-rights-draft.json')['provider_disclosure_allowed']

    sealed = read(IMAGE / 'self-contained-result.json')
    parent = AssessmentEnvironment.model_validate(read(IMAGE / 'self-contained-environment.json'))
    assert sealed['passed'] and sealed['accounting_settled'] and sealed['image']['id'] == parent.container_image
    parent_review = IMAGE / 'self-contained-operation-review.json'
    assert sealed['review_sha256'] == sha(parent_review)
    parent_tag = read(parent_review)['image_tag']
    assert parent_tag == 'aeep-skillsbench-react:sealed-amd64-20261108'
    dockerfile = f'FROM {parent_tag}\nCOPY runtime/ {DESTINATION}/\n'
    context = WORK / 'build'
    save(context / 'Dockerfile', dockerfile.encode())

    protected = WORK.parent / 'protected-continuation'
    for name in ('config.json', 'trace.jsonl', 'solve.sh', 'test_outputs.py', 'oracle_helpers.py'):
        path = protected / name
        assert path.is_file() and not path.is_symlink() and sha(path) == review['pins'][str(path)]
        save(context / 'runtime' / name, path.read_bytes())
    refs = read(REFERENCE)['files']
    native, = [Path(path) for path in refs if path.endswith('/grade/repository_suite_native_capture.py')]
    assert sha(native) == refs[str(native)]
    save(context / 'runtime' / native.name, native.read_bytes())
    wheels = {Path(path): digest for path, digest in refs.items() if path.endswith('.whl')}
    assert len(wheels) == 6
    for path, digest in sorted(wheels.items()):
        assert sha(path) == digest
        save(context / 'runtime' / 'wheels' / path.name, path.read_bytes())

    grade_path = HERE / 'grade.py'
    save(context / 'runtime' / 'grade.py', grade_path.read_bytes())
    reference = read(review_path.with_name('result.json'))['cases']['reference']
    identities = sorted('test_outputs.py::' + row['test_id'] for row in reference['tests'])
    assert len(identities) == len(set(identities)) == 10
    binding = {'task_id': TASK, 'archive_sha256': value['task_archive_sha256'],
               'output_field': 'report_b64', 'max_output_bytes': LIMIT, 'test_identities': identities}
    write(context / 'runtime' / 'binding.json', binding)
    checks(runpy.run_path(str(grade_path)), binding)
    for directory in (context / 'runtime', context / 'runtime' / 'wheels'):
        directory.chmod(0o755)
    inventory = {str(path.relative_to(context)): sha(path) for path in sorted(context.rglob('*')) if path.is_file()}

    builder = runpy.run_path(str(CARRIER / 'prepare-recipes.py'))
    draft = builder['recipe_for']('prefix-cache', binding, value, b'{}', b'{}').model_dump(mode='json')
    del draft['dependencies']['reference_output']
    draft['dependencies']['protected_context'] = content_digest(inventory)
    for kind in ('reference', 'grader'):
        command = draft['extension'][kind]['config']
        command['argv'] = ['/usr/bin/python3', '-I', '-B', DESTINATION + '/grade.py',
                           'reference' if kind == 'reference' else 'grade']
    recipe = RecipeDefinition.model_validate(draft)
    assert recipe.extension is not None
    validate_json(value, recipe.input_schema, label='pinned Prefix Cache input')
    artifact = ManagedHostArtifact(input_field='task_archive_b64', output_field='report_b64',
                                   input_name='skillsbench-task.zip', output_name='report.json', max_bytes=LIMIT)
    largest = {'report_b64': 'A' * (4 * ((LIMIT + 2) // 3))}
    validate_json(largest, recipe.output_schema, label='bounded output')
    payloads = [largest, *faulty_outputs(largest), *recipe.extension.fault_outputs]
    truth = {'task_archive_sha256': value['task_archive_sha256']}
    batches = bounded_batches([{'input': value, 'output': output, 'expected': truth} for output in payloads],
                              separate=True)
    assert len(batches) == len(payloads) == 7
    env = parent.model_copy(update={'environment_id': 'prefix-cache-protected-draft', 'cpu_count': 1.0,
                                    'memory_mb': 512, 'process_limit': 64, 'container_tmpfs_mb': 32})
    require_environment(recipe, env)
    spec = recipe.extension.grader
    request = ActionRequest(action_id='prefix-cache-preflight', capability=spec.capability, input={'examples': batches[0]})
    argv, _ = ContainerExecutor(env).command(ExecutionContext(
        request=request, spec=spec, estimate=spec.estimate, attempt=1, approved_side_effect=spec.side_effect))
    assert '--read-only' in argv and argv[argv.index('--network') + 1] == 'none'
    assert len([arg for arg in argv if arg.startswith('type=bind,')]) == 1

    write(WORK / 'recipe.json', recipe.model_dump(mode='json'))
    write(WORK / 'artifact.json', artifact.model_dump(mode='json'))
    write(HERE / 'result.json', {
        'task': TASK, 'source_revision': pack.source.revision, 'offline_audit_sha256': sha(audit_path),
        'draft_pack_digest': value['benchmark_pack_sha256'], 'public_archive_sha256': value['task_archive_sha256'],
        'parent_image_id': parent.container_image, 'parent_image_tag': parent_tag,
        'context': str(context), 'context_files': inventory, 'context_digest': content_digest(inventory),
        'recipe': str(WORK / 'recipe.json'), 'recipe_digest': content_digest(recipe),
        'artifact': artifact.model_dump(mode='json'), 'test_identities': identities,
        'local_contract_checks_passed': True, 'canonical_probe_payloads_bound': len(batches),
        'final_rights_pack_pending': True, 'builds': 0, 'containers': 0, 'models': 0, 'comparisons': 'PAUSED',
    })


if __name__ == '__main__':
    main()
