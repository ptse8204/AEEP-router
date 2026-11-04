"""Run the real CLI driver on owned synthetic files and executor substitutes only."""
import importlib.util,json,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import pytest
from test_toolkit_workflow_catalog import configured
from aeep.assessment.models import AssessmentAuthorization,AssessmentBudgetAmendment,AssessmentLimits,AssessmentScopeAmendment,content_digest
from aeep.executors.base import BaseExecutor
from aeep.models import RawExecution,utc_now
from aeep_toolkit import catalog_worker,workflow_catalog
from aeep_toolkit.file_runtime import prepare_files
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.install_runtime import parse_installation

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
spec=importlib.util.spec_from_file_location('first_party_driver_check',HERE/'run-workflow.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix='aeep-catalog-driver-fixture-') as temporary,pytest.MonkeyPatch.context() as monkeypatch:
 root=Path(temporary).resolve();path,router,repo,binding,scope_file,scope,plan=configured(root)
 try:
  # Existing fixture source is inert text, never an executable upstream binary.
  data=json.loads(path.read_bytes());selected=data['configurations']['document-data']
  selected['runtimes']={'skillrank-files':selected['runtimes']['skillrank-files']}
  data['configurations']['software-engineering']=json.loads(json.dumps(selected))
  disposable=prepare_files(plan.preview,plan.policy,root/'disposable-runtime',Path(plan.artifact_root),plan.files)
  write(root/'retained-installation.json',plan.model_dump(mode='json'));write(root/'disposable-installation.json',disposable.model_dump(mode='json'))
  selected['runtimes']['disposable-files']={'installation':{'path':str(root/'disposable-installation.json'),'sha256':sha(root/'disposable-installation.json')},'components':{'skillrank':'engine'}}
  write(path,data)
  scope=WorkflowAccountingDefinition.model_validate(scope.model_dump(mode='json')|{'workflow_sha256':sha(path),'configurations':['document-data','software-engineering'],'operations':['setup','readiness','remove','catalog']})
  write(scope_file,scope.model_dump(mode='json'));scope_ref=repo.put('toolkit_workflow_accounting',content_digest(scope),scope)
  root_grant=AssessmentAuthorization.model_validate(repo.get('authorization',scope.request.authorization_id))
  repo.approve_budget_amendment(AssessmentBudgetAmendment(authorization_id=root_grant.authorization_id,authorization_digest=content_digest(root_grant),
   limits=AssessmentLimits(max_operations=40,max_model_turns=0,max_elapsed_seconds=4500),expires_at=root_grant.expires_at))
  amendment=AssessmentScopeAmendment(authorization_id=root_grant.authorization_id,authorization_digest=content_digest(root_grant),
   subject_digests=[scope.request.subject_digest],recipe_digests=[scope.request.recipe_digest],environment_digests=[scope.request.environment_digest],reviewed_digests=[content_digest(binding),scope_ref])
  write(root/'scope-amendment.json',amendment.model_dump(mode='json'))
  write(root/'workflow-preparation.json',{'original_ledger':str(root/'canonical.sqlite3'),'grant_counters':[0,0,0.,'0'],
    'grant_original_limits':repo.effective_grant(root_grant.authorization_id).limits.model_dump(mode='json'),'runtime':str(root)})
  (root/'docker-config').mkdir()
  async def fake_probe(repo,request,definition,binary,config,operation):
   repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=60),stage='first_party_fixture_boundary')
   repo.finish_operation(operation,elapsed_seconds=0.)
  monkeypatch.setattr(workflow_catalog,'CatalogContainerExecutor',Fixture)
  monkeypatch.setattr(module,'probe',fake_probe);monkeypatch.setattr(module,'HERE',root);monkeypatch.setattr(module,'guard',lambda _:None)
  result=module.execute({'workflow':{'maximum_additional_operations':24}},'f'*64)
  assert result['passed'],{'result':result,'failures':{p.name:json.loads(p.read_bytes()) for p in (root/'runtime-execution').glob('*-failure.json')}}
  assert result['additional_operations']==24,result
  assert not result['cleanup_uncertain'] and not result['accounting_uncertain']
  output={'passed':True,'evidence_kind':'first_party_substitutes_only','additional_operations':24,'models':0,
   'actual_upstream_execution':False,'same_cli_driver_and_production_lifecycle':True,'temporary_fixture_removed':True}
 finally:router.store.close()
(HERE/'driver-controls.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output))
