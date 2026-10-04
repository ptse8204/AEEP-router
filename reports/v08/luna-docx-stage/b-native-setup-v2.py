"""Prepare or execute one exact zero-turn B project setup on the existing grant."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import signal
import sys
import tempfile
import time
from pathlib import Path

from aeep.assessment.identity import runtime_dependencies, verify_dependencies
from aeep.assessment.models import (
    AssessmentEnvironment,
    AssessmentLimits,
    AssessmentScopeAmendment,
    AssessmentSubject,
    ConformanceProbeRequest,
    RecipeRuntimeBinding,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.assessment.workbook import workbook_recipe
from aeep.hosts.workers import ManagedWorkerBinding, validate_worker_pair
from aeep.models import ManagedHostArtifact, StrictModel
from aeep.router import Router

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = '449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad'
PRODUCER = OUT / 'b-native-workbook-producer-final.py'
PRODUCER_SHA = '4d5db1fd761882f90bbaff5d1a6c392e2bab185a248f4a981399f95ee8aa539d'
OLD_PROFILES = ROOT / 'reports/v08/original-three-way-profile/current-composed-profiles.json'
REVIEW = OUT / 'b-native-setup-v2-review.json'
MANIFEST = ROOT / '.aeep/live-review-v3/aeep.json'
MANIFEST_SHA = '091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb'
CANONICAL_DB = ROOT / '.aeep/live-review-v3/aeep.sqlite3'
PROJECT = Path(tempfile.gettempdir()).resolve() / 'aeep-b-native-final-20261003'


class SetupDefinition(StrictModel):
    source_digest: str
    project: str
    producer_sha256: str
    worker_documents: dict[str, dict]
    maximum_seconds: int = 120


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def store_identity():
    if MANIFEST.is_symlink() or sha(MANIFEST) != MANIFEST_SHA:
        raise ValueError('exact canonical manifest changed')
    configured = Path(json.loads(MANIFEST.read_text())['database'])
    if configured != CANONICAL_DB or configured.is_symlink():
        raise ValueError('canonical store target changed')
    stat = CANONICAL_DB.stat()
    return {'manifest': str(MANIFEST), 'manifest_sha256': MANIFEST_SHA,
            'database': str(CANONICAL_DB), 'device': stat.st_dev, 'inode': stat.st_ino}


def preflight():
    store_identity()
    if verification_source_digest(ROOT) != SOURCE or sha(PRODUCER) != PRODUCER_SHA:
        raise ValueError('reviewed source/producer changed')
    if PROJECT.exists() or not PROJECT.parent.is_dir():
        raise ValueError('fresh exact external project required; never reset or reuse')
    if shutil.disk_usage(PROJECT.parent).free < 51 * 1024**3:
        raise ValueError('50 GiB reserve plus 1 GiB setup allowance required')


def prepare():
    preflight()
    if REVIEW.exists():
        raise ValueError('preserve existing setup review')
    old = json.loads(OLD_PROFILES.read_text())['pair']
    workers = {}
    for role, name in (('control', 'discovery'), ('treatment', 'aeep')):
        value = copy.deepcopy(old['treatment']['config']['managed_worker'])
        value['worker_id'] = 'b-luna-' + name + '-20261003'
        value['credential_volume'] = old[role]['config']['managed_worker']['credential_volume']
        workers[role] = ManagedWorkerBinding.model_validate(value)
    validate_worker_pair(workers['control'], workers['treatment'])
    router = Router.from_manifest(MANIFEST)
    repo = AssessmentRepository(router.store)
    try:
        definitions = {}
        def put(kind, value, identity=None):
            digest = content_digest(value)
            repo.put(kind, identity or digest, value)
            definitions[digest] = value.model_dump(mode='json')
            return digest
        subject = AssessmentSubject(kind='command', location=str(PRODUCER),
            dependency_digests={'producer': PRODUCER_SHA},
            description='Original B task-only AEEP intervention; native project setup only.')
        sd = put('subject', subject, subject.subject_id)
        recipe = workbook_recipe()
        rd = put('recipe', recipe, recipe.recipe_id)
        environment = AssessmentEnvironment(environment_id='b-native-setup-final-20261003',
            kind='trusted_local', identity={'purpose': 'fresh local task project setup; no task execution'})
        ed = put('environment', environment)
        definition = SetupDefinition(source_digest=SOURCE, project=str(PROJECT),
            producer_sha256=PRODUCER_SHA,
            worker_documents={role: worker.model_dump(mode='json') for role, worker in workers.items()})
        md = put('b_native_setup', definition)
        for worker in workers.values():
            put('worker_binding', worker, worker.digest())
        deps = runtime_dependencies() | {str(path): sha(path) for path in (Path(__file__).resolve(), PRODUCER, OLD_PROFILES, MANIFEST)}
        put('probe_runtime', RecipeRuntimeBinding(dependencies=deps))
        request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v2',
            operation='worker_inspection', subject_digest=sd, recipe_digest=rd,
            mapping_digest=md, environment_digest=ed, authorization_id='onboarding',
            definition_digests=list(definitions), worker_digest=workers['treatment'].digest(),
            executable_dependencies=deps)
        put('conformance_request', request, request.plan_id)
        original = repo.get('authorization', 'onboarding')
        amendment = AssessmentScopeAmendment(authorization_id='onboarding',
            authorization_digest=content_digest(original), subject_digests=[sd],
            recipe_digests=[rd], environment_digests=[ed], reviewed_digests=list(definitions))
        value = {'canonical_store': store_identity(), 'source_digest': SOURCE, 'authority': 'September 25/27 standing finite setup delegation',
            'purpose': 'one fresh protected native workbook project and callback declarations; no task/model/worker execution',
            'request': request.model_dump(mode='json'), 'request_digest': content_digest(request),
            'definitions': definitions, 'amendment': amendment.model_dump(mode='json'),
            'project': str(PROJECT), 'max_operations': 1, 'max_seconds': 120,
            'max_model_turns': 0, 'max_cash_usd': 0, 'max_project_bytes': 1024**3,
            'execution_authorized': False}
        with REVIEW.open('x') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
        print(json.dumps({'review': str(REVIEW), 'sha256': sha(REVIEW), 'request': request.plan_id}))
    finally:
        router.store.close()


def execute(review_sha):
    preflight()
    if sha(REVIEW) != review_sha:
        raise ValueError('exact reviewed setup hash required')
    validation = ROOT / 'reports/v08/luna-b-three-role-validation-20261003'
    for stem in ('04-compileall-retry', '05-schema-check-retry', '06-focused-retry',
                 '07-policy', '08-ruff', '09-mypy', '10-pytest', '11-coverage-run',
                 '12-coverage-report', '13-coverage-json', '14-critical-coverage', '15-assessment-coverage'):
        log = (validation / (stem + '.log')).read_text()
        if '\nEXIT_CODE: 0\n' not in log or ('VERIFICATION_SOURCE_DIGEST_AFTER: ' + SOURCE) not in log:
            raise ValueError('required frozen-source validation incomplete: ' + stem)
    review = json.loads(REVIEW.read_text())
    if review['canonical_store'] != store_identity():
        raise ValueError('reviewed canonical store identity changed')
    request = ConformanceProbeRequest.model_validate(review['request'])
    if review['source_digest'] != SOURCE or content_digest(request) != review['request_digest']:
        raise ValueError('setup request differs')
    definition = SetupDefinition.model_validate(review['definitions'][request.mapping_digest])
    if definition.project != str(PROJECT) or definition.producer_sha256 != PRODUCER_SHA or definition.maximum_seconds != 120:
        raise ValueError('setup target differs')
    with (OUT / 'b-native-setup-v2-started.json').open('x') as stream:
        json.dump({'review_sha256': review_sha, 'request_id': request.plan_id}, stream)
    router = Router.from_manifest(MANIFEST)
    repo = AssessmentRepository(router.store)
    operation = request.plan_id + ':b_native_project_setup'
    reserved = False
    result = {'request_id': request.plan_id, 'operation_id': operation,
        'source_digest': SOURCE, 'review_sha256': review_sha, 'project': str(PROJECT),
        'model_turns': 0, 'task_calls': 0, 'worker_launches': 0, 'setup_complete': False}
    started = time.monotonic()
    project_router = None
    def timeout(*_):
        raise TimeoutError('bounded native project setup deadline')
    previous = signal.signal(signal.SIGALRM, timeout)
    try:
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']), review['definitions'])
        repo.authorize(request)
        verify_dependencies(request.executable_dependencies)
        repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_model_turns=0,
            max_elapsed_seconds=120, max_cash_usd=0), stage='b_native_project_setup')
        reserved = True
        remaining = 120 - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError('native setup deadline exhausted before setup')
        signal.setitimer(signal.ITIMER_REAL, remaining)
        module_spec = importlib.util.spec_from_file_location('aeep_b_native_producer_9d09', PRODUCER)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        project_router, scope, spec, native, fixed, aeep = module.setup(PROJECT)
        artifact = ManagedHostArtifact(input_field='workbook_b64', output_field='workbook_b64',
            input_name='input.xlsx', output_name='output.xlsx', max_bytes=150000)
        callbacks = {}
        for role, services in (('control', (fixed,)), ('treatment', (fixed, aeep))):
            worker = ManagedWorkerBinding.model_validate(definition.worker_documents[role])
            callbacks[role] = module.document(services, worker, artifact, scope, spec, native)
        repo.authorize(request)
        verify_dependencies(request.executable_dependencies)
        if verification_source_digest(ROOT) != SOURCE:
            raise ValueError('source changed during setup')
        size = sum(path.stat().st_size for path in PROJECT.rglob('*') if path.is_file())
        if size > 1024**3:
            raise ValueError('project exceeded bounded storage allowance')
        result.update(setup_complete=True, scope_digest=content_digest(scope),
            scope_id=scope.scope_id, scope_expires_at=scope.expires_at.isoformat(),
            callback_documents_by_role=callbacks, worker_documents=definition.worker_documents,
            artifact=artifact.model_dump(mode='json'), project_bytes=size)
    except BaseException as exc:
        result.update(error_type=type(exc).__name__, error_summary=str(exc)[:240])
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        try:
            if project_router is not None:
                project_router.store.close()
        except Exception as exc:
            result.update(setup_complete=False, project_close_error=type(exc).__name__)
        try:
            result['elapsed_seconds'] = time.monotonic() - started
            result['operation_settled'] = False
            if reserved:
                repo.finish_operation(operation, elapsed_seconds=result['elapsed_seconds'])
                result['operation_settled'] = True
        except Exception as exc:
            result.update(setup_complete=False, accounting_error=type(exc).__name__)
        finally:
            try:
                with (OUT / 'b-native-setup-v2-result.json').open('x') as stream:
                    json.dump(result, stream, indent=2)
                    stream.write('\n')
            finally:
                router.store.close()
    if not result['setup_complete'] or not result.get('operation_settled'):
        raise RuntimeError('native setup incomplete; preserve project and recorded allowance')
    print(json.dumps({key: result[key] for key in ('setup_complete', 'operation_id', 'project', 'scope_digest', 'elapsed_seconds')}))


if __name__ == '__main__':
    if sys.argv[1:] == ['prepare']:
        prepare()
    elif len(sys.argv) == 3 and sys.argv[1] == 'execute':
        execute(sys.argv[2])
    else:
        raise SystemExit('usage: b-native-setup-v2.py prepare | execute REVIEW_SHA256')
