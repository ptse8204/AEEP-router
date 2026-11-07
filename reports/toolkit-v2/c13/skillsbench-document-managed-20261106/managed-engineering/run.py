"""Prepare both canonical plans and run at most one approved turn for each."""

import argparse
import asyncio
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from aeep.assessment.models import AssessmentEnvironment, AssessmentLimits, RecipeDefinition, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.models import utc_now
from aeep.router import Router
from aeep_toolkit.models import SourcePin
from aeep_toolkit.workflow_preparation import TaskRightsReview

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
C13 = HERE.parents[1]
PRIOR = C13 / 'skillsbench-managed-worker-preparation-20261105'
AFLOW = C13 / 'proposal-optimizer-preparation-20261105/calibration/finite-cycle/run.py'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write(chr(10))


def guard(review, digest):
    assert sha(HERE/'operation-review.json') == digest
    assert datetime.fromisoformat(review['expires_at']) > utc_now()
    assert shutil.disk_usage(ROOT).free >= 50*1024**3
    assert verification_source_digest(ROOT) == review['source_sha256']
    assert all(sha(path) == expected for path, expected in review['pins'].items())
    assert review['maximum_model_turns'] == 2 and review['maximum_cash_usd'] == '0'
    assert not review['automatic_retries'] and review['comparisons'] == 'PAUSED'


def preflight(review, digest):
    guard(review, digest)
    assert not (HERE/'started.json').exists() and not Path(review['work']).exists()
    engine = load('document_reviewed_managed_helpers', PRIOR/'run-engineering.py')
    grant_helper = load('document_read_only_grant_helper', AFLOW)
    assert grant_helper.grant_snapshot(review['database']) == review['grant']
    proxy = read(engine.PREVIOUS/'operation-review.json')
    assert engine.proxy_state(proxy) == proxy['proxy_metadata'] == review['proxy']
    selected = {}
    for case in review['cases']:
        role = case['role']
        recipe = RecipeDefinition.model_validate(read(case['recipe']))
        pair = WorkerPairInspection.model_validate(read(case['pair']))
        shared = read(case['shared'])
        assert content_digest(recipe) == case['recipe_digest']
        assert content_digest(pair) == case['pair_digest']
        assert content_digest(shared) == pair.differential.shared_definition_digest
        images = [case['grader_image_id']]
        for arm in ('control', 'treatment'):
            spec = getattr(pair, arm)
            assert spec.input_schema == recipe.input_schema and spec.output_schema == recipe.output_schema
            config = spec.managed_host_config()
            assert not config.store_prompt and not config.store_output
            assert config.model_constraints and tuple(config.model_constraints.allowed_model_ids) == (review['model'],)
            assert tuple(config.reasoning_efforts) == (review['reasoning_effort'],)
            images.append(engine.binding_from_config(config.managed_worker).image)
        assert images[1:] == [review['worker_image_ids'][arm] for arm in ('control','treatment')]
        for image in images:
            assert engine.docker('image', 'inspect', '--format', '{{.Id}}', image) == image
        selected[role] = case, recipe, pair, shared
    return engine, proxy, selected


def configure(engine, review, selected):
    engine.WORK = Path(review['work'])
    engine.MANIFEST = engine.WORK/'aeep.json'
    engine.CAMPAIGNS = engine.WORK/'campaigns'
    engine.prepared.DEFINITIONS = Path(review['definitions'])
    engine.emit = lambda name, value: write(HERE/name, value)

    def read_rights(case):
        right = TaskRightsReview.model_validate(read(case['rights']))
        assert content_digest(right) == case['rights_review_ref']
        assert right.local_execution_allowed and right.provider_disclosure_allowed
        return right

    def grader(role):
        case = selected[role][0]
        environment = AssessmentEnvironment.model_validate(read(case['grader_environment']))
        assert environment.container_image == case['grader_image_id'] and not environment.network
        return environment

    engine.read_rights = read_rights
    engine.grader_environment = grader


