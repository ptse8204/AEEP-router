"""Import one local grader carrier and exercise the canonical pre-turn payloads offline."""

import argparse
import asyncio
import base64
import hashlib
import json
import re
import runpy
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from aeep.assessment.containment import ContainerExecutor, container_name
from aeep.assessment.extensions import grader_results, require_environment
from aeep.assessment.models import (
    AssessmentAuthorization, AssessmentEnvironment, AssessmentLimits, RecipeDefinition,
    RecipeMaterializationRequest, content_digest,
)
from aeep.assessment.recipes import faulty_outputs
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutorSpec, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
stage = runpy.run_path(str(HERE / 'stage-self-contained-grader.py'))
helper = stage['helper']
receipt_helper = runpy.run_path(str(HERE / 'continue-worker-runtime.py'))
ROOT, WORK, read, sha, save = (stage[key] for key in ('ROOT', 'WORK', 'read', 'sha', 'save'))
GRADER = HERE.parent / 'skillsbench-react-readonly-grader-20261108'
PRIVATE = ROOT / '.aeep' / GRADER.name
ARCHIVE = stage['TARGET']
REVIEW = HERE / 'self-contained-operation-review.json'
TAG = 'aeep-skillsbench-react:sealed-amd64-20261108'
GRANT = 'skillsbench-react-sealed-carrier-20261108'
MAX_OPERATIONS, MAX_SECONDS = 9, 640


class Scope(StrictModel):
    review_sha256: str


def inputs():
    prior = RecipeDefinition.model_validate(read(PRIVATE / 'react-recipe.json'))
    assert prior.extension is not None and prior.extension.schema_version.endswith('.v6')
    spec = prior.extension.grader
    config = spec.config | {'argv': ['/usr/bin/python3', '-I', '-B',
        '/opt/aeep-react-reference/grade.py', str(ROOT / 'src')]}
    recipe = RecipeDefinition.model_validate(prior.model_dump(mode='json') | {
        'extension': prior.extension.model_dump(mode='json') | {
            'grader': spec.model_dump(mode='json') | {'config': config},
        },
    })
    previous = read(ROOT / '.aeep' / helper['CARRIER'].name / 'controls.json')
    assert previous['input']['task_archive_sha256'] == read(HERE / 'managed-definition-preflight.json')['public_archive_sha256']
    known = previous['variants'][0]
    assert known['name'] == 'reference'
    return recipe, previous['input'], known['artifact']


def environment(image_id, review):
    return AssessmentEnvironment(
        environment_id='react-sealed-protected-20261108', kind='container',
        identity={'archive_sha256': review['archive_sha256']}, container_image=image_id,
        container_runtime=helper['DOCKER'][0], container_socket=helper['DOCKER'][-1].removeprefix('unix://'),
        network=False, cpu_count=4, memory_mb=4096, process_limit=384, container_tmpfs_mb=160,
    )


def import_spec():
    return ExecutorSpec(
        id='skillsbench.react.carrier-import', capability='toolkit.upstream-engineering@1', kind='command',
        description='Import one immutable local offline grader root filesystem', side_effect='write',
        config={'argv': [*helper['DOCKER'], 'image', 'import', '--platform', 'linux/amd64',
                         '--change', 'USER 65534:65534', '--change', 'ENV PATH=/usr/local/bin:/usr/bin:/bin',
                         str(ARCHIVE), TAG],
                'argv_literal': True, 'inherit_env': False, 'env': helper['ENV'], 'cwd': str(WORK),
                'timeout_seconds': 140, 'max_output_bytes': 8192, 'output': {'type': 'text'}},
    )


def check_stage():
    record = read(HERE / 'self-contained-staging.json')
    assert record['passed'] and not record['source_container_started']
    assert ARCHIVE.stat().st_size == record['archive_bytes'] and sha(ARCHIVE) == record['archive_sha256']
    stage['inspect_source'](record['source_container'])
    assert shutil.disk_usage(ROOT).free >= 57 * 1024**3
    assert helper['docker']('system', 'df', '--format', '{{.Type}} {{.Size}}').returncode == 0
    assert helper['image'](TAG) is None
    assert verification_source_digest(ROOT) == helper['OLD']['source_sha256']
    return record


