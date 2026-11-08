"""Run the single unstarted managed React turn with the verified self-contained grader."""

import argparse
import asyncio
import json
import runpy
import shutil
import time
from datetime import datetime
from pathlib import Path

from aeep.assessment.boundary import require_candidate_access, require_conformance
from aeep.assessment.extensions import require_environment
from aeep.assessment.models import AssessmentEnvironment, AssessmentLimits, AssessmentPlan, AssessmentSubject, content_digest
from aeep.assessment.service import AssessmentService
from aeep.models import utc_now
from aeep.router import Router
from aeep_toolkit.models import SourcePin
from aeep_toolkit.stack_readiness import EngineeringRunReview, require_engineering_run
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition

HERE = Path(__file__).resolve().parent
draft = runpy.run_path(str(HERE / 'prepare-sealed-workflow.py'))
previous = draft['previous']
first = previous['first']
read, sha, save, engine = (draft[key] for key in ('read', 'sha', 'save', 'engine'))
root = draft['ROOT']
ORIGINAL = previous['ORIGINAL']
WORK = draft['WORK'] / 'sealed-managed-execution'
CORRECTED = draft['SEALED'] / 'workflow.json'
REVIEW = HERE / 'sealed-managed-review.json'
CONFIGURATION, RUN_TAG = draft['CONFIGURATION'], draft['RUN_TAG']


def validate_definition(prior):
    _, case, _old_recipe, pair, proxy = previous['exact_input'](prior)
    recipe, env, cases, request = draft['definitions']()
    definition = read(HERE / 'sealed-managed-definition.json')
    assert env.container_image == definition['grader_image']
    assert engine.docker('image', 'inspect', '--format', '{{.Id}}', env.container_image) == env.container_image
    assert content_digest(request) == definition['setup_request_sha256']
    assert content_digest(recipe) == definition['recipe_sha256']
    assert content_digest(env) == definition['environment_sha256']
    assert content_digest(cases) == definition['case_set_sha256']
    require_environment(recipe, env)
    preview = engine.cli('plan', '--workflow', CORRECTED, '--configuration', CONFIGURATION)
    assert preview['blockers'] == ['canonical plan preparation is selected but has not been performed']
    assert preview['review_sha256'] == definition['preview_sha256']
    return case, recipe, env, cases, request, pair, proxy, preview['review_sha256']


def guard(review, identity):
    assert sha(REVIEW) == identity and utc_now() < datetime.fromisoformat(review['expires_at'])
    assert first['verification_source_digest'](root) == review['source_sha256']
    assert shutil.disk_usage(root).free >= 50 * 1024**3
    assert all(sha(path) == pin for path, pin in review['pins'].items())
    verified = read(HERE / 'self-contained-result.json')
    assert verified['passed'] and verified['image']['id'] == review['grader_image']
    assert engine.docker('image', 'inspect', '--format', '{{.Id}}', review['grader_image']) == review['grader_image']