async def execute(review, digest, engine, proxy, selected):
    work = Path(review['work'])
    work.mkdir(mode=0o700)
    configure(engine, review, selected)
    origin = Router.from_manifest(engine.BASE)
    manifest = origin.manifest.model_copy(update={
        'database': origin.store.path,
        'executors': [getattr(item[2], arm) for item in selected.values() for arm in ('control','treatment')],
    })
    await origin.close()
    assert str(manifest.database) == review['database']
    engine.prepared.write(engine.MANIFEST, manifest.model_dump(mode='json'))
    router = Router.from_manifest(engine.MANIFEST)
    service = AssessmentService(router, engine.CAMPAIGNS)
    repo = service.repository
    initial = engine.previous.counters(repo)
    assert list(initial) == review['grant']['counters']
    pending = engine.reserved(repo)
    assert len(pending) == review['grant']['prior_reservations']
    with repo.store._lock:
        reservation_rows = [tuple(row) for row in repo.store._connection.execute(
            "SELECT id,reserved_json FROM assessment_operations WHERE grant_id='onboarding' AND state='reserved' ORDER BY id")]
    assert content_digest(reservation_rows) == review['grant']['prior_reservations_sha256']
    write(HERE/'started.json', {'review_sha256':digest,'comparisons':'PAUSED','automatic_retries':False})
    original = engine.budget.install(repo, repo.store._connection, initial, review)
    original_collect = engine.inspection.collect
    report = {'passed':False,'plans':{},'workloads':{},'model_turns_reserved':0,'comparisons':'PAUSED'}
    start = time.perf_counter()
    phase = 'setup'
    nested = 0.
    overhead = None
    proxy_started = False
    setup_before = {row[0] for row in repo.store._connection.execute("SELECT id FROM assessment_records WHERE kind='setup_cost'")}
    try:
        subject = service.inspect_local(engine.prepared.SKILL, kind='skill')
        first = next(iter(selected.values()))[1]
        repo.put('recipe', first.recipe_id, first)
        local = AssessmentEnvironment(environment_id='skillsbench-document-preparation-20261106',
            kind='trusted_local', identity={'implementation_source':review['source_sha256'],'review':digest})
        repo.put('environment', content_digest(local), local)
        bootstrap = engine.materialization(repo, 'skillsbench-document-overhead-20261106', subject, first, local)
        engine.scoped_approval(repo, [bootstrap])
        overhead = bootstrap.plan_id + ':exclusive'
        repo.reserve(bootstrap, overhead, AssessmentLimits(max_operations=1,max_elapsed_seconds=180),
                     stage='owned_workflow_preparation_and_proxy_overhead')
        for case, _recipe, _pair, shared in selected.values():
            repo.put('shared_environment_definition',content_digest(shared),engine.previous.Document(value=shared))
            right = engine.read_rights(case)
            ref = repo.put('toolkit_task_rights',content_digest(right),right)
            repo.review(ref)
        phase = 'proxy'
        guard(review,digest)
        assert engine.proxy_state(proxy) == review['proxy']
        proxy_started = True
        engine.docker('start',proxy['proxy_name'])
        active = engine.proxy_state(proxy)
        assert active['Running'] and active['Id'] == review['proxy']['Id'] and active['Image'] == review['proxy']['Image']
        assert active['Networks']['aeep-reviewed-model-private']['IPAddress'] == '172.18.0.2'
        boundaries = {}
        for role, (_case, recipe, pair, _shared) in selected.items():
            phase = role + ' worker and collector isolation'
            guard(review,digest)
            requests = engine.worker_requests(service, role, pair, recipe, subject, review['source_sha256'])
            engine.inspection.collect = engine.inspect_collector(original_collect)
            began = time.perf_counter()
            try:
                result = await engine.inspection.execute_pair(service, *requests)
            finally:
                nested += time.perf_counter()-began
                engine.inspection.collect = original_collect
            observed = [repo.get('worker_pair_inspection','pair-inspection:'+ident)['observations'] for ident in requests]
            if any(row.get('cleanup_error_type') or ('inspection' in row and not row.get('cleanup_confirmed')) for row in observed):
                report['worker_cleanup_uncertain'] = True
                raise RuntimeError('Worker cleanup is uncertain')
            assert result['probes_match'] and result['model_turns'] == 0
            boundaries[role] = engine.readiness(repo,role,requests,pair,review['source_sha256'])
        phase = 'ordinary CLI preparation'
        workflow = engine.workflow_base(review)
        plans = {}
        for role,item in selected.items():
            plans[role] = engine.draft(service,role,item,subject,boundaries[role],workflow,review['source_sha256'],run_tag='document-20261106')
            plan, ref, _accounting, _bound, workflow_ref, allowed = plans[role]
            report['plans'][role] = {'plan_id':plan.plan_id,'plan_digest':content_digest(plan),
                'workflow_review_sha256':workflow_ref,'execution_review_ref':ref,
                'upper_allowance':allowed['campaign_allowance']['upper_allowance']}
        total = tuple(map(sum,zip(*(engine.measure_allowance(row[-1]) for row in plans.values()),strict=True)))
        engine.budget.require_room(engine.previous.counters(repo),initial,
            AssessmentLimits(max_operations=total[0],max_model_turns=total[1],max_elapsed_seconds=total[2]),review)
        write(HERE/'dispatch-ready.json',{'review_sha256':digest,'plans':report['plans'],'zero_turn_workers_verified':True})
        source = SourcePin.model_validate(read(engine.PREVIOUS/'source.json'))
        for role,item in selected.items():
            phase = role + ' ordinary CLI run'
            guard(review,digest)
            assert set(engine.reserved(repo)) <= set(pending) | {overhead}
            plan, ref, accounting, bound, workflow_ref, _ = plans[role]
            operations, turns, seconds = engine.measure_allowance(service.budget_preview(plan.plan_id))
            engine.budget.require_room(engine.previous.counters(repo),initial,
                AssessmentLimits(max_operations=operations,max_model_turns=turns,max_elapsed_seconds=seconds),review)
            common = ('--workflow',bound,'--configuration',item[0]['configuration'],'--manifest',engine.MANIFEST,
                      '--directory',engine.CAMPAIGNS,'--reviewed-digest',workflow_ref,'--accounting',accounting)
            target = work/(role+'-result')
            began = time.perf_counter()
            try:
                engine.cli('run',*common,'--operation-id','execute','--output',target,'--engineering-review',ref,
                           output=role+'-run-cli.json',timeout=2100)
            finally:
                nested += time.perf_counter()-began
            pair = item[2]
            row = engine.verify_trial(service,plan,pair,pair.treatment.managed_host_config(),source,target)
            report['workloads'][role] = row
            phase = role+' ordinary CLI report'
            began = time.perf_counter()
            try:
                engine.cli('report',*common,'--operation-id','render','--report-id',row['report_id'],
                           '--output',work/(role+'-report'),output=role+'-report-cli.json')
            finally:
                nested += time.perf_counter()-began
        report['passed'] = len(report['workloads'])==2
    except (Exception, asyncio.CancelledError, KeyboardInterrupt) as error:
        report.update(stopped_phase=phase,error_type=type(error).__name__)
    finally:
        engine.inspection.collect = original_collect
        report['proxy_restored_stopped'] = not proxy_started
        if proxy_started:
            try:
                if engine.proxy_state(proxy)['Running']:
                    engine.docker('stop','--time','5',proxy['proxy_name'])
                report['proxy_restored_stopped'] = engine.proxy_state(proxy) == review['proxy']
            except Exception:
                report['proxy_restored_stopped'] = False
        if overhead is not None and report['proxy_restored_stopped'] and not report.get('worker_cleanup_uncertain'):
            try:
                setup, ids = engine.scoped_setups(repo,setup_before,subject,bootstrap)
                repo.finish_operation(overhead,elapsed_seconds=max(0.,time.perf_counter()-start-nested-setup))
                report['setup_cost_ids'] = ids
            except Exception as error:
                report['accounting_error_type'] = type(error).__name__
        now = engine.reserved(repo)
        report['new_unresolved_reservations'] = sorted(set(now)-set(pending))
        report['historical_reservations_preserved'] = all(now.get(key)==value for key,value in pending.items())
        after = engine.previous.counters(repo)
        report['grant_after'] = list(after)
        report['model_turns_reserved'] = after[1]-initial[1]
        report['passed'] &= (report['proxy_restored_stopped'] and not report['new_unresolved_reservations']
                             and report['historical_reservations_preserved'] and after[3]==initial[3])
        repo.reserve = original
        try:
            await router.close()
        finally:
            write(HERE/'result.json',report)
    print(json.dumps(report))
    return report['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--preflight')
    flags.add_argument('--execute-approved')
    args = parser.parse_args()
    digest = args.preflight or args.execute_approved
    review = read(HERE/'operation-review.json')
    engine, proxy, selected = preflight(review,digest)
    if args.preflight:
        print(json.dumps({'review_sha256':digest,'preflight_passed':True,'tasks':list(selected),'models':0}))
    else:
        assert read(HERE/'operator-approval.json') == {'approved':True,'review_sha256':digest}
        raise SystemExit(not asyncio.run(execute(review,digest,engine,proxy,selected)))
