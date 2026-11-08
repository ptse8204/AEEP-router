"""Prepare and run the single unstarted React engineering turn with GPT-6.1 Sol."""

import argparse
import asyncio
import json
import runpy
import shutil
import time
from datetime import datetime
from pathlib import Path

from aeep.assessment.extensions import require_environment
from aeep.assessment.models import AssessmentEnvironment, AssessmentLimits, IntegrationCaseSet, RecipeDefinition, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.models import utc_now
from aeep.router import Router
from aeep_toolkit.models import ExtensionManifest, SourcePin
from aeep_toolkit.workflow_preparation import TaskRightsReview

HERE = Path(__file__).resolve().parent
sealed = runpy.run_path(str(HERE / 'run-sealed-managed.py'))
draft = sealed['draft']
first = sealed['first']
owner = first['owner']
read, sha, save, engine = (sealed[key] for key in ('read', 'sha', 'save', 'engine'))
ROOT = draft['ROOT']
WORK = draft['WORK']
DEFS = WORK / 'sol-managed-definitions'
EXEC = WORK / 'sol-managed-execution'
REVIEW = HERE / 'sol-managed-review.json'
MODEL = 'gpt-6.1-sol'
OFFICIAL_MODEL = 'https://developers.openai.com/api/docs/models/gpt-6.1-sol'
OFFICIAL_CODEX = 'https://developers.openai.com/api/docs/guides/code-generation'


def definitions(prior):
    case, recipe, env, cases, _request, baseline, _proxy, _preview = sealed['validate_definition'](prior)
    env = env.model_copy(update={'environment_id': 'react-sol-sealed-20261108',
                                 'conformance_digests': {}, 'differential_conformance_digest': None})
    require_environment(recipe, env)
    cases = cases.model_copy(update={'request_id': 'react-sol-20261108-cases',
                                     'environment_digest': content_digest(env)})
    pair = baseline.model_dump(mode='json')
    shared = read(case['shared']) | {'recipe': content_digest(recipe), 'model': MODEL, 'reasoning_effort': 'medium'}
    ref = content_digest(shared)
    common = pair['differential']['control_inventory'] | {'common_profile': ref}
    pair['differential'].update(shared_definition_digest=ref, control_inventory=common,
                                treatment_inventory=common | pair['differential']['candidate_inventory'])
    for arm in ('control', 'treatment'):
        cfg = pair[arm]['config']
        assert cfg['reasoning_efforts'] == ['medium']
        assert cfg['model_constraints']['allowed_model_ids'] == ['gpt-6-astra']
        cfg['model_constraints']['allowed_model_ids'] = [MODEL]
        pair[arm]['id'] = 'skillsbench-react-sol.' + arm
        cfg['adapter_id'] = 'codex-app-server:skillsbench-react-sol-' + arm
        cfg['managed_worker']['worker_id'] = 'skillsbench-react-sol-' + arm
    pair = WorkerPairInspection.model_validate(pair)
    assert {arm: engine.binding_from_config(getattr(pair, arm).managed_host_config().managed_worker).image
            for arm in ('control', 'treatment')} == prior['worker_image_ids']
    assert all(getattr(pair, arm).managed_host_config().artifact
               == getattr(baseline, arm).managed_host_config().artifact for arm in ('control', 'treatment'))
    return case, recipe, env, cases, pair, shared


def grader_current():
    env = AssessmentEnvironment.model_validate(read(DEFS / 'react-environment.json'))
    proof = read(HERE / 'self-contained-result.json')
    assert proof['passed'] and proof['accounting_settled'] and proof['image']['id'] == env.container_image
    assert engine.docker('image', 'inspect', '--format', '{{.Id}}', env.container_image) == env.container_image
    return env


def inspect_selected(review):
    assert verification_source_digest(ROOT) == review['source_sha256']
    assert not EXEC.exists() and not (HERE / 'sol-managed-started.json').exists()
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    assert all(sha(path) == expected for path, expected in review['pins'].items())
    assert first['snapshot'](review['database']) == review['grant']
    proxy = read(engine.PREVIOUS / 'operation-review.json')
    assert engine.proxy_state(proxy) == proxy['proxy_metadata'] == review['proxy']
    case, = review['cases']
    recipe = RecipeDefinition.model_validate(read(case['recipe']))
    pair = WorkerPairInspection.model_validate(read(case['pair']))
    shared = read(case['shared'])
    env = grader_current()
    require_environment(recipe, env)
    assert content_digest(env) == case['grader_environment_digest']
    assert content_digest(recipe) == case['recipe_digest'] and content_digest(pair) == case['pair_digest']
    assert content_digest(shared) == pair.differential.shared_definition_digest
    cases = IntegrationCaseSet.model_validate(read(DEFS / 'react-integration-cases.json'))
    assert content_digest(cases) == case['integration_case_set_digest'] and len(cases.cases) == 1
    assert cases.cases[0].case_id == case['task_id']
    for arm in ('control', 'treatment'):
        config = getattr(pair, arm).managed_host_config()
        worker = engine.binding_from_config(config.managed_worker)
        assert worker.image == review['worker_image_ids'][arm]
        assert engine.docker('image', 'inspect', '--format', '{{.Id}}', worker.image) == worker.image
        assert not config.store_prompt and not config.store_output
        assert tuple(config.model_constraints.allowed_model_ids) == (MODEL,) == (review['model'],)
        assert tuple(config.reasoning_efforts) == (review['reasoning_effort'],)
    return proxy, case, recipe, pair, shared, env


