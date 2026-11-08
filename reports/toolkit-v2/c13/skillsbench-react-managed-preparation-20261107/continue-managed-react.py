"""Prepare the corrected React workflow and dispatch its one unstarted turn."""

import argparse
import asyncio
import json
import runpy
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from aeep.assessment.boundary import require_candidate_access, require_conformance
from aeep.assessment.models import (
    AssessmentEnvironment, AssessmentLimits, AssessmentPlan, AssessmentSetupRequest,
    AssessmentSubject, IntegrationCaseSet, RecipeDefinition, content_digest,
)
from aeep.assessment.service import AssessmentService
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.models import utc_now
from aeep.router import Router
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.models import SourcePin
from aeep_toolkit.stack_readiness import EngineeringRunReview, require_engineering_run
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_preparation import PreparationIntent

HERE = Path(__file__).resolve().parent
first = runpy.run_path(str(HERE / 'run-managed-react.py'))
read, sha, save, engine, root, work = (first[key] for key in ('read', 'sha', 'save', 'engine', 'ROOT', 'WORK'))
ORIGINAL = work / 'managed-execution'
WORK = work / 'managed-continuation'
REVIEW = HERE / 'managed-continuation-review.json'
CORRECTED = work / 'corrected-react-workflow.json'
CONFIGURATION = 'software-engineering'
RUN_TAG = 'react-corrected-20261108'


def load_record(db, kind, identity):
    result = db.execute("SELECT payload_json FROM assessment_records WHERE kind=? AND id=?", (kind, identity)).fetchone()
    assert result is not None
    return json.loads(result[0])


def guard(review, identity):
    assert sha(REVIEW) == identity and utc_now() < datetime.fromisoformat(review['expires_at'])
    assert first['verification_source_digest'](root) == review['source_sha256']
    assert shutil.disk_usage(root).free >= 50 * 1024**3
    assert all(sha(path) == pin for path, pin in review['pins'].items())
    first['grader_current']()


def exact_input(prior):
    old_result = read(HERE / 'managed-result.json')
    assert old_result['stopped_phase'] == 'ordinary CLI preparation'
    assert old_result['model_turns_reserved'] == 0 and old_result['proxy_restored_stopped']
    assert not old_result['new_unresolved_reservations'] and old_result['historical_reservations_preserved']
    case, = prior['cases']
    recipe = RecipeDefinition.model_validate(read(case['recipe']))
    pair = WorkerPairInspection.model_validate(read(case['pair']))
    assert content_digest(recipe) == case['recipe_digest'] and content_digest(pair) == case['pair_digest']
    original = read(ORIGINAL / 'react-workflow.json')
    initial = original['configurations'][CONFIGURATION]
    assert initial['task_ids'] == ['spring-boot-jakarta-migration']
    path = work / (case['task_id'] + '-bound-pack.json')
    asset_root = read(HERE / 'operation-review.json')['tasks'][0]['pack_root']
    config = initial | {'benchmark': engine.binding(path), 'benchmark_recipe': engine.binding(Path(case['recipe'])),
                        'task_ids': [case['task_id']], 'asset_root': asset_root}
    exact = original | {'configurations': {CONFIGURATION: config}}
    proxy = read(engine.PREVIOUS / 'operation-review.json')
    assert engine.proxy_state(proxy) == prior['proxy']
    for arm, image in prior['worker_image_ids'].items():
        cfg = getattr(pair, arm).managed_host_config()
        assert engine.binding_from_config(cfg.managed_worker).image == image
        assert engine.docker('image', 'inspect', '--format', '{{.Id}}', image) == image
    return exact, case, recipe, pair, proxy


