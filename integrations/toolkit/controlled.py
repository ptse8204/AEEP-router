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
from receipts import FixtureRecord
from stack import BASE, collect, fixture_payload, manifest, probe, sandbox, verify_runtime

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
    def __init__(self, repository, request, environment, spec, cases, skill):
        self.repository = repository
        self.request = request
        self.environment = environment
        self.spec = spec
        self.cases = cases
        self.skill = skill
        self.results = []

    async def dispatch(self, message):
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
                                   invocation_check=lambda: self.repository.authorize(self.request) and None)
        with persist_execution_events(lambda journal, event: self.repository.put('execution_event', f'{journal}:{event.sequence}', event)):
            raw = await (await executor.start(context)).task
        observation = raw.output if isinstance(raw.output, dict) else {}
        valid = (set(observation) == {'output', 'candidate_exposed', 'uid', 'python_available', 'shell_available'}
                 and isinstance(observation.get('output'), str) and len(observation['output']) <= 32768
                 and observation.get('candidate_exposed') is message['treatment'] and observation.get('uid') == 65534
                 and observation.get('python_available') is True and observation.get('shell_available') is True)
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
                 'worker_name': raw.metadata.get('container_name'), 'candidate_exposed': observation.get('candidate_exposed'),
                 'output_sha256': hashlib.sha256(observation.get('output', '').encode()).hexdigest() if valid else None}
        self.repository.put('toolkit_controlled_result', operation, FixtureRecord(facts=facts))
        self.repository.finish_operation(operation, elapsed_seconds=time.monotonic()-clock,
                                         accounting=raw.accounting, resources=raw.resources)
        self.results.append(facts)
        if not receipt.execution_success:
            raise ValueError('controlled worker failed; receipt and charge retained')
        return {'output': observation['output']}


async def execute(runtime: Path, output: Path, environment: AssessmentEnvironment):
    stack = manifest()
    facts = verify_runtime(runtime, stack)
    payload = fixture_payload(stack)
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
        coordinator.write_bytes(read_bytes(BASE/'controlled_engine.py'))
        worker_source = await asyncio.to_thread(Path(worker_temp).resolve)
        for name in SOURCE_NAMES:
            raw = read_bytes(runtime/'lib/python3.13/site-packages'/name)
            if hashlib.sha256(raw).hexdigest() != stack['evaluator']['source_files'][name]:
                raise ValueError('upstream worker source changed')
            target = worker_source/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        worker = worker_source/'controlled_fixture_worker.py'
        worker.write_bytes(read_bytes(BASE/'controlled_fixture_worker.py'))
        # Read-only mount only the adapter and three pinned upstream modules, never suite/grader/receipt files.
        environment = environment.model_copy(update={'read_only_roots': [str(worker_source)]})
        spec = ExecutorSpec(id='toolkit.fixture.worker', capability='toolkit.fixture.trial', kind='command',
                            description='Exact upstream fake harness in a fresh offline container',
                            config={'argv': ['python3', str(worker)], 'argv_literal': True, 'stdin_json': True,
                                    'timeout_seconds': 60, 'max_output_bytes': 65536, 'output': {'type': 'json'}},
                            side_effect=SideEffect.WRITE, idempotent=False)
        store = ReceiptStore(str(output/'receipts.sqlite3'))
        try:
            repository = AssessmentRepository(store)
            definition = FixtureRecord(facts={'stack': stack, 'runtime_inventory': facts, 'spec': spec.model_dump(mode='json'),
                                              'source_hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                                                for p in (BASE/'controlled.py', coordinator, worker)},
                                              'limits': {'trials': 4, 'model_turns': 0, 'cash': 0},
                                              'scope': 'synthetic harness dispatch; not real-agent conformance'})
            definition_ref = repository.put('toolkit_controlled_definition', 'fixture', definition)
            environment_ref = repository.put('environment', 'fixture', environment)
            # This is an explicit zero-turn engineering fixture, never a replacement for a live assessment grant.
            grant = AssessmentAuthorization(subject_digests=[definition_ref], recipe_digests=[definition_ref],
                                             environment_digests=[environment_ref],
                                             limits=AssessmentLimits(max_operations=4, max_model_turns=0, max_elapsed_seconds=260),
                                             expires_at=utc_now()+timedelta(hours=1))
            repository.grant(grant)
            repository.review(definition_ref)
            repository.review(environment_ref)
            request = AssessmentPlanningRequest(subject_digest=definition_ref, recipe_digest=definition_ref,
                                                 mapping_digest=definition_ref, environment_digest=environment_ref,
                                                 authorization_id=grant.authorization_id, definition_digests=[definition_ref], planner=spec)
            repository.put('toolkit_controlled_request', request.plan_id, request)
            suite = json.loads(payload[Path('fixtures/format-json/evals/evals.json')])
            analysis_plan, recipe = controlled_report.freeze(repository, request, suite, spec)
            bridge = TrialBridge(repository, request, environment, spec,
                                 {case['prompt']: case['id'] for case in suite['evals']},
                                 payload[Path('fixtures/format-json/SKILL.md')].decode())
            with (root/'coordinator.stderr').open('wb') as errors:
                process = await asyncio.create_subprocess_exec(*prefix, str(coordinator), str(root/'fixtures/format-json'),
                            str(root/'runs'), env=env, cwd=root, stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.PIPE, stderr=errors, limit=65536, start_new_session=True)
                try:
                    for _ in range(5):
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
                    shutil.copyfile(root/'coordinator.stderr', output/'coordinator.stderr')
            iteration = root/'runs/format-json-workspace/iteration-1'
            rows = collect(iteration)
            if len(bridge.results) != 4 or len({r['worker_name'] for r in bridge.results}) != 4:
                raise ValueError('missing or shared controlled workers')
            shutil.copytree(iteration, output/'upstream')
            controlled_report.create(output, repository, analysis_plan, recipe, definition, environment, bridge.results, rows)
            ledger = repository.operation_ledger(request.plan_id)
            result = {'schema': 'aeep.toolkit.controlled-fixture.v1', 'evidence_kind': 'synthetic',
                      'definition_ref': definition_ref, 'environment': environment.model_dump(mode='json'),
                      'trials': bridge.results, 'verified_upstream_rows': rows, 'ledger': ledger.model_dump(mode='json'),
                      'limitations': ['Real agent/credential conformance is not established.',
                                      'Upstream fake token/time constants are excluded from model observations.',
                                      'No live assessment grant was created, replaced or reset.']}
            (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
            return result
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
