"""Use only the original approved Spring plan. Never replay Sales or readiness."""

import argparse
import asyncio
import importlib.util
import json
import subprocess
import time
from pathlib import Path

from aeep.assessment.models import AssessmentEnvironment, RecipeMaterializationRequest, content_digest

HERE = Path(__file__).resolve().parent
module = importlib.util.spec_from_file_location('original_skillsbench_driver', HERE / 'run-engineering.py')
driver = importlib.util.module_from_spec(module)
module.loader.exec_module(driver)
auditor = driver.load_module('skillsbench_trial_audit', HERE / 'audit-trial.py')


async def run(identity, *, execute):
    review = driver.check_review()
    if identity != driver.SHA or (HERE / 'engineering-spring-started.json').exists():
        raise RuntimeError('Exact unstarted Spring scope is required')
    old = driver.prepared.read(HERE / 'engineering-result.json')
    sales = driver.prepared.read(HERE / 'engineering-sales-trial-audit.json')
    ready = driver.prepared.read(HERE / 'engineering-dispatch-ready.json')
    if (not old['proxy_restored_stopped'] or old['new_unresolved_reservations']
            or not old['historical_reservations_preserved'] or old['charged'][1] != 1
            or sales['job_state'] != 'complete' or not sales['worker_cleanup_confirmed']
            or sales['host_failure_code'] != 'worker_artifact_failed'
            or ready['review_sha256'] != identity or not ready['both_worker_pairs_passed']):
        raise RuntimeError('Prior execution or worker isolation is not settled')
    selected, proxy = driver.preflight(review)
    case, _recipe, pair, _shared = selected['spring']
    router = driver.Router.from_manifest(driver.MANIFEST)
    service = driver.AssessmentService(router, driver.CAMPAIGNS)
    repo = service.repository
    try:
        initial = tuple(driver.prepared.read(HERE / 'engineering-started.json')['counters_before'])
        previous = driver.previous.counters(repo)
        historical = driver.reserved(repo)
        if list(previous) != old['grant_after'] or len(historical) != review['grant']['historical_reserved_count']:
            raise RuntimeError('Grant counters changed since Sales')
        expected = ready['plans']['spring']
        plan = auditor.stored_plan(driver, 'spring')
        if (plan.plan_id != expected['plan_id'] or content_digest(plan) != expected['plan_digest']
                or not plan.suite.cases or plan.suite.cases[0].action.input['task_id'] != case['task_id']):
            raise RuntimeError('Spring plan is different')
        if ((driver.CAMPAIGNS / plan.plan_id / 'campaign.sqlite3').exists()
                or repo.store._connection.execute(
                    'SELECT 1 FROM assessment_jobs WHERE plan_id=?', (plan.plan_id,)).fetchone()
                or repo.operation_ledger(plan.plan_id).operations):
            raise RuntimeError('Spring has already started')
        source = review['source_sha256']
        ref = expected['execution_review_ref']
        driver.require_engineering_run(repo, ref, plan=plan, source_digest=source)
        service._verify_dependencies(plan)
        environment = AssessmentEnvironment.model_validate(repo.get('environment', plan.environment_digest))
        for role, result in driver.prepared.read(driver.WORK / 'spring-readiness.json')['boundaries'].items():
            if (environment.conformance_digests[getattr(pair, role).id] != result['conformance_digest']
                    or result['observed_probe_count'] != 11):
                raise RuntimeError('Spring conformance differs from the frozen plan')
            record = driver.require_conformance(repo, result['conformance_digest'],
                source_digest=source, worker_digest=result['worker_digest'], identity_digest=result['identity_digest'])
            driver.require_candidate_access(repo, record, pair.differential, available=role == 'treatment')
        allowance = service.budget_preview(plan.plan_id)
        operations, turns, seconds = driver.measure_allowance(allowance)
        if turns != 1 or not allowance['campaign_allowance']['fits_remaining']:
            raise RuntimeError('Unstarted Spring allowance is unavailable')
        driver.budget.require_room(previous, initial, driver.AssessmentLimits(
            max_operations=operations + 1, max_model_turns=turns, max_elapsed_seconds=seconds + 90), review)
        workflow = driver.WORK / 'spring-prepared/workflow.json'
        configuration = case['configuration']
        preview = driver.cli('plan', '--workflow', workflow, '--configuration', configuration)
        if preview['blockers'] or preview['review_sha256'] != expected['workflow_review_sha256']:
            raise RuntimeError('Ordinary Spring plan review changed')
        if not execute:
            print(json.dumps({'unstarted_spring_preflight': True, 'models_started': 0, 'reviews_reused': True}))
            return 0

        bootstrap = RecipeMaterializationRequest.model_validate(repo.get(
            'recipe_materialization_request', 'skillsbench-workflow-overhead-20261105'))
        operation = bootstrap.plan_id + ':unstarted-spring-proxy-overhead'
        driver.emit('engineering-spring-started.json', {'review_sha256': identity, 'plan_id': plan.plan_id,
                    'grant_before': previous, 'sales_replay': False, 'no_repeated_worker_probes': True})
        clock = time.perf_counter()
        repo.reserve(bootstrap, operation, driver.AssessmentLimits(max_operations=1, max_elapsed_seconds=90),
                     stage='owned_workflow_proxy_overhead')
        excluded = 0.0
        result = {'passed': False, 'comparisons': 'PAUSED', 'review_sha256': identity,
                  'candidate_usefulness': 'NOT_ASSESSED', 'selection_usefulness': 'NOT_ASSESSED'}
        proxy_start_attempted = False
        run_output = driver.WORK / 'spring-result'
        try:
            if driver.proxy_state(proxy) != proxy['proxy_metadata']:
                raise RuntimeError('Reviewed stopped proxy changed')
            proxy_start_attempted = True
            driver.docker('start', proxy['proxy_name'])
            active = driver.proxy_state(proxy)
            if (not active['Running'] or active['Id'] != review['proxy']['proxy_id']
                    or active['Image'] != review['proxy']['proxy_image']
                    or active['Networks']['aeep-reviewed-model-private']['IPAddress'] != '172.18.0.2'):
                raise RuntimeError('Proxy identity or worker destination changed')
            driver.check_review()
            common = ('--workflow', workflow, '--configuration', configuration, '--manifest', driver.MANIFEST,
                      '--directory', driver.CAMPAIGNS, '--reviewed-digest', preview['review_sha256'],
                      '--accounting', driver.WORK / 'spring-accounting.json')
            start = time.perf_counter()
            try:
                driver.cli('run', *common, '--operation-id', 'execute', '--output', run_output,
                           '--engineering-review', ref, output='engineering-spring-run-cli.json', timeout=2100)
            finally:
                excluded += time.perf_counter() - start
            outcome = auditor.audit(driver, service, plan, pair)
            driver.emit('engineering-spring-trial-audit.json', outcome)
            result['trial'] = outcome
            result['report'] = str(run_output / 'report.html')
            if auditor.passed(outcome):
                start = time.perf_counter()
                try:
                    driver.cli('report', *common, '--operation-id', 'render', '--report-id', outcome['report_id'],
                        '--output', driver.WORK / 'spring-report', output='engineering-spring-report-cli.json')
                finally:
                    excluded += time.perf_counter() - start
                result['passed'] = (run_output / 'report.html').is_file()
        except (Exception, asyncio.CancelledError, KeyboardInterrupt) as error:
            result['error_type'] = type(error).__name__
        finally:
            result['proxy_restored_stopped'] = False
            try:
                if proxy_start_attempted:
                    driver.docker('stop', '--time', '5', proxy['proxy_name'])
                result['proxy_restored_stopped'] = driver.proxy_state(proxy) == proxy['proxy_metadata']
            except (OSError, subprocess.SubprocessError):
                pass
            if result['proxy_restored_stopped']:
                repo.finish_operation(operation, elapsed_seconds=max(0.0, time.perf_counter() - clock - excluded))
            current = driver.previous.counters(repo)
            result['new_unresolved_reservations'] = sorted(set(driver.reserved(repo)) - set(historical))
            result['historical_reservations_preserved'] = all(
                driver.reserved(repo).get(key) == value for key, value in historical.items())
            result['grant_after'] = current
            result['cumulative_charge'] = [current[i] - initial[i] for i in range(3)]
            result['passed'] = (result['passed'] and result['proxy_restored_stopped']
                and not result['new_unresolved_reservations'] and result['historical_reservations_preserved']
                and current[3] == initial[3])
            driver.emit('engineering-spring-result.json', result)
            print(json.dumps(result))
        return 0 if result['passed'] else 1
    finally:
        await router.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--review', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.review, execute=args.execute)))