def freeze():
    prior = read(first['REVIEW'])
    _case, recipe, env, cases, request, _pair, _proxy, preview = validate_definition(prior)
    current = first['snapshot'](prior['database'])
    stopped = read(HERE / 'managed-continuation-result.json')
    assert current['counters'] == stopped['grant_after']
    assert stopped['model_turns_reserved'] == 0 and stopped['proxy_restored_stopped']
    assert stopped['historical_reservations_preserved'] and not stopped['new_unresolved_reservations']
    assert utc_now() < datetime.fromisoformat(current['expires_at'])
    previous_review = read(previous['REVIEW'])
    paths = [Path(__file__).resolve(), HERE / 'prepare-sealed-workflow.py', HERE / 'sealed-managed-definition.json',
             HERE / 'self-contained-result.json', HERE / 'self-contained-environment.json',
             HERE / 'self-contained-operation-review.json', HERE / 'managed-carrier-boundary.json',
             HERE / 'managed-continuation-result.json', previous['REVIEW'],
             draft['WORK'] / 'sealed-react-recipe.json', *sorted(draft['SEALED'].glob('*.json'))]
    save(REVIEW, {
        'scope': 'One previously unstarted managed React engineering turn after sealed grader validation.',
        'source_sha256': prior['source_sha256'], 'database': prior['database'], 'grant': current,
        'proxy': prior['proxy'], 'model': prior['model'], 'grader_image': env.container_image,
        'workflow_preview_sha256': preview, 'setup_request_sha256': content_digest(request),
        'recipe_sha256': content_digest(recipe), 'case_set_sha256': content_digest(cases),
        'pins': previous_review['pins'] | {str(path): sha(path) for path in paths},
        'maximum_operations': 71, 'maximum_model_turns': 1, 'maximum_reserved_seconds': 3900,
        'maximum_cash_usd': '0', 'new_worker_inspections': 0, 'downloads': False, 'builds': 0,
        'automatic_retries': False, 'comparisons': 'PAUSED', 'expires_at': current['expires_at'],
    })
    print(sha(REVIEW))


async def execute(identity):
    review, prior = read(REVIEW), read(first['REVIEW'])
    guard(review, identity)
    assert read(HERE / 'sealed-managed-approval.json') == {'approved': True, 'review_sha256': identity}
    assert not WORK.exists() and not (HERE / 'sealed-managed-started.json').exists()
    case, recipe, env, cases, request, pair, proxy, preview = validate_definition(prior)
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
    save(HERE / 'sealed-managed-started.json', {'review_sha256': identity})
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
        repo.put('recipe', recipe.recipe_id, recipe)
        repo.put('environment', env.environment_id, env)
        case_ref = content_digest(cases)
        assert repo.put('integration_case_set', case_ref, cases) == case_ref
        local = AssessmentEnvironment(environment_id=RUN_TAG + '-preparation', kind='trusted_local',
                                      identity={'source_digest': review['source_sha256'], 'review': identity})
        repo.put('environment', content_digest(local), local)
        bootstrap = engine.materialization(repo, RUN_TAG + '-overhead', subject, recipe, local)
        engine.scoped_approval(repo, [bootstrap])
        overhead = bootstrap.plan_id + ':exclusive'
        repo.reserve(bootstrap, overhead, AssessmentLimits(max_operations=1, max_elapsed_seconds=180),
                     stage='owned_workflow_preparation_and_proxy_overhead')
        prepared_scope = engine.materialization(repo, RUN_TAG + '-setup', subject, recipe, env,
            definitions=(case_ref, request.experiment_id))
        engine.scoped_approval(repo, [prepared_scope])
        phase = 'sealed-grader ordinary CLI preparation'
        output = WORK / 'prepared'
        summary = engine.cli('prepare', '--workflow', CORRECTED, '--configuration', CONFIGURATION,
                             '--write-plan', output, '--directory', engine.CAMPAIGNS, '--reviewed-digest', preview,
                             output='sealed-managed-prepare-cli.json')
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
        save(HERE / 'sealed-managed-ready.json', {'review_sha256': identity, 'plan_id': plan.plan_id,
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
                       '--engineering-review', ref, output='sealed-managed-run-cli.json', timeout=2100)
        finally:
            excluded += time.perf_counter() - nested
        source = SourcePin.model_validate(read(engine.PREVIOUS / 'source.json'))
        outcome['workload'] = engine.verify_trial(service, plan, pair, pair.treatment.managed_host_config(), source, WORK / 'result')
        phase = 'ordinary CLI report'
        nested = time.perf_counter()
        try:
            engine.cli('report', *common, '--operation-id', 'render', '--report-id', outcome['workload']['report_id'],
                       '--output', WORK / 'report', output='sealed-managed-report-cli.json')
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
            save(HERE / 'sealed-managed-result.json', outcome)
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
