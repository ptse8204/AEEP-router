"""Run one ordinary CLI React engineering journey under an exact provider approval."""

import argparse
import asyncio
import json
import runpy
import shutil
import sqlite3
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from aeep.assessment.models import (
    AssessmentBudgetAmendment, AssessmentEnvironment, AssessmentLimits, IntegrationCaseSet,
    RecipeDefinition, content_digest,
)
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.models import utc_now
from aeep.router import Router
from aeep_toolkit.models import ExtensionManifest, SourcePin
from aeep_toolkit.workflow_preparation import TaskRightsReview

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
C13 = HERE.parent
WORK = ROOT / '.aeep' / HERE.name
DEFS = WORK / 'managed-definitions'
EXEC = WORK / 'managed-execution'
GRADER = C13 / 'skillsbench-react-readonly-grader-20261108'
REVIEW = HERE / 'managed-operation-review.json'
PRIOR = C13 / 'skillsbench-managed-worker-preparation-20261105/run-engineering.py'
owner = runpy.run_path(str(C13 / 'skillsbench-document-managed-20261106/managed-engineering/run.py'))
read, sha, save = (owner[key] for key in ('read', 'sha', 'write'))
engine = owner['load']('reviewed_react_engineering_helpers', PRIOR)


def snapshot(database):
    with sqlite3.connect(Path(database).as_uri() + '?mode=ro', uri=True) as db:
        state = db.execute("SELECT revoked,operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone()
        root = db.execute("SELECT digest,payload_json FROM assessment_records WHERE kind='authorization' AND id='onboarding'").fetchone()
        latest = db.execute(
            "SELECT digest,payload_json FROM assessment_records WHERE kind='budget_amendment' "
            "AND json_extract(payload_json,'$.authorization_id')='onboarding' ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        pending = db.execute(
            "SELECT id,reserved_json FROM assessment_operations WHERE grant_id='onboarding' AND state='reserved' ORDER BY id"
        ).fetchall()
    assert state and not state[0] and Decimal(state[4]) == 0 and root and latest
    base = json.loads(root[1])
    amendment = AssessmentBudgetAmendment.model_validate_json(latest[1])
    assert content_digest(amendment) == latest[0] and amendment.authorization_digest == root[0]
    assert not base['remote_disclosure'] and 'codex' in base['allowed_destinations']
    assert amendment.limits.max_cash_usd == 0
    return {'counters': list(state[1:]), 'root_sha256': root[0], 'amendment_sha256': latest[0],
            'limits': amendment.limits.model_dump(mode='json'), 'expires_at': amendment.expires_at.isoformat(),
            'prior_reservations': len(pending), 'prior_reservations_sha256': content_digest(pending)}


def grader_current():
    module = runpy.run_path(str(GRADER / 'run-grader.py'))
    record = read(GRADER / 'operation-review.json')
    assert content_digest(module['inventory']()) == record['mount_inventory_sha256']
    return AssessmentEnvironment.model_validate(read(GRADER / 'environment.json'))


def inspect_selected(review):
    assert verification_source_digest(ROOT) == review['source_sha256']
    assert not EXEC.exists() and not (HERE / 'managed-started.json').exists()
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    assert all(sha(path) == expected for path, expected in review['pins'].items())
    assert snapshot(review['database']) == review['grant']
    proxy = read(engine.PREVIOUS / 'operation-review.json')
    assert engine.proxy_state(proxy) == proxy['proxy_metadata'] == review['proxy']
    case, = review['cases']
    recipe = RecipeDefinition.model_validate(read(case['recipe']))
    pair = WorkerPairInspection.model_validate(read(case['pair']))
    shared = read(case['shared'])
    env = grader_current()
    assert content_digest(env) == case['grader_environment_digest']
    assert content_digest(recipe) == case['recipe_digest']
    assert content_digest(pair) == case['pair_digest']
    assert content_digest(shared) == pair.differential.shared_definition_digest
    cases = IntegrationCaseSet.model_validate(read(DEFS / 'react-integration-cases.json'))
    assert content_digest(cases) == case['integration_case_set_digest'] and len(cases.cases) == 1
    assert cases.cases[0].case_id == case['task_id']
    assert cases.cases[0].action.input['task_archive_sha256'] == case['public_archive_sha256']
    for arm in ('control', 'treatment'):
        config = getattr(pair, arm).managed_host_config()
        worker = engine.binding_from_config(config.managed_worker)
        assert worker.image == review['worker_image_ids'][arm]
        assert not config.store_prompt and not config.store_output
        assert tuple(config.model_constraints.allowed_model_ids) == (review['model'],)
        assert tuple(config.reasoning_efforts) == (review['reasoning_effort'],)
        assert engine.docker('image', 'inspect', '--format', '{{.Id}}', worker.image) == worker.image
    assert engine.docker('image', 'inspect', '--format', '{{.Id}}', env.container_image) == env.container_image
    return proxy, case, recipe, pair, shared, env


def freeze():
    definition = read(HERE / 'managed-definition-preflight.json')
    task = read(HERE / 'operation-review.json')['tasks'][0]
    database = engine.BASE.parent / 'aeep.sqlite3'
    current = snapshot(database)
    expires = utc_now() + timedelta(hours=12)
    assert expires > datetime.fromisoformat(current['expires_at'])
    amendment = AssessmentBudgetAmendment(
        amendment_id='skillsbench-react-engineering-expiry-20261108', authorization_id='onboarding',
        authorization_digest=current['root_sha256'], previous_amendment_digest=current['amendment_sha256'],
        limits=AssessmentLimits.model_validate(current['limits']), expires_at=expires, issued_at=utc_now(),
    )
    recipe = ROOT / '.aeep' / GRADER.name / 'react-recipe.json'
    case = {'configuration': 'software-engineering', 'role': 'react', 'task_id': task['task_id'],
            'public_archive_sha256': task['public_archive_sha256'], 'public_files': task['public_files'],
            'rights': str(HERE / 'proposed-rights.json'), 'rights_review_ref': definition['rights_review_ref'],
            'recipe': str(recipe), 'recipe_digest': definition['recipe_digest'],
            'pair': str(DEFS / 'react-pair.json'), 'pair_digest': definition['pair_digest'],
            'shared': str(DEFS / 'react-shared.json'),
            'grader_environment': str(GRADER / 'environment.json'),
            'grader_environment_digest': definition['environment_digest'],
            'grader_image_id': grader_current().container_image,
            'integration_case_set_digest': definition['case_set_digest']}
    workflow = read(DEFS / 'workflow.json')
    pins = [Path(__file__).resolve(), PRIOR, Path(owner['__file__']), engine.prepared.HERE / 'prepare-engineering.py',
            engine.PREVIOUS / 'operation-review.json', engine.PREVIOUS / 'source.json',
            engine.PILOT / 'run-collector.py', engine.PILOT / 'trial-evidence.py', engine.PILOT / 'review-budget.py',
            GRADER / 'run-grader.py', GRADER / 'operation-review.json', GRADER / 'result.json',
            HERE / 'operation-review.json', HERE / 'managed-definition-preflight.json', HERE / 'prepare-managed-react.py',
            HERE / 'candidate-smoke-result.json', HERE / 'worker-image-parity.json',
            Path(case['rights']), recipe, Path(case['pair']), Path(case['shared']), Path(case['grader_environment']),
            *sorted(DEFS.glob('*.json')), *(Path(workflow[k]['path']) for k in ('registry', 'policy'))]
    review = {'scope': 'One ordinary CLI React engineering task on the pinned public archive.',
              'pins': {str(path): sha(path) for path in pins}, 'source_sha256': definition['source_sha256'],
              'database': str(database), 'definitions': str(DEFS), 'work': str(EXEC),
              'grant': current, 'time_only_amendment': amendment.model_dump(mode='json'),
              'proxy': read(engine.PREVIOUS / 'operation-review.json')['proxy_metadata'],
              'cases': [case], 'worker_image_ids': definition['worker_images'],
              'maximum_operations': 80, 'maximum_model_turns': 1, 'maximum_reserved_seconds': 4000,
              'maximum_cash_usd': '0', 'model': 'gpt-6-astra', 'reasoning_effort': 'medium',
              'expires_at': expires.isoformat(), 'automatic_retries': False, 'comparisons': 'PAUSED',
              'authority': 'Exact operator approval required for the public inputs and the one existing Codex destination turn.',
              'pre_dispatch': 'Verify both worker and collector boundaries and prepare one exact ordinary CLI plan.'}
    inspect_selected(review)
    save(REVIEW, review)
    print(sha(REVIEW))


def workflow_base(review):
    workflow = read(DEFS / 'workflow.json')
    registry, policy = (read(workflow[k]['path']) for k in ('registry', 'policy'))
    origins = ['https://auth.openai.com', 'https://chatgpt.com', 'https://api.openai.com']
    for item in registry['extensions']:
        identity = item['extension_id']
        if identity not in {'aeep-evaluator', 'skillsbench'}:
            continue
        effect = 'Reuse the exact managed worker pair, protected grader and existing scoped Codex proxy.'
        rights = 'Exact approved public React task. Protected grader inputs stay local.'
        item.update(purpose='One original React engineering journey', status='experimental', blockers=[],
                    install_effects=[effect], rollback='Retain the pinned images and stop the reviewed proxy.')
        item['source'].update(artifact_sha256=content_digest({'review': sha(REVIEW), 'integration': identity}),
                              data_rights=rights)
        if identity == 'aeep-evaluator':
            item['source']['revision'] = '1260dffb474987d17c32e169a4398145fa7d9d35'
            item['permissions'].update(network_destinations=origins, authentication='host_owned',
                                       financial_exposure='subscription_unpriced')
        policy['allowed_data_rights'].append(rights)
        policy['reviewed_dependency_manifests'].append(engine.manifest_digest(ExtensionManifest.model_validate(item)))
    policy['allowed_network_destinations'] = origins
    policy['allowed_authentication'].append('host_owned')
    policy['allowed_financial_exposure'].append('subscription_unpriced')
    policy['free_disk_bytes'] = shutil.disk_usage(ROOT).free
    for label, value in [('registry', registry), ('policy', policy)]:
        path = EXEC / ('react-' + label + '.json')
        engine.prepared.write(path, value)
        workflow[label] = engine.binding(path)
    return workflow


def guard(review, digest):
    assert sha(REVIEW) == digest and utc_now() < datetime.fromisoformat(review['expires_at'])
    assert verification_source_digest(ROOT) == review['source_sha256']
    assert all(sha(path) == expected for path, expected in review['pins'].items())
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    grader_current()


async def execute(identity):
    review = read(REVIEW)
    guard(review, identity)
    assert read(HERE / 'managed-approval.json') == {'approved': True, 'review_sha256': identity}
    proxy, case, recipe, pair, shared, protected = inspect_selected(review)
    EXEC.mkdir(mode=0o700)
    selected = {'react': (case, recipe, pair, shared)}
    owner['configure'](engine, review, selected)
    origin = Router.from_manifest(engine.BASE)
    manifest = origin.manifest.model_copy(update={'database': origin.store.path, 'executors': [pair.control, pair.treatment]})
    await origin.close()
    assert str(manifest.database) == review['database']
    engine.prepared.write(engine.MANIFEST, manifest.model_dump(mode='json'))
    router = Router.from_manifest(engine.MANIFEST)
    service = AssessmentService(router, engine.CAMPAIGNS)
    repo = service.repository
    initial, pending = engine.previous.counters(repo), engine.reserved(repo)
    assert list(initial) == review['grant']['counters'] and len(pending) == review['grant']['prior_reservations']
    save(HERE / 'managed-started.json', {'review_sha256': identity, 'automatic_retries': False, 'comparisons': 'PAUSED'})
    original_reserve = engine.budget.install(repo, repo.store._connection, initial, review)
    original_collect = engine.inspection.collect
    outcome = {'review_sha256': identity, 'passed': False, 'comparisons': 'PAUSED', 'model_turns_reserved': 0}
    overhead, proxy_started, excluded = None, False, 0.
    begin = time.perf_counter()
    setup_before = {row[0] for row in repo.store._connection.execute("SELECT id FROM assessment_records WHERE kind='setup_cost'")}
    phase = 'expiry amendment'
    try:
        amendment = AssessmentBudgetAmendment.model_validate(review['time_only_amendment'])
        assert amendment.limits == repo.effective_grant('onboarding').limits
        repo.approve_budget_amendment(amendment)
        assert engine.previous.counters(repo) == initial
        phase = 'scope and rights preparation'
        subject = service.inspect_local(engine.prepared.SKILL, kind='skill')
        repo.put('recipe', recipe.recipe_id, recipe)
        local = AssessmentEnvironment(environment_id='react-managed-preparation-20261108',
            kind='trusted_local', identity={'source_digest': review['source_sha256'], 'review': identity})
        repo.put('environment', content_digest(local), local)
        bootstrap = engine.materialization(repo, 'react-managed-overhead-20261108', subject, recipe, local)
        engine.scoped_approval(repo, [bootstrap])
        overhead = bootstrap.plan_id + ':exclusive'
        repo.reserve(bootstrap, overhead, AssessmentLimits(max_operations=1, max_elapsed_seconds=180),
                     stage='owned_workflow_preparation_and_proxy_overhead')
        repo.put('shared_environment_definition', content_digest(shared), engine.previous.Document(value=shared))
        rights = TaskRightsReview.model_validate(read(case['rights']))
        assert rights.local_execution_allowed and rights.provider_disclosure_allowed
        assert content_digest(rights) == case['rights_review_ref']
        repo.review(repo.put('toolkit_task_rights', content_digest(rights), rights))
        phase = 'proxy start and zero-turn worker checks'
        guard(review, identity)
        assert engine.proxy_state(proxy) == review['proxy']
        proxy_started = True
        engine.docker('start', proxy['proxy_name'])
        active = engine.proxy_state(proxy)
        assert active['Running'] and active['Id'] == review['proxy']['Id'] and active['Image'] == review['proxy']['Image']
        assert active['Networks']['aeep-reviewed-model-private']['IPAddress'] == '172.18.0.2'
        ids = engine.worker_requests(service, 'react', pair, recipe, subject, review['source_sha256'])
        engine.inspection.collect = engine.inspect_collector(original_collect)
        nested = time.perf_counter()
        try:
            observed = await engine.inspection.execute_pair(service, *ids)
        finally:
            excluded += time.perf_counter() - nested
            engine.inspection.collect = original_collect
        facts = [repo.get('worker_pair_inspection', 'pair-inspection:' + item)['observations'] for item in ids]
        if any(row.get('cleanup_error_type') or ('inspection' in row and not row.get('cleanup_confirmed')) for row in facts):
            outcome['worker_cleanup_uncertain'] = True
            raise RuntimeError('Worker cleanup unverified')
        assert observed['probes_match'] and observed['model_turns'] == 0
        boundary = engine.readiness(repo, 'react', ids, pair, review['source_sha256'])
        phase = 'ordinary CLI preparation'
        assert engine.grader_environment('react') == protected
        plan, ref, accounting, bound, workflow_ref, allowance = engine.draft(
            service, 'react', selected['react'], subject, boundary, workflow_base(review),
            review['source_sha256'], run_tag='react-20261108')
        operations, turns, seconds = engine.measure_allowance(allowance)
        assert turns == 1
        engine.budget.require_room(engine.previous.counters(repo), initial,
            AssessmentLimits(max_operations=operations, max_model_turns=turns, max_elapsed_seconds=seconds), review)
        save(HERE / 'managed-dispatch-ready.json', {'review_sha256': identity, 'plan_id': plan.plan_id,
            'plan_digest': content_digest(plan), 'workflow_ref': workflow_ref, 'worker_boundary_verified': True})
        phase = 'ordinary CLI run'
        guard(review, identity)
        assert set(engine.reserved(repo)) <= set(pending) | {overhead}
        common = ('--workflow', bound, '--configuration', case['configuration'], '--manifest', engine.MANIFEST,
                  '--directory', engine.CAMPAIGNS, '--reviewed-digest', workflow_ref, '--accounting', accounting)
        target = EXEC / 'react-result'
        nested = time.perf_counter()
        try:
            engine.cli('run', *common, '--operation-id', 'execute', '--output', target,
                       '--engineering-review', ref, output='managed-react-run-cli.json', timeout=2100)
        finally:
            excluded += time.perf_counter() - nested
        source = SourcePin.model_validate(read(engine.PREVIOUS / 'source.json'))
        outcome['workload'] = engine.verify_trial(service, plan, pair, pair.treatment.managed_host_config(), source, target)
        phase = 'ordinary CLI report'
        nested = time.perf_counter()
        try:
            engine.cli('report', *common, '--operation-id', 'render', '--report-id', outcome['workload']['report_id'],
                       '--output', EXEC / 'react-report', output='managed-react-report-cli.json')
        finally:
            excluded += time.perf_counter() - nested
        outcome['passed'] = True
    except (Exception, asyncio.CancelledError, KeyboardInterrupt) as error:
        outcome.update(stopped_phase=phase, error_type=type(error).__name__)
    finally:
        engine.inspection.collect = original_collect
        outcome['proxy_restored_stopped'] = not proxy_started
        if proxy_started:
            try:
                if engine.proxy_state(proxy)['Running']:
                    engine.docker('stop', '--time', '5', proxy['proxy_name'])
                outcome['proxy_restored_stopped'] = engine.proxy_state(proxy) == review['proxy']
            except Exception:
                outcome['proxy_restored_stopped'] = False
        if overhead is not None and outcome['proxy_restored_stopped'] and not outcome.get('worker_cleanup_uncertain'):
            try:
                setup, ids = engine.scoped_setups(repo, setup_before, subject, bootstrap)
                repo.finish_operation(overhead, elapsed_seconds=max(0., time.perf_counter()-begin-excluded-setup))
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
        repo.reserve = original_reserve
        try:
            await router.close()
        finally:
            save(HERE / 'managed-result.json', outcome)
    print(json.dumps(outcome))
    return outcome['passed']


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