def freeze():
    record = check_stage()
    recipe, value, good = inputs()
    extension = recipe.extension
    assert not extension.independent_fixtures and not extension.transformed_fixtures
    assert len(faulty_outputs(good)) == 5 and len(extension.fault_outputs) == 1
    assert extension.reference.config['timeout_seconds'] == 30 and extension.grader.config['timeout_seconds'] == 60
    example = {'input': value, 'output': good, 'expected': {'task_archive_sha256': value['task_archive_sha256']}}
    context = ExecutionContext(request=ActionRequest(action_id='preflight', capability=extension.grader.capability,
                                                     input={'examples': [example]}), spec=extension.grader,
                               estimate=extension.grader.estimate, attempt=1, approved_side_effect=extension.grader.side_effect)
    env = environment(helper['OLD']['parent_id'], record)
    require_environment(recipe, env)
    argv, _name = ContainerExecutor(env).command(context)
    mounts = [item for item in argv if item.startswith('type=bind,')]
    assert len(mounts) == 1 and '/src,' in mounts[0]
    paths = [Path(__file__).resolve(), HERE / 'stage-self-contained-grader.py', HERE / 'self-contained-staging.json',
             HERE / 'worker-runtime.py', HERE / 'continue-worker-runtime.py', HERE / 'managed-carrier-boundary.json',
             HERE / 'managed-continuation-result.json', PRIVATE / 'react-recipe.json',
             ROOT / '.aeep' / helper['CARRIER'].name / 'controls.json',
             helper['CARRIER'] / 'runtime-review.json', Path(helper['DOCKER'][0]),
             Path(helper['DOCKER'][2]) / 'config.json']
    save(REVIEW, {
        'scope': 'One local archive import and the real reference, known-good and six pre-turn fault payloads.',
        'pins': {str(path): sha(path) for path in paths}, 'archive_sha256': record['archive_sha256'],
        'archive_bytes': record['archive_bytes'], 'image_tag': TAG, 'source_sha256': helper['OLD']['source_sha256'],
        'recipe_digest': content_digest(recipe), 'input_digest': content_digest(value),
        'import_spec_digest': content_digest(import_spec()), 'requires_no_extra_host_roots': True,
        'maximum_operations': MAX_OPERATIONS, 'maximum_reserved_seconds': MAX_SECONDS, 'minimum_free_gib': 50,
        'models': 0, 'cash_usd': '0', 'network': False, 'downloads': False, 'provider_transfer': False,
        'keep_existing_resources': True, 'automatic_retries': False, 'comparisons': 'PAUSED',
        'expires_at': (utc_now() + timedelta(hours=14)).isoformat(),
    })
    print(sha(REVIEW))


