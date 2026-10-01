"""Disposable fake orchestration checks; no worker, model, auth or real store."""
import asyncio
import importlib.util
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aeep.assessment.models import ConformanceProbeRequest, content_digest
from aeep.assessment.identity import file_digest
from aeep.attempts import ExecutionAttempt
from aeep.errors import ConfigurationError
from aeep.execution import EventJournal
from aeep.models import (
    ActionConstraints, ActionRequest, ExecutionReceipt, ExecutionStatus,
    ExecutorKind, ModelTokenUsage, RawExecution, ResourceAccounting, RouteEstimate,
    SideEffect,
)

path = Path(__file__).with_name('native-composed-post-reset-runner.py')
specification = importlib.util.spec_from_file_location('inert_composed_runner', path)
runner = importlib.util.module_from_spec(specification)
specification.loader.exec_module(runner)


class Repository:
    def __init__(self):
        self.operations = {}
        self.records = {}
        self.finish = []

    def reserve(self, request, identity, limits, *, stage):
        if identity in self.operations:
            raise ConfigurationError('blind retry denied')
        self.operations[identity] = (limits, stage)

    def authorize(self, request):
        return None

    def put(self, kind, identity, value):
        self.records[(kind, identity)] = value.model_dump(mode='json')
        return content_digest(value)

    def get(self, kind, identity):
        return self.records[(kind, identity)]

    def finish_operation(self, identity, **measurement):
        self.finish.append((identity, measurement))


