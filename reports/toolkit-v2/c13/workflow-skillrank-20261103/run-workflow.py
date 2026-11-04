"""Run only the reviewed ordinary-CLI SkillRank lifecycle; never a comparison."""
from __future__ import annotations
import argparse,asyncio,contextlib,hashlib,io,json,shutil,sys,time
from datetime import datetime,UTC
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
SNAPSHOT=json.loads((HERE/'source-snapshot.json').read_bytes());SOURCE=Path(SNAPSHOT['coordinator_source_snapshot'])
sys.path.insert(0,str(SOURCE/'src'))
from aeep.assessment.identity import file_digest
from aeep.assessment.models import AssessmentLimits,AssessmentScopeAmendment,RecipeMaterializationRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.execution import ExecutionEvidence,persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest,ExecutionReceipt,ExecutorKind,ExecutorSpec,ResourceVector,SideEffect,utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.cli import main as cli
from aeep_toolkit.install_runtime import digest,parse_installation
from aeep_toolkit.workflow_catalog import CatalogContainerExecutor,CatalogRuntimeDefinition


def load(path):return json.loads(Path(path).read_bytes())
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def guard(review):
 assert verification_source_digest(SOURCE)==review['source']
 assert datetime.now(UTC)<datetime.fromisoformat(review['expires_at'].replace('Z','+00:00'))
 assert shutil.disk_usage(ROOT).free>=50*1024**3
 for path,expected in review['assets'].items():assert file_digest(Path(path))==expected,path
 checks=load(review['source_checks']);assert checks['source_before']==checks['source_after']==review['source']
 assert len(checks['checks'])==13 and all(c['exit_code']==0 for c in checks['checks'])


async def probe(repo,request,definition,binary,config,operation):
 source=(HERE/'boundary-program.py').read_text()
 spec=ExecutorSpec(id='skillrank.boundary',capability='toolkit.catalog-boundary@1',kind=ExecutorKind.COMMAND,
  side_effect=SideEffect.READ,description='Owned first-party offline boundary check before catalog execution',
  config={'argv':['python3','-I','-B','-c',source],'argv_literal':True,'stdin_json':True,'max_output_bytes':64000,
          'timeout_seconds':20,'output':{'type':'json'}})
 action=ActionRequest(action_id=operation,capability=spec.capability,input={'host_canary':str(HERE/'boundary-program.py'),
  'docker_socket':str(definition.environment.container_socket),'binary_sha256':file_digest(binary)})
 repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=60),stage='skillrank_cli_boundary')
 executor=CatalogContainerExecutor(definition,binary,config);raw=None;error=None;began=time.perf_counter();started=utc_now()
 try:
  with persist_execution_events(lambda journal,event:repo.put('execution_event',journal+':'+str(event.sequence),event)):
   raw=await(await executor.start(ExecutionContext(request=action,spec=spec,estimate=spec.estimate,attempt=1,
      attempt_id=operation,approved_side_effect=SideEffect.READ,invocation_check=lambda:(repo.authorize(request),content_digest(definition.environment))[1]))).task
  assert raw.status.value=='success' and raw.output['passed'] and executor.cleanup_verified
  evidence=ExecutionEvidence.model_validate(raw.metadata['execution_evidence']);assert evidence.complete
  repo.put('execution_evidence',evidence.digest(),evidence)
 except BaseException as failure:error=type(failure).__name__
 finally:
  if not executor.cleanup_verified:await executor.cleanup(operation)
  await executor.close();elapsed=time.perf_counter()-began
  repo.finish_operation(operation,elapsed_seconds=elapsed,accounting=raw.accounting if raw else None,resources=ResourceVector(latency_ms=elapsed*1000))
  receipt=ExecutionReceipt(decision_id=operation,action_id=operation,capability=spec.capability,executor_id=spec.id,executor_kind=spec.kind,
    status='success' if error is None else 'failed',started_at=started,ended_at=utc_now(),estimated=spec.estimate,
    actual_resources=ResourceVector(latency_ms=elapsed*1000),execution_success=error is None,error_type=error,
    metadata={'cleanup_verified':executor.cleanup_verified,'implementation_source':SNAPSHOT['source'],
              'observed_resource_dimensions':['latency_ms'],'container_resource_usage':'unavailable'})
  repo.store.save_receipt(receipt);write(HERE/'runtime-execution/boundary-receipt.json',receipt.model_dump(mode='json'))
  if raw is not None:write(HERE/'runtime-execution/boundary-result.json',raw.output)
  if not executor.cleanup_verified:repo.put('toolkit_catalog_cleanup_uncertain',operation,receipt)
 assert error is None and executor.cleanup_verified,'Boundary failed; preserve charge/resources and stop'


