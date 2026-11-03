"""In-memory accounting and substituted-boundary controls; no Docker or install."""
from __future__ import annotations
import asyncio,importlib.util,json,tempfile
from pathlib import Path
from unittest.mock import patch
from aeep.assessment.models import AssessmentAuthorization,AssessmentBudgetAmendment,AssessmentScopeAmendment
from aeep.assessment.repository import AssessmentRepository
from aeep.executors.base import BaseExecutor
from aeep.models import RawExecution
from aeep.store import ReceiptStore

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('proposed_scanner_driver',HERE/'run-cli.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
authority=json.loads((HERE/'cli-authority.json').read_bytes())
runtime=module.ScannerRuntimeDefinition.model_validate_json((HERE/'scanner-runtime.json').read_bytes())

def fixture_repository():
    store=ReceiptStore(':memory:');repo=AssessmentRepository(store)
    for ref,value in authority['definitions'].items():
        store._connection.execute('INSERT INTO assessment_records VALUES (?,?,?,?)',('fixture_metadata',ref,ref,json.dumps(value)))
    store._connection.commit()
    for value in authority['original_grants']:
        repo.grant(AssessmentAuthorization.model_validate(value))
        baseline=authority['baseline'][value['authorization_id']]
        # Explicit synthetic prior counters, never copied into the real repository.
        store._connection.execute('UPDATE assessment_grants SET operations=?,elapsed_seconds=? WHERE id=?',
            (baseline['operations'],baseline['elapsed_seconds'],value['authorization_id']))
        store._connection.commit()
    budget=AssessmentBudgetAmendment.model_validate(authority['budget_amendment'])
    for value in authority['scope_amendments']:
        amendment=AssessmentScopeAmendment.model_validate(value)
        repo.approve_bundle(amendment,authority['definitions'],budget_amendment=budget if amendment.authorization_id==budget.authorization_id else None)
    return store,repo

results=[]
for passed,cleanup in ((True,True),(False,True),(True,False)):
    store,repo=fixture_repository();calls=[]
    class Fixture(BaseExecutor):
        async def execute(self,context):
            argv=context.spec.config['argv'];calls.append(argv)
            assert argv[argv.index('--entrypoint')+1]=='python3'
            assert argv[-3:-1]==['-B','-c']
            assert context.request.input==json.loads((HERE/'bootstrap-input.json').read_bytes())
            return RawExecution(status='success',output={'passed':passed,'category':'FIRST_PARTY_FIXTURE'})
    async def absent(*_args):return 1,b'No such container'
    async def finish(self,_identity):self.cleanup_verified=cleanup;return cleanup
    with tempfile.TemporaryDirectory(prefix='aeep-scanner-driver-fixture-') as tmp:
        out=Path(tmp);identity='first-party-'+str(passed)+'-'+str(cleanup)
        try:
            with patch.object(module,'CommandExecutor',Fixture),patch.object(module.ScanContainerExecutor,'checked_docker',absent),patch.object(module.ScanContainerExecutor,'cleanup',finish):
                asyncio.run(module.boundary(repo,runtime,out,identity))
        except AssertionError:
            assert not (passed and cleanup)
        else:assert passed and cleanup
        receipt=json.loads((out/'boundary-receipt.json').read_bytes())
        assert receipt['execution_success']==(passed and cleanup)
        assert (receipt['status']=='success')==(passed and cleanup)
        ledger=repo.operation_ledger(runtime.request.plan_id)
        assert len(ledger.operations)==1 and ledger.operations[0].elapsed_seconds is not None
        row=store._connection.execute('SELECT operations FROM assessment_grants WHERE id=?',(runtime.request.authorization_id,)).fetchone()
        assert row[0]==2,'One fixture prior operation plus one new probe, no counter reset'
        assert len(calls)==1
        results.append({'probe_passed':passed,'cleanup_verified':cleanup,'receipt_status':receipt['status'],
            'new_operations':1,'prior_fixture_counter_preserved':True})
    store.close()

print(json.dumps({'passed':True,'scenarios':results,'evidence_kind':'first_party_in_memory_and_executor_substitutes',
    'actual_docker_calls':0,'actual_scanner_calls':0,'actual_grant_amendments':0,'actual_installations':0}))
