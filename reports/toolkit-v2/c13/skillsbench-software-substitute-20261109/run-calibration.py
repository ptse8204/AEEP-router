"""Freeze and run the first exact Prefix Cache Replay engineering checks."""

import argparse
import asyncio
import hashlib
import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, StrictModel, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.benchmarks import BenchmarkPack, inspect_pack

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
C13 = HERE.parent
PRIVATE = ROOT / '.aeep' / HERE.name
PROTECTED = PRIVATE / 'protected'
TASK = 'llm-prefix-cache-replay'
UPSTREAM = PRIVATE / f'pack/tasks/{TASK}'
REFERENCE = C13 / 'skillsbench-react-readonly-grader-20261108' / 'environment.json'
PYTEST_REVIEW = C13 / 'skillsbench-invoice-fraud-20261106/continuation/reference-operation-review.json'
TOOLS = ROOT / '.aeep/skillsbench-invoice-fraud-20261106/reference/tools'
DELEGATION = C13 / 'pipeline-standing-authority-20261104.json'
REVIEW = HERE / 'calibration-review.json'
GRANT = 'skillsbench-prefix-cache-reference-20261109'
CASES = ('reference', 'incomplete', 'destructive', 'intentional_skip', 'infrastructure')


class Scope(StrictModel):
    review_sha256: str


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def names():
    row = read(HERE / 'candidate-review.json')['protected_verifier']
    names = set(row['test_functions']) - {'test_per_request_sample'}
    names.update(f'test_per_request_sample[{idx}]' for idx in row['parametrized_indices'])
    assert len(names) == row['expected_test_instances'] == 10
    return names


def classify(case, facts):
    assert facts['case'] == case and facts['pytest_version'] == '8.4.1'
    rows = facts['tests']
    assert len(rows) == 10 and {row['test_id'] for row in rows} == names()
    status = {row['test_id']: row['status'] for row in rows}
    assert set(status.values()) <= {'passed', 'failure', 'error', 'skipped'}
    codes = set(status.values())
    success = facts['pytest_exit'] == 0 and codes == {'passed'}
    if case == 'reference':
        assert success
    elif case in ('incomplete', 'destructive'):
        assert facts['pytest_exit'] == 1 and 'failure' in codes and codes <= {'failure', 'passed'}
    elif case == 'intentional_skip':
        assert facts['pytest_exit'] == 0 and status['test_total_hit_tokens'] == 'skipped'
        assert list(status.values()).count('skipped') == 1 and codes == {'passed', 'skipped'}
    elif case == 'infrastructure':
        assert facts['pytest_exit'] != 0 and codes == {'error'}
    else:
        raise ValueError('unknown review case')
    # A skipped assertion or infrastructure error is a failed evidence gate.
    award = 1 if success else 0 if case in ('incomplete', 'destructive') else None
    return facts | {'verified_upstream_binary_reward': award, 'calibration_case_passed': True}


def image_id(env):
    command = [env.container_runtime, '--host', 'unix://' + env.container_socket, 'image', 'inspect',
               '--format', '{{.Id}} {{.Os}}/{{.Architecture}} {{json (index .Config "Volumes")}}',
               env.container_image]
    out = subprocess.run(command, check=True, timeout=10, env={}, capture_output=True, text=True).stdout.strip()
    assert out == f'{env.container_image} linux/amd64 null'
    return env.container_image


def container_absent(env, name):
    command = [env.container_runtime, '--host', 'unix://' + env.container_socket, 'container', 'ls',
               '--all', '--quiet', '--filter', f'name=^/{name}$']
    output = subprocess.run(command, check=True, timeout=6, env={}, capture_output=True, text=True)
    return not output.stdout.strip()


def checked_environment():
    parent = AssessmentEnvironment.model_validate(read(REFERENCE))
    env = AssessmentEnvironment.model_validate(parent.model_dump() | {
        'environment_id': GRANT, 'identity': {'scope': 'protected prefix cache reference'},
        'read_only_roots': [str(PROTECTED), str(TOOLS)], 'container_tmpfs_mb': 32,
        'network': False, 'cpu_count': 1, 'memory_mb': 512, 'process_limit': 64,
    })
    image_id(env)
    return env


