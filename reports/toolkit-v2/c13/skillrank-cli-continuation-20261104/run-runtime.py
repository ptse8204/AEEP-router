"""Finish only unstarted CLI phases; retain all terminal attempts and charges."""
from __future__ import annotations
import argparse,asyncio,contextlib,hashlib,importlib.util,io,json,shutil,sys,time
from datetime import datetime,UTC
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OLD=HERE.parent/'workflow-skillrank-20261103'
loader=importlib.util.spec_from_file_location('original_skillrank_cli_review',OLD/'run-workflow.py')
base=importlib.util.module_from_spec(loader);loader.loader.exec_module(base)
from aeep.assessment.models import AssessmentBudgetAmendment,AssessmentLimits,RecipeMaterializationRequest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import ResourceVector,utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.cli import main as cli
from aeep_toolkit.install_runtime import file_digest,parse_installation
from aeep_toolkit.workflow_catalog import CatalogContainerExecutor,CatalogRuntimeDefinition

def load(path):return json.loads(Path(path).read_bytes())
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def validate(review):
 assert datetime.now(UTC)<datetime.fromisoformat(review['expires_at'].replace('Z','+00:00'))
 assert verification_source_digest(Path(review['coordinator_source_snapshot']))==review['source']
 assert shutil.disk_usage(ROOT).free>=50*1024**3+64*1024**2
 for path,expected in review['assets'].items():assert file_digest(Path(path))==expected,path
 assert not load(OLD/'runtime-execution/summary.json')['passed']
 assert load(OLD/'package-execution/summary.json')['passed'] and load(OLD/'docs-attempt-1.json')['passed']
 gates=load(review['source_checks']);assert gates['source_before']==gates['source_after']==review['source']
 assert len(gates['checks'])==13 and all(row['exit_code']==0 for row in gates['checks'])

class DiagnosticCatalogExecutor(CatalogContainerExecutor):
 async def execute(self,context):
  raw=await super().execute(context)
  # Real delegation, not a substituted result. Persist only declared error categories.
  suffix=hashlib.sha256(str(context.attempt_id).encode()).hexdigest()[:16]
  write(HERE/'runtime-execution'/('raw-status-'+suffix+'.json'),{'status':raw.status.value,'error_type':raw.error_type,
   'error_message_category':raw.error_message,'exit_code':raw.exit_code,'cleanup_verified':self.cleanup_verified,
   'result':raw.output,'execution_evidence':raw.metadata.get('execution_evidence')})
  return raw

