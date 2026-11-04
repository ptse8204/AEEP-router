"""Execute one approved two-engine engineering journey through the ordinary CLI."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(HERE))
import integration as prepared

from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.assessment.extensions import grader_name
from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (
    AssessmentAuthorization, AssessmentEnvironment, AssessmentLimits, AssessmentScopeAmendment,
    ConformanceProbeRequest, IncrementalExperiment, IntegrationCaseSet,
    RecipeMaterializationRequest, UtilityPolicy, content_digest,
)
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.benchmarking import BenchmarkCase
from aeep.hosts import codex_pair_inspection as inspection
from aeep.hosts.workers import binding_from_config
from aeep.models import ActionRequest, StrictModel, ValidationSpec
from aeep.router import Router
from aeep_toolkit.managed import plan_preview
from aeep_toolkit.models import SourcePin
from aeep_toolkit.stack_readiness import EngineeringRunReview, require_engineering_run

BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']


from pydantic import model_serializer


class Document(StrictModel):
    value: dict

    @model_serializer(mode='plain')
    def document(self):
        return self.value


def emit(name, value):
    path = HERE / name
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def docker(*args, timeout=30):
    return subprocess.check_output([*DOCKER, *args], text=True,
        stderr=subprocess.PIPE, timeout=timeout).strip()


def counters(repository):
    return tuple(repository.store._connection.execute(
        "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'"
    ).fetchone())


def approve(repository, scopes, extra=()):
    definitions = {}
    for request in scopes:
        for digest in {*request.definition_digests, request.subject_digest, request.recipe_digest,
                       request.mapping_digest, request.environment_digest, content_digest(request)}:
            row = repository.store._connection.execute(
                'SELECT payload_json FROM assessment_records WHERE digest=?', (digest,)).fetchone()
            if row is None:
                raise RuntimeError('Missing canonical definition during bounded preparation')
            definitions[digest] = json.loads(row[0])
    for kind, value in extra:
        digest = repository.put(kind, content_digest(value), value)
        definitions[digest] = value.model_dump(mode='json')
    original = AssessmentAuthorization.model_validate(repository.get('authorization', 'onboarding'))
    amendment = AssessmentScopeAmendment(authorization_id='onboarding',
        authorization_digest=content_digest(original),
        subject_digests=sorted({request.subject_digest for request in scopes}),
        recipe_digests=sorted({request.recipe_digest for request in scopes}),
        environment_digests=sorted({request.environment_digest for request in scopes}),
        reviewed_digests=list(definitions))
    emit('definition-review-' + amendment.amendment_id + '.json', {
        'authority': 'Standing finite definition delegation inside this exact execution/disclosure review',
        'amendment': amendment.model_dump(mode='json'), 'definitions': definitions,
        'no_counter_reset_or_paid_authority': True})
    repository.approve_bundle(amendment, definitions)


def require_assets(review):
    if verification_source_digest(ROOT) != review['source_digest']:
        raise RuntimeError('Current source differs from the approved engineering review')
    for name, digest in review['assets'].items():
        if prepared.sha(Path(name)) != digest:
            raise RuntimeError('Reviewed asset changed')
    if shutil.disk_usage(ROOT).free < review['minimum_free_bytes']:
        raise RuntimeError('50 GiB host reserve blocks execution')
    from datetime import datetime
    from aeep.models import utc_now
    if utc_now() >= datetime.fromisoformat(review['review_expires_at'].replace('Z', '+00:00')):
        raise RuntimeError('Exact engineering review expired')
    checks = prepared.load(Path(review['source_checks']))
    if (checks['source_before'] != review['source_digest'] or checks['source_after'] != review['source_digest']
            or len(checks['checks']) != 13 or not all(item['exit_code'] == 0 for item in checks['checks'])):
        raise RuntimeError('Source verification is incomplete')


def require_image(review, metadata):
    parent = review['parent_metadata']
    if (metadata['Id'] == parent['Id'] or metadata['Layers'][:len(parent['Layers'])] != parent['Layers']
            or len(metadata['Layers']) != len(parent['Layers']) + 5
            or metadata['Size'] - parent['Size'] > 2 * 1024**2
            or any(metadata[key] != parent[key] for key in ('User', 'Workdir', 'Entrypoint'))):
        raise RuntimeError('Reviewed local image changed inherited configuration or layers')


def prepare_inspection(service, pair, recipe, subject):
    repo = service.repository
    recipe_ref = repo.put('recipe', recipe.recipe_id, recipe)
    source_requests = []
    for role in ('control', 'treatment'):
        executor = getattr(pair, role)
        worker = binding_from_config(executor.managed_host_config().managed_worker)
        environment = AssessmentEnvironment(environment_id='ase-stack-inspection-' + role,
            kind='codex_sandbox', identity={'source_digest': verification_source_digest(ROOT),
                'purpose': 'Engineering-only worker and collector containment', 'image': worker.image})
        env_ref = repo.put('environment', content_digest(environment), environment)
        probe = BoundaryProbeDefinition(name='worker_inspection', executor=executor, expected={})
        probe_ref = repo.put('boundary_probe_definition', content_digest(probe), probe)
        request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v2',
            operation='worker_inspection', subject_digest=content_digest(subject), recipe_digest=recipe_ref,
            mapping_digest=probe_ref, environment_digest=env_ref, authorization_id='onboarding',
            definition_digests=[recipe_ref, env_ref, probe_ref], worker_digest=worker.digest(),
            executable_dependencies=runtime_dependencies())
        repo.put('conformance_request', request.plan_id, request)
        source_requests.append(request.plan_id)
    value = inspection.prepare_pair(service, *source_requests, pair)
    requests = [ConformanceProbeRequest.model_validate(item) for item in value['requests']]
    approve(repo, requests)
    emit('worker-definitions.json', value)
    return requests


def prepare_plan(service, pair, recipe, subject, boundary, engine):
    repo = service.repository
    environment = AssessmentEnvironment(environment_id='ase-stack-grader-' + engine,
        kind='container', identity={'source_digest': verification_source_digest(ROOT),
            'purpose': 'One already-exposed engineering task; no qualification or comparison claim'},
        container_image=prepared.GRADER, container_runtime='/usr/local/bin/docker',
        container_socket='/Users/edwintse/.docker/run/docker.sock', memory_mb=512,
        conformance_digests={getattr(pair, role).id: boundary['boundaries'][role]['conformance_digest']
                             for role in ('control', 'treatment')},
        differential_conformance_digest=boundary['differential_conformance_digest'])
    rec_ref = repo.put('recipe', recipe.recipe_id, recipe)
    env_ref = repo.put('environment', content_digest(environment), environment)
    task = prepared.load(HERE / 'task.json')
    public, truth = task['input'], task['truth']
    case = BenchmarkCase(case_id=public['task_id'], split='qualification',
        variation=public['family'], template_family=task['source_repository'].casefold(),
        action=ActionRequest(capability=recipe.capability, input=public),
        validators=[ValidationSpec(kind='callback', config={'name': grader_name(public, truth), 'expected': truth})])
    integration = IntegrationCaseSet(request_id='ase-stack-cases-' + engine, recipe_digest=rec_ref,
        environment_digest=env_ref, benchmark_pack_digest=recipe.dependencies['benchmark_pack'],
        seed=71, cases=[case])
    integration_ref = repo.put('integration_case_set', content_digest(integration), integration)
    repo.review(integration_ref)
    repo.review(rec_ref)
    scheduler = prepared.scheduler() if engine == 'agent-skill-eval' else None
    scheduler_ref = None
    if scheduler is not None:
        scheduler_ref = repo.put('scheduler', content_digest(scheduler), scheduler)
        repo.review(scheduler_ref)
    experiment = IncrementalExperiment(stage='qualification', exposure='required',
        environment=pair.differential,
        utility=UtilityPolicy(benefit_dimensions=['wall_time_ms'], guardrail_dimensions=['wall_time_ms']))
    plan = service.propose(subject_id=subject.subject_id, family=recipe.recipe_id,
        candidate_id=pair.treatment.id, baseline_id=pair.control.id, authorization_id='onboarding',
        environment=environment, seed=71, structure='controlled_agent',
        integration_case_set_id=integration_ref, scheduler_digest=scheduler_ref, experiment=experiment)
    review = EngineeringRunReview(plan_digest=content_digest(plan),
        implementation_source=verification_source_digest(ROOT), scope_request_id='ase-stack-scope-' + engine,
        case_ids=(case.case_id,), maximum_model_turns=1)
    engineering_ref = repo.put('toolkit_engineering_run', content_digest(review), review)
    scope = RecipeMaterializationRequest(plan_id=review.scope_request_id,
        subject_digest=plan.subject_digest, recipe_digest=plan.recipe_digest,
        mapping_digest=plan.mapping_digest, environment_digest=plan.environment_digest,
        authorization_id='onboarding', definition_digests=[*plan.definition_digests, engineering_ref], seed=71)
    repo.put('recipe_materialization_request', scope.plan_id, scope)
    approve(repo, [scope], extra=[('toolkit_engineering_run', review)])
    require_engineering_run(repo, engineering_ref, plan=plan, source_digest=review.implementation_source)
    if plan.blocked_reasons or len(plan.suite.routes) != 1 or len(plan.suite.cases) != 1:
        raise RuntimeError('Engineering plan is blocked or exceeds one selected task turn')
    service._verify_dependencies(plan)
    emit('plan-' + engine + '.json', plan.model_dump(mode='json'))
    emit('engineering-' + engine + '.json', review.model_dump(mode='json'))
    return plan, engineering_ref


async def main():
    if len(sys.argv) != 2 or prepared.sha(HERE / 'operation-review.json') != sys.argv[1]:
        raise RuntimeError('Exact review digest required')
    review = prepared.load(HERE / 'operation-review.json')
    approval = prepared.load(HERE / 'operator-approval.json')
    if approval != {'approved': True, 'review_sha256': sys.argv[1]}:
        raise RuntimeError('Exact operator approval is absent')
    require_assets(review)
    if (HERE / 'execution-started.json').exists():
        raise RuntimeError('Prior attempt exists; inspect records, never replay')
    # Docker inspection selects no environment values or credential contents.
    emit('docker-before.json', {'usage': docker('system', 'df', '--format', 'json'), 'available_host_bytes': shutil.disk_usage(ROOT).free})
    context_root = prepared.WORK / 'build-context'
    if ({str(path.relative_to(context_root)) for path in context_root.rglob('*') if path.is_file()}
            != {'Dockerfile', 'candidate/SKILL.md', 'candidate/LICENSE'}
            or any(path.is_symlink() for path in context_root.rglob('*'))):
        raise RuntimeError('Build context differs from its three reviewed files')
    parent = json.loads(docker('image', 'inspect', '--format', review['image_format'], prepared.PARENT_TAG))
    if parent != review['parent_metadata']:
        raise RuntimeError('Retained parent image changed')
    proxy = json.loads(docker('inspect', '--format', review['proxy_inspect_format'], review['proxy_name']))
    if proxy != review['proxy_metadata'] or proxy['Running']:
        raise RuntimeError('Reviewed proxy state differs')
    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    repo = service.repository
    current_start = counters(repo)
    initial = prepared.load(prepared.OLD / 'execution-started.json')['grant_before']
    old_reserved = {row[0]: row[1] for row in repo.store._connection.execute(
        "SELECT id,state FROM assessment_operations WHERE grant_id='onboarding' AND state='reserved'")}
    emit('execution-started.json', {'review_sha256': sys.argv[1], 'grant_before': current_start, 'original_cumulative_anchor': initial, 'old_reserved_operations': old_reserved,
        'automatic_retry': False, 'candidate_usefulness': 'NOT_ASSESSED', 'selection_usefulness': 'NOT_ASSESSED'})
    result = {'passed': False, 'engines': {}, 'models_ceiling': 2, 'comparisons': 'PAUSED'}
    # This helper guards all in-process reservations; fixed one-trial CLI plans
    # are separately bounded by their canonical engineering scopes and previews.
    module_spec = importlib.util.spec_from_file_location('same_review_budget',
        HERE.parent / 'repository-usefulness-pilot-20261029/review-budget.py')
    budget = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(budget)
    original_reserve = budget.install(repo, repo.store._connection, initial, review)
    lifecycle = None
    bootstrap = None
    lifecycle_started = 0.0
    excluded = 0.0
    proxy_started = False
    process = None
    setup_start = set()
    preparation_elapsed = 0.0
    original_collect = inspection.collect
    try:
        # Settle the measured historical static inspection once under its original scope.
        # This is accounting reconciliation, never a replay or refunded allowance.
        from aeep.assessment.models import AssessmentSetupCost
        from aeep.models import ResourceVector
        historical = review['historical_static_inspection']
        cost = AssessmentSetupCost.model_validate(repo.get('setup_cost', historical['cost_id']))
        scope = RecipeMaterializationRequest.model_validate(repo.get(
            'recipe_materialization_request', historical['request_id']))
        if (content_digest(cost) != historical['cost_digest']
                or content_digest(scope) != historical['request_digest']
                or cost.subject_digest != scope.subject_digest
                or repo.store._connection.execute('SELECT 1 FROM assessment_operations WHERE id=?', (cost.cost_id,)).fetchone()):
            raise RuntimeError('Historical setup accounting differs; preserve all states')
        repo.reserve(scope, cost.cost_id, AssessmentLimits(max_operations=1,
            max_elapsed_seconds=max(cost.elapsed_seconds, .000001)), stage=cost.stage)
        repo.finish_operation(cost.cost_id, elapsed_seconds=cost.elapsed_seconds,
            resources=ResourceVector(latency_ms=cost.elapsed_seconds * 1000, cpu_ms=cost.cpu_ms))
        result['historical_static_inspection_settled'] = historical
        # A typed local scope is preparation/build accounting only, never a
        # fabricated functional probe or all-stack-completion record.
        payload = prepared.inspect(HERE / 'candidate')
        preparation_clock = time.perf_counter()
        setup_start = {row[0] for row in repo.store._connection.execute("SELECT id FROM assessment_records WHERE kind='setup_cost'")}
        subject = service.inspect_local(HERE / 'candidate', kind='skill')
        recipe = prepared.recipe()
        rec_ref = repo.put('recipe', recipe.recipe_id, recipe)
        environment = AssessmentEnvironment(environment_id='stack-readiness-owned-build', kind='trusted_local',
            identity={'source': review['source_digest'], 'parent_image': prepared.PARENT_ID})
        env_ref = repo.put('environment', content_digest(environment), environment)
        bootstrap = RecipeMaterializationRequest(plan_id='stack-readiness-owned-build-20261103',
            subject_digest=content_digest(subject), recipe_digest=rec_ref, mapping_digest=rec_ref,
            environment_digest=env_ref, authorization_id='onboarding',
            definition_digests=[rec_ref, env_ref], seed=71)
        repo.put('recipe_materialization_request', bootstrap.plan_id, bootstrap)
        approve(repo, [bootstrap])
        lifecycle = bootstrap.plan_id + ':proxy-exclusive-overhead'
        repo.reserve(bootstrap, lifecycle, AssessmentLimits(max_operations=1, max_elapsed_seconds=120), stage='owned_proxy_exclusive_overhead')
        # Include already measured preparation; exclude nested execution below.
        lifecycle_started = preparation_clock
        build_op = bootstrap.plan_id + ':copy-image'
        repo.reserve(bootstrap, build_op, AssessmentLimits(max_operations=1, max_elapsed_seconds=180), stage='owned_copy_image_build')
        began = time.perf_counter()
        try:
            if docker('images', '-q', prepared.TAG):
                raise RuntimeError('Output image tag already exists; preserve it')
            build = subprocess.run([*DOCKER, 'build', '--pull=false', '--network=none',
                '-t', prepared.TAG, '-f', str(prepared.WORK / 'build-context/Dockerfile'), str(prepared.WORK / 'build-context')],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=170)
            emit('build-result.json', {'exit_code': build.returncode,
                'log_sha256': hashlib.sha256(build.stdout.encode()).hexdigest()})
            (HERE / 'build.log').write_text(build.stdout)
            if build.returncode:
                raise RuntimeError('Reviewed COPY-only build failed')
            image = json.loads(docker('image', 'inspect', '--format', review['image_format'], prepared.TAG))
            require_image(review, image)
            emit('built-image.json', image)
            mode_spec = importlib.util.spec_from_file_location('reviewed_image_mode_audit', HERE / 'image-audit.py')
            mode_module = importlib.util.module_from_spec(mode_spec)
            mode_spec.loader.exec_module(mode_module)
            pair_fixture, _ = prepared.pair(image['Id'], review['source_digest'])
            emit('image-mode-audit.json', mode_module.audit(DOCKER, image['Id'], pair_fixture.reviewed_skill.files))
        finally:
            build_elapsed = time.perf_counter() - began
            excluded += build_elapsed
            repo.finish_operation(build_op, elapsed_seconds=build_elapsed)
        pair, shared = prepared.pair(image['Id'], review['source_digest'])
        repo.put('shared_environment_definition', content_digest(shared), Document(value=shared))
        requests = prepare_inspection(service, pair, recipe, subject)
        proxy_started = True
        docker('start', review['proxy_name'])
        active_proxy = json.loads(docker('inspect', '--format', review['proxy_inspect_format'], review['proxy_name']))
        if (not active_proxy['Running'] or active_proxy['Id'] != review['proxy_metadata']['Id']
                or active_proxy['Image'] != review['proxy_metadata']['Image']
                or active_proxy['Networks']['aeep-reviewed-model-private']['IPAddress'] != '172.18.0.2'):
            raise RuntimeError('Proxy identity or reviewed worker destination differs')

        async def collect(adapter, config, journal, recheck):
            facts = await original_collect(adapter, config, journal, recheck)
            if not facts.get('inspection_complete'):
                return facts  # Keep the original partial failure; no collector probe.
            worker = binding_from_config(config.managed_worker)
            container = 'aeep-' + hashlib.sha256(adapter._worker_process_id.encode()).hexdigest()[:32]
            legacy = HERE.parent / 'repository-usefulness-pilot-20261029/run-collector.py'
            spec = importlib.util.spec_from_file_location('collector_denial_programs', legacy)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            ports = json.loads(await inspection.docker(worker, 'exec', '-i', '--user', '65534:65534',
                container, 'python3', '-I', '-c', module.PORTS))['loopback_listener_ports']
            if len(ports) != 1 or type(ports[0]) is not int or not 0 < ports[0] < 65536:
                raise RuntimeError('Collector listener identity is indeterminate')
            recheck()
            program = module.DENIED.replace('PORT', str(ports[0]))
            action_digest = hashlib.sha256(program.encode()).hexdigest()
            journal.append('action.started', 'collector-access-start', action_digest=action_digest)
            observed = await inspection.command(adapter, program)
            journal.append('action.completed', 'collector-access-complete', action_digest=action_digest)
            journal.append('artifact.created', 'collector-denied-result', evidence_ref=content_digest(observed))
            if observed != {'collector_connection_denied': True}:
                raise RuntimeError('Trial code can reach trusted collector')
            result.setdefault('collector_boundary', {})[worker.digest()] = {
                **observed, 'program_sha256': action_digest,
                'scope_sha256': hashlib.sha256(adapter.transport.metrics_scope.encode()).hexdigest()}
            facts['collector_boundary'] = observed
            return facts

        inspection.collect = collect
        began = time.perf_counter()
        try:
            boundary = await inspection.execute_pair(service, *(request.plan_id for request in requests))
        finally:
            excluded += time.perf_counter() - began
            inspection.collect = original_collect
        emit('boundary-result.json', boundary)
        for request in requests:
            observed = repo.get('worker_pair_inspection', 'pair-inspection:' + request.plan_id)['observations']
            if 'inspection' in observed and (observed.get('cleanup_confirmed') is not True or 'cleanup_error_type' in observed):
                result['cleanup_uncertain'] = True
        if not boundary['probes_match']:
            raise RuntimeError('Fresh worker qualification is incomplete')
        for spec in (pair.control, pair.treatment):
            router.register(spec)
        router.managed_hosts.configure([pair.control, pair.treatment],
            principal_salt=router.store.host_principal_key, manifest_directory=router.manifest_path.parent)
        manifest = router.manifest.model_copy(update={'database': repo.store.path,
            'executors': [pair.control, pair.treatment]})
        # Preserve the original policy/resource settings. No provider/auth setup.
        manifest_path = prepared.WORK / 'selected-manifest.json'
        manifest_path.write_text(manifest.model_dump_json(indent=2))
        manifest_path.chmod(0o600)
        # Execute the ordinary command; never synthesize conformance in the driver.
        readiness_output = HERE / 'readiness-review.json'
        readiness = subprocess.run([sys.executable, '-B', '-m', 'aeep_toolkit',
            'workflow', 'prepare-worker-readiness', '--manifest', str(manifest_path),
            '--control-request', requests[0].plan_id, '--treatment-request', requests[1].plan_id,
            '--output', str(readiness_output)], cwd=ROOT,
            env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'src'),
                 'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, timeout=60)
        emit('readiness-command.json', {'exit_code': readiness.returncode,
            'stdout_sha256': hashlib.sha256(readiness.stdout).hexdigest(),
            'stderr_sha256': hashlib.sha256(readiness.stderr).hexdigest()})
        if readiness.returncode:
            raise RuntimeError('Ordinary readiness preparation stopped; do not repeat workers')
        boundary = prepared.load(readiness_output)
        if (boundary['reviewed'] or boundary['workers_started'] or boundary['execution_authorized']
                or any(item['observed_probe_count'] != 11 for item in boundary['boundaries'].values())):
            raise RuntimeError('Readiness review has unexpected authority or probe coverage')
        amendment = AssessmentScopeAmendment.model_validate(boundary['amendment'])
        emit('readiness-operator-review.json', {'authority':
            'Existing operator delegation for finite exact definition reviews; no new execution or cash authority',
            'amendment': boundary['amendment'], 'definitions': boundary['definitions']})
        repo.approve_bundle(amendment, boundary['definitions'])
        from aeep.assessment.boundary import require_conformance, require_candidate_access
        for role in ('control', 'treatment'):
            item = boundary['boundaries'][role]
            conformance = require_conformance(repo, item['conformance_digest'],
                source_digest=review['source_digest'], worker_digest=item['worker_digest'],
                identity_digest=item['identity_digest'])
            require_candidate_access(repo, conformance, pair.differential, available=role == 'treatment')
        emit('readiness-consumption.json', {'passed': True,
            'differential_conformance_digest': boundary['differential_conformance_digest'],
            'scope': 'Observed boundaries only; no task, usefulness or all-stack acceptance'})
        for engine in review['engines']:
            require_assets(review)
            plan, engineering_ref = prepare_plan(service, pair, recipe, subject, boundary, engine)
            preview = service.budget_preview(plan.plan_id)
            budget.require_room(counters(repo), initial, AssessmentLimits(
                max_operations=preview['campaign_allowance']['upper_allowance']['operations'],
                max_model_turns=preview['campaign_allowance']['upper_allowance']['model_turns'],
                max_elapsed_seconds=preview['campaign_allowance']['upper_allowance']['elapsed_seconds']), review)
            emit('budget-' + engine + '.json', preview)
            if preview['minimum_trial_model_turns'] != 1 or not preview['campaign_allowance']['fits_remaining']:
                raise RuntimeError('One-turn canonical reservation does not fit')
            source = SourcePin.model_validate(prepared.load(HERE / 'source.json'))
            argv = [sys.executable, '-B', '-m', 'aeep_toolkit', 'eval', 'managed', 'run',
                '--plan', str(HERE / ('plan-' + engine + '.json')), '--source', str(HERE / 'source.json'),
                '--manifest', str(manifest_path), '--directory', str(service.directory),
                '--reviewed-digest', plan_preview(plan, source)['review_sha256'],
                '--engineering-review', engineering_ref, '--output', str(HERE / ('result-' + engine))]
            if engine == 'agent-skill-eval':
                argv += ['--scheduler', str(HERE / 'scheduler.json')]
            emit('command-' + engine + '.json', {'argv': argv, 'automatic_retry': False})
            began = time.perf_counter()
            try:
                process = await asyncio.create_subprocess_exec(*argv, cwd=ROOT,
                    env={'PATH': '/usr/bin:/bin:/usr/local/bin', 'PYTHONPATH': str(ROOT / 'src'),
                         'PYTHONDONTWRITEBYTECODE': '1'},
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=4200)
            finally:
                excluded += time.perf_counter() - began
            emit('cli-' + engine + '.json', {'exit_code': process.returncode,
                'stdout_sha256': hashlib.sha256(stdout).hexdigest(), 'stderr_sha256': hashlib.sha256(stderr).hexdigest()})
            if process.returncode:
                result['model_attempt_unreconciled'] = True
                raise RuntimeError('CLI stopped; preserve attempt and do not switch/retry this engine')
            from aeep_toolkit.managed import AEEPAssessmentAdapter
            # Reopen canonical completion; normalization starts no worker.
            adapter = AEEPAssessmentAdapter(service, plan.plan_id, source)
            job = adapter.preview()['job']
            if job is None or job['state'] != 'complete' or job['error_code'] is not None:
                raise RuntimeError('Engineering task did not settle completely')
            bundle = adapter.normalize(job['report_id'])
            from aeep.benchmarking import BenchmarkTrial
            evidence_spec = importlib.util.spec_from_file_location('canonical_trial_gate',
                HERE.parent / 'repository-usefulness-pilot-20261029/trial-evidence.py')
            evidence = importlib.util.module_from_spec(evidence_spec)
            evidence_spec.loader.exec_module(evidence)
            expected_rows = prepared.load(HERE / 'task-delivery-controls.json')['checks']
            expected = {(row['case'], row['role']): row['instruction_sha256'] for row in expected_rows}
            campaign_path = service.directory / plan.plan_id / 'campaign.sqlite3'
            with sqlite3.connect(campaign_path.as_uri() + '?mode=ro', uri=True) as connection:
                trial_rows = list(connection.execute('SELECT payload_json FROM trials'))
                if len(trial_rows) != 1:
                    raise RuntimeError('Engineering trial positions differ')
                trial = BenchmarkTrial.model_validate_json(trial_rows[0][0])
                trial_evidence = evidence.read_trial(connection, trial, pair, expected,
                    service.directory / plan.plan_id / 'attempts')
                evidence.require_complete(trial_evidence)
                emit('trial-evidence-' + engine + '.json', trial_evidence)
            details = adapter.details
            captures = list(details['telemetry_capture'].values())
            if (len(bundle.runs) != 1 or bundle.runs[0].verification not in {'pass', 'fail'}
                    or bundle.runs[0].status != 'completed' or bundle.runs[0].retries != 0
                    or details['normalization_gaps'] or details['unresolved_operations']
                    or len(captures) != 1 or captures[0]['tokens']['status'] != 'verified'
                    or captures[0]['candidate']['instructions_loaded'] is not True):
                raise RuntimeError('Task grading, prompt, loading, accounting or token capture is incomplete')
            if engine == 'agent-skill-eval' and details.get('external_scheduler', {}).get('completion') == 'UNKNOWN':
                raise RuntimeError('Canonical upstream scheduler observation is missing')
            result['engines'][engine] = {'report_id': job['report_id'],
                'bundle_ref': content_digest(bundle), 'task_grade': bundle.runs[0].verification, 'details': adapter.details,
                'candidate_usefulness': 'NOT_ASSESSED', 'selection_usefulness': 'NOT_ASSESSED'}
            budget.require_room(counters(repo), initial,
                AssessmentLimits(max_operations=1, max_elapsed_seconds=1), review)
        result['passed'] = len(result['engines']) == 2
    except BaseException as error:
        result.update(error_type=type(error).__name__, error_message=str(error)[:300])
    finally:
        inspection.collect = original_collect
        try:
            if process is not None and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=10)
                except TimeoutError:
                    process.kill()
                    await process.wait()
                result['interrupted_cli_effects_uncertain'] = True
                result['passed'] = False

            if proxy_started:
                try:
                    docker('stop', '--time', '5', review['proxy_name'])
                    result['proxy_restored_stopped'] = docker('inspect', '--format', '{{.State.Running}}', review['proxy_name']) == 'false'
                    if not result['proxy_restored_stopped']:
                        raise RuntimeError('Proxy stop is unverified')
                except Exception as cleanup_error:
                    result.update(passed=False, cleanup_uncertain=True,
                        cleanup_error_type=type(cleanup_error).__name__)

            if lifecycle is not None:
                # Static inspection and proposal setup costs are charged by the
                # existing campaign. Exclude their measured intervals here.
                setup_records = [(identity, json.loads(raw)) for identity, raw in repo.store._connection.execute(
                    "SELECT id,payload_json FROM assessment_records WHERE kind='setup_cost' "
                    "AND json_extract(payload_json,'$.subject_digest')=?", (bootstrap.subject_digest,)) if identity not in setup_start]
                # A failed phase can leave measured preparation outside a campaign.
                # Reconcile only this subject's known local setup intervals; never
                # finish a reserved/uncertain operation or another user's costs.
                for identity, record in setup_records:
                    state = repo.store._connection.execute('SELECT state FROM assessment_operations WHERE id=?', (identity,)).fetchone()
                    if state is None:
                        try:
                            repo.reserve(bootstrap, identity, AssessmentLimits(max_operations=1,
                                max_elapsed_seconds=max(record['elapsed_seconds'], .000001)), stage=record['stage'])
                            repo.finish_operation(identity, elapsed_seconds=record['elapsed_seconds'],
                                resources=ResourceVector(latency_ms=record['elapsed_seconds'] * 1000, cpu_ms=record['cpu_ms']))
                        except Exception as accounting_error:
                            result.update(passed=False, accounting_uncertain=True,
                                accounting_error_type=type(accounting_error).__name__)
                    elif state[0] != 'complete':
                        result.update(passed=False, accounting_uncertain=True)

                nested_setup = sum(record['elapsed_seconds'] for _identity, record in setup_records)
                exclusive = max(0.0, preparation_elapsed + time.perf_counter() - lifecycle_started - excluded - nested_setup)
                if not result.get('cleanup_uncertain'):
                    try:
                        repo.finish_operation(lifecycle, elapsed_seconds=exclusive)
                    except Exception as accounting_error:
                        result.update(passed=False, accounting_uncertain=True,
                            accounting_error_type=type(accounting_error).__name__)
                result['wrapper_accounting'] = {'exclusive_seconds': exclusive,
                    'canonical_execution_intervals_excluded_seconds': excluded,
                    'setup_cost_intervals_excluded_seconds': nested_setup,
                    'setup_cost_ids': [identity for identity, _record in setup_records],
                    'unstarted_setup_costs_are_not_inferred_paid': True}
            if bootstrap is not None:
                result['auxiliary_operations'] = repo.operation_ledger(bootstrap.plan_id).model_dump(mode='json')
            result['old_operation_states_after'] = {identity: repo.store._connection.execute(
                'SELECT state FROM assessment_operations WHERE id=?', (identity,)).fetchone()[0]
                for identity in old_reserved}
            if result['old_operation_states_after'] != old_reserved:
                result.update(passed=False, unrelated_operation_changed=True)
            newly_unresolved = [row[0] for row in repo.store._connection.execute(
                "SELECT id FROM assessment_operations WHERE grant_id='onboarding' AND state='reserved'") if row[0] not in old_reserved]
            result['newly_unresolved_operations'] = newly_unresolved
            if newly_unresolved:
                result.update(passed=False, accounting_uncertain=True)
            result['grant_after'] = counters(repo)
            result['source_unchanged'] = verification_source_digest(ROOT) == review['source_digest']
            result['runtime_unchanged'] = prepared.snapshot(prepared.RUNTIME) == prepared.load(HERE / 'context.json')['runtime_tree_sha256']
            result['retained_images_and_runtimes'] = True
            emit('execution-result.json', result)
        finally:
            repo.reserve = original_reserve
            await router.close()
    print(json.dumps({k: v for k, v in result.items() if k != 'engines'}))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