def stage_files():
    assert shutil.disk_usage(ROOT).free >= 51 * 1024**3
    pack = BenchmarkPack.model_validate(read(HERE / 'task-pack.json'))
    inspect_pack(pack, PRIVATE / 'pack', (TASK,))
    selection = read(HERE / 'selection.json')
    assert selection['approved_selection'] == TASK and not selection['provider_disclosure']
    assert selection['candidate_review_sha256'] == sha(HERE / 'candidate-review.json')
    rights = read(HERE / 'local-rights-draft.json')
    assert rights['local_execution_allowed'] and not rights['provider_disclosure_allowed']
    assert rights['assets'] == {a.path: a.sha256 for a in pack.task(TASK).assets}
    PROTECTED.mkdir(mode=0o755, exist_ok=True)
    for source, target in (
        (UPSTREAM / 'environment/trace.jsonl', 'trace.jsonl'),
        (UPSTREAM / 'environment/config.json', 'config.json'),
        (UPSTREAM / 'oracle/solve.sh', 'solve.sh'),
        (UPSTREAM / 'verifier/test_outputs.py', 'test_outputs.py'),
        (UPSTREAM / 'verifier/oracle_helpers.py', 'oracle_helpers.py'),
        (HERE / 'calibrate.py', 'calibrate.py'),
    ):
        original = source.read_bytes()
        adapted = original
        if target in ('solve.sh', 'test_outputs.py'):
            assert original.count(b'/root/') == 3
            adapted = original.replace(b'/root/', b'/tmp/aeep-prefix/')
            assert adapted.replace(b'/tmp/aeep-prefix/', b'/root/') == original
        destination = PROTECTED / target
        if destination.exists():
            assert not destination.is_symlink() and destination.read_bytes() == adapted
        else:
            with destination.open('xb') as stream:
                stream.write(adapted)
            destination.chmod(0o444)
    PROTECTED.chmod(0o555)


def tool_files():
    refs = read(PYTEST_REVIEW)['files']
    files = {}
    for path in sorted(TOOLS.rglob('*')):
        assert not path.is_symlink()
        if path.is_file():
            assert sha(path) == refs[str(path)]
            files[str(path)] = refs[str(path)]
    assert files and set(files) == {key for key in refs if Path(key).is_relative_to(TOOLS)}
    return files


def spec_for(case):
    assert case in CASES
    return ExecutorSpec(id='skillsbench.prefix-cache.protected', capability='assessment.skillsbench.prefix-cache@1',
        kind='command', description='Protected upstream prefix cache calibration',
        side_effect='read', config={'argv': ['/usr/bin/python3', '-I', '-B', str(PROTECTED / 'calibrate.py'), case,
                                           str(TOOLS)], 'argv_literal': True, 'timeout_seconds': 42,
                                   'max_output_bytes': 32768, 'output': {'type': 'json'}})


def context(case, invocation_check=None):
    spec = spec_for(case)
    operation = GRANT + ':' + case
    return ExecutionContext(request=ActionRequest(action_id=operation, capability=spec.capability), spec=spec,
        estimate=spec.estimate, attempt=1, attempt_id=operation, approved_side_effect=spec.side_effect,
        invocation_check=invocation_check)


def preflight(review):
    assert utc_now() < datetime.fromisoformat(review['expires_at'])
    assert verification_source_digest(ROOT) == review['source_sha256']
    assert shutil.disk_usage(ROOT).free >= 51 * 1024**3
    assert all(sha(path) == digest for path, digest in review['pins'].items())
    assert tool_files() == review['tool_inventory']
    assert {str(path) for path in PROTECTED.iterdir()} == {name for name in review['pins'] if Path(name).parent == PROTECTED}
    env = checked_environment()
    assert content_digest(env) == review['environment_sha256']
    for case in CASES:
        assert content_digest(spec_for(case)) == review['executors'][case]
        argv, name = ContainerExecutor(env).command(context(case))
        assert argv[argv.index('--network') + 1] == 'none' and '--pull=never' in argv and '--read-only' in argv
        assert argv[argv.index('--user') + 1] == '65534:65534' and re.fullmatch('aeep-[a-f0-9]{32}', name)
        assert len([arg for arg in argv if arg.startswith('type=bind,') and arg.endswith(',readonly')]) == 3
    return env


def freeze():
    stage_files()
    env = checked_environment()
    assets = [Path(__file__).resolve(), HERE / 'candidate-review.json', HERE / 'selection.json',
              HERE / 'task-pack.json', HERE / 'local-rights-draft.json', HERE / 'calibrate.py', REFERENCE,
              PYTEST_REVIEW, DELEGATION, Path(env.container_runtime), *sorted(PROTECTED.iterdir())]
    fixture = {'case': 'reference', 'pytest_version': '8.4.1', 'pytest_exit': 0,
               'tests': [{'test_id': name, 'status': 'passed'} for name in sorted(names())]}
    assert classify('reference', fixture)['verified_upstream_binary_reward'] == 1
    fixture['tests'][0]['status'] = 'skipped'
    try:
        classify('reference', fixture)
    except AssertionError:
        pass
    else:
        raise AssertionError('skipped reference accepted')
    save(REVIEW, {'purpose': 'First protected original reference and rejection controls for Prefix Cache Replay.',
        'pins': {str(path): sha(path) for path in assets}, 'tool_inventory': tool_files(),
        'source_sha256': verification_source_digest(ROOT), 'image': env.container_image,
        'environment_sha256': content_digest(env), 'executors': {case: content_digest(spec_for(case)) for case in CASES},
        'cases': list(CASES), 'maximum_operations': 5, 'maximum_reserved_seconds': 275,
        'network': False, 'models': 0, 'cash_usd': '0', 'downloads': False, 'installs': False,
        'provider_transfer': False, 'resource_deletion': 'Only newly owned temporary test containers',
        'automatic_retries': False, 'comparisons': 'PAUSED',
        'expires_at': (utc_now() + timedelta(hours=12)).isoformat()})
    preflight(read(REVIEW))
    save(HERE / 'calibration-authority.json', {'review_sha256': sha(REVIEW),
        'standing_authority_sha256': sha(DELEGATION), 'first_attempt': True, 'model_dispatch': False})
    print(sha(REVIEW))


