"""Execute the two exact SkillsBench engineering journeys once."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from aeep.assessment.boundary import BoundaryProbeDefinition, require_candidate_access, require_conformance
from aeep.assessment.extensions import grader_name
from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (
    AssessmentBudgetAmendment, AssessmentEnvironment, AssessmentLimits, AssessmentPlan,
    AssessmentScopeAmendment, AssessmentSetupCost, AssessmentSetupRequest, ConformanceProbeRequest,
    IncrementalExperiment, IntegrationCaseSet, RecipeMaterializationRequest, UtilityPolicy, content_digest,
)
from aeep.assessment.service import AssessmentService
from aeep.benchmarking import BenchmarkTrial
from aeep.hosts import codex_pair_inspection as inspection
from aeep.hosts.workers import binding_from_config
from aeep.models import ResourceVector, ValidationSpec, utc_now
from aeep.router import Router
from aeep.templates import render
from aeep_toolkit.installation import manifest_digest
from aeep_toolkit.managed import AEEPAssessmentAdapter
from aeep_toolkit.models import ExtensionManifest, SourcePin
from aeep_toolkit.stack_readiness import EngineeringRunReview, require_engineering_run
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_preparation import TaskRightsReview

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
ROOT = HERE.parents[3]
PREVIOUS = REPORTS / 'integration-snapshot-correction-20261103'
PILOT = REPORTS / 'repository-usefulness-pilot-20261029'
BASE = ROOT.parent / 'aeep-agent-router/.aeep/live-review-v3/aeep.json'
SHA = '036e3cb4c53b06437d9ee336ea800897fc871288b54d161aafd25452bb50277f'
OVERHEAD = 60
RESERVE = 50 * 1024**3


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError('Reviewed preparation helper unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepared = load_module('prepare_skillsbench_engineering', HERE / 'prepare-engineering.py')
budget = load_module('engineering_budget_guard', PILOT / 'review-budget.py')
collector = load_module('collector_denial_programs', PILOT / 'run-collector.py')
evidence = load_module('trial_evidence', PILOT / 'trial-evidence.py')
previous = load_module('prior_verified_engineering_driver', PREVIOUS / 'run.py')
WORK = prepared.PRIVATE
MANIFEST = WORK / 'aeep.json'
CAMPAIGNS = WORK / 'campaigns'
PATH_ENV = {'PATH': '/usr/bin:/bin:/usr/local/bin', 'PYTHONPATH': str(ROOT / 'src'),
            'PYTHONDONTWRITEBYTECODE': '1', 'LC_ALL': 'C'}


def emit(name, value):
    prepared.write(HERE / name, value)


def scoped_approval(repo, requests, extra=()):
    # Reuse the existing exact amendment builder but retain raw definitions privately.
    previous.emit = lambda name, value: prepared.write(WORK / name, value)
    previous.approve(repo, requests, extra=extra)


def docker(*args):
    return previous.docker(*args)


def check_review():
    review = prepared.require_review()
    if prepared.sha(HERE / 'engineering-dispatch-review.json') != SHA:
        raise RuntimeError('Dispatch authority differs')
    if (utc_now() >= datetime.fromisoformat(review['grant']['time_only_amendment']['expires_at'])
            or shutil.disk_usage(ROOT).free < RESERVE):
        raise RuntimeError('Review expired or host reserve unavailable')
    return review


def binding(path):
    return {'path': str(path), 'sha256': prepared.sha(path)}


def preflight(review):
    selected = prepared.pairs(review)
    old_proxy = prepared.read(PREVIOUS / 'operation-review.json')
    proxy = review['proxy']
    if old_proxy['proxy_name'] != proxy['proxy_name']:
        raise RuntimeError('Reviewed proxy name differs')
    if proxy_state(old_proxy) != old_proxy['proxy_metadata']:
        raise RuntimeError('Exact proxy is unavailable or not stopped')
    for domain, (case, recipe, pair, shared) in selected.items():
        for suffix, record in [('pair', pair.model_dump(mode='json')), ('shared', shared)]:
            if prepared.read(WORK / f'{domain}-{suffix}.json') != record:
                raise RuntimeError('Stored pair or shared inventory changed')
        for image in (case['grader_image_id'], *(binding_from_config(getattr(pair, role).managed_host_config().managed_worker).image
                                               for role in ('control', 'treatment'))):
            if docker('image', 'inspect', '--format', '{{.Id}}', image) != image:
                raise RuntimeError('Retained image drift')
        grader = grader_environment(domain)
        if (content_digest(grader) != case['grader_environment_digest']
                or grader.container_image != case['grader_image_id'] or grader.network):
            raise RuntimeError('Protected grader changed')
        raw_cases = IntegrationCaseSet.model_validate(prepared.read(prepared.DEFINITIONS / f'{domain}-integration-cases.json'))
        if content_digest(raw_cases) != case['integration_case_set_id'] or raw_cases.recipe_digest != content_digest(recipe):
            raise RuntimeError('Reviewed inert task set changed')
        rights = read_rights(case)
        if not rights.provider_disclosure_allowed or not rights.local_execution_allowed:
            raise RuntimeError('Approved rights do not permit the exact task')
    return selected, old_proxy


def proxy_state(old):
    return json.loads(docker('inspect', '--format', old['proxy_inspect_format'], old['proxy_name']))


def read_rights(case):
    path = REPORTS / 'skillsbench-task-disclosure-20261105' / (case['task_id'] + '.json')
    rights = TaskRightsReview.model_validate(prepared.read(path))
    if content_digest(rights) != case['rights_review_ref'] or rights.task_id != case['task_id']:
        raise RuntimeError('Reviewed rights changed')
    return rights


def grader_environment(domain):
    folder = 'skillsbench-sales-dependencies-20261105' if domain == 'sales' else 'skillsbench-contained-graders-20261105'
    return AssessmentEnvironment.model_validate(prepared.read(REPORTS / folder / 'grader-execution' / f'{domain}-environment.json'))


def cli(*arguments, output=None, timeout=90):
    run = subprocess.run([sys.executable, '-B', '-m', 'aeep_toolkit', 'workflow', *map(str, arguments)],
                         cwd=ROOT, env=PATH_ENV, capture_output=True, timeout=timeout)
    result = {'exit_code': run.returncode,
              'stdout_sha256': hashlib.sha256(run.stdout).hexdigest(),
              'stderr_sha256': hashlib.sha256(run.stderr).hexdigest()}
    if output is not None:
        emit(output, result)
    if run.returncode:
        (WORK / (output or f'{arguments[0]}-cli-failure.json')).with_suffix('.stderr').write_bytes(run.stderr)
        raise RuntimeError(f'Ordinary CLI {arguments[0]} failed')
    return json.loads(run.stdout)


def worker_requests(service, domain, pair, recipe, subject, source):
    repo = service.repository
    rec_ref = repo.put('recipe', recipe.recipe_id, recipe)
    sources = []
    for role in ('control', 'treatment'):
        executor = getattr(pair, role)
        worker = binding_from_config(executor.managed_host_config().managed_worker)
        environment = AssessmentEnvironment(environment_id=f'skillsbench-{domain}-inspection-{role}',
            kind='codex_sandbox', identity={'source_digest': source, 'image': worker.image})
        env_ref = repo.put('environment', content_digest(environment), environment)
        probe = BoundaryProbeDefinition(name='worker_inspection', executor=executor, expected={})
        probe_ref = repo.put('boundary_probe_definition', content_digest(probe), probe)
        request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v2',
            operation='worker_inspection', subject_digest=content_digest(subject), recipe_digest=rec_ref,
            mapping_digest=probe_ref, environment_digest=env_ref, authorization_id='onboarding',
            definition_digests=[rec_ref, env_ref, probe_ref], worker_digest=worker.digest(),
            executable_dependencies=runtime_dependencies())
        repo.put('conformance_request', request.plan_id, request)
        sources.append(request.plan_id)
    draft = inspection.prepare_pair(service, *sources, pair)
    requests = [ConformanceProbeRequest.model_validate(item) for item in draft['requests']]
    scoped_approval(repo, requests)
    return [request.plan_id for request in requests]


def inspect_collector(original):
    async def collect(adapter, config, journal, recheck):
        facts = await original(adapter, config, journal, recheck)
        if not facts.get('inspection_complete'):
            return facts
        worker = binding_from_config(config.managed_worker)
        container = 'aeep-' + hashlib.sha256(adapter._worker_process_id.encode()).hexdigest()[:32]
        result = await inspection.docker(worker, 'exec', '-i', '--user', '65534:65534',
                                         container, 'python3', '-I', '-c', collector.PORTS)
        ports = json.loads(result)['loopback_listener_ports']
        if len(ports) != 1 or type(ports[0]) is not int or not 0 < ports[0] < 65536:
            raise RuntimeError('Collector listener identity is indeterminate')
        recheck()
        program = collector.DENIED.replace('PORT', str(ports[0]))
        digest = hashlib.sha256(program.encode()).hexdigest()
        journal.append('action.started', 'collector-access-start', action_digest=digest)
        observed = await inspection.command(adapter, program)
        journal.append('action.completed', 'collector-access-complete', action_digest=digest)
        journal.append('artifact.created', 'collector-denied-result', evidence_ref=content_digest(observed))
        if observed != {'collector_connection_denied': True}:
            raise RuntimeError('Trial code can reach the trusted collector')
        facts['collector_boundary'] = observed
        return facts
    return collect


def readiness(repo, domain, ids, pair, source):
    path = WORK / f'{domain}-readiness.json'
    cli('prepare-worker-readiness', '--manifest', MANIFEST, '--control-request', ids[0],
        '--treatment-request', ids[1], '--output', path, output=f'engineering-{domain}-readiness-cli.json')
    value = prepared.read(path)
    if value['reviewed'] or value['workers_started'] or value['execution_authorized']:
        raise RuntimeError('Unexpected authority in readiness draft')
    amendment = AssessmentScopeAmendment.model_validate(value['amendment'])
    repo.approve_bundle(amendment, value['definitions'])
    for role, row in value['boundaries'].items():
        if row['observed_probe_count'] != 11:
            raise RuntimeError('Containment observation count differs')
        record = require_conformance(repo, row['conformance_digest'], source_digest=source,
                                     worker_digest=row['worker_digest'], identity_digest=row['identity_digest'])
        require_candidate_access(repo, record, pair.differential, available=role == 'treatment')
    return value


def materialization(repo, identity, subject, recipe, environment, *, mapping=None, definitions=()):
    request = RecipeMaterializationRequest(plan_id=identity, subject_digest=content_digest(subject),
        recipe_digest=content_digest(recipe), mapping_digest=mapping or content_digest(recipe),
        environment_digest=content_digest(environment), authorization_id='onboarding',
        definition_digests=list(dict.fromkeys([content_digest(recipe), content_digest(environment), *definitions])),
        seed=0)
    repo.put('recipe_materialization_request', request.plan_id, request)
    return request


def workflow_base(review):
    workflow = prepared.read(prepared.DEFINITIONS / 'workflow.json')
    original = {name: Path(workflow[name]['path']) for name in ('registry', 'policy')}
    if any(prepared.sha(path) != workflow[name]['sha256'] for name, path in original.items()):
        raise RuntimeError('Original registry or policy changed')
    registry, policy = (prepared.read(original[name]) for name in ('registry', 'policy'))
    origins = ['https://auth.openai.com', 'https://chatgpt.com', 'https://api.openai.com']
    inventory = {
        'aeep-evaluator': {
            'purpose': 'Managed AEEP runner for the two approved engineering turns',
            'pin': content_digest({'source': review['source_sha256'], 'worker_images': review['worker_image_ids'],
                                   'proxy': review['proxy']}),
            'rights': 'Exact approval for these two public SkillsBench engineering inputs only.',
            'effects': 'Reuse the four reviewed worker images and the existing scoped Codex proxy.',
        },
        'skillsbench': {
            'purpose': 'Two SkillsBench tasks with their protected pinned verifier images',
            'pin': content_digest(review['cases']),
            'rights': 'Exact reviewed public task inputs. Oracle, grader and bundled skills remain private.',
            'effects': 'Reuse the two verified local grader images and the original public input archives.',
        },
    }
    for item in registry['extensions']:
        identity = item['extension_id']
        if identity not in inventory:
            continue
        facts = inventory[identity]
        item.update(purpose=facts['purpose'], status='experimental', blockers=[],
                    install_effects=[facts['effects']],
                    rollback='Keep retained images. Stop only reviewed owned runtime sessions.')
        item['source'].update(artifact_sha256=facts['pin'], data_rights=facts['rights'])
        if identity == 'aeep-evaluator':
            item['source']['revision'] = '1260dffb474987d17c32e169a4398145fa7d9d35'
            item['permissions'].update(network_destinations=origins, authentication='host_owned',
                                       financial_exposure='subscription_unpriced')
        policy['allowed_data_rights'].append(facts['rights'])
        policy['reviewed_dependency_manifests'].append(manifest_digest(ExtensionManifest.model_validate(item)))
    policy['allowed_network_destinations'] = origins
    policy['allowed_authentication'].append('host_owned')
    policy['allowed_financial_exposure'].append('subscription_unpriced')
    policy['free_disk_bytes'] = shutil.disk_usage(ROOT).free
    for name, value in [('registry', registry), ('policy', policy)]:
        path = WORK / f'engineering-{name}.json'
        prepared.write(path, value)
        workflow[name] = binding(path)
    return workflow


def draft(service, domain, selected, subject, boundary, workflow, source, *, run_tag='20261105'):
    case, recipe, pair, _shared = selected
    repo = service.repository
    protected = grader_environment(domain)
    env = protected.model_copy(update={
        'environment_id': f'skillsbench-{domain}-engineering-grader-{run_tag}',
        'identity': {**protected.identity, 'source_digest': source},
        'conformance_digests': {getattr(pair, role).id: row['conformance_digest']
                                for role, row in boundary['boundaries'].items()},
        'differential_conformance_digest': boundary['differential_conformance_digest'],
    })
    repo.put('environment', env.environment_id, env)
    old_cases = IntegrationCaseSet.model_validate(prepared.read(prepared.DEFINITIONS / f'{domain}-integration-cases.json'))
    task = old_cases.cases[0]
    truth = task.validators[-1].config['expected']
    graded = task.model_copy(update={'validators': [ValidationSpec(kind='callback',
        config={'name': grader_name(task.action.input, truth), 'expected': truth})]})
    cases = old_cases.model_copy(update={'request_id': f'skillsbench-{domain}-engineering-{run_tag}',
        'environment_digest': content_digest(env), 'cases': [graded]})
    cases_ref = repo.put('integration_case_set', content_digest(cases), cases)
    experiment = IncrementalExperiment(stage='qualification', exposure='required', environment=pair.differential,
        utility=UtilityPolicy(benefit_dimensions=['wall_time_ms'], guardrail_dimensions=['wall_time_ms']))
    experiment_ref = repo.put('experiment', content_digest(experiment), experiment)
    setup_scope = materialization(repo, f'skillsbench-{domain}-preparation-{run_tag}', subject, recipe, env,
                                  definitions=(cases_ref, experiment_ref))
    scoped_approval(repo, [setup_scope])
    req = AssessmentSetupRequest(schema_version='assessment.setup.v2', authorization_id='onboarding',
        subject_id=subject.subject_id, recipe_id=recipe.recipe_id, environment_id=env.environment_id,
        candidate_id=pair.treatment.id, baseline_id=pair.control.id, structure='controlled_agent',
        integration_case_set_id=cases_ref, experiment_id=experiment_ref)
    configuration = case['configuration']
    request_path = WORK / f'{domain}-setup.json'
    prepared.write(request_path, req.model_dump(mode='json'))
    candidate_source = PREVIOUS / 'source.json'
    target = workflow['configurations'][configuration] | {
        'candidate': {'path': str(prepared.SKILL),
                      'sha256': SourcePin.model_validate(prepared.read(candidate_source)).artifact_sha256},
        'preparation': {'source': binding(candidate_source), 'manifest': binding(MANIFEST), 'request': binding(request_path)},
    }
    workflow_path = WORK / f'{domain}-workflow.json'
    prepared.write(workflow_path, workflow | {'configurations': {configuration: target}})
    common = ('--workflow', workflow_path, '--configuration', configuration)
    preview = cli('plan', *common)
    if preview['blockers'] != ['canonical plan preparation is selected but has not been performed']:
        prepared.write(WORK / f'{domain}-preview.json', preview)
        raise RuntimeError(f'{configuration} CLI preview has unresolved requirements')
    output = WORK / f'{domain}-prepared'
    summary = cli('prepare', *common, '--write-plan', output, '--directory', CAMPAIGNS,
                  '--reviewed-digest', preview['review_sha256'], output=f'engineering-{domain}-prepare-cli.json')
    plan = AssessmentPlan.model_validate_json((output / 'plan.json').read_bytes())
    if (summary['plan_digest'] != content_digest(plan) or plan.blocked_reasons or plan.scheduler_digest is not None
            or plan.suite.cases != [graded] or plan.suite.repetitions != 1 or plan.suite.conditions != ['fresh-worker']
            or [route.executor_id for route in plan.suite.routes] != [pair.treatment.id]):
        raise RuntimeError('Exact prepared case, route or evaluator differs')
    engineering = EngineeringRunReview(plan_digest=content_digest(plan), implementation_source=source,
        scope_request_id=f'skillsbench-{domain}-execution-{run_tag}', case_ids=(case['task_id'],), maximum_model_turns=1)
    engineering_ref = repo.put('toolkit_engineering_run', content_digest(engineering), engineering)
    scope = materialization(repo, engineering.scope_request_id, subject, recipe, env,
                            mapping=plan.mapping_digest, definitions=(*plan.definition_digests, engineering_ref))
    bound = output / 'workflow.json'
    accounting = WorkflowAccountingDefinition(workflow_sha256=prepared.sha(bound),
        configurations=(configuration,), operations=('run', 'report'), source_digest=source,
        manifest_path=str(MANIFEST), manifest_sha256=prepared.sha(MANIFEST), request=scope,
        maximum_overhead_seconds=OVERHEAD)
    accounting_path = WORK / f'{domain}-accounting.json'
    prepared.write(accounting_path, accounting.model_dump(mode='json'))
    scoped_approval(repo, [scope], extra=[('toolkit_workflow_accounting', accounting), ('plan', plan)])
    require_engineering_run(repo, engineering_ref, plan=plan, source_digest=source)
    service._verify_dependencies(plan)
    run_preview = cli('plan', '--workflow', bound, '--configuration', configuration)
    if run_preview['blockers'] or run_preview['assessment']['backend_review']['plan_sha256'] != content_digest(plan):
        raise RuntimeError('Bound workflow CLI readiness changed')
    allowed = service.budget_preview(plan.plan_id)
    if allowed['minimum_trial_model_turns'] != 1 or not allowed['campaign_allowance']['fits_remaining']:
        raise RuntimeError('One-turn canonical allowance is unavailable')
    return plan, engineering_ref, accounting_path, bound, run_preview['review_sha256'], allowed


def measure_allowance(allowed):
    upper = allowed['campaign_allowance']['upper_allowance']
    return (upper['operations'] + 2, upper['model_turns'], upper['elapsed_seconds'] + 2 * OVERHEAD)


def verify_trial(service, plan, pair, config, source, result_root):
    adapter = AEEPAssessmentAdapter(service, plan.plan_id, source)
    job = adapter.preview()['job']
    if job is None or job['state'] != 'complete' or job['error_code'] is not None:
        raise RuntimeError('Canonical managed trial did not settle')
    bundle = adapter.normalize(job['report_id'])
    if len(bundle.runs) != 1:
        raise RuntimeError('Unexpected number of observed trials')
    run = bundle.runs[0]
    path = service.directory / plan.plan_id / 'campaign.sqlite3'
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
        rows = list(connection.execute('SELECT payload_json FROM trials'))
        if len(rows) != 1:
            raise RuntimeError('Canonical trial positions differ')
        trial = BenchmarkTrial.model_validate_json(rows[0][0])
        prompt = dict(plan.suite.cases[0].action.input)
        artifact = config.artifact
        prompt.pop(artifact.input_field)
        prompt.update(input_path='/workspace/' + artifact.input_name, output_path='/workspace/' + artifact.output_name)
        instruction = str(render(config.instructions, {'input': prompt}))
        digest = hashlib.sha256(instruction.encode()).hexdigest()
        record = evidence.read_trial(connection, trial, pair, {(trial.case_id, 'skill'): digest},
                                     service.directory / plan.plan_id / 'attempts')
    prepared.write(WORK / f'{plan.candidate_id}-trial-evidence.json', record)
    evidence.require_complete(record)
    details = adapter.details
    if (run.status != 'completed' or run.retries != 0 or run.verification not in {'pass', 'fail'}
            or details['normalization_gaps'] or details['unresolved_operations']
            or not record.get('candidate_loading') or record['candidate_loading']['instructions_loaded'] is not True
            or not (result_root / 'report.html').is_file()):
        raise RuntimeError('Required loading, normalization or report evidence is incomplete')
    return {'plan_id': plan.plan_id, 'report_id': job['report_id'], 'task_id': trial.case_id,
            'trial_id': trial.trial_id, 'receipt_id': run.receipt_ids[0],
            'score': next(item.quality_score for item in trial.case_validation if item.kind.value == 'callback' and item.trust.value == 'verified'), 'task_passed': record['task_grade'],
            'tokens': record['token_capture'], 'candidate_loading': record['candidate_loading'],
            'wall_time_ms': run.wall_time_ms, 'retries': run.retries,
            'report': str(result_root / 'report.html')}


def scoped_setups(repo, before, subject, bootstrap):
    nested = 0.
    ids = []
    for identity, raw in repo.store._connection.execute(
            "SELECT id,payload_json FROM assessment_records WHERE kind='setup_cost' "
            "AND json_extract(payload_json,'$.subject_digest')=?", (content_digest(subject),)).fetchall():
        if identity in before:
            continue
        cost = AssessmentSetupCost.model_validate_json(raw)
        state = repo.store._connection.execute('SELECT state FROM assessment_operations WHERE id=?', (identity,)).fetchone()
        if state is None:
            repo.reserve(bootstrap, identity, AssessmentLimits(max_operations=1,
                         max_elapsed_seconds=max(cost.elapsed_seconds, 0.000001)), stage=cost.stage)
            repo.finish_operation(identity, elapsed_seconds=cost.elapsed_seconds,
                resources=ResourceVector(latency_ms=cost.elapsed_seconds * 1000, cpu_ms=cost.cpu_ms))
        elif state[0] != 'complete':
            raise RuntimeError('A new setup cost has uncertain settlement')
        nested += cost.elapsed_seconds
        ids.append(identity)
    return nested, ids


def reserved(repo):
    return dict(repo.store._connection.execute(
        "SELECT id,state FROM assessment_operations WHERE grant_id='onboarding' AND state='reserved'"))


async def execute(review, selected, old_proxy):
    origin = Router.from_manifest(BASE)
    manifest = origin.manifest.model_copy(update={'database': origin.store.path,
        'executors': [getattr(item[2], role) for item in selected.values() for role in ('control', 'treatment')]})
    await origin.close()
    prepared.write(MANIFEST, manifest.model_dump(mode='json'))
    router = Router.from_manifest(MANIFEST)
    service = AssessmentService(router, CAMPAIGNS)
    repo = service.repository
    initial = previous.counters(repo)
    old_reserved = reserved(repo)
    if ([*initial[:3], str(initial[3])] != review['grant']['counters_at_preparation']
            or len(old_reserved) != review['grant']['historical_reserved_count']):
        await router.close()
        raise RuntimeError('Prior grant counters or historical reservations changed')
    current = repo.effective_grant('onboarding')
    amendment = AssessmentBudgetAmendment.model_validate(review['grant']['time_only_amendment'])
    if (amendment.limits != current.limits or amendment.expires_at <= current.expires_at
            or current.remote_disclosure or 'codex' not in current.allowed_destinations):
        await router.close()
        raise RuntimeError('Scope or time-only amendment differs')
    emit('engineering-started.json', {'review_sha256': SHA, 'counters_before': initial,
         'historical_reserved': old_reserved, 'automatic_retry': False, 'comparisons': 'PAUSED'})
    original_reserve = budget.install(repo, repo.store._connection, initial, review)
    original_collect = inspection.collect
    phase = 'time-only grant amendment'
    report = {'passed': False, 'reviews': {}, 'plans': {}, 'domains': {},
              'comparisons': 'PAUSED', 'candidate_usefulness': 'NOT_ASSESSED', 'selection_usefulness': 'NOT_ASSESSED'}
    started = time.perf_counter()
    excluded = 0.
    overhead_id = None
    proxy_started = False
    setup_before = {row[0] for row in repo.store._connection.execute("SELECT id FROM assessment_records WHERE kind='setup_cost'")}
    try:
        repo.approve_budget_amendment(amendment)
        if previous.counters(repo) != initial:
            raise RuntimeError('Expiry amendment changed existing counters')
        phase = 'scope and proxy preparation'
        subject = service.inspect_local(prepared.SKILL, kind='skill')
        first = next(iter(selected.values()))[1]
        repo.put('recipe', first.recipe_id, first)
        local = AssessmentEnvironment(environment_id='skillsbench-owned-workflow-preparation',
            kind='trusted_local', identity={'implementation_source': review['source_sha256'], 'review': SHA})
        repo.put('environment', content_digest(local), local)
        bootstrap = materialization(repo, 'skillsbench-workflow-overhead-20261105', subject, first, local)
        scoped_approval(repo, [bootstrap])
        overhead_id = bootstrap.plan_id + ':exclusive'
        repo.reserve(bootstrap, overhead_id, AssessmentLimits(max_operations=1, max_elapsed_seconds=180),
                     stage='owned_workflow_preparation_and_proxy_overhead')
        for case, _recipe, _pair, shared in selected.values():
            repo.put('shared_environment_definition', content_digest(shared), previous.Document(value=shared))
            right = read_rights(case)
            ref = repo.put('toolkit_task_rights', content_digest(right), right)
            repo.review(ref)
        check_review()
        if proxy_state(old_proxy) != old_proxy['proxy_metadata']:
            raise RuntimeError('Reviewed proxy changed before startup')
        proxy_started = True
        docker('start', old_proxy['proxy_name'])
        active = proxy_state(old_proxy)
        if (not active['Running'] or active['Id'] != review['proxy']['proxy_id']
                or active['Image'] != review['proxy']['proxy_image']
                or active['Networks']['aeep-reviewed-model-private']['IPAddress'] != '172.18.0.2'):
            raise RuntimeError('Proxy identity or worker destination changed')
        boundaries = {}
        for domain, (_case, recipe, pair, _shared) in selected.items():
            phase = f'{domain} worker and collector isolation'
            check_review()
            ids = worker_requests(service, domain, pair, recipe, subject, review['source_sha256'])
            inspection.collect = inspect_collector(original_collect)
            began = time.perf_counter()
            try:
                boundary = await inspection.execute_pair(service, *ids)
            finally:
                inspection.collect = original_collect
                excluded += time.perf_counter() - began
            observed = {role: repo.get('worker_pair_inspection', 'pair-inspection:' + identity)['observations']
                        for role, identity in zip(('control', 'treatment'), ids, strict=True)}
            report['reviews'][domain] = {'requests': ids, 'boundaries': boundary,
                'worker_outcomes': {role: {key: facts.get(key) for key in (
                    'cleanup_confirmed', 'cleanup_error_type', 'failure_stage', 'failure_type', 'full_conformance',
                    'probes_match')} for role, facts in observed.items()}}
            if any(facts.get('cleanup_error_type') or ('inspection' in facts and not facts.get('cleanup_confirmed'))
                   for facts in observed.values()):
                report['worker_cleanup_uncertain'] = True
                raise RuntimeError('Worker cleanup could not be verified')
            if not boundary['probes_match']:
                report['worker_probe_names'] = {role: sorted(facts.get('observed_probes', {}))
                                                for role, facts in observed.items()}
                raise RuntimeError('Fresh worker conformance did not pass')
            boundaries[domain] = readiness(repo, domain, ids, pair, review['source_sha256'])
        phase = 'both ordinary CLI plans'
        workflow = workflow_base(review)
        plans = {}
        for domain, item in selected.items():
            plans[domain] = draft(service, domain, item, subject, boundaries[domain], workflow, review['source_sha256'])
            plan, ref, _accounting, _bound, workflow_ref, allowed = plans[domain]
            report['plans'][domain] = {'plan_id': plan.plan_id, 'plan_digest': content_digest(plan),
                'workflow_review_sha256': workflow_ref, 'execution_review_ref': ref,
                'upper_allowance': allowed['campaign_allowance']['upper_allowance']}
        total = tuple(map(sum, zip(*(measure_allowance(item[-1]) for item in plans.values()), strict=True)))
        budget.require_room(previous.counters(repo), initial,
            AssessmentLimits(max_operations=total[0], max_model_turns=total[1], max_elapsed_seconds=total[2]), review)
        emit('engineering-dispatch-ready.json', {'review_sha256': SHA, 'plans': report['plans'],
                                                'both_worker_pairs_passed': True, 'counters': previous.counters(repo)})
        source = SourcePin.model_validate(prepared.read(PREVIOUS / 'source.json'))
        for domain, item in selected.items():
            phase = f'{domain} ordinary CLI run'
            check_review()
            if set(reserved(repo)) - set(old_reserved) - {overhead_id}:
                raise RuntimeError('New unresolved accounting blocks dispatch')
            plan, ref, accounting, bound, workflow_ref, _allowed = plans[domain]
            allowed = service.budget_preview(plan.plan_id)
            operations, turns, seconds = measure_allowance(allowed)
            budget.require_room(previous.counters(repo), initial,
                AssessmentLimits(max_operations=operations, max_model_turns=turns, max_elapsed_seconds=seconds), review)
            common = ('--workflow', bound, '--configuration', item[0]['configuration'], '--manifest', MANIFEST,
                '--directory', CAMPAIGNS, '--reviewed-digest', workflow_ref, '--accounting', accounting)
            result_root = WORK / f'{domain}-result'
            began = time.perf_counter()
            try:
                cli('run', *common, '--operation-id', 'execute', '--output', result_root,
                    '--engineering-review', ref, output=f'engineering-{domain}-run-cli.json', timeout=2100)
            finally:
                excluded += time.perf_counter() - began
            pair = item[2]
            row = verify_trial(service, plan, pair, pair.treatment.managed_host_config(), source, result_root)
            report['domains'][domain] = row
            phase = f'{domain} ordinary CLI report'
            began = time.perf_counter()
            try:
                cli('report', *common, '--operation-id', 'render', '--report-id', row['report_id'],
                    '--output', WORK / f'{domain}-report', output=f'engineering-{domain}-report-cli.json')
            finally:
                excluded += time.perf_counter() - began
        report['passed'] = len(report['domains']) == 2
    except (Exception, asyncio.CancelledError, KeyboardInterrupt) as error:
        # Error logs and private runtime state may contain task or provider data.
        report.update(stopped_phase=phase, error_type=type(error).__name__,
                      error_message=str(error)[:280] if type(error) is RuntimeError else None)
    finally:
        inspection.collect = original_collect
        if proxy_started:
            try:
                docker('stop', '--time', '5', old_proxy['proxy_name'])
                report['proxy_restored_stopped'] = proxy_state(old_proxy) == old_proxy['proxy_metadata']
            except (subprocess.SubprocessError, OSError):
                report['proxy_restored_stopped'] = False
        if overhead_id is not None:
            try:
                nested, cost_ids = scoped_setups(repo, setup_before, subject, bootstrap)
                exclusive = max(0., time.perf_counter() - started - excluded - nested)
                report['overhead'] = {'exclusive_seconds': exclusive, 'excluded_nested_seconds': excluded,
                                      'excluded_setup_seconds': nested, 'setup_cost_ids': cost_ids}
                if report.get('proxy_restored_stopped', not proxy_started) and not report.get('worker_cleanup_uncertain'):
                    repo.finish_operation(overhead_id, elapsed_seconds=exclusive)
            except Exception as error:
                report['accounting_error_type'] = type(error).__name__
        now = reserved(repo)
        report['new_unresolved_reservations'] = sorted(set(now) - set(old_reserved))
        report['historical_reservations_preserved'] = all(now.get(key) == value for key, value in old_reserved.items())
        report['grant_after'] = previous.counters(repo)
        report['charged'] = [report['grant_after'][i] - initial[i] for i in range(3)]
        report['passed'] = (report['passed'] and report.get('proxy_restored_stopped') is True
                            and not report['new_unresolved_reservations'] and report['historical_reservations_preserved']
                            and report['grant_after'][3] == initial[3])
        repo.reserve = original_reserve
        try:
            await router.close()
        finally:
            emit('engineering-result.json', report)
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-approved')
    args = parser.parse_args()
    review = check_review()
    if (HERE / 'engineering-started.json').exists():
        raise SystemExit('A prior exact attempt exists; inspect it without replay.')
    selected, proxy = preflight(review)
    if args.run_approved is None:
        print(json.dumps({'inert_preflight_passed': True, 'domains': list(selected), 'models_started': 0}))
    elif args.run_approved == SHA:
        raise SystemExit(asyncio.run(execute(review, selected, proxy)))
    else:
        raise SystemExit('Exact approved review digest required.')
