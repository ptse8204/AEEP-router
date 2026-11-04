"""Validate continuation accounting with real CLI and first-party substitutes."""
import importlib.util,json,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import pytest
from test_toolkit_workflow_catalog import configured
from aeep.assessment.models import AssessmentAuthorization,AssessmentBudgetAmendment,AssessmentLimits,content_digest
from aeep.executors.base import BaseExecutor
from aeep.models import RawExecution
from aeep_toolkit import catalog_worker,workflow_catalog
from aeep_toolkit.file_runtime import prepare_files
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition

def write(path,value):path.write_text(json.dumps(value))
def sha(path):
 import hashlib
 return hashlib.sha256(path.read_bytes()).hexdigest()
class Fixture(BaseExecutor):
 cleanup_verified=True
 def __init__(self,*_):pass
 async def cleanup(self,*_):return True
 async def execute(self,context):
  p=context.request.input;q=p['query'];missing=q['value']=='aeep/not-a-real-record'
  result=None if missing else {'items':[{'slug':'aeep/document-catalog-control'}]} if q['mode']=='search' else {'slug':q['value']}
  return RawExecution(status='success',output={'component':'skillrank','source_revision':catalog_worker.SOURCE_REVISION,
   'version':catalog_worker.VERSION,'binary_sha256':p['binary_sha256'],'catalog_sha256':p['catalog_sha256'],
   'implementation_source':p['implementation_source'],'server_stopped':True,'status':'not_found' if missing else 'completed',
   'result':result,'provider_claims_are_not_scan_or_usefulness_evidence':True})
loader=importlib.util.spec_from_file_location('continuation_fixture',HERE/'run-runtime.py')
module=importlib.util.module_from_spec(loader);loader.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix='aeep-skillrank-continuation-fixture-') as temporary,pytest.MonkeyPatch.context() as monkeypatch:
 root=Path(temporary).resolve();path,router,repo,binding,scope_file,scope,plan=configured(root)
 try:
  data=json.loads(path.read_bytes());selected=data['configurations']['document-data']
  selected['runtimes']={'skillrank-files':selected['runtimes']['skillrank-files']}
  data['configurations']['software-engineering']=json.loads(json.dumps(selected))
  disposable=prepare_files(plan.preview,plan.policy,root/'disposable-runtime',Path(plan.artifact_root),plan.files)
  write(root/'retained-installation.json',plan.model_dump(mode='json'));write(root/'disposable-installation.json',disposable.model_dump(mode='json'))
  selected['runtimes']['disposable-files']={'installation':{'path':str(root/'disposable-installation.json'),'sha256':sha(root/'disposable-installation.json')},'components':{'skillrank':'engine'}}
  write(path,data)
  scope=WorkflowAccountingDefinition.model_validate(scope.model_dump(mode='json')|{'workflow_sha256':sha(path),'configurations':['document-data','software-engineering'],'operations':['setup','readiness','remove','catalog']})
  write(scope_file,scope.model_dump(mode='json'));repo.review(repo.put('toolkit_workflow_accounting',content_digest(scope),scope))
  grant=AssessmentAuthorization.model_validate(repo.get('authorization',scope.request.authorization_id))
  first=AssessmentBudgetAmendment(authorization_id=grant.authorization_id,authorization_digest=content_digest(grant),limits=AssessmentLimits(max_operations=40,max_model_turns=0,max_elapsed_seconds=4500),expires_at=grant.expires_at)
  repo.approve_budget_amendment(first)
  history=scope.request.model_copy(update={'plan_id':'first-party-previous-charges'})
  for i in range(24):
   repo.reserve(history,'history-'+str(i),AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=1),stage='first_party_history')
   repo.finish_operation('history-'+str(i),elapsed_seconds=0.)
  counters=list(repo.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone())
  fresh=root/'continuation';fresh.mkdir()
  amendment=AssessmentBudgetAmendment(authorization_id=grant.authorization_id,authorization_digest=content_digest(grant),previous_amendment_digest=content_digest(first),limits=AssessmentLimits(max_operations=42,max_model_turns=0,max_elapsed_seconds=4500),expires_at=grant.expires_at)
  write(fresh/'budget-amendment.json',amendment.model_dump(mode='json'))
  write(root/'workflow-preparation.json',{'original_ledger':str(root/'canonical.sqlite3'),'runtime':str(root)})
  (root/'docker-config').mkdir()
  async def fake_probe(repo,request,*args):
   operation=args[-1];repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=60),stage='first_party_probe')
   repo.finish_operation(operation,elapsed_seconds=0.)
  monkeypatch.setattr(module,'HERE',fresh);monkeypatch.setattr(module,'OLD',root)
  monkeypatch.setattr(module,'validate',lambda _:None);monkeypatch.setattr(module.base,'probe',fake_probe)
  monkeypatch.setattr(module,'DiagnosticCatalogExecutor',Fixture)
  result=module.execute({'counters_before':counters,'unstarted_cli_operation_keys':[]},'e'*64)
  assert result['passed'],result
  assert result['additional_operations']==18 and result['counters_after'][0]==42
  assert not result['cleanup_uncertain'] and not result['accounting_uncertain']
  record={'passed':True,'evidence_kind':'first_party_substitutes_only','prior_operations_preserved':24,'additional_operations':18,'final_operations':42,
    'actual_upstream_execution':False,'production_cli_lifecycle':True,'fixture_workspace_removed':True,'models':0}
 finally:router.store.close()
(HERE/'driver-controls.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