async def execute(identity):
    review = read(REVIEW)
    authority = read(HERE / 'calibration-authority.json')
    assert sha(REVIEW) == identity == authority['review_sha256'] and authority['first_attempt']
    assert authority['standing_authority_sha256'] == sha(DELEGATION) and not authority['model_dispatch']
    assert not (HERE / 'calibration-started.json').exists()
    env = preflight(review)
    save(HERE / 'calibration-started.json', {'review_sha256': identity, 'models': 0})
    scope = Scope(review_sha256=identity)
    ref = content_digest(scope)
    expiry = datetime.fromisoformat(review['expires_at'])
    request = RecipeMaterializationRequest(plan_id=GRANT, subject_digest=ref, recipe_digest=ref,
        environment_digest=ref, mapping_digest=ref, authorization_id=GRANT, definition_digests=[ref], seed=0)
    result = {'review_sha256': identity, 'passed': False, 'models': 0, 'cases': {}}
    with ReceiptStore(str(PRIVATE / 'calibration.sqlite3')) as store:
        repo = AssessmentRepository(store)
        assert repo.put('toolkit_skillsbench_prefix_reference_scope', ref, scope) == ref
        repo.approve_bundle(AssessmentAuthorization(authorization_id=GRANT, subject_digests=[ref],
            recipe_digests=[ref], environment_digests=[ref], allowed_destinations=['local'],
            remote_disclosure=False, expires_at=expiry,
            limits=AssessmentLimits(max_operations=5, max_model_turns=0, max_elapsed_seconds=275)),
            {ref: scope.model_dump(mode='json')})
        executor = ContainerExecutor(env)

        def authorize():
            repo.authorize(request)
            preflight(review)
            return identity

        try:
            for case in CASES:
                invocation = context(case, authorize)
                spec = invocation.spec
                op = invocation.attempt_id
                _, name = executor.command(invocation)
                assert container_absent(env, name)
                repo.reserve(request, op, AssessmentLimits(max_operations=1, max_elapsed_seconds=55), stage=case)
                started, clock = utc_now(), time.monotonic()
                facts, error = None, None
                try:
                    try:
                        raw = await executor.execute(invocation)
                    finally:
                        await executor.close()
                        assert container_absent(env, name), 'owned container cleanup unverified'
                    if raw.status.value != 'success':
                        error = raw.error_type or 'contained_program_failed'
                        raise RuntimeError(error)
                    try:
                        facts = classify(case, raw.output)
                    except AssertionError:
                        result['unexpected_observation'] = raw.output
                        raise
                    facts['cleanup_confirmed'] = True
                    result['cases'][case] = facts
                except Exception as exc:
                    error = error or type(exc).__name__
                    raise
                finally:
                    elapsed = time.monotonic() - clock
                    receipt = ExecutionReceipt(decision_id=op, action_id=op, capability=spec.capability,
                        executor_id=spec.id, executor_kind=spec.kind, status='success' if facts else 'failed',
                        started_at=started, ended_at=utc_now(), estimated=spec.estimate,
                        actual_resources=ResourceVector(latency_ms=elapsed * 1000),
                        execution_success=facts is not None, error_type=error,
                        metadata={'review_sha256': identity, 'observation': facts,
                                  'observed_resource_dimensions': ['latency_ms']})
                    store.save_receipt(receipt)
                    repo.finish_operation(op, elapsed_seconds=elapsed, resources=receipt.actual_resources)
                    save(HERE / f'{case}-receipt.json', receipt.model_dump(mode='json'))
            result['passed'] = True
        except Exception as exc:
            result['error_type'] = type(exc).__name__
        finally:
            ledger = repo.operation_ledger(GRANT)
            result['operations'] = len(ledger.operations)
            result['accounting_settled'] = all(row.elapsed_seconds is not None for row in ledger.operations)
            save(HERE / 'calibration-ledger.json', ledger.model_dump(mode='json'))
            save(HERE / 'calibration-result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}))
    return result['passed'] and result['accounting_settled']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--execute-delegated')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    else:
        raise SystemExit(not asyncio.run(execute(args.execute_delegated)))