def check_canonical(prior, corrected, case):
    before = engine.cli('plan', '--workflow', ORIGINAL / 'react-workflow.json', '--configuration', CONFIGURATION)
    after = engine.cli('plan', '--workflow', CORRECTED, '--configuration', CONFIGURATION)
    expected = ['canonical plan preparation is selected but has not been performed']
    assert before['blockers'] == after['blockers'] == expected
    request = AssessmentSetupRequest.model_validate(read(ORIGINAL / 'react-setup.json'))
    intent = PreparationIntent(workflow_review=before['review_sha256'], configuration=CONFIGURATION,
                               request_digest=content_digest(request))
    readiness = read(ORIGINAL / 'react-readiness.json')
    with sqlite3.connect(Path(prior['database']).as_uri() + '?mode=ro', uri=True) as db:
        assert db.execute("SELECT 1 FROM assessment_records WHERE kind='toolkit_workflow_preparation' AND id=?",
                          (content_digest(intent),)).fetchone() is None
        cases = IntegrationCaseSet.model_validate(load_record(db, 'integration_case_set', request.integration_case_set_id))
        subject = AssessmentSubject.model_validate(load_record(db, 'subject', request.subject_id))
        assert subject.dependency_digests == after['candidate']['files']
        assert content_digest(RecipeDefinition.model_validate(load_record(db, 'recipe', request.recipe_id))) == case['recipe_digest']
    pack = BenchmarkPack.model_validate(read(corrected['benchmark']['path']))
    assert cases.benchmark_pack_digest == content_digest(pack.model_dump(mode='json'))
    current = task_input(pack, Path(corrected['asset_root']), case['task_id'])
    assert len(cases.cases) == 1 and cases.cases[0].action.input == current
    assert readiness['differential_conformance_digest']
    assert all(row['observed_probe_count'] == 11 for row in readiness['boundaries'].values())
    return after['review_sha256'], request


def freeze():
    prior = read(first['REVIEW'])
    exact, case, _, _, _ = exact_input(prior)
    if CORRECTED.exists():
        assert read(CORRECTED) == exact
    else:
        save(CORRECTED, exact)
    preview, request = check_canonical(prior, exact['configurations'][CONFIGURATION], case)
    current = first['snapshot'](prior['database'])
    assert current['counters'] == read(HERE / 'managed-result.json')['grant_after']
    assert current['amendment_sha256'] == content_digest(first['AssessmentBudgetAmendment'].model_validate(prior['time_only_amendment']))
    assert utc_now() < datetime.fromisoformat(current['expires_at'])
    paths = [Path(__file__).resolve(), first['REVIEW'], HERE / 'managed-result.json', CORRECTED,
             ORIGINAL / 'react-workflow.json', ORIGINAL / 'react-setup.json', ORIGINAL / 'react-readiness.json',
             ORIGINAL / 'aeep.json', ORIGINAL / 'react-registry.json', ORIGINAL / 'react-policy.json',
             *[Path(exact['configurations'][CONFIGURATION][key]['path']) for key in ('benchmark', 'benchmark_recipe')]]
    review = {'scope': 'Corrected exact React preparation, one previously unstarted Codex engineering turn and report.',
              'previous_review_sha256': sha(first['REVIEW']), 'workflow_preview_sha256': preview,
              'setup_request_sha256': content_digest(request), 'grant': current,
              'source_sha256': prior['source_sha256'], 'pins': prior['pins'] | {str(p): sha(p) for p in paths},
              'database': prior['database'], 'proxy': prior['proxy'], 'model': prior['model'],
              'maximum_operations': 76, 'maximum_model_turns': 1, 'maximum_reserved_seconds': 3900,
              'maximum_cash_usd': '0', 'cash_or_grant_amendment': False, 'new_worker_inspections': 0,
              'automatic_retries': False, 'comparisons': 'PAUSED', 'expires_at': current['expires_at']}
    save(REVIEW, review)
    print(sha(REVIEW))


