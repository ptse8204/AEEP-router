"""One reviewed proxy lifecycle around the zero-turn worker inspection."""
from __future__ import annotations
import asyncio
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
from aeep.assessment.identity import runtime_dependencies, verify_dependencies
from aeep.assessment.models import AssessmentLimits, AssessmentScopeAmendment, ConformanceProbeRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import StrictModel
from aeep.router import Router

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = '449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad'
MANIFEST = ROOT / '.aeep/live-review-v3/aeep.json'
SETUP_REVIEW = OUT / 'b-native-setup-v3-review.json'
SETUP_SHA = 'ab4f78de528080b8684d8d608786d15a5b8aa616755d7f9033957ac0c44ef7b5'
REVIEW = OUT / 'b-worker-proxy-lifecycle-v3-review.json'
RUNNER = OUT / 'b-run-worker-components-v3.py'
WORKER_REVIEW = OUT / 'b-worker-components-execution-review-v3.json'
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']
NAME = 'aeep-reviewed-model-proxy'
ID = '5f9a44f86633409a250d11a78cf59357495da2078724ee0261bc73acff57f0f3'
IMAGE = 'sha256:5bf590eb0bf8a06187ff092f0f75cf83b540cc27bd6a75fd8bd91305ca7b13de'
NETWORK = '8f657f861de8897d53df66efdf595c6d2e202b174af81f2827db409fe53f19d6'

class Definition(StrictModel):
    source_digest: str
    proxy_id: str
    proxy_image: str
    network_id: str
    worker_review_sha256: str
    start_seconds: int = 60
    stop_seconds: int = 60
    worker_seconds: int = 420
    model_turns: int = 0

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def docker(*args, timeout=15):
    return subprocess.check_output(DOCKER + list(args), text=True, timeout=timeout, stderr=subprocess.DEVNULL).strip()

def inspect():
    value = json.loads(docker('inspect', '--format', '{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Networks":{{json .NetworkSettings.Networks}}}', NAME))
    if (value['Id'] != ID or value['Image'] != IMAGE
            or NETWORK not in [item['NetworkID'] for item in value['Networks'].values()]):
        raise ValueError('exact existing proxy identity changed')
    return value

def canonical_identity():
    setup = json.loads(SETUP_REVIEW.read_text())
    expected = setup['canonical_store']
    database = Path(json.loads(MANIFEST.read_text())['database'])
    stat = database.stat()
    if (sha(SETUP_REVIEW) != SETUP_SHA or sha(MANIFEST) != expected['manifest_sha256']
            or str(database) != expected['database'] or database.is_symlink()
            or stat.st_dev != expected['device'] or stat.st_ino != expected['inode']):
        raise ValueError('canonical store identity changed')
    return setup

def prepare():
    if REVIEW.exists() or verification_source_digest(ROOT) != SOURCE or inspect()['Running']:
        raise ValueError('fresh stopped-proxy preparation required')
    setup = canonical_identity()
    definition = Definition(source_digest=SOURCE, proxy_id=ID, proxy_image=IMAGE,
        network_id=NETWORK, worker_review_sha256=sha(WORKER_REVIEW))
    definitions = dict(setup['definitions'])
    mapping = content_digest(definition)
    definitions[mapping] = definition.model_dump(mode='json')
    base = setup['request']
    dependencies = runtime_dependencies() | {str(path.resolve()): sha(path) for path in (Path(__file__), RUNNER, WORKER_REVIEW, SETUP_REVIEW, MANIFEST)}
    request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v2',
        subject_digest=base['subject_digest'], recipe_digest=base['recipe_digest'],
        mapping_digest=mapping, environment_digest=base['environment_digest'],
        authorization_id='onboarding', definition_digests=list(definitions),
        worker_digest=base['worker_digest'], executable_dependencies=dependencies,
        operation='worker_inspection')
    definitions[content_digest(request)] = request.model_dump(mode='json')
    amendment = AssessmentScopeAmendment(authorization_id='onboarding',
        authorization_digest=setup['amendment']['authorization_digest'],
        subject_digests=[request.subject_digest], recipe_digests=[request.recipe_digest],
        environment_digests=[request.environment_digest], reviewed_digests=list(definitions))
    value = {'source_digest': SOURCE, 'authority': 'September 25/27 standing finite setup delegation',
        'purpose': 'start exact existing proxy for zero-turn model catalog/worker inspection, then restore stopped state',
        'request': request.model_dump(mode='json'), 'definitions': definitions,
        'definition': definition.model_dump(mode='json'), 'amendment': amendment.model_dump(mode='json'),
        'runner_sha256': sha(Path(__file__)), 'worker_runner_sha256': sha(RUNNER),
        'worker_review_sha256': sha(WORKER_REVIEW), 'operations': 2, 'reserved_seconds': 120,
        'model_turns': 0, 'cash_usd': 0, 'initial_proxy_running': False,
        'separate_worker_allowance': {'operations': 2, 'seconds': 480, 'model_turns': 0},
        'prepared_only': True}
    with REVIEW.open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')
    print(json.dumps({'review': str(REVIEW), 'sha256': sha(REVIEW), 'request_id': request.plan_id}))

