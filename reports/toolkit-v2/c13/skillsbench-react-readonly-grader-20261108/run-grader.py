"""Use the verified React parent with separately pinned read-only grader mounts."""

import argparse
import asyncio
import json
import re
import runpy
import shutil
import stat
import time
from datetime import datetime, timedelta
from pathlib import Path

from aeep.assessment.containment import ContainerExecutor, container_name
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeDefinition,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREVIOUS = HERE.parent / 'skillsbench-react-ordinary-carrier-20261108'
WORK = ROOT / '.aeep' / HERE.name
PREVIOUS_WORK = WORK.with_name(PREVIOUS.name)
PROTECTED = WORK / 'protected'
CONTEXT = PREVIOUS_WORK / 'context'
REVIEW = HERE / 'operation-review.json'
GRANT = 'skillsbench-react-readonly-grader-20261108'
RESERVE = 50 * 1024**3

old = runpy.run_path(str(PREVIOUS / 'run-carrier.py'))
stage = old['stage']
prior = stage.read(PREVIOUS / 'runtime-review.json')


class Scope(StrictModel):
    review_sha256: str
    source_sha256: str


def inventory():
    paths = {}
    for root in (CONTEXT / 'python', CONTEXT / 'browser', PROTECTED):
        assert root.resolve() == root
        for path in (root, *sorted(root.rglob('*'))):
            assert not path.is_symlink() and path.resolve() == path
            mode = stat.S_IMODE(path.stat().st_mode)
            if path.is_dir():
                assert mode & 0o005 == 0o005
                paths[str(path)] = {'mode': mode}
            else:
                assert path.is_file() and mode & 0o004
                paths[str(path)] = {'mode': mode, 'sha256': stage.sha(path)}
    return paths


def substitute(source, old_text, new_text):
    assert source.count(old_text) == 1
    return source.replace(old_text, new_text)


def retain_file(path, data):
    if path.exists():
        assert not path.is_symlink() and path.read_bytes() == data
        assert stat.S_IMODE(path.stat().st_mode) == 0o444
        return
    with path.open('xb') as stream:
        stream.write(data)
    path.chmod(0o444)


def stage_files():
    WORK.mkdir(mode=0o700, exist_ok=True)
    PROTECTED.mkdir(exist_ok=True)
    original = CONTEXT / 'protected'
    for name in ('test_outputs.py', 'conftest.py', 'repository_suite_native_capture.py', 'pins.json'):
        retain_file(PROTECTED / name, (original / name).read_bytes())
    driver = substitute((original / 'verifier-driver.py').read_text(),
                        "Path('/opt/aeep-react-reference')", 'Path(__file__).parent')
    driver = substitute(driver, "'/opt/aeep-react-browser'", repr(str(CONTEXT / 'browser')))
    grader = substitute((original / 'grade.py').read_text(),
                        "Path('/opt/aeep-react-reference')", 'Path(__file__).parent')
    grader = substitute(grader, '    sys.path.append(sys.argv[1])',
                        f'    sys.path.extend([sys.argv[1], {str(CONTEXT / "python")!r}])')
    for name, source in (('verifier-driver.py', driver), ('grade.py', grader)):
        compile(source, name, 'exec')
        retain_file(PROTECTED / name, source.encode())
    PROTECTED.chmod(0o555)


