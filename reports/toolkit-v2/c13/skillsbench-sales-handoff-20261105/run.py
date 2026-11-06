"""One Sales-only handoff repeat. Both benchmark inputs and grading stay frozen."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import subprocess
import time
from pathlib import Path

from aeep.assessment.models import AssessmentEnvironment, AssessmentLimits, content_digest
from aeep.hosts.codex_pair_inspection import WorkerPairInspection

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'skillsbench-managed-worker-preparation-20261105'
DIAGNOSTIC = HERE.parent / 'skillsbench-sales-artifact-diagnostic-20261105'
spec = importlib.util.spec_from_file_location('skillsbench_workflow_helpers', PRIOR / 'run-engineering.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
auditor = driver.load_module('skillsbench_trial_audit', PRIOR / 'audit-trial.py')
WORK = driver.ROOT / '.aeep' / HERE.name
TAG = 'handoff-20261105'

# These are path/transport directions. Original task text and grading stay intact.
INSTRUCTIONS = (
    'Use the bound input_path /workspace/skillsbench-task.zip. Read the original task and unpack '
    'its public inputs under /workspace/task-input. In the original task, /root/population.pdf '
    'and /root/income.xlsx refer to the copies in the archive under its environment directory. '
    'The original /root/demographic_analysis.xlsx output maps to the exact bound file '
    '/workspace/demographic_analysis.xlsx. Do not write under /root or deliver a similarly named '
    'file elsewhere. Before returning completion, use Python to verify the exact bound output '
    'is a regular, non-symlink file, is readable, and has a size from 1 to 300000 bytes. '
    'Keep the requested workbook content and native pivot structures. '
)


def candidate(review):
    old = driver.check_review()
    row, recipe, pair, shared = driver.prepared.pairs(old)['sales']
    raw = pair.model_dump(mode='json')
    for role in ('control', 'treatment'):
        cfg = raw[role]['config']
        cfg['instructions'] = INSTRUCTIONS + cfg['instructions']
    prompt_digest = hashlib.sha256(raw['treatment']['config']['instructions'].encode()).hexdigest()
    shared = shared | {'operator_path_mapping_sha256': prompt_digest}
    reference = content_digest(shared)
    inv = raw['differential']['control_inventory'] | {'common_profile': reference}
    raw['differential'].update(shared_definition_digest=reference, control_inventory=inv,
        treatment_inventory=inv | raw['differential']['candidate_inventory'])
    changed = WorkerPairInspection.model_validate(raw)
    case = driver.prepared.read(driver.prepared.DEFINITIONS / 'sales-integration-cases.json')['cases'][0]
    expected = case['action']['input']
    assert expected['task_archive_sha256'] == row['archive_sha256']
    assert review is None or (review['instruction_sha256'] == prompt_digest
        and review['pair_sha256'] == content_digest(changed) and review['cases'] == [row])
    return old, (row, recipe, changed, shared), prompt_digest


def freeze():
    original, item, instruction = candidate(None)
    row, _recipe, pair, _shared = item
    prior = driver.prepared.read(PRIOR / 'engineering-spring-result.json')
    outcome = driver.prepared.read(DIAGNOSTIC / 'result.json')
    assert prior['passed'] and outcome['passed'] and outcome['owned_container_cleaned']
    pins = {str(path): driver.prepared.sha(path) for path in (
        HERE / 'run.py', PRIOR / 'run-engineering.py', PRIOR / 'audit-trial.py',
        PRIOR / 'engineering-result.json', PRIOR / 'engineering-sales-trial-audit.json',
        PRIOR / 'engineering-spring-result.json', DIAGNOSTIC / 'result.json',
        driver.PREVIOUS / 'source.json', driver.prepared.DEFINITIONS / 'sales-recipe.json',
        driver.prepared.DEFINITIONS / 'sales-integration-cases.json',
    )}
    # Avoid embedding private recipe or case bytes.
    return {
        'purpose': 'One Sales Pivot ordinary CLI repeat after the ungraded worker handoff failure.',
        'previous_review_sha256': driver.SHA, 'source_sha256': original['source_sha256'],
        'cases': [row], 'worker_image_ids': {role: image for role, image in original['worker_image_ids'].items()
                                            if role.startswith('sales-')},
        'proxy': original['proxy'], 'pair_sha256': content_digest(pair), 'instruction_sha256': instruction,
        'changes': 'Clarify only archive extraction, original /root path mapping, and exact file/size check.',
        'workload_unchanged': True, 'allowed_destination': 'codex', 'model': original['model'],
        'reasoning_effort': original['reasoning_effort'], 'evaluator': 'managed',
        'counters_before': prior['grant_after'], 'maximum_operations': 48,
        'maximum_reserved_seconds': 3200, 'maximum_model_turns': 1, 'maximum_cash_usd': '0',
        'phases': ['One fresh paired zero-turn isolation check', 'One new canonical CLI plan for Sales',
                   'One required-use model turn and original protected grading', 'Report and restore stopped proxy'],
        'no_spring_replay': True, 'automatic_retries': False, 'comparisons': 'PAUSED', 'pins': pins,
        'expiry_unchanged': original['grant']['time_only_amendment']['expires_at'],
        'initial_failure_cause_known': False, 'started': False,
    }


async def run(review, identity, *, execute):
    if review != freeze():
        raise RuntimeError('Exact Sales review differs')
    original, selection, _ = candidate(review)
    _selected, proxy = driver.preflight(original)
    row, recipe, pair, shared = selection
    origin = driver.Router.from_manifest(driver.MANIFEST)
    manifest = origin.manifest.model_copy(update={'executors': [pair.control, pair.treatment]})
    repo = driver.AssessmentService(origin, driver.CAMPAIGNS).repository
    current = driver.previous.counters(repo)
    historical = driver.reserved(repo)
    try:
        assert list(current) == review['counters_before'] and len(historical) == original['grant']['historical_reserved_count']
        assert repo.current_grant('onboarding').remote_disclosure is False
        assert not WORK.exists()
    finally:
        await origin.close()
    if not execute:
        print(json.dumps({'unstarted': True, 'review_sha256': identity, 'domain': 'document-data',
                          'models_started': 0, 'protected_recipe_changed': False}))
        return 0

    approval = driver.prepared.read(HERE / 'operator-approval.json')
    assert approval['approved'] is True and approval['review_sha256'] == identity
    driver.HERE, driver.WORK = HERE, WORK
    driver.MANIFEST, driver.CAMPAIGNS = WORK / 'aeep.json', WORK / 'campaigns'
    WORK.mkdir(mode=0o700)
    driver.prepared.write(driver.MANIFEST, manifest.model_dump(mode='json'))
    driver.emit('started.json', {'review_sha256': identity, 'grant_before': current, 'automatic_retry': False})
    router = driver.Router.from_manifest(driver.MANIFEST)
    service = driver.AssessmentService(router, driver.CAMPAIGNS)
    repo = service.repository
    reserve = driver.budget.install(repo, repo.store._connection, current, review)
    original_collect = driver.inspection.collect
    phase = 'preparation'
    result = {'passed': False, 'comparisons': 'PAUSED', 'review_sha256': identity}
    clock = time.perf_counter()
    excluded = 0.
    bootstrap = None
    proxy_attempted = False
    setup_before = {r[0] for r in repo.store._connection.execute(
        "SELECT id FROM assessment_records WHERE kind='setup_cost'")}
    try:
        assert driver.previous.counters(repo) == current
        subject = service.inspect_local(driver.prepared.SKILL, kind='skill')
        repo.put('shared_environment_definition', content_digest(shared), driver.previous.Document(value=shared))
        repo.put('recipe', recipe.recipe_id, recipe)
        local = AssessmentEnvironment(environment_id='skillsbench-sales-handoff-overhead',
            kind='trusted_local', identity={'source': review['source_sha256'], 'review': identity})
        repo.put('environment', content_digest(local), local)
        bootstrap = driver.materialization(repo, HERE.name, subject, recipe, local)
        driver.scoped_approval(repo, [bootstrap])
        repo.reserve(bootstrap, bootstrap.plan_id + ':overhead',
                     AssessmentLimits(max_operations=1, max_elapsed_seconds=180), stage='owned_workflow_proxy_overhead')
        if driver.proxy_state(proxy) != proxy['proxy_metadata']:
            raise RuntimeError('Reviewed proxy changed before startup')
        proxy_attempted = True
        driver.docker('start', proxy['proxy_name'])
        active = driver.proxy_state(proxy)
        if (not active['Running'] or active['Id'] != review['proxy']['proxy_id']
                or active['Image'] != review['proxy']['proxy_image']
                or active['Networks']['aeep-reviewed-model-private']['IPAddress'] != '172.18.0.2'):
            raise RuntimeError('Proxy identity or approved destination changed')
        phase = 'fresh Sales containment'
        ids = driver.worker_requests(service, 'sales', pair, recipe, subject, review['source_sha256'])
        driver.inspection.collect = driver.inspect_collector(original_collect)
        began = time.perf_counter()
        try:
            boundary = await driver.inspection.execute_pair(service, *ids)
        finally:
            driver.inspection.collect = original_collect
            excluded += time.perf_counter() - began
        result['worker_boundaries'] = boundary
        for request in ids:
            observations = repo.get('worker_pair_inspection', 'pair-inspection:' + request)['observations']
            if observations.get('cleanup_error_type') or ('inspection' in observations and not observations.get('cleanup_confirmed')):
                result['worker_cleanup_uncertain'] = True
                raise RuntimeError('Worker cleanup is uncertain')
        if not boundary['probes_match']:
            raise RuntimeError('Fresh containment did not pass')
        ready = driver.readiness(repo, 'sales', ids, pair, review['source_sha256'])
        phase = 'ordinary Sales CLI plan'
        workflow = driver.workflow_base(review)
        plan, ref, accounting, bound, workflow_ref, allowed = driver.draft(
            service, 'sales', selection, subject, ready, workflow, review['source_sha256'], run_tag=TAG)
        operations, turns, seconds = driver.measure_allowance(allowed)
        driver.budget.require_room(driver.previous.counters(repo), current, AssessmentLimits(
            max_operations=operations, max_model_turns=turns, max_elapsed_seconds=seconds), review)
        driver.prepared.require_review()
        if (driver.prepared.sha(HERE / 'operation-review.json') != identity
                or any(driver.prepared.sha(path) != digest for path, digest in review['pins'].items())
                or driver.shutil.disk_usage(driver.ROOT).free < driver.RESERVE):
            raise RuntimeError('Exact Sales source, review, or host reserve changed')
        if set(driver.reserved(repo)) - set(historical) != {bootstrap.plan_id + ':overhead'}:
            raise RuntimeError('New unresolved accounting blocks dispatch')
        common = ('--workflow', bound, '--configuration', row['configuration'], '--manifest', driver.MANIFEST,
                  '--directory', driver.CAMPAIGNS, '--reviewed-digest', workflow_ref, '--accounting', accounting)
        result['plan_id'], result['plan_sha256'] = plan.plan_id, content_digest(plan)
        phase = 'ordinary Sales CLI run'
        output = WORK / 'sales-result'
        began = time.perf_counter()
        try:
            driver.cli('run', *common, '--operation-id', 'execute', '--output', output,
                       '--engineering-review', ref, output='run-cli.json', timeout=2100)
        finally:
            excluded += time.perf_counter() - began
        result['trial'] = auditor.audit(driver, service, plan, pair)
        result['report'] = str(output / 'report.html')
        if auditor.passed(result['trial']):
            phase = 'ordinary Sales CLI report'
            began = time.perf_counter()
            try:
                driver.cli('report', *common, '--operation-id', 'render', '--report-id', result['trial']['report_id'],
                           '--output', WORK / 'sales-report', output='report-cli.json')
            finally:
                excluded += time.perf_counter() - began
            result['passed'] = (output / 'report.html').is_file()
    except (Exception, KeyboardInterrupt, asyncio.CancelledError) as error:
        result.update(error_type=type(error).__name__, stopped_phase=phase)
    finally:
        driver.inspection.collect = original_collect
        try:
            if proxy_attempted:
                driver.docker('stop', '--time', '5', proxy['proxy_name'])
            result['proxy_restored_stopped'] = driver.proxy_state(proxy) == proxy['proxy_metadata']
        except (OSError, subprocess.SubprocessError):
            result['proxy_restored_stopped'] = False
        if bootstrap and result['proxy_restored_stopped'] and not result.get('worker_cleanup_uncertain'):
            try:
                nested, ids = driver.scoped_setups(repo, setup_before, subject, bootstrap)
                exclusive = max(0., time.perf_counter() - clock - excluded - nested)
                repo.finish_operation(bootstrap.plan_id + ':overhead', elapsed_seconds=exclusive)
                result['overhead'] = {'exclusive_seconds': exclusive, 'excluded_nested_seconds': excluded,
                                      'excluded_setup_seconds': nested, 'setup_cost_ids': ids}
            except Exception as error:
                result['accounting_error_type'] = type(error).__name__
        result['grant_after'] = driver.previous.counters(repo)
        result['new_unresolved_reservations'] = sorted(set(driver.reserved(repo)) - set(historical))
        result['historical_reservations_preserved'] = all(
            driver.reserved(repo).get(key) == value for key, value in historical.items())
        result['passed'] = (result['passed'] and result['proxy_restored_stopped']
            and not result['new_unresolved_reservations'] and result['historical_reservations_preserved']
            and result['grant_after'][3] == current[3])
        repo.reserve = reserve
        try:
            await router.close()
        finally:
            driver.emit('result.json', result)
            print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--execute-approved')
    args = parser.parse_args()
    path = HERE / 'operation-review.json'
    if args.prepare:
        driver.prepared.write(path, freeze())
        print(driver.prepared.sha(path))
    else:
        identity = driver.prepared.sha(path)
        if args.execute_approved is not None and args.execute_approved != identity:
            raise SystemExit('Exact review digest is required')
        raise SystemExit(asyncio.run(run(driver.prepared.read(path), identity, execute=args.execute_approved is not None)))
