"""One reviewed AFlow turn through the existing AEEP managed worker and ledger."""

import argparse
import asyncio
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from aeep.accounting import aggregate_accounting
from aeep.assessment.boundary import require_managed_boundaries
from aeep.assessment.destinations import require_destination
from aeep.assessment.identity import local_dependencies, runtime_dependencies, verify_dependencies, verify_subject
from aeep.assessment.models import (
    AssessmentBudgetAmendment, AssessmentEnvironment, AssessmentLimits,
    AssessmentPlanningRequest, AssessmentSubject, content_digest,
)
from aeep.assessment.planning import PlanningDefinition
from aeep.assessment.recipes import shipped_recipe
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.execution import ExecutionEvidence, persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.hosts.workers import binding_from_config
from aeep.models import ActionConstraints, ActionRequest, ExecutionReceipt, ExecutorSpec, Manifest, ResourceVector, utc_now
from aeep.qualification import behavior_fingerprint
from aeep.router import Router
from aeep.templates import render

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
C13 = HERE.parents[2]
HANDOFF = HERE.parent / 'optimizer-directory-correction'
SKILLSBENCH = C13 / 'skillsbench-managed-worker-preparation-20261105'
PRIOR_WORK = ROOT / '.aeep' / SKILLSBENCH.name / 'engineering'
WORK = ROOT / '.aeep' / 'proposal-optimizer-preparation-20261105' / 'calibration-managed-cycle'
SOURCE_MANIFEST = PRIOR_WORK / 'aeep.json'
SOURCE_PAIR = PRIOR_WORK / 'spring-pair.json'
CAPABILITY = 'assessment.aflow.proposal@1'
STAGES = {
    'overhead': AssessmentLimits(max_operations=1, max_elapsed_seconds=180),
    'turn': AssessmentLimits(max_operations=1, max_model_turns=1, max_elapsed_seconds=150),
    'reply': AssessmentLimits(max_operations=1, max_elapsed_seconds=70),
}


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with Path(path).open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def encode(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError('reviewed helper is unavailable')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def payload():
    handoff = read(HANDOFF / 'result.json')
    original = read(HANDOFF / 'operation-review.json')
    path = Path(original['work']) / 'request.json'
    assert handoff['passed'] and handoff['models'] == 0 and handoff['cleanup_verified']
    assert not path.is_symlink() and path.stat().st_mode & 0o777 == 0o600
    captured = read(path)
    assert set(captured) == {'request', 'sha256'}
    request = captured['request']
    assert len(request.encode()) == handoff['request_bytes']
    assert hashlib.sha256(request.encode()).hexdigest() == captured['sha256'] == handoff['request_sha256']
    prompt = (
        'Complete this public AFlow engineering round. Use no tools, commands, files or network calls. '
        'The optimizer request below describes general graph optimization. This reviewed integration only accepts '
        'one of two existing graph changes: reject_duplicate returns {"error":"invalid_input"} on a '
        'repeated requested label; keep_first keeps its first value. Choose the change that meets the stated '
        'requirements. Do not produce Python or any new prompts. Return JSON with one xml string, exactly '
        '<modification>one short plain ASCII description</modification><graph>CHOICE</graph><prompt></prompt>, '
        'where CHOICE is reject_duplicate or keep_first. The description may contain only ASCII letters, digits, '
        'spaces, commas, periods, apostrophes, parentheses, underscores and hyphens.\n\n'
        'Original upstream formatted request:\n' + request
    )
    schema = {'type': 'object', 'required': ['xml'], 'additionalProperties': False,
              'properties': {'xml': {'type': 'string', 'maxLength': 512}}}
    wire = prompt + '\nReturn only JSON satisfying this output schema:\n' + encode(schema)
    return handoff, path, prompt, schema, hashlib.sha256(wire.encode()).hexdigest()


def pair_for(schema):
    prior = read(SOURCE_PAIR)
    shared = read(PRIOR_WORK/'spring-shared.json')
    assert content_digest(shared) == prior['differential']['shared_definition_digest']
    shared = {**shared, 'purpose':'One public AFlow planning turn', 'proposal_schema_sha256':content_digest(schema)}
    common = content_digest(shared)
    inventory = prior['differential']['control_inventory'] | {'common_profile':common}
    prior['differential'].update(
        shared_definition_digest=common, control_inventory=inventory,
        treatment_inventory=inventory | prior['differential']['candidate_inventory'],
    )
    for role in ('control','treatment'):
        spec = prior[role]
        spec.update(id='aflow-proposal.' + role, capability=CAPABILITY, output_schema=schema,
                    input_schema={'type':'object','required':['prompt'],'additionalProperties':False,
                                  'properties':{'prompt':{'type':'string','maxLength':32768}}})
        config = spec['config']
        assert config['model_constraints']['allowed_model_ids'] == ['gpt-6-astra']
        assert config['reasoning_efforts'] == ['medium'] and config['invocation']['local_profile'] == 'capable_local'
        assert config['adapter_options']['output_schema_mode'] == 'prompt'
        config.update(instructions='{input.prompt}', artifact=None, timeout_seconds=120, sandbox_policy='read_only',
                      store_prompt=False, store_output=False)
    pair = WorkerPairInspection.model_validate(prior)
    assert pair.control.side_effect.value == 'read' and pair.control.idempotent and not pair.control.requires_network
    assert pair.control.estimate.cash.upper_bound_usd == 0
    return pair, shared


def grant_snapshot(database):
    with sqlite3.connect(Path(database).as_uri() + '?mode=ro', uri=True) as connection:
        state = connection.execute("SELECT revoked,operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone()
        root = connection.execute("SELECT digest,payload_json FROM assessment_records WHERE kind='authorization' AND id='onboarding'").fetchone()
        latest = connection.execute(
            "SELECT digest,payload_json FROM assessment_records WHERE kind='budget_amendment' "
            "AND json_extract(payload_json, '$.authorization_id')='onboarding' ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        pending = connection.execute(
            "SELECT id,reserved_json FROM assessment_operations WHERE grant_id='onboarding' AND state='reserved' ORDER BY id"
        ).fetchall()
    assert state and not state[0] and root and latest
    base = json.loads(root[1])
    amendment = AssessmentBudgetAmendment.model_validate_json(latest[1])
    assert amendment.authorization_digest == root[0] and latest[0] == content_digest(amendment)
    assert amendment.expires_at > utc_now() and base['remote_disclosure'] is False
    assert set(base['allowed_destinations']) >= {'local','codex'}
    assert amendment.limits.max_cash_usd == Decimal(0) and Decimal(state[4]) == 0
    return {'counters':list(state[1:]), 'root_sha256':root[0], 'amendment_sha256':latest[0],
            'limits':amendment.limits.model_dump(mode='json'), 'expires_at':amendment.expires_at.isoformat(),
            'prior_reservations':len(pending), 'prior_reservations_sha256':content_digest(pending)}


def docker(review, *args, timeout=20):
    return subprocess.check_output([*review['docker'],*args],env=review['docker_environment'],
                                   timeout=timeout,text=True,stderr=subprocess.PIPE).strip()


def proxy_state(review):
    return json.loads(docker(review,'inspect','--format',review['proxy_inspect_format'],review['proxy_id']))


def verify_files(review, identity):
    assert sha(HERE/'operation-review.json') == identity
    assert datetime.fromisoformat(review['expires_at']) > utc_now()
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    assert verification_source_digest(ROOT) == review['source_sha256']
    assert all(sha(path) == digest for path,digest in review['assets'].items())


def preflight(review, identity):
    verify_files(review, identity)
    assert not WORK.exists() and not (HERE/'started.json').exists()
    handoff, _, prompt, schema, wire_digest = payload()
    assert review['request_sha256'] == handoff['request_sha256'] and review['provider_text_sha256'] == wire_digest
    assert review['provider_text_bytes'] == len((
        prompt + '\nReturn only JSON satisfying this output schema:\n' + encode(schema)).encode())
    pair, shared = pair_for(schema)
    assert content_digest(pair) == review['pair_sha256'] and content_digest(shared) == review['shared_sha256']
    assert behavior_fingerprint(pair.control) == review['turn_executor_fingerprint']
    assert render('{input.prompt}', {'input':{'prompt':prompt}}) == prompt
    for image in [review['aflow_image'], *review['worker_images'].values()]:
        assert docker(review,'image','inspect','--format','{{.Id}}',image) == image
    assert proxy_state(review) == review['stopped_proxy']
    assert grant_snapshot(review['database']) == review['grant']
    return pair, shared, prompt, schema


def named_container_absent(review, name):
    return not docker(review,'ps','-aq','--filter','name=^/' + name + '$')


async def validate_reply(review, repo, scope, response, *, preflight=False):
    name = review['local_validator_container']
    assert named_container_absent(review,name)
    ident = scope.plan_id + ':reply'
    repo.reserve(scope,ident,STAGES['reply'],stage='aflow_reply_validation')
    start, clock = utc_now(), time.perf_counter()
    raw = reference = None
    error = None
    executor = CommandExecutor()
    spec = ExecutorSpec(id='aflow.offline-reply',capability=CAPABILITY,kind='command',
        description='Validate one bounded reply with the pinned AFlow parser',side_effect='write',
        config={'argv':review['finish_argv'],'argv_literal':True,'inherit_env':False,'stdin_json':True,
                'max_stdin_bytes':33792,'env':review['docker_environment'],
                'timeout_seconds':60,'max_output_bytes':8192,'output':{'type':'json'}})
    try:
        with persist_execution_events(lambda key,event:repo.put('execution_event',key+':'+str(event.sequence),event)):
            handle = await executor.start(ExecutionContext(
                request=ActionRequest(action_id=ident,capability=CAPABILITY,
                    input={'request_sha256':review['request_sha256'],'text':encode(response)}),
                spec=spec,estimate=spec.estimate,attempt=1,attempt_id=ident,
                approved_side_effect=spec.side_effect,invocation_check=lambda:(repo.authorize(scope),review['request_sha256'])[1]))
            raw = await handle.task
        evidence = ExecutionEvidence.model_validate(raw.metadata['execution_evidence'])
        reference = repo.put('execution_evidence',evidence.digest(),evidence)
        if raw.exit_code and isinstance(raw.stdout, str) and len(raw.stdout.encode()) <= 4096:
            try:
                diagnostic = json.loads(raw.stdout)
            except json.JSONDecodeError:
                diagnostic = {}
            if isinstance(diagnostic, dict) and diagnostic.get('status') == 'failed':
                write((Path(review['fixture_output']) if preflight else HERE) / 'guest-diagnostic.json',
                      {key: diagnostic[key] for key in ('stage', 'error_type', 'locations')})
        assert raw.exit_code == 0 and evidence.complete and named_container_absent(review,name)
        observed = raw.output
        assert observed['status'] == 'cycle_complete' and observed['request_sha256'] == review['request_sha256']
        assert observed['initial_grade_sha256'] == review['initial_grade_sha256']
        assert observed['upstream_optimizer_executed'] and observed['upstream_experience_updated']
        assert observed['proposal_requests'] == 1 and observed['models_in_guest'] == 0
        assert not observed['generated_code_executed'] and observed['engineering_only']
        assert observed['boundary']['inherited_sockets'] == 0 and observed['boundary']['local_unix_pair_verified']
        certificates = read(review['certificate_file'])
        assert observed['policy'] in certificates
        certificate = certificates[observed['policy']]
        assert observed['outputs_sha256'] == certificate['outputs_sha256']
        assert observed['selected_score'] == certificate['passed'] / certificate['cases']
        assert observed['initial_score'] == 2 / 3
        return observed
    except BaseException as exc:
        error = type(exc).__name__
        raise
    finally:
        await executor.close()
        elapsed = time.perf_counter()-clock
        receipt = ExecutionReceipt(decision_id=ident,action_id=ident,capability=CAPABILITY,
            executor_id=spec.id,executor_kind=spec.kind,status='failed' if error else 'success',
            started_at=start,ended_at=utc_now(),estimated=spec.estimate,execution_success=error is None,
            error_type=error,actual_resources=ResourceVector(latency_ms=elapsed*1000),
            metadata={'execution_evidence_ref':reference,'request_sha256':review['request_sha256'],
                      'reply_sha256':hashlib.sha256(encode(response).encode()).hexdigest(),
                      'local_fixture':preflight,
                      'stderr_sha256':hashlib.sha256((raw.stderr or '').encode()).hexdigest() if raw else None})
        repo.store.save_receipt(receipt)
        repo.finish_operation(ident,elapsed_seconds=elapsed,resources=receipt.actual_resources)
        write((Path(review['fixture_output']) if preflight else HERE)/'validation-receipt.json',receipt.model_dump(mode='json'))


async def execute(review, identity, pair, shared, prompt, schema):
    helpers = load_module('aflow_existing_worker_helpers',SKILLSBENCH/'run-engineering.py')
    manifest = Manifest.model_validate(read(SOURCE_MANIFEST))
    assert str(manifest.database) == review['database']
    manifest = manifest.model_copy(update={'executors':[pair.control,pair.treatment],'registries':[]})
    for policy in manifest.policies.values():
        policy.fallback.enabled = False
    WORK.mkdir(mode=0o700)
    helpers.WORK,helpers.MANIFEST,helpers.CAMPAIGNS = WORK,WORK/'manifest.json',WORK/'campaigns'
    helpers.emit = lambda name,value:write(WORK/name,value)
    write(helpers.MANIFEST,manifest.model_dump(mode='json'))
    router = Router.from_manifest(helpers.MANIFEST)
    service = AssessmentService(router,helpers.CAMPAIGNS)
    repo = service.repository
    campaign = None
    grant = repo.current_grant('onboarding')
    assert grant.limits.model_dump(mode='json') == review['grant']['limits']
    assert grant.expires_at.isoformat() == review['grant']['expires_at']
    helpers.budget.install(repo,repo.store._connection,tuple(review['grant']['counters']),review)
    write(HERE/'started.json',{'review_sha256':identity,'automatic_retries':False,'comparisons':'PAUSED'})
    status = {'review_sha256':identity,'passed':False,'comparisons':'PAUSED','model_turns_reserved':0,
              'model_turns_observed':0,'provider_reply_validated':False,'stack_executed':False}
    phase = 'scope'
    started = time.perf_counter()
    excluded = 0.
    plan_ids = []
    overhead = None
    proxy_intent = False
    try:
        subject = AssessmentSubject(subject_id='aflow-proposal-20261106',kind='command',
            location=str(HERE/'cycle.py'),
            dependency_digests={'planner-bridge.py':sha(HERE/'cycle.py')},
            description='Public AFlow data-workflow planning relay', output_schema=schema,
            declarations={'request_sha256':review['request_sha256'],'provider_text_sha256':review['provider_text_sha256']})
        repo.put('subject',subject.subject_id,subject)
        recipe = shipped_recipe('text')
        # The recipe supplies the existing review envelope only. It runs no generator or benchmark.
        repo.put('recipe',recipe.recipe_id,recipe)
        local = AssessmentEnvironment(environment_id='aflow-managed-turn-local-20261106',kind='trusted_local',
            identity={'review_sha256':identity,'source_digest':review['source_sha256']})
        repo.put('environment',content_digest(local),local)
        scope = helpers.materialization(repo,'aflow-managed-turn-local-20261106',subject,recipe,local)
        plan_ids.append(scope.plan_id)
        helpers.scoped_approval(repo,[scope])
        operation = scope.plan_id + ':overhead'
        repo.reserve(scope,operation,STAGES['overhead'],stage='owned_aflow_proxy_and_review_overhead')
        overhead = operation
        repo.put('shared_environment_definition',content_digest(shared),helpers.previous.Document(value=shared))
        phase = 'proxy startup'
        assert proxy_state(review) == review['stopped_proxy']
        proxy_intent = True
        docker(review,'start',review['proxy_id'])
        running = proxy_state(review)
        assert running['Running'] and running['Id'] == review['proxy_id'] and running['Image'] == review['stopped_proxy']['Image']
        assert running['Networks'][review['private_network']]['IPAddress'] == review['proxy_ip']
        phase = 'zero-turn worker and collector inspection'
        verify_files(review,identity)
        ids = helpers.worker_requests(service,'aflow',pair,recipe,subject,review['source_sha256'])
        plan_ids.extend(ids)
        original = helpers.inspection.collect
        helpers.inspection.collect = helpers.inspect_collector(original)
        began = time.perf_counter()
        try:
            boundaries = await helpers.inspection.execute_pair(service,*ids)
        finally:
            helpers.inspection.collect = original
            excluded += time.perf_counter()-began
        assert boundaries['probes_match'] and boundaries['model_turns'] == 0
        ready = helpers.readiness(repo,'aflow',ids,pair,review['source_sha256'])
        phase = 'exact managed turn preparation'
        spec = pair.control
        record = ready['boundaries']['control']
        env = AssessmentEnvironment(environment_id='aflow-managed-proposal-20261106',kind='codex_sandbox',
            identity={'source_digest':review['source_sha256'],'request_sha256':review['request_sha256']},
            conformance_digests={spec.id:record['conformance_digest']})
        env_ref = repo.put('environment',content_digest(env),env)
        dependencies = {**runtime_dependencies(),**local_dependencies(spec)}
        mapping = PlanningDefinition(planner=spec,executable_dependencies=dependencies)
        mapping_ref = repo.put('planning_mapping',content_digest(mapping),mapping)
        planning = AssessmentPlanningRequest(plan_id='aflow-managed-proposal-20261106',
            subject_digest=content_digest(subject),recipe_digest=content_digest(recipe),mapping_digest=mapping_ref,
            environment_digest=env_ref,authorization_id='onboarding',planner=spec,executable_dependencies=dependencies,
            definition_digests=[content_digest(recipe),mapping_ref,env_ref,record['conformance_digest']])
        repo.put('planning_request',planning.plan_id,planning)
        helpers.scoped_approval(repo,[planning])
        plan_ids.append(planning.plan_id)
        require_destination(spec,env,repo.authorize(planning))
        require_managed_boundaries(repo,env,[spec],{spec.id:record['identity_digest']})
        verify_files(review,identity)
        phase = 'one managed Codex turn'
        operation = planning.plan_id + ':turn'
        repo.reserve(planning,operation,STAGES['turn'],stage='aflow_managed_proposal')
        status.update(model_turns_reserved=1,model_turns_observed=None)
        began = time.perf_counter()
        outcome = None
        try:
            campaign = router._campaign_router([spec],plan_digest=content_digest(planning),database=WORK/'proposal.sqlite3')
            def check():
                verify_files(review,identity)
                require_destination(spec,env,repo.authorize(planning))
                verify_dependencies(dependencies)
                verify_subject(subject)
                identities = {key:value[1] for key,value in campaign.store.host_runtime_digests.items()}
                require_managed_boundaries(repo,env,[spec],identities)

            campaign._trial_check = check
            campaign._trial_boundary_references = dict(env.conformance_digests)
            campaign._trial_deadline = asyncio.get_running_loop().time()+125
            async with asyncio.timeout_at(campaign._trial_deadline):
                await campaign._resolve_host_identity(spec)
                check()
                campaign.store.expected_host_runtime_digests[spec.id] = record['identity_digest']
                outcome = await campaign.execute(ActionRequest(action_id=operation,capability=CAPABILITY,
                    input={'prompt':prompt},constraints=ActionConstraints(allowed_executor_ids=[spec.id],allow_network=False)))
            status['receipts'] = [receipt.receipt_id for receipt in outcome.receipts]
            for receipt in outcome.receipts:
                persisted = campaign.store.get_receipt(receipt.receipt_id)
                if persisted is not None:
                    repo.put('planning_receipt',receipt.receipt_id,persisted)
        finally:
            try:
                if campaign is not None:
                    await campaign.close()
                    campaign = None
            finally:
                elapsed = time.perf_counter()-began
                excluded += elapsed
                repo.finish_operation(operation,elapsed_seconds=elapsed,
                    accounting=aggregate_accounting(outcome.receipts) if outcome else None)
        assert outcome is not None and len(outcome.receipts) == 1
        receipt = outcome.receipts[0]
        meta = receipt.metadata
        status.update(model_turns_observed=meta.get('model_turn_count'), recorded_tool_calls=meta.get('tool_call_count'),
                      worker_cleanup_confirmed=meta.get('worker_cleanup_confirmed'))
        assert outcome.ok and receipt.attempt == 1 and receipt.executor_id == spec.id
        assert meta.get('model_turn_count') == 1 and meta.get('actual_model') == review['model']
        assert meta.get('worker_cleanup_confirmed') is True
        assert meta.get('tool_call_count') == 0 and json.loads(meta['host_tools_used']) == []
        assert receipt.accounting.model_usage and isinstance(outcome.output,dict)
        phase = 'offline validation of the actual managed reply'
        verify_files(review,identity)
        began = time.perf_counter()
        try:
            validation = await validate_reply(review,repo,scope,outcome.output)
        finally:
            excluded += time.perf_counter()-began
        status.update(provider_reply_validated=True,validation=validation,passed=True)
    except BaseException as exc:
        status.update(failure_stage=phase,error_type=type(exc).__name__)
    finally:
        if proxy_intent:
            try:
                actual = proxy_state(review)
                assert actual['Id'] == review['proxy_id'] and actual['Image'] == review['stopped_proxy']['Image']
                if actual['Running']:
                    docker(review,'stop',review['proxy_id'],timeout=25)
                status['proxy_restored_stopped'] = proxy_state(review) == review['stopped_proxy']
            except BaseException:
                status['proxy_restored_stopped'] = False
        if overhead is not None:
            repo.finish_operation(overhead,elapsed_seconds=max(0.,time.perf_counter()-started-excluded))
        ledger = [repo.operation_ledger(plan_id).model_dump(mode='json') for plan_id in plan_ids]
        write(HERE/'ledger.json',ledger)
        with repo.store._lock:
            current = repo.store._connection.execute(
                "SELECT revoked,operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'"
            ).fetchone()
            pending = repo.store._connection.execute(
                "SELECT id,reserved_json FROM assessment_operations WHERE grant_id='onboarding' AND state='reserved' ORDER BY id"
            ).fetchall()
        status['grant_after'] = list(current[1:])
        status['accounting_settled'] = (
            content_digest([tuple(row) for row in pending]) == review['grant']['prior_reservations_sha256']
            and all(op['elapsed_seconds'] is not None for part in ledger for op in part['operations'])
        )
        status['passed'] = (status['passed'] and not current[0] and status['accounting_settled']
                            and status.get('proxy_restored_stopped',False))
        write(HERE/'result.json',status)
        await router.close()
    return status


def main():
    parser = argparse.ArgumentParser()
    args = parser.add_mutually_exclusive_group(required=True)
    args.add_argument('--preflight')
    args.add_argument('--execute-approved')
    options = parser.parse_args()
    identity = sha(HERE/'operation-review.json')
    assert identity == (options.preflight or options.execute_approved)
    review = read(HERE/'operation-review.json')
    pair, shared, prompt, schema = preflight(review,identity)
    if options.preflight:
        print(encode({'review_sha256':identity,'passed':True,'models':0,'workers_started':0}))
        return
    assert read(HERE/'operator-approval.json') == {'approved':True,'review_sha256':identity}
    result = asyncio.run(execute(review,identity,pair,shared,prompt,schema))
    print(encode(result))
    raise SystemExit(not result['passed'])


if __name__ == '__main__':
    main()