def freeze():
    assert not (HERE / 'started.json').exists()
    assert verification_source_digest(ROOT) == prior['source_sha256']
    assert shutil.disk_usage(ROOT).free >= RESERVE + 1024**3
    assert old['image'](prior, prior['parent_id']) == prior['parent']
    assert content_digest(stage.inventory()) == prior['context_sha256']
    stage_files()
    assets = inventory()
    inventory_path = WORK / 'mount-inventory.json'
    if inventory_path.exists():
        assert stage.read(inventory_path) == assets
    else:
        stage.write(inventory_path, assets)
    environment = AssessmentEnvironment(
        environment_id='react-readonly-protected-20261108', kind='container',
        identity={'mount_inventory_sha256': content_digest(assets)},
        container_image=prior['parent_id'], container_runtime=prior['docker'][0],
        container_socket=prior['docker'][-1].removeprefix('unix://'),
        read_only_roots=[str(CONTEXT / 'python'), str(CONTEXT / 'browser'), str(PROTECTED)],
        network=False, cpu_count=prior['cpu'], memory_mb=prior['memory_mib'],
        process_limit=prior['pids'], container_tmpfs_mb=prior['scratch_mib'],
    )
    spec = ExecutorSpec(
        id='skillsbench.react.grader', capability='assessment.skillsbench.react@1', kind='command',
        description='Original React verifier on a bounded source artifact',
        side_effect='read', config={
            'argv': ['/usr/bin/python3', '-I', '-B', str(PROTECTED / 'grade.py'), str(ROOT / 'src')],
            'argv_literal': True, 'stdin_json': True, 'timeout_seconds': 60, 'max_output_bytes': 32768,
            'output': {'type': 'json'},
        },
    )
    previous_recipe = stage.read(PREVIOUS_WORK / 'react-recipe.json')
    assert content_digest(RecipeDefinition.model_validate(previous_recipe)) == stage.read(
        PREVIOUS / 'recipe-preparation.json')['recipe_digest']
    previous_recipe['extension']['grader'] = spec.model_dump(mode='json')
    recipe = RecipeDefinition.model_validate(previous_recipe)
    stage.write(WORK / 'react-recipe.json', recipe.model_dump(mode='json'))
    (WORK / 'react-recipe.json').chmod(0o400)
    stage.write(HERE / 'environment.json', environment.model_dump(mode='json'))
    stage.write(HERE / 'grader-spec.json', spec.model_dump(mode='json'))
    pins = {
        str(path): stage.sha(path) for path in (
            Path(__file__), PREVIOUS / 'runtime-review.json', PREVIOUS / 'run-carrier.py',
            PREVIOUS / 'stage-carrier.py', PREVIOUS / 'grade.py', PREVIOUS / 'source-verification.json',
            PREVIOUS / 'runtime-ledger.json', PREVIOUS / 'runtime-result.json',
            HERE / 'export-observation.json', HERE / 'environment.json', HERE / 'grader-spec.json',
            WORK / 'mount-inventory.json', WORK / 'react-recipe.json', PREVIOUS_WORK / 'controls.json',
            Path(prior['docker'][0]), Path(prior['docker'][2]) / 'config.json',
        )
    }
    stage.write(REVIEW, {
        'purpose': 'Four previously unstarted protected checks through the ordinary executor on the original local React image.',
        'failed_parent_review_sha256': stage.sha(PREVIOUS / 'runtime-review.json'),
        'source_sha256': prior['source_sha256'], 'image': prior['parent_id'],
        'mount_inventory_sha256': content_digest(assets), 'mount_inventory_entries': len(assets),
        'recipe_digest': content_digest(recipe), 'grader_spec_digest': content_digest(spec),
        'environment_digest': content_digest(environment), 'pins': pins,
        'maximum_operations': 4, 'maximum_reserved_seconds': 300,
        'scratch_mib': prior['scratch_mib'], 'minimum_free_gib': 50, 'cases': [
            'reference', 'incomplete', 'destructive', 'outside_source',
        ],
        'models': 0, 'cash_usd': '0', 'downloads': False, 'builds': False, 'network': False,
        'provider_transfer': False, 'existing_resource_deletion': False, 'automatic_retries': False,
        'comparisons': 'PAUSED', 'expires_at': (utc_now() + timedelta(hours=12)).isoformat(),
    })


def control_request(controls, row, spec, identity):
    data = {'examples': [{'input': controls['input'], 'output': row['artifact'],
        'expected': {'task_archive_sha256': controls['input']['task_archive_sha256']}}]}
    return ExecutionContext(
        request=ActionRequest(action_id=identity, capability=spec.capability, input=data),
        spec=spec, estimate=spec.estimate, attempt=1, attempt_id=identity, approved_side_effect=spec.side_effect,
    )