def execute(review,identity):
 guard(review)
 prepared=load(HERE/'workflow-preparation.json')
 execution=HERE/'runtime-execution';execution.mkdir(mode=0o700)
 with (HERE/'runtime-started.json').open('x') as f:json.dump({'review_sha256':identity,'started_at':utc_now().isoformat()},f)
 repo_store=ReceiptStore(prepared['original_ledger']);repo=AssessmentRepository(repo_store)
 amendment=AssessmentScopeAmendment.model_validate(load(HERE/'scope-amendment.json'))
 scope=load(HERE/'accounting.json');request=RecipeMaterializationRequest.model_validate(scope['request'])
 before=list(repo_store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(request.authorization_id,)).fetchone())
 assert before==prepared['grant_counters'],'Original counters changed; reconcile before dispatch'
 grant=repo.effective_grant(request.authorization_id)
 assert grant.limits.model_dump(mode='json')==prepared['grant_original_limits']
 assert not repo_store._connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(request.authorization_id,)).fetchone()
 definitions={ref:repo_store._connection.execute('SELECT payload_json FROM assessment_records WHERE digest=?',(ref,)).fetchone()[0]
  for ref in {*amendment.subject_digests,*amendment.recipe_digests,*amendment.environment_digests,*amendment.reviewed_digests}}
 repo.approve_bundle(amendment,{ref:json.loads(value) for ref,value in definitions.items()})
 outer='skillrank-cli:'+identity+':overhead'
 overhead_request=request.model_copy(update={'plan_id':request.plan_id+':driver-overhead'})
 repo.put('recipe_materialization_request',overhead_request.plan_id,overhead_request)
 repo.reserve(overhead_request,outer,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=60),stage='skillrank_cli_driver_overhead')
 began=time.perf_counter();nested=0.;results=[];status={'passed':False,'models':0,'comparisons':'PAUSED','all_stack_complete':False,
  'skillrank_bounded_evaluation':'OPEN','candidate_usefulness':'NOT_ASSESSED','selection_usefulness':'NOT_ASSESSED',
  'cleanup_uncertain':False,'accounting_uncertain':False,'original_grant_preserved':request.authorization_id,'counters_before':before}
 def call(name,arguments,expected_exit=0):
  nonlocal nested
  guard(review);clock=time.perf_counter();stream=io.StringIO();errors=io.StringIO()
  try:
   with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(errors):
    try:code=cli(arguments)
    except SystemExit as stopped:code=stopped.code
   assert code==expected_exit,'CLI failed; do not repeat started operation'
   value=json.loads(stream.getvalue());write(execution/(name+'.json'),value)
   results.append({'name':name,'result':str(execution/(name+'.json'))});return value
  except BaseException as error:
   write(execution/(name+'-failure.json'),{'error_type':type(error).__name__,'stdout':stream.getvalue()[:8192],'stderr':errors.getvalue()[:8192]})
   raise
  finally:nested+=time.perf_counter()-clock
 def life(stage,name,runtime='skillrank-files',configuration='document-data',execute=True,expected_exit=0):
  args=['workflow',stage,'--workflow',str(HERE/'workflow.json'),'--configuration',configuration,'--runtime',runtime,
   '--accounting',str(HERE/'accounting.json'),'--operation-id',name+'-preview']
  facts=call(name+'-preview',args)
  if stage=='readiness' or not execute:return facts
  assert not facts['blockers'],facts['blockers']
  args[args.index(name+'-preview')]=name
  return call(name,[*args,'--reviewed-digest',facts['review_sha256']],expected_exit=expected_exit)
 try:
  assert life('setup','retained-setup')['complete']
  assert life('setup','retained-idempotent')['complete']
  for configuration in ('document-data','software-engineering'):
   ready=life('readiness',configuration+'-readiness',configuration=configuration)
   assert ready['observations']['skillrank-files']['installed'] is True
   assert ready['observations']['skillrank-files']['functional_readiness']=='NOT_VERIFIED'
  definition=CatalogRuntimeDefinition.model_validate(load(HERE/'catalog-runtime.json'))
  plan=parse_installation(load(HERE/'retained-installation.json'));binary=Path(plan.destination)/next(f.destination for f in plan.files if f.primary and f.executable)
  clock=time.perf_counter()
  try:asyncio.run(probe(repo,request,definition,binary,Path(prepared['runtime'])/'docker-config','skillrank-cli:'+identity+':boundary'))
  finally:nested+=time.perf_counter()-clock
  for name,configuration,mode,value in [('document-search','document-data','search','spreadsheet'),
     ('software-show','software-engineering','show','aeep/software-catalog-control'),
     ('missing-show','document-data','show','aeep/not-a-real-record')]:
   args=['workflow','catalog','--workflow',str(HERE/'workflow.json'),'--configuration',configuration,'--mode',mode,'--value',value,
    '--accounting',str(HERE/'accounting.json'),'--operation-id',name+'-preview']
   preview=call(name+'-preview',args);assert not preview['blockers']
   args[args.index(name+'-preview')]=name
   found=call(name,[*args,'--reviewed-digest',preview['review_sha256']])
   assert found['cleanup_verified'] and found['status']==('not_found' if name=='missing-show' else 'completed')
   if name=='document-search':assert [i['slug'] for i in found['result']['items']]==['aeep/document-catalog-control']
   if name=='software-show':assert found['result']['slug']==value
  # The retained installation is referenced by both configurations and cannot be removed.
  shared=life('remove','retained-shared-removal',execute=False)
  assert shared['blockers'] and shared['shared_references']['skillrank-files']==['software-engineering:skillrank-files']
  assert life('setup','disposable-setup','disposable-files')['complete']
  disposable=parse_installation(load(HERE/'disposable-installation.json'))
  note=Path(disposable.destination)/'owned-preservation-control.txt';note.write_text('Exact first-party removal control; preserve until checked.\n')
  original_hash=file_digest(note)
  # A changed tree is a failed removal, never a reason for broad cleanup.
  failed=life('remove','disposable-conflict','disposable-files',expected_exit=2);assert not failed['complete'] and file_digest(note)==original_hash
  note.unlink()  # Only this exact newly owned fixture is authorized for removal.
  assert life('remove','disposable-remove','disposable-files')['complete']
  assert not Path(disposable.destination).exists() and binary.is_file()
  status.update(passed=True,retained_runtime=str(Path(plan.destination)),disposable_removed=True,
   retained_shared_removal_blocked=True,results=results,current_source_cli_catalog=True)
 except BaseException as failure:status['error_type']=type(failure).__name__
 finally:
  try:
   elapsed=time.perf_counter()-began-nested
   repo.finish_operation(outer,elapsed_seconds=max(0.,elapsed),resources=ResourceVector(latency_ms=max(0.,elapsed)*1000))
   write(execution/'operation-ledger.json',repo.operation_ledger(request.plan_id).model_dump(mode='json'))
   write(execution/'driver-operation-ledger.json',repo.operation_ledger(overhead_request.plan_id).model_dump(mode='json'))
   after=list(repo_store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(request.authorization_id,)).fetchone())
   status['counters_after']=after;status['additional_operations']=after[0]-before[0]
   status['cleanup_uncertain']=repo_store._connection.execute("SELECT 1 FROM assessment_records WHERE kind='toolkit_catalog_cleanup_uncertain' LIMIT 1").fetchone() is not None
   status['accounting_uncertain']=repo_store._connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(request.authorization_id,)).fetchone() is not None
   assert after[0]<=40 and after[1]==0 and after[2]<=4500 and after[3]=='0'
   assert status['additional_operations']<=review['workflow']['maximum_additional_operations']
  except BaseException as failure:status.update(passed=False,accounting_uncertain=True,accounting_error_type=type(failure).__name__)
  status['free_bytes_after']=shutil.disk_usage(ROOT).free
  write(execution/'summary.json',status);repo_store.close()
 return status


if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--execute-approved');args=parser.parse_args()
 review=load(HERE/'operation-review.json');identity=file_digest(HERE/'operation-review.json')
 guard(review)
 if args.execute_approved is None:print(json.dumps({'review_sha256':identity,'execution':False}));raise SystemExit(0)
 approval=load(HERE/'operator-approval.json');assert args.execute_approved==identity==approval['review_sha256'] and approval['approved'] is True
 result=execute(review,identity);print(json.dumps(result))
 if not result['passed']:raise SystemExit(1)