class Checks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repo = Repository()
        self.request = ConformanceProbeRequest.model_construct(
            schema_version='assessment.conformance-request.v4',operation='composed_pair_inspection',
            plan_id='disposable', subject_digest='1'*64, recipe_digest='2'*64,
            mapping_digest='3'*64, environment_digest='4'*64,
            authorization_id='fake', definition_digests=['c'*64], worker_digest='5'*64,
            pair_definition_digest='c'*64,executable_dependencies={'fixture':'d'*64}, composed_model_turns=1)
        self.action = ActionRequest(capability='fixture', constraints=ActionConstraints(allowed_executor_ids=['host']))
        self.profile = SimpleNamespace(id='host', managed_host_config=lambda: SimpleNamespace(timeout_seconds=0.2,adapter_id='fixture'))
        self.definition = SimpleNamespace(name='callback_authority', expected={
            'callback_origin':'native_app_server', 'native_callback_observed':True})
        self.closed = 0
        self.calls = 0
        self.runtime = SimpleNamespace(host_runtime_digests={'host':('unretained','6'*64)}, expected_host_runtime_digests={})
        def factory():
            return None
        self.adapter = SimpleNamespace(dynamic_tools_factory=factory)
        self.request.executable_dependencies[str(Path(__file__).resolve())] = file_digest(Path(__file__).resolve())
        self.scoped = SimpleNamespace(store=self.runtime, _resolve_host_identity=self.resolve,
            execute=self.execute, close=self.close,managed_hosts=SimpleNamespace(get=lambda identity: self.adapter))
        self.service = SimpleNamespace(repository=self.repo, router=SimpleNamespace(
            _campaign_router=lambda *args, **kwargs: self.scoped))
        self.temporary = tempfile.TemporaryDirectory(prefix='aeep-offline-runner-')
        self.addCleanup(self.temporary.cleanup)

    async def resolve(self, spec):
        return None

    async def close(self):
        self.closed += 1

    async def execute(self, action, **kwargs):
        self.calls += 1
        assert action is self.action
        assert self.scoped._callback_conformance_identity == ('disposable','composed:disposable')
        self.scoped._trial_check()
        accounting = ResourceAccounting(model_usage=[ModelTokenUsage(provider='offline_fake',model='fixture')])
        journal = EventJournal('fake-outer-attempt')
        journal.append('execution.started','start')
        journal.append('action.completed','dynamic-complete:one',action_digest='7'*64)
        journal.append('artifact.created','dynamic-link:one',action_digest='7'*64,evidence_ref='8'*64)
        journal.append('usage.reported','usage',accounting=accounting)
        journal.append('execution.completed','terminal')
        evidence = journal.evidence('codex-app-server',RawExecution(status=ExecutionStatus.SUCCESS,
            metadata={'boundary_digest':'5'*64,'host_runtime_digest':'6'*64}))
        self.repo.put('execution_evidence',evidence.digest(),evidence)
        receipt = ExecutionReceipt(decision_id='fake-decision',action_id=action.action_id,
            capability=action.capability,executor_id='host',executor_kind=ExecutorKind.MANAGED_HOST,
            status=ExecutionStatus.SUCCESS,estimated=RouteEstimate(),accounting=accounting,
            metadata={'execution_evidence_digest':evidence.digest(),'model_turn_count':1,
                      'dynamic_cleanup_confirmed':True})
        return SimpleNamespace(ok=True,receipts=[receipt])

    async def invoke(self, *, confirmed=True, operation='composed:disposable', capture=None):
        with patch.object(runner,'RESET',datetime(2000,1,1,tzinfo=timezone.utc)), \
             patch.object(runner,'prepare',return_value=(self.request,self.definition,self.action,self.profile)), \
             patch.object(runner,'verify_dependencies',return_value=None), \
             patch.object(runner,'preserve_scoped',new=capture or (lambda *args:([],[],None))), \
             patch.object(runner,'confirm_cleanup',new=AsyncMock(return_value=True)), \
             patch.object(runner,'AssessmentRepository',return_value=self.repo):
            return await runner.run_once(self.service,request_id='unused',definition_digest='9'*64,
                action_digest='a'*64,operation_id=operation,source_root='/unused',
                fresh_database=Path(self.temporary.name)/'unused.db',capacity_confirmed=confirmed)

    async def test_capacity_block_precedes_reservation(self):
        with self.assertRaises(ConfigurationError):
            await self.invoke(confirmed=False)
        self.assertEqual(self.repo.operations,{})
        self.assertEqual(self.calls,0)

    async def test_operator_factory_and_captured_producer_must_be_pinned(self):
        def producer():
            return None
        def factory():
            return producer()
        source = Path(__file__).resolve()
        runner.pinned_factory(factory,{str(source):file_digest(source)})
        with self.assertRaises(ConfigurationError):
            runner.pinned_factory(factory,{})
        class OpaqueProducer:
            def __call__(self):
                return None
        opaque = OpaqueProducer()
        def opaque_factory():
            return opaque()
        with self.assertRaises(ConfigurationError):
            runner.pinned_factory(opaque_factory,{str(source):file_digest(source)})
        def class_factory():
            return OpaqueProducer()
        with self.assertRaises(ConfigurationError):
            runner.pinned_factory(class_factory,{str(source):file_digest(source)})
        unreviewed_path = Path(self.temporary.name)/'unreviewed-producer.py'
        unreviewed_path.write_text('def producer():\n    return None\n')
        def unreviewed():
            return None
        unreviewed.__code__ = unreviewed.__code__.replace(co_filename=str(unreviewed_path))
        def default_factory(producer=unreviewed):
            return producer()
        def keyword_factory(*, producer=unreviewed):
            return producer()
        for function in (default_factory,keyword_factory):
            with self.assertRaises(ConfigurationError):
                runner.pinned_factory(function,{str(source):file_digest(source)})

    async def test_new_operation_id_cannot_replay_same_request(self):
        with self.assertRaises(ConfigurationError):
            await self.invoke(operation='fresh-looking-replay')
        self.assertEqual(self.repo.operations,{})
        self.assertEqual(self.calls,0)

    async def test_zero_turn_request_cannot_enter_model_runner(self):
        zero = self.request.model_copy(update={'composed_model_turns':0})
        self.repo.put('conformance_request','zero',zero)
        with self.assertRaises(ConfigurationError):
            runner.prepare(self.service,'zero','9'*64,'a'*64,'/unused')
        self.assertEqual(self.repo.operations,{})

    async def test_wrong_loaded_source_root_rejected(self):
        self.repo.put('conformance_request','source',self.request)
        result = SimpleNamespace(fetchone=lambda: (datetime.now(timezone.utc).isoformat(),0))
        self.repo.store = SimpleNamespace(_lock=threading.RLock(),_connection=SimpleNamespace(execute=lambda *args: result))
        with patch.object(runner,'RESET',datetime(2000,1,1,tzinfo=timezone.utc)):
            with self.assertRaises(ConfigurationError):
                runner.prepare(self.service,'source','9'*64,'a'*64,'/wrong-loaded-root')
        self.assertEqual(self.repo.operations,{})

    async def test_cleanup_uses_owned_absence_and_live_process_refusal(self):
        worker = object()
        transport = SimpleNamespace(_process=SimpleNamespace(returncode=0),_dynamic_tasks=set())
        adapter = SimpleNamespace(transport=transport,_worker=worker,_worker_process_id='fixture-owned')
        observation = AsyncMock(return_value='')
        with patch.object(runner,'docker',new=observation):
            self.assertTrue(await runner.confirm_cleanup(adapter))
            arguments = observation.call_args.args
            self.assertIs(arguments[0],worker)
            self.assertIn('name=^/',arguments[4])
            transport._process.returncode = None
            self.assertFalse(await runner.confirm_cleanup(adapter))
            self.assertEqual(observation.await_count,1)

    async def test_one_operation_and_exact_evidence_then_retry_denied(self):
        probe = await self.invoke()
        self.assertEqual(probe.observed,self.definition.expected)
        evidence = self.repo.get('execution_evidence',probe.execution_evidence_digest)
        self.assertEqual(evidence['attempt_id'],'fake-outer-attempt')
        self.assertTrue(any(event['evidence_ref']==content_digest(probe.observed) for event in evidence['events']))
        self.assertEqual(self.repo.operations['composed:disposable'][0].max_model_turns,1)
        self.assertEqual((self.closed,self.calls,len(self.repo.finish)),(1,1,1))
        self.assertFalse(self.repo.records[('composed_runner_result','composed:disposable')]['full_conformance'])
        with self.assertRaises(ConfigurationError):
            await self.invoke()
        self.assertEqual((self.calls,len(self.repo.finish)),(1,1))

    async def test_execution_failure_preserves_charge_and_cleanup(self):
        async def fail(*args,**kwargs):
            raise RuntimeError('synthetic')
        self.scoped.execute = fail
        with self.assertRaises(RuntimeError):
            await self.invoke()
        observation = self.repo.records[('composed_runner_result','composed:disposable')]
        self.assertEqual((observation['stage'],observation['error_type']),('host_execution','RuntimeError'))
        self.assertTrue(observation['cleanup_confirmed'])
        self.assertEqual(len(self.repo.finish),1)
        self.assertIsNone(self.repo.finish[0][1]['accounting'])

    async def test_cancelled_execution_still_finishes_one_turn_reservation(self):
        async def cancelled(*args,**kwargs):
            raise asyncio.CancelledError()
        self.scoped.execute = cancelled
        with self.assertRaises(asyncio.CancelledError):
            await self.invoke()
        self.assertEqual(len(self.repo.finish),1)
        self.assertEqual(self.repo.operations['composed:disposable'][0].max_model_turns,1)
        self.assertTrue(self.repo.records[('composed_runner_result','composed:disposable')]['cleanup_confirmed'])

    async def test_timeout_preserves_exact_partial_lineage_and_accounting(self):
        usage = ResourceAccounting(model_usage=[ModelTokenUsage(provider='offline_fake',model='partial')])
        partial = ExecutionReceipt(decision_id='partial-decision',action_id=self.action.action_id,
            capability=self.action.capability,executor_id='host',executor_kind=ExecutorKind.MANAGED_HOST,
            status=ExecutionStatus.TIMEOUT,estimated=RouteEstimate(),accounting=usage)
        attempt = ExecutionAttempt(decision_id=partial.decision_id,action_digest='1'*64,
            executor_id='host',executor_fingerprint='2'*64,side_effect=SideEffect.READ,idempotent=True,
            state='INDETERMINATE',owner_id='offline-fixture')
        queries = []
        def query(statement, arguments):
            queries.append((statement,arguments))
            rows = [(attempt.model_dump_json(),)] if 'execution_attempts' in statement else [(partial.model_dump_json(),)]
            return SimpleNamespace(fetchall=lambda:rows)
        self.runtime._lock = threading.RLock()
        self.runtime._connection = SimpleNamespace(execute=query)
        async def timeout(*args,**kwargs):
            raise TimeoutError()
        self.scoped.execute = timeout
        capture = runner.preserve_scoped
        with self.assertRaises(TimeoutError):
            await self.invoke(capture=capture)
        observation = self.repo.records[('composed_runner_result','composed:disposable')]
        self.assertEqual(observation['outer_attempt_digests'],[content_digest(attempt)])
        self.assertEqual(observation['outer_receipt_digests'],[content_digest(partial)])
        self.assertEqual(self.repo.finish[0][1]['accounting'],usage)
        self.assertTrue(all(arguments==(self.action.action_id,) and 'LIMIT 2' in statement for statement,arguments in queries))
        self.assertFalse(any(kind == 'boundary_probe' for kind,identity in self.repo.records))

    async def test_cleanup_failure_does_not_drop_measurement(self):
        async def fail_close():
            raise RuntimeError('synthetic cleanup')
        self.scoped.close = fail_close
        with self.assertRaises(RuntimeError):
            await self.invoke()
        self.assertEqual(len(self.repo.finish),1)
        self.assertFalse(self.repo.records[('composed_runner_result','composed:disposable')]['cleanup_confirmed'])
        self.assertIsNotNone(self.repo.finish[0][1]['accounting'])
        self.assertFalse(any(kind == 'boundary_probe' for kind,identity in self.repo.records))


if __name__ == '__main__':
    unittest.main()