def execute(review,identity):
 validate(review);prepared=load(OLD/'workflow-preparation.json');scope=load(OLD/'accounting.json')
 request=RecipeMaterializationRequest.model_validate(scope['request'])
 with ReceiptStore(prepared['original_ledger']) as store:
  repo=AssessmentRepository(store)
  counters=list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(request.authorization_id,)).fetchone())
  assert counters==review['counters_before']
  assert not store._connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(request.authorization_id,)).fetchone()
  for key in review['unstarted_cli_operation_keys']:
   assert not store._connection.execute('SELECT 1 FROM assessment_operations WHERE id=?',('workflow:'+request.plan_id+':'+key,)).fetchone(),key
  (HERE/'runtime-execution').mkdir(mode=0o700)
  with (HERE/'execution-started.json').open('x') as f:json.dump({'review_sha256':identity,'started_at':utc_now().isoformat()},f)
  amendment=AssessmentBudgetAmendment.model_validate(load(HERE/'budget-amendment.json'))
  repo.approve_budget_amendment(amendment)
  overhead_request=request.model_copy(update={'plan_id':request.plan_id+':continuation-overhead'})
  repo.put('recipe_materialization_request',overhead_request.plan_id,overhead_request)
  outer='skillrank-cli:'+identity+':continuation-overhead'
  repo.reserve(overhead_request,outer,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=60),stage='skillrank_cli_driver_overhead')
  began=time.perf_counter();nested=0.;result={'passed':False,'models':0,'comparisons':'PAUSED','all_stack_complete':False,
   'bounded_evaluation':'OPEN','counters_before':counters,'cleanup_uncertain':False,'accounting_uncertain':False}
  def call(name,args,expected_exit=0):
   nonlocal nested
   validate(review);clock=time.perf_counter();out=io.StringIO();err=io.StringIO()
   try:
    with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
     try:code=cli(args)
     except SystemExit as stopped:code=stopped.code
    assert code==expected_exit
    value=json.loads(out.getvalue());write(HERE/'runtime-execution'/(name+'.json'),value);return value
   except BaseException as failure:
    write(HERE/'runtime-execution'/(name+'-failure.json'),{'error_type':type(failure).__name__,'stdout':out.getvalue()[:8192],'stderr':err.getvalue()[:8192]});raise
   finally:nested+=time.perf_counter()-clock
  def life(stage,name,runtime,*,preview_only=False,expected_exit=0):
   args=['workflow',stage,'--workflow',str(OLD/'workflow.json'),'--configuration','document-data','--runtime',runtime,
    '--accounting',str(OLD/'accounting.json'),'--operation-id',name+'-preview']
   facts=call(name+'-preview',args)
   if preview_only:return facts
   assert not facts['blockers']
   args[args.index(name+'-preview')]=name
   return call(name,[*args,'--reviewed-digest',facts['review_sha256']],expected_exit)
  try:
   definition=CatalogRuntimeDefinition.model_validate(load(OLD/'catalog-runtime.json'))
   plan=parse_installation(load(OLD/'retained-installation.json'));binary=Path(plan.destination)/next(f.destination for f in plan.files if f.primary and f.executable)
   # Reuse the original actual executor/probe lifecycle, adding diagnostic retention.
   base.HERE=HERE;base.CatalogContainerExecutor=DiagnosticCatalogExecutor
   import aeep_toolkit.workflow_catalog as catalog_module
   catalog_module.CatalogContainerExecutor=DiagnosticCatalogExecutor
   clock=time.perf_counter()
   try:asyncio.run(base.probe(repo,request,definition,binary,Path(prepared['runtime'])/'docker-config','skillrank-cli:'+identity+':boundary'))
   finally:nested+=time.perf_counter()-clock
   for name,config,mode,value in [('document-search','document-data','search','spreadsheet'),('software-show','software-engineering','show','aeep/software-catalog-control'),('missing-show','document-data','show','aeep/not-a-real-record')]:
    args=['workflow','catalog','--workflow',str(OLD/'workflow.json'),'--configuration',config,'--mode',mode,'--value',value,
     '--accounting',str(OLD/'accounting.json'),'--operation-id',name+'-preview']
    facts=call(name+'-preview',args);assert not facts['blockers']
    args[args.index(name+'-preview')]=name
    actual=call(name,[*args,'--reviewed-digest',facts['review_sha256']])
    assert actual['cleanup_verified'] and actual['status']==('not_found' if name=='missing-show' else 'completed')
    if name=='document-search':assert [item['slug'] for item in actual['result']['items']]==['aeep/document-catalog-control']
    if name=='software-show':assert actual['result']['slug']==value
   shared=life('remove','retained-shared-removal','skillrank-files',preview_only=True)
   assert shared['blockers'] and shared['shared_references']['skillrank-files']==['software-engineering:skillrank-files']
   assert life('setup','disposable-setup','disposable-files')['complete']
   disposable=parse_installation(load(OLD/'disposable-installation.json'))
   note=Path(disposable.destination)/'owned-preservation-control.txt';note.write_text('Exact first-party removal control; preserve until checked.\n');before=file_digest(note)
   refused=life('remove','disposable-conflict','disposable-files',expected_exit=2)
   assert not refused['complete'] and file_digest(note)==before
   note.unlink();assert life('remove','disposable-remove','disposable-files')['complete']
   assert binary.is_file() and not Path(disposable.destination).exists()
   result.update(passed=True,current_source_cli_catalog=True,retained_runtime=str(Path(plan.destination)),disposable_removed=True,shared_runtime_preserved=True)
  except BaseException as failure:result['error_type']=type(failure).__name__
  finally:
   try:
    elapsed=max(0.,time.perf_counter()-began-nested)
    repo.finish_operation(outer,elapsed_seconds=elapsed,resources=ResourceVector(latency_ms=elapsed*1000))
    write(HERE/'runtime-execution/operation-ledger.json',repo.operation_ledger(request.plan_id).model_dump(mode='json'))
    write(HERE/'runtime-execution/overhead-ledger.json',repo.operation_ledger(overhead_request.plan_id).model_dump(mode='json'))
    after=list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(request.authorization_id,)).fetchone())
    result.update(counters_after=after,additional_operations=after[0]-counters[0])
    result['cleanup_uncertain']=store._connection.execute("SELECT 1 FROM assessment_records WHERE kind='toolkit_catalog_cleanup_uncertain' LIMIT 1").fetchone() is not None
    result['accounting_uncertain']=store._connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(request.authorization_id,)).fetchone() is not None
    assert after[0]<=42 and after[1]==0 and after[2]<=4500 and after[3]=='0' and result['additional_operations']<=18
   except BaseException as failure:result.update(passed=False,accounting_uncertain=True,accounting_error_type=type(failure).__name__)
   result['free_bytes_after']=shutil.disk_usage(ROOT).free
   write(HERE/'runtime-execution/summary.json',result)
  return result

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--execute-approved');args=parser.parse_args()
 review=load(HERE/'operation-review.json');identity=file_digest(HERE/'operation-review.json');validate(review)
 if args.execute_approved is None:print(json.dumps({'review_sha256':identity,'execution':False}));raise SystemExit(0)
 approval=load(HERE/'operator-approval.json');assert args.execute_approved==identity==approval['review_sha256'] and approval['approved'] is True
 result=execute(review,identity);print(json.dumps(result))
 if not result['passed']:raise SystemExit(1)