async def execute(identity):
    review = read(REVIEW)
    assert sha(REVIEW) == identity
    assert read(HERE / 'self-contained-approval.json') == {'approved': True, 'review_sha256': identity}
    assert not (HERE / 'self-contained-started.json').exists()
    expires = datetime.fromisoformat(review['expires_at'])
    assert utc_now() < expires and check_stage()['archive_sha256'] == review['archive_sha256']
    assert all(sha(Path(path)) == expected for path, expected in review['pins'].items())
    recipe, value, known = inputs()
    extension = recipe.extension
    assert content_digest(recipe) == review['recipe_digest'] and content_digest(value) == review['input_digest']
    spec = import_spec()
    assert content_digest(spec) == review['import_spec_digest']
    scope = Scope(review_sha256=identity)
    digest = content_digest(scope)
    request = RecipeMaterializationRequest(plan_id=GRANT, subject_digest=digest, recipe_digest=digest,
        environment_digest=digest, mapping_digest=digest, authorization_id=GRANT, definition_digests=[digest], seed=0)
    grant = AssessmentAuthorization(authorization_id=GRANT, subject_digests=[digest], recipe_digests=[digest],
        environment_digests=[digest], allowed_destinations=['local'], remote_disclosure=False,
        limits=AssessmentLimits(max_operations=MAX_OPERATIONS, max_elapsed_seconds=MAX_SECONDS), expires_at=expires)
    save(HERE / 'self-contained-started.json', {'review_sha256': identity})
    facts = {'review_sha256': identity, 'passed': False, 'models': 0, 'comparisons': 'PAUSED', 'observations': {}}
    with ReceiptStore(helper['OLD']['ledger']) as store:
        repo = AssessmentRepository(store)
        assert repo.put('toolkit_react_sealed_scope', digest, scope) == digest
        repo.approve_bundle(grant, {digest: scope.model_dump(mode='json')})

        async def operation(name, current, executor, payload, reservation, check):
            op = GRANT + ':' + name
            container = container_name(op) if isinstance(executor, ContainerExecutor) else None
            if container:
                assert helper['absent'](container)
            repo.reserve(request, op, AssessmentLimits(max_operations=1, max_elapsed_seconds=reservation), stage=name)
            started, clock = utc_now(), time.perf_counter()
            observation, failure = None, None

            def authorize():
                repo.authorize(request)
                assert utc_now() < expires and shutil.disk_usage(ROOT).free >= stage['MIN_FREE']
                assert verification_source_digest(ROOT) == review['source_sha256']
                assert all(sha(Path(path)) == expected for path, expected in review['pins'].items())
                if name == 'import':
                    assert sha(ARCHIVE) == review['archive_sha256'] and helper['image'](TAG) is None
                return identity

            try:
                raw = await executor.execute(ExecutionContext(
                    request=ActionRequest(action_id=op, capability=current.capability, input=payload),
                    spec=current, estimate=current.estimate, attempt=1, attempt_id=op,
                    approved_side_effect=current.side_effect, invocation_check=authorize,
                ))
                if raw.status.value != 'success':
                    failure = raw.error_type or 'command_failed'
                    raise RuntimeError(failure)
                if container:
                    assert helper['absent'](container), 'owned_container_cleanup_unverified'
                observation = check(raw)
                return raw.output, observation
            except Exception as error:
                failure = failure or type(error).__name__
                raise
            finally:
                await executor.close()
                elapsed = time.perf_counter() - clock
                receipt = receipt_helper['make_receipt'](op, current, started, elapsed, identity, observation, failure)
                store.save_receipt(receipt)
                repo.finish_operation(op, elapsed_seconds=elapsed, resources=receipt.actual_resources)
                save(HERE / ('self-contained-' + name + '-receipt.json'), receipt.model_dump(mode='json'))

        try:
            def verify_import(raw):
                image = helper['image'](TAG)
                assert image and image['platform'] == 'linux/amd64' and image['user'] == '65534:65534'
                assert not image['volumes'] and len(image['layers']) == 1
                emitted = raw.output.strip()
                assert re.fullmatch(r'sha256:[a-f0-9]{64}', emitted)
                metadata = helper['docker']('image', 'inspect', '--format', '{{json .Descriptor}}', TAG)
                assert metadata.returncode == 0
                descriptor = json.loads(metadata.stdout) or {}
                assert emitted in {image['id'], descriptor.get('digest'),
                                   descriptor.get('annotations', {}).get('config.digest')}
                return image

            _, image = await operation('import', spec, CommandExecutor(), {}, 150, verify_import)
            facts['image'] = image
            env = environment(image['id'], review)
            require_environment(recipe, env)
            save(HERE / 'self-contained-environment.json', env.model_dump(mode='json'))
            recipe_path = WORK / 'sealed-react-recipe.json'
            save(recipe_path, recipe.model_dump(mode='json'))
            recipe_path.chmod(0o400)

            def verify_reference(raw):
                assert raw.output == {'outputs': [known]}
                payload = base64.b64decode(known['patch_b64'], validate=True)
                return {'output_sha256': hashlib.sha256(payload).hexdigest(), 'owned_container_removed': True}

            reply, reference = await operation('reference', extension.reference, ContainerExecutor(env),
                                               {'inputs': [value]}, 35, verify_reference)
            facts['observations']['reference'] = reference
            good, = reply['outputs']
            outputs = [good, *faulty_outputs(good), *extension.fault_outputs]
            truth = {'task_archive_sha256': value['task_archive_sha256']}
            for index, output in enumerate(outputs):
                def grade(raw):
                    result, = grader_results(raw.output, extension, 1)
                    expected = index == 0
                    expected_code = None if expected else 'upstream_rejected' if index == len(outputs)-1 else 'output_contract'
                    assert result.valid is expected and (result.detail or None) == expected_code
                    return {'binary_score': int(result.valid), 'failure_code': result.detail or None,
                            'owned_container_removed': True}

                name = 'grader-probe-' + str(index)
                data = {'examples': [{'input': value, 'output': output, 'expected': truth}]}
                _, observed = await operation(name, extension.grader, ContainerExecutor(env), data, 65, grade)
                facts['observations'][name] = observed
            facts['passed'] = True
        except Exception as error:
            facts['error_type'] = type(error).__name__
        finally:
            ledger = repo.operation_ledger(GRANT)
            facts['operations'] = len(ledger.operations)
            facts['accounting_settled'] = all(row.elapsed_seconds is not None for row in ledger.operations)
            save(HERE / 'self-contained-ledger.json', ledger.model_dump(mode='json'))
            save(HERE / 'self-contained-result.json', facts)
    print(json.dumps(facts))
    return facts['passed'] and facts['accounting_settled']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--freeze', action='store_true')
    flags.add_argument('--execute-approved')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    else:
        raise SystemExit(not asyncio.run(execute(args.execute_approved)))
