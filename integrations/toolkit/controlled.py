"""Development-only ASE per-trial bridge using existing AEEP workers and ledger."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import signal
import tempfile
import time
from datetime import timedelta
from pathlib import Path

import controlled_report
from definition import Inputs, digest
from receipts import FixtureRecord
from stack import (
    BASE,
    collect,
    fixture_payload,
    manifest,
    probe,
    require_host,
    sandbox,
    verify_runtime,
)

from aeep.assessment import verification as assessment_verification
from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    AssessmentPlanningRequest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.execution import persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.models import (
    ActionRequest,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorSpec,
    PolicyConfig,
    RouteDecision,
    SideEffect,
    utc_now,
)
from aeep.store import ReceiptStore
from aeep_toolkit.cli import read_bytes

SOURCE_NAMES = ('agent_skill_eval/__init__.py', 'agent_skill_eval/models.py',
                'agent_skill_eval/harnesses/__init__.py')


class TrialBridge:
    def __init__(self, repository, request, environment, spec, cases, skill, check_current=lambda: None):
        self.repository = repository
        self.request = request
        self.environment = environment
        self.spec = spec
        self.cases = cases
        self.skill = skill
        self.results = []
        self.check_current = check_current

    def authorize(self):
        self.check_current()
        self.repository.authorize(self.request)

    async def dispatch(self, message):
        self.check_current()
        if (set(message) != {'kind', 'prompt', 'treatment'} or message['kind'] != 'trial'
                or type(message['treatment']) is not bool or message['prompt'] not in self.cases):
            raise ValueError('unreviewed trial request')
        case = self.cases[message['prompt']]
        arm = 'treatment' if message['treatment'] else 'control'
        operation = f'{self.request.plan_id}:{case}:{arm}'
        # An interrupted/failed operation stops the entire fixture, including after reopening the database.
        ledger = self.repository.operation_ledger(self.request.plan_id)
        for previous in ledger.operations:
            if previous.elapsed_seconds is None:
                raise ValueError('unresolved prior operation; blind continuation refused')
            result = self.repository.get('toolkit_controlled_result', previous.operation_id)
            if not result['facts']['execution_success']:
                raise ValueError('previous worker failed; stop fixture')
        self.repository.reserve(self.request, operation,
                                AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=65), stage='trial')
        started, clock = utc_now(), time.monotonic()
        action = ActionRequest(capability=self.spec.capability,
                               input={'prompt': message['prompt'], 'skill': self.skill if message['treatment'] else None})
        decision = RouteDecision(action=action, policy=PolicyConfig(name='controlled-fixture', fallback={'enabled': False, 'max_attempts': 1}),
                                 selected_executor_id=self.spec.id, disposition='BYPASS_ROUTER', bypass_reason='pinned_executor',
                                 explanation='Reviewed fixed upstream fixture; one fresh container per trial')
        stored_decision = decision.model_copy(deep=True)
        stored_decision.action.input = {'__aeep_redacted__': True}
        self.repository.store.save_decision(stored_decision)
        decision_ref = self.repository.put('toolkit_controlled_decision', operation, stored_decision)
        executor = ContainerExecutor(self.environment)
        context = ExecutionContext(request=action, spec=self.spec, estimate=self.spec.estimate, attempt=1,
                                   attempt_id=operation, approved_side_effect=SideEffect.WRITE,
                                   invocation_check=self.authorize)
        with persist_execution_events(lambda journal, event: self.repository.put('execution_event', f'{journal}:{event.sequence}', event)):
            raw = await (await executor.start(context)).task
        observation = raw.output if isinstance(raw.output, dict) else {}
        valid = (set(observation) in ({'output', 'candidate_exposed', 'uid', 'python_available', 'shell_available'},
                                      {'output', 'candidate_exposed', 'payload_sha256', 'uid', 'python_available', 'shell_available'})
                 and isinstance(observation.get('output'), str) and len(observation['output']) <= 32768
                 and observation.get('candidate_exposed') is message['treatment'] and observation.get('uid') == 65534
                 and observation.get('python_available') is True and observation.get('shell_available') is True)
        if isinstance(self.skill,dict):
            valid = valid and 'payload_sha256' in observation and observation['payload_sha256'] == (self.skill['sha256'] if message['treatment'] else None)
        if raw.status == ExecutionStatus.SUCCESS and not valid:
            raw.status, raw.error_type = ExecutionStatus.FAILED, 'FIXTURE_PROTOCOL_ERROR'
        receipt = ExecutionReceipt(decision_id=decision.decision_id, action_id=action.action_id, capability=self.spec.capability,
                                   executor_id=self.spec.id, executor_kind=self.spec.kind, status=raw.status,
                                   started_at=started, ended_at=utc_now(), estimated=self.spec.estimate,
                                   actual_resources=raw.resources, accounting=raw.accounting,
                                   execution_success=raw.status == ExecutionStatus.SUCCESS, error_type=raw.error_type,
                                   metadata={**raw.metadata, 'decision_ref': decision_ref, 'operation_id': operation,
                                             'case': case, 'arm': arm, 'evidence_kind': 'synthetic'})
        self.repository.store.save_receipt(receipt)
        receipt_ref = self.repository.put('toolkit_controlled_receipt', operation, receipt)
        facts = {'case': case, 'arm': arm, 'operation_id': operation, 'receipt_id': receipt.receipt_id,
                 'receipt_ref': receipt_ref, 'execution_success': receipt.execution_success,
                 'worker_name': raw.metadata.get('container_name'), 'candidate_exposed': observation.get('candidate_exposed') if valid else None,
                 'payload_sha256': observation.get('payload_sha256') if valid else None,
                 'output_sha256': hashlib.sha256(observation.get('output', '').encode()).hexdigest() if valid else None}
        self.repository.put('toolkit_controlled_result', operation, FixtureRecord(facts=facts))
        self.repository.finish_operation(operation, elapsed_seconds=time.monotonic()-clock,
                                         accounting=raw.accounting, resources=raw.resources)
        self.results.append(facts)
        if not receipt.execution_success:
            raise ValueError('controlled worker failed; receipt and charge retained')
        return {'output': observation['output']}


def preview(runtime: Path, output: Path, environment: AssessmentEnvironment, inputs: Inputs):
    from aeep_toolkit.install_runtime import canonical
    inputs.verify()
    canonical(str(output))
    if output.resolve() != output or output.exists() or not output.parent.is_dir():
        raise ValueError('evaluation output must be a new canonical directory with an existing parent')
    files = [BASE/name for name in ('controlled.py','controlled_engine.py','controlled_fixture_worker.py',
                                    'controlled_report.py','stack.py','definition.py','synthetic_edit.py','evaluate.py','verify_controlled.py')]
    files.extend(BASE.parents[1]/'src/aeep_toolkit'/name for name in ('candidate.py','__init__.py'))
    return {'schema':'aeep.toolkit.synthetic-evaluation-plan.v1','inputs':inputs.binding(),
            'runtime':str(runtime),'runtime_inventory':verify_runtime(runtime,manifest()),
            'aeep_source_sha256':assessment_verification.verification_source_digest(Path(assessment_verification.__file__).parents[3]),
            'output':str(output),'environment':environment.model_dump(mode='json'),
            'source_hashes':{p.name:hashlib.sha256(read_bytes(p)).hexdigest() for p in files},
            'effects':'Run only scripted trials in separate offline containers; no model, credential or billing calls.'}


async def execute(runtime: Path, output: Path, environment: AssessmentEnvironment,
                  inputs: Inputs | None = None, reviewed_digest: str | None = None):
    stack = manifest()
    facts = verify_runtime(runtime, stack)
    review = preview(runtime,output,environment,inputs) if inputs is not None else None
    if review is not None and reviewed_digest != digest(review):
        raise ValueError('exact synthetic evaluation review required before effects')
    if inputs is None:
        payload = fixture_payload(stack)
        skill_name = 'format-json'
    else:
        skill_name = inputs.suite.skill_name
        payload = {Path('fixtures')/skill_name/name:raw for name,raw in inputs.candidate.files.items()}
        payload[Path('fixtures')/skill_name/'evals/evals.json'] = json.dumps(inputs.suite.upstream()).encode()
        stack = stack | {'fixture_source':inputs.source.model_dump(mode='json')}
    fixture = Path('fixtures')/skill_name
    suite = json.loads(payload[fixture/'evals/evals.json'])
    trial_count = 2*len(suite['evals'])
    def source_bytes(path):
        raw = read_bytes(path)
        if review is not None and hashlib.sha256(raw).hexdigest() != review['source_hashes'][path.name]:
            raise ValueError('reviewed adapter source changed before staging')
        return raw

    require_host()
    if environment.network or environment.read_only_roots:
        raise ValueError('fixed fixture requires network disabled and no operator mounts')
    if await asyncio.to_thread(output.exists):
        raise ValueError('output already exists; no replay into prior evidence')
    await asyncio.to_thread(output.mkdir, parents=True)
    with tempfile.TemporaryDirectory(prefix='aeep-ase-controlled-') as temp, tempfile.TemporaryDirectory(prefix='aeep-ase-worker-source-') as worker_temp:
        root = await asyncio.to_thread(Path(temp).resolve)
        prefix, env = sandbox(root, runtime)
        probe(prefix, env, root)
        for name, raw in payload.items():
            destination = root/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        coordinator = root/'controlled_engine.py'
        coordinator.write_bytes(source_bytes(BASE/'controlled_engine.py'))
        worker_source = await asyncio.to_thread(Path(worker_temp).resolve)
        for name in SOURCE_NAMES:
            raw = read_bytes(runtime/'lib/python3.13/site-packages'/name)
            if hashlib.sha256(raw).hexdigest() != stack['evaluator']['source_files'][name]:
                raise ValueError('upstream worker source changed')
            target = worker_source/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        core_source = BASE.parents[1]/'src/aeep_toolkit'
        for name in ('__init__.py','candidate.py'):
            target = worker_source/'aeep_toolkit'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(source_bytes(core_source/name))
        (worker_source/'synthetic_edit.py').write_bytes(source_bytes(BASE/'synthetic_edit.py'))
        worker = worker_source/'controlled_fixture_worker.py'
        worker.write_bytes(source_bytes(BASE/'controlled_fixture_worker.py'))
        # Read-only mount only the adapter and three pinned upstream modules, never suite/grader/receipt files.
        environment = environment.model_copy(update={'read_only_roots': [str(worker_source)]})
        spec = ExecutorSpec(id='toolkit.fixture.worker', capability='toolkit.fixture.trial', kind='command',
                            description='Exact upstream fake harness in a fresh offline container',
                            config={'argv': ['python3', str(worker)], 'argv_literal': True, 'stdin_json': True,
                                    'timeout_seconds': 60, 'max_output_bytes': 65536, 'output': {'type': 'json'}},
                            side_effect=SideEffect.WRITE, idempotent=False)
        store = ReceiptStore(str(output/'receipts.sqlite3'))
        bridge = None
        try:
            repository = AssessmentRepository(store)
            definition = FixtureRecord(facts={'stack': stack, 'runtime_inventory': facts, 'spec': spec.model_dump(mode='json'),
                                              'source_hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                                                for p in (BASE/'controlled.py', BASE/'stack.py', coordinator, worker,
                                                                          worker_source/'synthetic_edit.py',worker_source/'aeep_toolkit/candidate.py',worker_source/'aeep_toolkit/__init__.py')},
                                              'limits': {'trials': trial_count, 'model_turns': 0, 'cash': 0},
                                              'review':review, 'review_sha256':digest(review) if review else None,
                                              'scope': 'synthetic harness dispatch; not real-agent conformance'})
            definition_ref = repository.put('toolkit_controlled_definition', 'fixture', definition)
            environment_ref = repository.put('environment', 'fixture', environment)
            # This is an explicit zero-turn engineering fixture, never a replacement for a live assessment grant.
            grant = AssessmentAuthorization(subject_digests=[definition_ref], recipe_digests=[definition_ref],
                                             environment_digests=[environment_ref],
                                             limits=AssessmentLimits(max_operations=trial_count, max_model_turns=0, max_elapsed_seconds=65*trial_count),
                                             expires_at=utc_now()+timedelta(hours=1))
            repository.grant(grant)
            repository.review(definition_ref)
            repository.review(environment_ref)
            request = AssessmentPlanningRequest(subject_digest=definition_ref, recipe_digest=definition_ref,
                                                 mapping_digest=definition_ref, environment_digest=environment_ref,
                                                 authorization_id=grant.authorization_id, definition_digests=[definition_ref], planner=spec)
            repository.put('toolkit_controlled_request', request.plan_id, request)
            analysis_plan, recipe = controlled_report.freeze(repository, request, suite, spec)
            bridge = TrialBridge(repository, request, environment, spec,
                                 {case['prompt']: case['id'] for case in suite['evals']},
                                 inputs.worker_payload() if inputs is not None else payload[fixture/'SKILL.md'].decode(),
                                 check_current=inputs.verify if inputs is not None else lambda: None)
            with (root/'coordinator.stderr').open('wb') as errors:
                process = await asyncio.create_subprocess_exec(*prefix, str(coordinator), str(root/fixture),
                            str(root/'runs'), env=env, cwd=root, stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.PIPE, stderr=errors, limit=65536, start_new_session=True)
                try:
                    for _ in range(trial_count+1):
                        line = await asyncio.wait_for(process.stdout.readline(), timeout=90)
                        message = json.loads(line)
                        if message == {'kind': 'done'}:
                            break
                        response = await bridge.dispatch(message)
                        process.stdin.write((json.dumps(response)+'\n').encode())
                        await process.stdin.drain()
                    else:
                        raise ValueError('coordinator exceeded fixed request count')
                    if await asyncio.wait_for(process.wait(), timeout=30) != 0:
                        raise ValueError('upstream coordinator failed')
                finally:
                    if process.returncode is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        await process.wait()
                    errors.flush()
                    diagnostic = read_bytes(root/'coordinator.stderr')
                    (output/'coordinator-diagnostic.json').write_text(json.dumps({
                        'returncode':process.returncode,'bytes':len(diagnostic),
                        'sha256':hashlib.sha256(diagnostic).hexdigest(),
                        'contents_retained':False})+'\n')
            iteration = root/'runs'/f'{skill_name}-workspace'/'iteration-1'
            rows = collect(iteration,suite,inputs.candidate.files if inputs is not None else None)
            if len(bridge.results) != trial_count or len({r['worker_name'] for r in bridge.results}) != trial_count:
                raise ValueError('missing or shared controlled workers')
            # General task prompts and upstream transcripts remain transient.
            retained = inputs is None or inputs.suite.retain_outputs
            for row in rows if retained else []:
                relative = Path(row['artifact'])/'outputs/output.txt'
                destination = output/'upstream'/relative
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(iteration/relative,destination)
            controlled_report.create(output, repository, analysis_plan, recipe, definition, environment, bridge.results, rows, artifact_root=iteration)
            ledger = repository.operation_ledger(request.plan_id)
            result = {'schema': 'aeep.toolkit.controlled-fixture.v1', 'evidence_kind': 'synthetic',
                      'definition_ref': definition_ref, 'outputs_retained':retained, 'environment': environment.model_dump(mode='json'),
                      'trials': bridge.results, 'verified_upstream_rows': rows, 'ledger': ledger.model_dump(mode='json'),
                      'limitations': ['Real agent/credential conformance is not established.',
                                      'Upstream fake token/time constants are excluded from model observations.',
                                      'No live assessment grant was created, replaced or reset.']}
            repository.put('toolkit_controlled_completion',request.plan_id,FixtureRecord(facts=result))
            (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
            return result
        except BaseException as error:
            if bridge is not None:
                # Preserve the original exception if recording incomplete evidence also fails.
                try:
                    controlled_report.create(output, repository, analysis_plan, recipe, definition,
                                             environment, bridge.results, [], incomplete=True)
                    ledger = repository.operation_ledger(request.plan_id)
                    result = {'schema':'aeep.toolkit.controlled-fixture.v1','evidence_kind':'synthetic',
                              'state':'incomplete','failure_code':type(error).__name__,
                              'definition_ref':definition_ref,'outputs_retained':False,
                              'environment':environment.model_dump(mode='json'),'trials':bridge.results,
                              'verified_upstream_rows':[],'ledger':ledger.model_dump(mode='json'),
                              'limitations':['Execution stopped without retry; unknown grades remain unknown.',
                                             'Real agent conformance and live benefit are not established.']}
                    repository.put('toolkit_controlled_completion',request.plan_id,FixtureRecord(facts=result))
                    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
                except Exception as reporting_error:
                    error.add_note('Partial reporting failed: '+type(reporting_error).__name__+'; inspect the retained receipt store.')
            raise
        finally:
            store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--docker', required=True)
    parser.add_argument('--socket', required=True)
    args = parser.parse_args()
    environment = AssessmentEnvironment(environment_id='toolkit-offline-fixture', kind='container',
                    identity={'purpose': 'upstream synthetic dispatch'}, container_image=args.image,
                    container_runtime=args.docker, container_socket=args.socket)
    result = asyncio.run(execute(args.runtime.resolve(), args.output.resolve(), environment))
    print(json.dumps({'trials': len(result['trials']), 'evidence_kind': 'synthetic', 'output': str(args.output)}))