def assert_command(executor, context):
    argv, name = executor.command(context)
    roots = {str(ROOT / 'src'), *executor.environment.read_only_roots}
    assert argv[argv.index('--network')+1] == 'none' and '--pull=never' in argv
    assert '--read-only' in argv and argv[argv.index('--user')+1] == '65534:65534'
    assert argv[argv.index('--tmpfs')+1] == '/tmp:rw,noexec,nosuid,nodev,size=160m'
    assert set(item for item in argv if item.startswith('type=bind,')) == {
        f'type=bind,src={root},dst={root},readonly' for root in roots
    }
    assert name == container_name(context.attempt_id)
    return name


def preflight(identity):
    review = stage.read(REVIEW)
    assert stage.sha(REVIEW) == identity and datetime.fromisoformat(review['expires_at']) > utc_now()
    assert not (HERE / 'started.json').exists()
    assert verification_source_digest(ROOT) == review['source_sha256']
    assert shutil.disk_usage(ROOT).free >= RESERVE + 512 * 1024**2
    assert all(stage.sha(Path(name)) == digest for name, digest in review['pins'].items())
    assert content_digest(inventory()) == review['mount_inventory_sha256']
    source = stage.read(PREVIOUS / 'source-verification.json')
    assert len(source['checks']) == 13 and all(row['exit_code'] == 0 for row in source['checks'])
    assert source['source_sha256'] == review['source_sha256']
    assert old['image'](prior, review['image']) == prior['parent']
    evidence = stage.read(PREVIOUS / 'runtime-result.json')
    assert evidence['accounting_settled'] and evidence['operations'] == 2 and not evidence['observations']
    environment = AssessmentEnvironment.model_validate_json((HERE / 'environment.json').read_bytes())
    spec = ExecutorSpec.model_validate_json((HERE / 'grader-spec.json').read_bytes())
    assert content_digest(environment) == review['environment_digest']
    assert content_digest(spec) == review['grader_spec_digest']
    recipe = RecipeDefinition.model_validate_json((WORK / 'react-recipe.json').read_bytes())
    assert content_digest(recipe) == review['recipe_digest']
    assert content_digest(recipe.extension.grader) == review['grader_spec_digest']
    controls = stage.read(PREVIOUS_WORK / 'controls.json')
    assert [row['name'] for row in controls['variants']] == review['cases']
    guest = runpy.run_path(str(PROTECTED / 'grade.py'))
    for row in controls['variants']:
        context = control_request(controls, row, spec, GRANT + ':' + row['name'])
        assert_command(ContainerExecutor(environment), context)
        try:
            from aeep.assessment.repository_suites import decode_patch
            guest['checked_changes'](row['artifact'], controls['input']['task_archive_sha256'],
                                     stage.read(PROTECTED / 'pins.json')['app_files'], decode_patch)
        except ValueError:
            assert row['failure_code'] == 'output_contract'
        else:
            assert row['failure_code'] != 'output_contract'
    return review, environment, spec, controls


def missing(name):
    result = old['docker'](prior, 'ps', '-aq', '--filter', 'name=^/' + name + '$')
    return result.returncode == 0 and not result.stdout.strip()