async def execute(review_sha):
    if sha(REVIEW) != review_sha or verification_source_digest(ROOT) != SOURCE:
        raise ValueError('exact reviewed source and lifecycle required')
    review = json.loads(REVIEW.read_text())
    if (review['runner_sha256'] != sha(Path(__file__)) or review['worker_runner_sha256'] != sha(RUNNER)
            or review['worker_review_sha256'] != sha(WORKER_REVIEW) or inspect()['Running']):
        raise ValueError('exact stopped proxy/worker inputs required')
    canonical_identity()
    request = ConformanceProbeRequest.model_validate(review['request'])
    verify_dependencies(request.executable_dependencies)
    started_path = OUT / 'b-worker-proxy-lifecycle-v3-started.json'
    result_path = OUT / 'b-worker-proxy-lifecycle-v3-result.json'
    if started_path.exists() or result_path.exists():
        raise ValueError('preserve prior attempt; replay denied')
    router = Router.from_manifest(MANIFEST); repo = AssessmentRepository(router.store)
    result = {'source_digest': SOURCE, 'request_id': request.plan_id, 'review_sha256': review_sha,
        'proxy_id': ID, 'model_turns': 0, 'whole_system_cost_complete': False,
        'preparation_and_bookkeeping_cost': 'unmeasured', 'worker_component_passed': False}
    start_op = request.plan_id + ':proxy_start'; stop_op = request.plan_id + ':proxy_stop'
    start_reserved = stop_reserved = attempted = False
    try:
        definition = Definition.model_validate(review['definition'])
        if content_digest(definition) != request.mapping_digest:
            raise ValueError('proxy definition changed')
        repo.put('b_proxy_lifecycle', request.mapping_digest, definition)
        repo.put('conformance_request', request.plan_id, request)
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']), review['definitions'])
        repo.authorize(request)
        with started_path.open('x') as stream: json.dump({'review_sha256': review_sha, 'request_id': request.plan_id}, stream)
        repo.reserve(request, start_op, AssessmentLimits(max_operations=1,max_elapsed_seconds=60,max_model_turns=0), stage='reviewed_proxy_setup'); start_reserved = True
        began = time.monotonic()
        try:
            repo.reserve(request, stop_op, AssessmentLimits(max_operations=1,max_elapsed_seconds=60,max_model_turns=0), stage='reviewed_proxy_cleanup'); stop_reserved = True
            if inspect()['Running']: raise ValueError('proxy changed before start')
            attempted = True
            docker('start', NAME, timeout=25)
            if not inspect()['Running']: raise ValueError('proxy start not confirmed')
            result['proxy_started'] = True
        finally:
            result['start_elapsed_seconds'] = time.monotonic() - began
            repo.finish_operation(start_op, elapsed_seconds=result['start_elapsed_seconds'])
        loader = importlib.util.spec_from_file_location('reviewed_b_worker_runner', RUNNER)
        module = importlib.util.module_from_spec(loader); loader.loader.exec_module(module)
        async with asyncio.timeout(450):
            await module.execute(review['worker_review_sha256'])
        worker_result = json.loads((OUT / 'b-worker-components-v2-result.json').read_text())
        result['worker_component_passed'] = worker_result.get('component_probes_match') is True
        result['worker_result_sha256'] = sha(OUT / 'b-worker-components-v2-result.json')
    except BaseException as exc:
        result['error_type'] = type(exc).__name__
        result['error_message_sha256'] = hashlib.sha256(str(exc).encode()).hexdigest()
        if isinstance(exc, SystemExit): result['preflight_error'] = str(exc)[:240]
    finally:
        began = time.monotonic()
        try:
            if attempted and inspect()['Running']: docker('stop', '--time', '5', NAME, timeout=20)
            result['proxy_restored_stopped'] = not inspect()['Running']
        except BaseException as exc:
            result.update(proxy_restored_stopped=False, cleanup_error_type=type(exc).__name__)
        finally:
            if stop_reserved:
                result['stop_elapsed_seconds'] = time.monotonic() - began
                try:
                    repo.finish_operation(stop_op, elapsed_seconds=result['stop_elapsed_seconds'])
                    result['cleanup_operation_settled'] = True
                except BaseException as exc: result['cleanup_accounting_error'] = type(exc).__name__
        result['source_unchanged'] = verification_source_digest(ROOT) == SOURCE
        with result_path.open('x') as stream: json.dump(result, stream, indent=2); stream.write('\n')
        router.store.close()
    print(json.dumps(result))
    if not result['worker_component_passed'] or not result.get('proxy_restored_stopped') or not result.get('cleanup_operation_settled') or not result['source_unchanged']:
        raise SystemExit(1)

if __name__ == '__main__':
    if sys.argv[1:] == ['prepare']: prepare()
    elif len(sys.argv) == 3 and sys.argv[1] == 'execute': asyncio.run(execute(sys.argv[2]))
    else: raise SystemExit('usage: b-worker-proxy-lifecycle.py prepare | execute REVIEW_SHA')
