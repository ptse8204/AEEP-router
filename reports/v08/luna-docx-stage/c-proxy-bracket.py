"""Exact report-local proxy bracket; inner runners retain their own allowances."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import math
import shutil
import subprocess
import time
from pathlib import Path

from aeep.assessment.identity import runtime_dependencies, verify_dependencies
from aeep.assessment.models import (
    AssessmentLimits,
    AssessmentScopeAmendment,
    ConformanceProbeRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import StrictModel
from aeep.router import Router

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = '50de999eb8fcd15ffef056c6b67db9f1dc0e491a3b32a3f236bbd81cd52651f7'
MANIFEST = ROOT / '.aeep/live-review-v3/aeep.json'
DB = ROOT / '.aeep/live-review-v3/aeep.sqlite3'
SETUP = OUT / 'b-native-setup-v3-review.json'
PROXY_ID = '5f9a44f86633409a250d11a78cf59357495da2078724ee0261bc73acff57f0f3'
PROXY_IMAGE = 'sha256:5bf590eb0bf8a06187ff092f0f75cf83b540cc27bd6a75fd8bd91305ca7b13de'
NETWORK_ID = '8f657f861de8897d53df66efdf595c6d2e202b174af81f2827db409fe53f19d6'
EGRESS_NETWORK_ID = 'dc46efd9e7306a1671da13301e0cea413270af6a7bd9c4634b2f0e3f8aeab4dc'
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']


class Definition(StrictModel):
    source_digest: str
    proxy_id: str
    proxy_image: str
    network_id: str
    egress_network_id: str
    role: str
    worker_digest: str
    purpose: str
    runner: str
    runner_sha256: str
    inner_review: str
    inner_review_sha256: str
    inner_result: str
    inner_timeout_seconds: int
    operations: int
    reserved_seconds: int
    model_turns: int
    cash_usd: int


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


def check_static():
    if (verification_source_digest(ROOT) != SOURCE
            or sha(MANIFEST) != '091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb'
            or DB.is_symlink() or (DB.stat().st_dev, DB.stat().st_ino) != (16777231, 166293865)
            or sha(SETUP) != 'ab4f78de528080b8684d8d608786d15a5b8aa616755d7f9033957ac0c44ef7b5'):
        raise ValueError('source or canonical store changed')


def docker(*args, timeout=15):
    return subprocess.check_output(DOCKER + list(args), text=True, timeout=timeout,
                                   stderr=subprocess.DEVNULL).strip()


def inspect_proxy():
    value = json.loads(docker('inspect', '--format',
        '{"Id":{{json .Id}},"Name":{{json .Name}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Networks":{{json .NetworkSettings.Networks}}}', PROXY_ID))
    if (value['Id'] != PROXY_ID or value['Name'] != '/aeep-reviewed-model-proxy'
            or value['Image'] != PROXY_IMAGE
            or {name: x['NetworkID'] for name, x in value['Networks'].items()} != {
                'aeep-reviewed-model-private': NETWORK_ID,
                'aeep-reviewed-model-egress': EGRESS_NETWORK_ID}):
        raise ValueError('exact proxy identity or network changed')
    return value


def prepare(stem, runner_name, inner_review_name, inner_result_name, timeout, role, purpose):
    check_static()
    if not stem.startswith('c-') or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in stem):
        raise ValueError('fresh C report stem required')
    paths = [OUT / name for name in (runner_name, inner_review_name)]
    if any(p.parent != OUT or p.is_symlink() or not p.is_file() for p in paths):
        raise ValueError('exact existing report-local runner and review required')
    if Path(inner_result_name).name != inner_result_name or (OUT / inner_result_name).exists():
        raise ValueError('fresh report-local result required')
    if role not in {'control', 'treatment', 'pair'} or not 1 <= timeout <= 500:
        raise ValueError('bounded reviewed inner runner required')
    if purpose not in {'worker', 'capacity', 'callback'}:
        raise ValueError('known conformance runner purpose required')
    setup = json.loads(SETUP.read_text())
    base = setup['request']
    worker_digest = ('e15b7ee0ecabb077cc64ba80f724c739bc51bda8dc71d4038efc92f7678df345'
                     if role == 'control' else '19027f56cdc99fc9b728dc2bf7af597f33c6a0d8f4b5d71d19739aa512a56df0')
    definition = dict(source_digest=SOURCE, proxy_id=PROXY_ID, proxy_image=PROXY_IMAGE,
        network_id=NETWORK_ID, egress_network_id=EGRESS_NETWORK_ID,
        role=role, worker_digest=worker_digest, purpose=purpose,
        runner=runner_name, runner_sha256=sha(paths[0]),
        inner_review=inner_review_name, inner_review_sha256=sha(paths[1]),
        inner_result=inner_result_name, inner_timeout_seconds=timeout,
        operations=3, reserved_seconds=150, model_turns=0, cash_usd=0)
    definitions = dict(setup['definitions'])
    mapping = content_digest(definition)
    definitions[mapping] = definition
    request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v2',
        subject_digest=base['subject_digest'], recipe_digest=base['recipe_digest'],
        mapping_digest=mapping, environment_digest=base['environment_digest'],
        authorization_id='onboarding', definition_digests=list(definitions),
        worker_digest=worker_digest, operation='worker_inspection',
        executable_dependencies=runtime_dependencies() | {
            str(p.resolve()): sha(p) for p in [Path(__file__), SETUP, MANIFEST, *paths]})
    definitions[content_digest(request)] = request.model_dump(mode='json')
    amendment = AssessmentScopeAmendment(authorization_id='onboarding',
        authorization_digest=setup['amendment']['authorization_digest'],
        subject_digests=[request.subject_digest], recipe_digests=[request.recipe_digest],
        environment_digests=[request.environment_digest], reviewed_digests=list(definitions))
    review = dict(source_digest=SOURCE, stem=stem, role=role, definition=definition,
        worker_digest=worker_digest, proxy_id=PROXY_ID,
        runner_sha256=sha(Path(__file__)), request=request.model_dump(mode='json'),
        definitions=definitions, amendment=amendment.model_dump(mode='json'),
        authority='September 25/27 standing finite setup delegation', prepared_only=True)
    target = OUT / (stem + '-proxy-review.json')
    write_new(target, review)
    print(json.dumps({'review': str(target), 'sha256': sha(target)}))


async def execute(review_path, review_sha):
    check_static()
    path = await asyncio.to_thread(Path(review_path).resolve, strict=True)
    if path.parent != OUT or sha(path) != review_sha:
        raise ValueError('exact report-local review required')
    review = json.loads(path.read_text())
    definition = review['definition']
    request = ConformanceProbeRequest.model_validate(review['request'])
    verify_dependencies(request.executable_dependencies)
    if (review['runner_sha256'] != sha(Path(__file__))
            or content_digest(definition) != request.mapping_digest):
        raise ValueError('exact reviewed wrapper changed')
    stem = review['stem']
    started, result_path = OUT / (stem + '-proxy-started.json'), OUT / (stem + '-proxy-result.json')
    if started.exists() or result_path.exists():
        raise ValueError('existing attempt must not be replayed')
    router = Router.from_manifest(MANIFEST)
    repo = AssessmentRepository(router.store)
    result = dict(source_digest=SOURCE, review_sha256=review_sha, request_id=request.plan_id,
        proxy_id=PROXY_ID, role=review['role'], model_turns=0,
        whole_system_cost_complete=False, inner_returned=False, status='failed')
    cleanup_reserved = attempted = stopped_verified = False
    cleanup_id = request.plan_id + ':proxy_stop'
    try:
        repo.put('c_proxy_lifecycle', request.mapping_digest, Definition.model_validate(definition))
        repo.put('conformance_request', request.plan_id, request)
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']), review['definitions'])
        repo.authorize(request)
        write_new(started, {'review_sha256': review_sha, 'request_id': request.plan_id})
        preflight_id = request.plan_id + ':proxy_preflight'
        repo.reserve(request, preflight_id, AssessmentLimits(max_operations=1, max_elapsed_seconds=30), stage='proxy_preflight')
        began = time.monotonic()
        try:
            result['ordinary_free_bytes'] = shutil.disk_usage(ROOT).free
            if result['ordinary_free_bytes'] < 51 * 1024**3:
                raise ValueError('host reserve plus one GiB inspection allowance unavailable')
            result['docker_usage'] = docker('system', 'df', '--format', '{{json .}}')
            if inspect_proxy()['Running']:
                raise ValueError('proxy must start stopped')
            stopped_verified = True
        finally:
            repo.finish_operation(preflight_id, elapsed_seconds=time.monotonic() - began)
        repo.reserve(request, cleanup_id, AssessmentLimits(max_operations=1, max_elapsed_seconds=60), stage='reviewed_proxy_cleanup')
        cleanup_reserved = True
        start_id = request.plan_id + ':proxy_start'
        repo.reserve(request, start_id, AssessmentLimits(max_operations=1, max_elapsed_seconds=60), stage='reviewed_proxy_setup')
        began = time.monotonic()
        try:
            if inspect_proxy()['Running']:
                raise ValueError('proxy changed before start')
            attempted = True
            docker('start', PROXY_ID, timeout=25)
            if not inspect_proxy()['Running']:
                raise ValueError('proxy start not confirmed')
            result['proxy_started'] = True
        finally:
            repo.finish_operation(start_id, elapsed_seconds=time.monotonic() - began)
        runner = OUT / definition['runner']
        if sha(runner) != definition['runner_sha256']:
            raise ValueError('inner runner changed')
        loader = importlib.util.spec_from_file_location('reviewed_c_inner', runner)
        module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(module)
        async with asyncio.timeout(definition['inner_timeout_seconds']):
            await module.execute(definition['inner_review_sha256'])
        inner = json.loads((OUT / definition['inner_result']).read_text())
        if inner.get('source_digest') != SOURCE or inner.get('source_unchanged') is not True:
            raise ValueError('inner evidence source changed')
        purpose = definition['purpose']
        if purpose == 'worker':
            if (inner.get('component_probes_match') is not True
                    or set(inner.get('workers', {})) != {'control', 'treatment'}
                    or any(w.get('cleanup_confirmed') is not True
                           or w.get('component_probes_match') is not True
                           for w in inner['workers'].values())):
                raise ValueError('worker checks or cleanup failed')
            inner_operations = ['pair-inspection:' + identity for identity in inner['request_ids']]
        elif purpose == 'capacity':
            if inner.get('status') != 'passed' or inner.get('cleanup_confirmed') is not True:
                raise ValueError('capacity check or cleanup failed')
            inner_operations = [inner['operation_id']]
        elif purpose == 'callback':
            if (inner.get('stage') != 'callback_probe_recorded'
                    or inner.get('cleanup_confirmed') is not True
                    or inner.get('result_status', 'passed') != 'passed'):
                raise ValueError('callback check or cleanup failed')
            inner_operations = [inner['operation_id']]
        else:
            raise ValueError('unknown reviewed inner purpose')
        for operation_id in inner_operations:
            row = router.store._connection.execute(
                'SELECT grant_id,state FROM assessment_operations WHERE id=?', (operation_id,)).fetchone()
            if row is None or tuple(row) != ('onboarding', 'complete'):
                raise ValueError('inner operation is not settled under the same grant')
        result['inner_returned'] = True
        result['inner_result_sha256'] = sha(OUT / definition['inner_result'])
    except BaseException as exc:
        result['error_type'] = type(exc).__name__
        result['error_message_sha256'] = hashlib.sha256(str(exc).encode()).hexdigest()
    finally:
        began = time.monotonic()
        try:
            if attempted:
                # Cleanup must still be attempted if Docker inspection is unavailable.
                docker('stop', '--time', '5', PROXY_ID, timeout=20)
                stopped_verified = not inspect_proxy()['Running']
            result['proxy_restored_stopped'] = stopped_verified
        except BaseException as exc:
            result['proxy_restored_stopped'] = False
            result['cleanup_error_type'] = type(exc).__name__
        if cleanup_reserved:
            try:
                repo.finish_operation(cleanup_id, elapsed_seconds=time.monotonic() - began)
                result['cleanup_operation_settled'] = True
            except BaseException as exc:
                result['cleanup_accounting_error'] = type(exc).__name__
        try:
            measured = {}
            for suffix, ceiling in (('proxy_preflight', 30), ('proxy_start', 60), ('proxy_stop', 60)):
                operation_id = request.plan_id + ':' + suffix
                measurement = repo.get('operation_measurement', operation_id)
                elapsed = measurement.get('elapsed_seconds')
                if (not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool)
                        or not math.isfinite(elapsed) or not 0 <= elapsed <= ceiling):
                    raise ValueError('proxy operation exceeded its measured allowance')
                measured[operation_id] = elapsed
            repo.current_grant('onboarding')
            result['measured_operation_seconds'] = measured
            result['allowances_satisfied'] = True
        except BaseException as exc:
            result['allowances_satisfied'] = False
            result['allowance_error_type'] = type(exc).__name__
        try:
            await router.close()
            result['coordinator_closed'] = True
        except BaseException as exc:
            result['close_error_type'] = type(exc).__name__
        result['source_unchanged'] = verification_source_digest(ROOT) == SOURCE
        if all(result.get(k) is True for k in ('inner_returned', 'proxy_restored_stopped',
                'cleanup_operation_settled', 'coordinator_closed', 'source_unchanged', 'allowances_satisfied')):
            result['status'] = 'passed'
        write_new(result_path, result)
    print(json.dumps(result))
    if result['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('prepare')
    for name in ('stem', 'runner', 'inner_review', 'inner_result', 'role', 'purpose'):
        p.add_argument(name)
    p.add_argument('timeout', type=int)
    p = sub.add_parser('execute')
    p.add_argument('review')
    p.add_argument('sha256')
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.stem, args.runner, args.inner_review, args.inner_result, args.timeout, args.role, args.purpose)
    else:
        asyncio.run(execute(args.review, args.sha256))