async def execute(identity, review, environment, spec, controls):
    scope = Scope(review_sha256=identity, source_sha256=review['source_sha256'])
    digest = content_digest(scope)
    request = RecipeMaterializationRequest(
        plan_id=GRANT, subject_digest=digest, recipe_digest=digest, mapping_digest=digest,
        environment_digest=digest, authorization_id=GRANT, definition_digests=[digest], seed=0,
    )
    grant = AssessmentAuthorization(
        authorization_id=GRANT, subject_digests=[digest], recipe_digests=[digest],
        environment_digests=[digest], allowed_destinations=['local'], remote_disclosure=False,
        limits=AssessmentLimits(max_operations=4, max_elapsed_seconds=300),
        expires_at=datetime.fromisoformat(review['expires_at']),
    )
    outcome = {'review_sha256': identity, 'models': 0, 'comparisons': 'PAUSED', 'observations': {}, 'passed': False}
    stage.write(HERE / 'started.json', {'review_sha256': identity})
    with ReceiptStore(prior['ledger']) as store:
        repo = AssessmentRepository(store)
        assert repo.put('toolkit_react_readonly_grader_scope', digest, scope) == digest
        repo.approve_bundle(grant, {digest: scope.model_dump(mode='json')})
        failure = None
        try:
            for row in controls['variants']:
                failure = None
                name = row['name']
                operation = GRANT + ':' + name
                executor = ContainerExecutor(environment)
                context = control_request(controls, row, spec, operation)

                def invocation():
                    repo.authorize(request)
                    assert datetime.fromisoformat(review['expires_at']) > utc_now()
                    assert shutil.disk_usage(ROOT).free >= RESERVE
                    assert verification_source_digest(ROOT) == review['source_sha256']
                    assert content_digest(inventory()) == review['mount_inventory_sha256']
                    return identity

                container = assert_command(executor, context)
                assert missing(container)
                context.invocation_check = invocation
                repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=75), stage=name)
                clock, started = time.perf_counter(), utc_now()
                facts, failure = None, None
                try:
                    raw = await executor.execute(context)
                    assert raw.status.value == 'success', raw.error_type or 'contained_program_failed'
                    assert raw.output == {'valid': [row['valid']], 'failure_codes': [row['failure_code']]}, 'grade_mismatch'
                    assert missing(container), 'container_cleanup_unverified'
                    facts = {'valid': row['valid'], 'failure_code': row['failure_code'],
                             'binary_score': int(row['valid']), 'owned_container_removed': True}
                except Exception as error:
                    label = str(error)
                    failure = label if re.fullmatch(r'[A-Za-z_]{1,60}', label) else type(error).__name__
                    raise
                finally:
                    await executor.close()
                    elapsed = time.perf_counter() - clock
                    receipt = ExecutionReceipt(
                        decision_id=operation, action_id=operation, capability=spec.capability,
                        executor_id=spec.id, executor_kind=spec.kind, status='success' if facts else 'failed',
                        started_at=started, ended_at=utc_now(), estimated=spec.estimate,
                        actual_resources=ResourceVector(latency_ms=elapsed * 1000), execution_success=facts is not None,
                        error_type=failure, metadata={'review_sha256': identity, 'observation': facts,
                                                     'observed_resource_dimensions': ['latency_ms']},
                    )
                    store.save_receipt(receipt)
                    repo.finish_operation(operation, elapsed_seconds=elapsed, resources=receipt.actual_resources)
                    stage.write(HERE / (name + '-receipt.json'), receipt.model_dump(mode='json'))
                outcome['observations'][name] = facts
            outcome['passed'] = True
        except Exception:
            outcome['error_type'] = failure or 'pre_dispatch_check_failed'
        finally:
            ledger = repo.operation_ledger(GRANT)
            outcome['accounting_settled'] = all(row.elapsed_seconds is not None for row in ledger.operations)
            outcome['operations'] = len(ledger.operations)
            stage.write(HERE / 'ledger.json', ledger.model_dump(mode='json'))
            stage.write(HERE / 'result.json', outcome)
    print(json.dumps(outcome))
    return outcome['passed'] and outcome['accounting_settled']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--freeze', action='store_true')
    flags.add_argument('--preflight')
    flags.add_argument('--execute-approved')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    identity = stage.sha(REVIEW) if args.freeze else args.preflight or args.execute_approved
    review, environment, spec, controls = preflight(identity)
    if args.execute_approved:
        assert stage.read(HERE / 'approval.json') == {'approved': True, 'review_sha256': identity}
        raise SystemExit(not asyncio.run(execute(identity, review, environment, spec, controls)))
    print(json.dumps({'passed': True, 'review_sha256': identity, 'build': False, 'containers': 0, 'models': 0}))