def freeze():
    prior = read(first['REVIEW'])
    unused = read(sealed['REVIEW'])
    assert unused['model'] == 'gpt-6-astra' and not (HERE / 'sealed-managed-started.json').exists()
    assert not (HERE / 'sealed-managed-approval.json').exists()
    current = first['snapshot'](prior['database'])
    assert utc_now() < datetime.fromisoformat(current['expires_at'])
    case, recipe, env, cases, pair, shared = definitions(prior)
    assert not DEFS.exists()
    DEFS.mkdir(mode=0o700)
    for name, model in (('recipe', recipe), ('environment', env), ('integration-cases', cases), ('pair', pair)):
        save(DEFS / ('react-' + name + '.json'), model.model_dump(mode='json'))
    save(DEFS / 'react-shared.json', shared)
    workflow = read(sealed['CORRECTED'])
    config = workflow['configurations']['software-engineering']
    config.pop('preparation')
    config['benchmark_recipe'] = engine.binding(DEFS / 'react-recipe.json')
    save(DEFS / 'workflow.json', workflow)
    paths = [Path(__file__).resolve(), sealed['REVIEW'], Path(sealed['__file__']),
             Path(draft['__file__']), *sorted(DEFS.glob('*.json'))]
    case.update(recipe=str(DEFS / 'react-recipe.json'), recipe_digest=content_digest(recipe),
                grader_environment=str(DEFS / 'react-environment.json'), grader_environment_digest=content_digest(env),
                grader_image_id=env.container_image, pair=str(DEFS / 'react-pair.json'), pair_digest=content_digest(pair),
                shared=str(DEFS / 'react-shared.json'), integration_case_set_digest=content_digest(cases))
    review = {
        'scope': 'Sol-only React engineering run after exact worker catalogue and collector checks.',
        'supersedes_unstarted_astra_review': sha(sealed['REVIEW']),
        'documentation': [OFFICIAL_MODEL, OFFICIAL_CODEX],
        'pins': unused['pins'] | {str(path): sha(path) for path in paths},
        'source_sha256': prior['source_sha256'], 'database': prior['database'], 'definitions': str(DEFS), 'work': str(EXEC),
        'grant': current, 'proxy': prior['proxy'], 'cases': [case], 'worker_image_ids': prior['worker_image_ids'],
        'maximum_operations': 71, 'maximum_model_turns': 1, 'maximum_reserved_seconds': 3900,
        'maximum_cash_usd': '0', 'model': MODEL, 'reasoning_effort': 'medium',
        'account_model_availability': 'Requires zero-turn App Server model/list and reviewed identity on both workers.',
        'fresh_worker_inspections': 2, 'no_model_fallback': True, 'downloads': False, 'builds': 0,
        'automatic_retries': False, 'comparisons': 'PAUSED', 'expires_at': current['expires_at'],
    }
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
    assert read(HERE / 'sol-managed-approval.json') == {'approved': True, 'review_sha256': identity}
    proxy, case, recipe, pair, shared, protected = inspect_selected(review)
    EXEC.mkdir(mode=0o700)
    selected = {'react': (case, recipe, pair, shared)}
    owner['configure'](engine, review, selected)
    engine.emit = lambda name, value: save(HERE / ('sol-' + name), value)
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
    save(HERE / 'sol-managed-started.json', {'review_sha256': identity, 'automatic_retries': False, 'comparisons': 'PAUSED'})
    original_reserve = engine.budget.install(repo, repo.store._connection, initial, review)
    original_collect = engine.inspection.collect
    outcome = {'review_sha256': identity, 'passed': False, 'comparisons': 'PAUSED', 'model_turns_reserved': 0}
    overhead, proxy_started, excluded = None, False, 0.
    begin = time.perf_counter()
    setup_before = {row[0] for row in repo.store._connection.execute("SELECT id FROM assessment_records WHERE kind='setup_cost'")}
    phase = 'scope and rights preparation'
    try:
        subject = service.inspect_local(engine.prepared.SKILL, kind='skill')
        repo.put('recipe', recipe.recipe_id, recipe)
        local = AssessmentEnvironment(environment_id='react-sol-managed-preparation-20261108',
            kind='trusted_local', identity={'source_digest': review['source_sha256'], 'review': identity})
        repo.put('environment', content_digest(local), local)
        bootstrap = engine.materialization(repo, 'react-sol-managed-overhead-20261108', subject, recipe, local)
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
            review['source_sha256'], run_tag='react-sol-20261108')
        operations, turns, seconds = engine.measure_allowance(allowance)
        assert turns == 1
        engine.budget.require_room(engine.previous.counters(repo), initial,
            AssessmentLimits(max_operations=operations, max_model_turns=turns, max_elapsed_seconds=seconds), review)
        save(HERE / 'sol-managed-dispatch-ready.json', {'review_sha256': identity, 'plan_id': plan.plan_id,
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
                       '--engineering-review', ref, output='sol-managed-run-cli.json', timeout=2100)
        finally:
            excluded += time.perf_counter() - nested
        source = SourcePin.model_validate(read(engine.PREVIOUS / 'source.json'))
        outcome['workload'] = engine.verify_trial(service, plan, pair, pair.treatment.managed_host_config(), source, target)
        phase = 'ordinary CLI report'
        nested = time.perf_counter()
        try:
            engine.cli('report', *common, '--operation-id', 'render', '--report-id', outcome['workload']['report_id'],
                       '--output', EXEC / 'react-report', output='sol-managed-report-cli.json')
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
            save(HERE / 'sol-managed-result.json', outcome)
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