async def execute(identity):
    review, prior = read(REVIEW), read(first['REVIEW'])
    guard(review, identity)
    assert read(HERE / 'managed-continuation-approval.json') == {'approved': True, 'review_sha256': identity}
    assert not WORK.exists() and not (HERE / 'managed-continuation-started.json').exists()
    exact, case, recipe, pair, proxy = exact_input(prior)
    assert exact == read(CORRECTED)
    preview, request = check_canonical(prior, exact['configurations'][CONFIGURATION], case)
    assert preview == review['workflow_preview_sha256'] and content_digest(request) == review['setup_request_sha256']
    assert first['snapshot'](review['database']) == review['grant']
    WORK.mkdir(mode=0o700)
    engine.WORK, engine.MANIFEST, engine.CAMPAIGNS = WORK, ORIGINAL / 'aeep.json', WORK / 'campaigns'
    engine.emit = lambda name, value: save(HERE / name, value)
    router = Router.from_manifest(engine.MANIFEST)
    service = AssessmentService(router, engine.CAMPAIGNS)
    repo = service.repository
    initial, pending = engine.previous.counters(repo), engine.reserved(repo)
    assert list(initial) == review['grant']['counters'] and len(pending) == review['grant']['prior_reservations']
    save(HERE / 'managed-continuation-started.json', {'review_sha256': identity})
    reserve = engine.budget.install(repo, repo.store._connection, initial, review)
    outcome = {'review_sha256': identity, 'passed': False, 'comparisons': 'PAUSED'}
    phase, overhead, started, excluded = 'reuse verified worker boundaries', None, False, 0.
    clock = time.perf_counter()
    setup_before = {row[0] for row in repo.store._connection.execute("SELECT id FROM assessment_records WHERE kind='setup_cost'")}
    try:
        readiness = read(ORIGINAL / 'react-readiness.json')
        for arm, proof in readiness['boundaries'].items():
            worker = engine.binding_from_config(getattr(pair, arm).managed_host_config().managed_worker)
            assert worker.digest() == proof['worker_digest']
            record = require_conformance(repo, proof['conformance_digest'], source_digest=review['source_sha256'],
                                         worker_digest=worker.digest(), identity_digest=proof['identity_digest'])
            require_candidate_access(repo, record, pair.differential, available=arm == 'treatment')
        subject = AssessmentSubject.model_validate(repo.get('subject', request.subject_id))
        env = AssessmentEnvironment.model_validate(repo.get('environment', request.environment_id))
        local = AssessmentEnvironment(environment_id=RUN_TAG + '-preparation', kind='trusted_local',
                                      identity={'source_digest': review['source_sha256'], 'review': identity})
        repo.put('environment', content_digest(local), local)
        bootstrap = engine.materialization(repo, RUN_TAG + '-overhead', subject, recipe, local)
        engine.scoped_approval(repo, [bootstrap])
        overhead = bootstrap.plan_id + ':exclusive'
        repo.reserve(bootstrap, overhead, AssessmentLimits(max_operations=1, max_elapsed_seconds=180),
                     stage='owned_workflow_preparation_and_proxy_overhead')
        phase = 'corrected ordinary CLI preparation'
        output = WORK / 'prepared'
        summary = engine.cli('prepare', '--workflow', CORRECTED, '--configuration', CONFIGURATION,
                             '--write-plan', output, '--directory', engine.CAMPAIGNS, '--reviewed-digest', preview,
                             output='managed-continuation-prepare-cli.json')
        plan = AssessmentPlan.model_validate_json((output / 'plan.json').read_bytes())
        assert summary['plan_digest'] == content_digest(plan) and not plan.blocked_reasons
        assert len(plan.suite.cases) == 1 and plan.suite.cases[0].case_id == case['task_id']
        assert [route.executor_id for route in plan.suite.routes] == [pair.treatment.id]
        assert plan.suite.repetitions == 1 and plan.suite.conditions == ['fresh-worker'] and plan.scheduler_digest is None
        engineering = EngineeringRunReview(plan_digest=content_digest(plan), implementation_source=review['source_sha256'],
            scope_request_id=RUN_TAG + '-execution', case_ids=(case['task_id'],), maximum_model_turns=1)
        ref = repo.put('toolkit_engineering_run', content_digest(engineering), engineering)
        scope = engine.materialization(repo, engineering.scope_request_id, subject, recipe, env,
            mapping=plan.mapping_digest, definitions=(*plan.definition_digests, ref))
        bound = output / 'workflow.json'
        accounting = WorkflowAccountingDefinition(workflow_sha256=sha(bound), configurations=(CONFIGURATION,),
            operations=('run', 'report'), source_digest=review['source_sha256'], manifest_path=str(engine.MANIFEST),
            manifest_sha256=sha(engine.MANIFEST), request=scope, maximum_overhead_seconds=engine.OVERHEAD)
        accounting_path = WORK / 'accounting.json'
        save(accounting_path, accounting.model_dump(mode='json'))
        engine.scoped_approval(repo, [scope], extra=[('toolkit_workflow_accounting', accounting), ('plan', plan)])
        require_engineering_run(repo, ref, plan=plan, source_digest=review['source_sha256'])
        service._verify_dependencies(plan)
        prepared = engine.cli('plan', '--workflow', bound, '--configuration', CONFIGURATION)
        assert not prepared['blockers'] and prepared['assessment']['backend_review']['plan_sha256'] == content_digest(plan)
        allowance = service.budget_preview(plan.plan_id)
        operations, turns, seconds = engine.measure_allowance(allowance)
        assert turns == 1 and allowance['campaign_allowance']['fits_remaining']
        engine.budget.require_room(engine.previous.counters(repo), initial,
            AssessmentLimits(max_operations=operations, max_model_turns=turns, max_elapsed_seconds=seconds), review)
        save(HERE / 'managed-continuation-ready.json', {'review_sha256': identity, 'plan_id': plan.plan_id,
            'plan_digest': content_digest(plan), 'worker_boundaries_reused': True})
        phase = 'proxy start and one ordinary CLI engineering turn'
        guard(review, identity)
        assert engine.proxy_state(proxy) == review['proxy'] and set(engine.reserved(repo)) <= set(pending) | {overhead}
        started = True
        engine.docker('start', proxy['proxy_name'])
        active = engine.proxy_state(proxy)
        assert active['Running'] and active['Id'] == review['proxy']['Id'] and active['Image'] == review['proxy']['Image']
        assert active['Networks']['aeep-reviewed-model-private']['IPAddress'] == '172.18.0.2'
        common = ('--workflow', bound, '--configuration', CONFIGURATION, '--manifest', engine.MANIFEST,
                  '--directory', engine.CAMPAIGNS, '--reviewed-digest', prepared['review_sha256'], '--accounting', accounting_path)
        nested = time.perf_counter()
        try:
            engine.cli('run', *common, '--operation-id', 'execute', '--output', WORK / 'result',
                       '--engineering-review', ref, output='managed-continuation-run-cli.json', timeout=2100)
        finally:
            excluded += time.perf_counter() - nested
        source = SourcePin.model_validate(read(engine.PREVIOUS / 'source.json'))
        outcome['workload'] = engine.verify_trial(service, plan, pair, pair.treatment.managed_host_config(), source, WORK / 'result')
        phase = 'ordinary CLI report'
        nested = time.perf_counter()
        try:
            engine.cli('report', *common, '--operation-id', 'render', '--report-id', outcome['workload']['report_id'],
                       '--output', WORK / 'report', output='managed-continuation-report-cli.json')
        finally:
            excluded += time.perf_counter() - nested
        outcome['passed'] = True
    except (Exception, asyncio.CancelledError, KeyboardInterrupt) as error:
        outcome.update(stopped_phase=phase, error_type=type(error).__name__)
    finally:
        outcome['proxy_restored_stopped'] = not started
        if started:
            try:
                if engine.proxy_state(proxy)['Running']:
                    engine.docker('stop', '--time', '5', proxy['proxy_name'])
                outcome['proxy_restored_stopped'] = engine.proxy_state(proxy) == review['proxy']
            except Exception:
                outcome['proxy_restored_stopped'] = False
        if overhead is not None and outcome['proxy_restored_stopped']:
            try:
                setup, ids = engine.scoped_setups(repo, setup_before, subject, bootstrap)
                repo.finish_operation(overhead, elapsed_seconds=max(0., time.perf_counter()-clock-excluded-setup))
                outcome['setup_cost_ids'] = ids
            except Exception as error:
                outcome['accounting_error_type'] = type(error).__name__
        now, after = engine.reserved(repo), engine.previous.counters(repo)
        outcome['new_unresolved_reservations'] = sorted(set(now) - set(pending))
        outcome['historical_reservations_preserved'] = all(now.get(key) == value for key, value in pending.items())
        outcome['grant_after'] = list(after)
        outcome['model_turns_reserved'] = after[1] - initial[1]
        outcome['passed'] &= (outcome['proxy_restored_stopped'] and not outcome['new_unresolved_reservations']
                              and outcome['historical_reservations_preserved'] and after[3] == initial[3])
        repo.reserve = reserve
        try:
            await router.close()
        finally:
            save(HERE / 'managed-continuation-result.json', outcome)
    print(json.dumps(outcome))
    return outcome['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument('--freeze', action='store_true')
    options.add_argument('--execute-approved')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    else:
        raise SystemExit(not asyncio.run(execute(args.execute_approved)))
