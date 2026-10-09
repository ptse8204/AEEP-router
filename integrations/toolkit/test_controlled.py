"""No Docker/model calls: exercise durable pre-dispatch checks and per-trial receipts."""
import asyncio
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import controlled
import controlled_report
import stack
from receipts import FixtureRecord

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    AssessmentPlanningRequest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.errors import ConfigurationError
from aeep.models import ExecutionStatus, ExecutorSpec, RawExecution, utc_now
from aeep.store import ReceiptStore


class ControlledTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ReceiptStore(str(Path(self.temp.name)/'receipts.sqlite3'))
        self.addCleanup(self.store.close)
        self.repo = AssessmentRepository(self.store)
        definition = self.repo.put('fixture', 'source', FixtureRecord(facts={'synthetic': True}))
        self.repo.review(definition)
        self.grant = AssessmentAuthorization(subject_digests=[definition], recipe_digests=[definition], environment_digests=[definition],
                                             limits=AssessmentLimits(max_operations=2, max_elapsed_seconds=150),
                                             expires_at=utc_now()+timedelta(hours=1))
        self.repo.grant(self.grant)
        self.spec = ExecutorSpec(id='test', capability='fixture', kind='command', description='test', config={'argv': ['unused']})
        self.request = AssessmentPlanningRequest(subject_digest=definition, recipe_digest=definition, mapping_digest=definition,
                                                environment_digest=definition, authorization_id=self.grant.authorization_id,
                                                definition_digests=[definition], planner=self.spec)
        environment = AssessmentEnvironment(environment_id='test', kind='container', identity={}, container_image='sha256:'+'a'*64, container_runtime='/unused/docker', container_socket='/unused/socket')
        self.bridge = controlled.TrialBridge(self.repo, self.request, environment, self.spec, {'current prompt': 'case'}, 'fixture skill')
        self.calls = []

    def message(self, treatment=False):
        return {'kind': 'trial', 'prompt': 'current prompt', 'treatment': treatment}

    async def execute(self, context):
        self.calls.append(context)
        # Reservation is already durable before the executor is entered.
        ledger = self.repo.operation_ledger(self.request.plan_id)
        self.assertIsNone(ledger.operations[-1].elapsed_seconds)
        context.invocation_check()
        return RawExecution(status=ExecutionStatus.SUCCESS, output={'output': 'synthetic output',
                    'candidate_exposed': context.request.input['skill'] is not None, 'uid': 65534,
                    'python_available': True, 'shell_available': True}, metadata={'container_name': context.attempt_id})

    def dispatch(self, message):
        with patch.object(controlled.ContainerExecutor, 'execute', self.execute):
            return asyncio.run(self.bridge.dispatch(message))

    def test_each_arm_has_own_reserved_operation_receipt_and_no_persisted_payload(self):
        self.assertEqual(self.dispatch(self.message()), {'output': 'synthetic output'})
        self.dispatch(self.message(True))
        results = self.bridge.results
        self.assertEqual(len({r['receipt_ref'] for r in results}), 2)
        self.assertEqual(len({r['worker_name'] for r in results}), 2)
        self.assertIsNone(self.calls[0].request.input['skill'])
        self.assertEqual(self.calls[1].request.input['skill'], 'fixture skill')
        for operation in self.repo.operation_ledger(self.request.plan_id).operations:
            self.assertIsNotNone(operation.elapsed_seconds)
        stored = '\n'.join(row[0] for row in self.store._connection.execute('SELECT payload_json FROM assessment_records'))
        self.assertNotIn('current prompt', stored)
        self.assertNotIn('fixture skill', stored)
        self.assertNotIn('synthetic output', stored)

    def test_replay_and_unreviewed_messages_never_dispatch(self):
        for bad in [self.message() | {'prompt': 'future case'}, self.message() | {'command': 'injected'}, self.message() | {'treatment': 1}]:
            with self.assertRaises(ValueError):
                self.dispatch(bad)
        self.assertEqual(self.calls, [])
        self.dispatch(self.message())
        with self.assertRaises(ConfigurationError):
            self.dispatch(self.message())
        self.assertEqual(len(self.calls), 1)

    def test_revocation_before_dispatch_preserves_counters(self):
        self.repo.revoke(self.grant.authorization_id)
        with self.assertRaises(ConfigurationError):
            self.dispatch(self.message())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.repo.operation_ledger(self.request.plan_id).operations, [])

    def test_interruption_retains_reservation_and_stops_other_arm(self):
        async def failed(_executor, context):
            raise RuntimeError('lost process')
        with patch.object(controlled.ContainerExecutor, 'execute', failed), self.assertRaises(RuntimeError):
            asyncio.run(self.bridge.dispatch(self.message()))
        with self.assertRaises((ValueError, ConfigurationError)):
            self.dispatch(self.message(True))
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.repo.operation_ledger(self.request.plan_id).operations[0].elapsed_seconds)
        self.assertGreater(self.store._connection.execute("SELECT COUNT(*) FROM assessment_records WHERE kind='execution_event'").fetchone()[0], 0)

    def test_bad_worker_output_charged_and_stops_other_arm(self):
        async def malformed(_executor, context):
            return RawExecution(status=ExecutionStatus.SUCCESS, output={'output': 'untrusted'})
        with patch.object(controlled.ContainerExecutor, 'execute', malformed), self.assertRaises(ValueError):
            asyncio.run(self.bridge.dispatch(self.message()))
        operation = self.repo.operation_ledger(self.request.plan_id).operations[0]
        self.assertIsNotNone(operation.elapsed_seconds)
        self.assertFalse(self.repo.get('toolkit_controlled_result', operation.operation_id)['facts']['execution_success'])
        with self.assertRaises(ValueError):
            self.dispatch(self.message(True))
        self.assertEqual(self.calls, [])

    def test_missing_or_wrong_payload_identity_is_charged_and_rejected(self):
        self.bridge.skill = {'name':'fixture','sha256':'a'*64,'files':{}}
        with self.assertRaises(ValueError):
            self.dispatch(self.message(True))
        operation = self.repo.operation_ledger(self.request.plan_id).operations[0]
        self.assertIsNotNone(operation.elapsed_seconds)
        self.assertFalse(self.repo.get('toolkit_controlled_result', operation.operation_id)['facts']['execution_success'])

    def test_timeout_receipt_remains_and_prevents_next_worker(self):
        async def timed_out(_executor, context):
            return RawExecution(status=ExecutionStatus.TIMEOUT, error_type='TIMEOUT')
        with patch.object(controlled.ContainerExecutor, 'execute', timed_out), self.assertRaises(ValueError):
            asyncio.run(self.bridge.dispatch(self.message()))
        operation = self.repo.operation_ledger(self.request.plan_id).operations[0]
        self.assertIsNotNone(operation.elapsed_seconds)
        with self.assertRaises(ValueError):
            self.dispatch(self.message(True))
        self.assertEqual(self.calls, [])

    def test_existing_analysis_binds_complete_positions_and_receipts(self):
        suite = {'evals':[{'id':'case','prompt':'current prompt'}]}
        plan, recipe = controlled_report.freeze(self.repo, self.request, suite, self.spec)
        self.dispatch(self.message())
        self.dispatch(self.message(True))
        output = Path(self.temp.name)
        rows = []
        for arm in ('control','treatment'):
            artifact = output/'upstream'/arm/'outputs'
            artifact.mkdir(parents=True)
            (artifact/'output.txt').write_text('synthetic output')
            rows.append({'case':'case','arm':'with_skill' if arm=='treatment' else 'without_skill',
                         'artifact':arm,'verified':True})
        definition = FixtureRecord(facts={'stack':stack.manifest()})
        args = (output,self.repo,plan,recipe,definition,self.bridge.environment)
        summary = controlled_report.create(*args,self.bridge.results,rows)
        self.assertEqual(summary['reviewed_analysis']['outcome'], 'insufficient_evidence')
        self.assertFalse(summary['reviewed_analysis']['qualification_passed'])
        self.assertEqual(summary['reviewed_analysis']['minimum_holdout_cases'],100)
        self.assertIsNone(summary['reviewed_analysis']['actual_cash'])
        with self.assertRaises(ValueError):
            controlled_report.create(*args,self.bridge.results[:-1],rows)
        (output/'upstream/control/outputs/output.txt').write_text('changed')
        with self.assertRaises(ValueError):
            controlled_report.create(*args,self.bridge.results,rows)

    def test_budget_exhaustion_stops_new_worker(self):
        self.dispatch(self.message())
        self.dispatch(self.message(True))
        self.bridge.cases['another prompt'] = 'second'
        with self.assertRaises(ConfigurationError):
            self.dispatch(self.message() | {'prompt': 'another prompt'})
        self.assertEqual(len(self.calls), 2)


if __name__ == '__main__':
    unittest.main()
