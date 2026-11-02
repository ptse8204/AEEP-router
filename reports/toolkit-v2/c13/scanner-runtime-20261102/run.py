"""Bounded offline scanner execution; existing receipts/grants, no new service."""
from __future__ import annotations
import argparse,asyncio,json,shutil,subprocess,sys,time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
FROZEN=ROOT/'.aeep/stack-frozen-source-e363cfa5'
sys.path.insert(0,str(FROZEN/'src'))
from aeep.assessment.models import AssessmentAuthorization,AssessmentLimits,RecipeMaterializationRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest,ExecutionReceipt,ExecutorSpec,SideEffect,StrictModel,utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

DOCKER=['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock']
class Scope(StrictModel):
 role:str
 review_sha256:str
 purpose:str='Offline actual static scanner engineering; no capability comparison'


def readonly(arguments):
 completed=subprocess.run([*DOCKER,*arguments],capture_output=True,text=True,timeout=30,check=True)
 return completed.stdout


def verify():
 review=json.loads((HERE/'operation-review.json').read_bytes())
 for name,value in review['bound_files'].items():assert file_digest(ROOT/name)==value,name
 context=json.loads((HERE/'context.json').read_bytes())
 directory=Path(context['context'])
 actual={str(p.relative_to(directory)):file_digest(p) for p in directory.rglob('*') if p.is_file()}
 assert actual==context['assets'] and not any(p.is_symlink() for p in directory.rglob('*'))
 assert verification_source_digest(FROZEN)==review['source']
 gates=json.loads((ROOT/review['verification_checks']).read_bytes())
 ready=(gates['source_before']==gates['source_after']==review['source'] and len(gates['checks'])==13 and all(c['exit_code']==0 for c in gates['checks']))
 return review,context,ready


def spec(name,argv,seconds,output='json'):
 return ExecutorSpec(id='toolkit.scanner-'+name,capability='toolkit.upstream-engineering@1',
  description='Reviewed offline Cisco scanner image/component engineering',kind='command',side_effect='write',
  config={'argv':argv,'argv_literal':True,'stdin_json':True,'inherit_env':False,
   'timeout_seconds':seconds,'max_output_bytes':1048576,'output':{'type':output},
   'env':{'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':str(HERE/'execution/home'),
          'TMPDIR':str(HERE/'execution/tmp'),'LC_ALL':'C'}})


def container(image,name,command):
 return [*DOCKER,'run','--rm','--name',name,'--label','aeep.review=scanner-runtime-20261102',
  '--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
  '--user','65532:65532','--pids-limit','128','--memory','1g','--cpus','2',
  '--tmpfs','/workspace:rw,nosuid,nodev,noexec,size=67108864,mode=1777',
  '--env','HOME=/workspace/home','--env','TMPDIR=/workspace','--env','PYTHONDONTWRITEBYTECODE=1',
  '--workdir','/workspace',image,*command]


async def execute(review,context):
 identity=file_digest(HERE/'operation-review.json')
 with (HERE/'execution-started.json').open('x') as stream:json.dump({'review_sha256':identity},stream)
 execution=HERE/'execution';execution.mkdir()
 for child in ('home','tmp'):(execution/child).mkdir(mode=0o700)
 started=time.monotonic()
 result={'passed':False,'models':0,'cash_usd':0,'review_sha256':identity,
         'all_stack_integrations_complete':False,'candidate_usefulness':'NOT_ASSESSED'}
 store=ReceiptStore(execution/'canonical.sqlite3');repo=AssessmentRepository(store)
 refs=[]
 for role in ('subject','recipe','environment','mapping'):
  value=Scope(role=role,review_sha256=identity);ref=repo.put('toolkit_engineering_scope',role,value);repo.review(ref);refs.append(ref)
 grant=AssessmentAuthorization(authorization_id='scanner-engineering-'+identity,subject_digests=[refs[0]],
  recipe_digests=[refs[1]],environment_digests=[refs[2]],limits=AssessmentLimits(max_model_turns=0,max_operations=8,max_elapsed_seconds=1200,max_cash_usd=Decimal(0)),
  allowed_destinations=['local'],expires_at=utc_now()+timedelta(minutes=30))
 repo.grant(grant)
 scope=RecipeMaterializationRequest(subject_digest=refs[0],recipe_digest=refs[1],environment_digest=refs[2],mapping_digest=refs[3],
  authorization_id=grant.authorization_id,definition_digests=refs,seed=0)
 repo.put('recipe_materialization_request',scope.plan_id,scope)
 executor=CommandExecutor()
 owned_names=[]
 async def run(name,argv,seconds,payload=None,output='json'):
  repo.authorize(scope)
  assert verification_source_digest(FROZEN)==review['source']
  if name not in {'stop-owned','remove-owned'}:
   assert shutil.disk_usage(ROOT).free>50*1024**3+(review['execution_headroom_bytes'] if name=='build' else 32*1024**2)
  model=spec(name,argv,seconds,output);action=ActionRequest(capability=model.capability,input=payload or {})
  key='scanner:'+identity+':'+name
  repo.reserve(scope,key,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=seconds+5),stage='scanner_'+name)
  raw=None;began=utc_now();clock=time.monotonic()
  try:
   request=ExecutionContext(request=action,spec=model,estimate=model.estimate,attempt=1,attempt_id=key,
                            approved_side_effect=SideEffect.WRITE,invocation_check=lambda:(repo.authorize(scope),None)[1])
   raw=await(await executor.start(request)).task
   receipt=ExecutionReceipt(decision_id=key,action_id=action.action_id,capability=model.capability,executor_id=model.id,
    executor_kind=model.kind,status=raw.status,started_at=began,ended_at=utc_now(),estimated=model.estimate,
    actual_resources=raw.resources,accounting=raw.accounting,execution_success=raw.status.value=='success',error_type=raw.error_type,
    metadata={'review_sha256':identity,'evidence_kind':'upstream_engineering','docker_client_resources_are_not_worker_resources':True,**raw.metadata})
   store.save_receipt(receipt)
   (execution/(name+'-receipt.json')).write_text(receipt.model_dump_json(indent=2)+'\n')
   if isinstance(raw.output,dict):(execution/(name+'-result.json')).write_text(json.dumps(raw.output,indent=2)+'\n')
   (execution/(name+'-process.json')).write_text(json.dumps({'stdout':(raw.stdout or '')[:8192],'stderr':(raw.stderr or '')[:8192]},indent=2)+'\n')
   return raw
  finally:repo.finish_operation(key,elapsed_seconds=time.monotonic()-clock,accounting=raw.accounting if raw else None,resources=raw.resources if raw else None)
 try:
  parent=json.loads(readonly(['image','inspect',context['parent_tag']]))[0]
  assert parent['Id']==context['parent_id']
  (execution/'docker-before.json').write_text(readonly(['system','df','--format','json']))
  raw=await run('build',[*DOCKER,'build','--pull=false','--network=none','--tag',review['output_tag'],context['context']],600,output='text')
  assert raw.status.value=='success','image build failed'
  image=json.loads(readonly(['image','inspect',review['output_tag']]))[0]
  assert image['RootFS']['Layers'][:len(parent['RootFS']['Layers'])]==parent['RootFS']['Layers']
  assert image['Config']['User']=='65532:65532' and not image['Config'].get('Volumes')
  result['image_id']=image['Id'];result['image_retained']=True
  (execution/'image-binding.json').write_text(json.dumps({'image_id':image['Id'],'tag':review['output_tag'],'parent_id':parent['Id'],
   'parent_layers_verified':True,'context_sha256':file_digest(HERE/'context.json')},indent=2)+'\n')
  def own_name(name):
   probe=subprocess.run([*DOCKER,'container','inspect',name],capture_output=True,text=True,timeout=10)
   assert probe.returncode != 0 and 'No such' in probe.stderr,'container name is not proven absent'
   owned_names.append(name)
   return name
  probe=await run('boundary',container(image['Id'],own_name('aeep-scanner-boundary-'+identity[:10]),['python3','-I','-B','-c',(HERE/'boundary.py').read_text()]),30)
  assert probe.status.value=='success' and probe.output['passed'] is True
  assert probe.output['worker_sha256']==context['assets']['scanner_worker.py']
  for name in ('selected-candidate','static-negative-control'):
   payload=json.loads((ROOT/context['payloads'][name]['path']).read_bytes())
   raw=await run(name,container(image['Id'],own_name('aeep-scanner-'+name+'-'+identity[:10]),
      ['/opt/aeep-scanner/bin/python','-I','-B','/opt/aeep-stack/scanner_worker.py']),125,payload)
   assert raw.status.value=='success','actual scanner failed; retain receipt and stop'
   assert raw.output['candidate_sha256']==payload['candidate_sha256'] and raw.output['candidate_bytes_bound'] is True
   assert raw.output['analyzers_executed']>0 and raw.output['safety_verdict']=='NOT_ESTABLISHED'
   if name=='static-negative-control':assert raw.output['findings_count']>0,'reviewed static control was not detected'
  ledger=repo.operation_ledger(scope.plan_id)
  assert len(ledger.operations)==4 and all(row.elapsed_seconds is not None for row in ledger.operations)
  (execution/'operation-ledger.json').write_text(ledger.model_dump_json(indent=2)+'\n')
  result['passed']=True
 except BaseException as error:result['error_type']=type(error).__name__
 finally:
  cleanup=[]
  for name in owned_names:
   try:
    inspected=subprocess.run([*DOCKER,'container','inspect',name],capture_output=True,text=True,timeout=10)
    if inspected.returncode:
     assert 'No such' in inspected.stderr
     cleanup.append({'name':name,'state':'already_removed_by_owned_rm_flag'})
     continue
    found=json.loads(inspected.stdout)[0]
    assert found['Config']['Labels'].get('aeep.review')=='scanner-runtime-20261102'
    assert found['Image']==result.get('image_id')
    if found['State']['Running']:
     stopped=await run('stop-owned',[*DOCKER,'stop','--time','10',found['Id']],30,output='text')
     assert stopped.status.value=='success'
    again=subprocess.run([*DOCKER,'container','inspect',name],capture_output=True,text=True,timeout=10)
    if again.returncode==0:
     retained=json.loads(again.stdout)[0]
     assert retained['Id']==found['Id'] and not retained['State']['Running']
     removed=await run('remove-owned',[*DOCKER,'rm',found['Id']],30,output='text')
     assert removed.status.value=='success'
    else:assert 'No such' in again.stderr
    cleanup.append({'name':name,'state':'stopped_and_removed_owned_container'})
   except BaseException as error:
    result['passed']=False;cleanup.append({'name':name,'state':'UNRESOLVED_PRESERVED','error_type':type(error).__name__})
    break
  (execution/'cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
  final_ledger=repo.operation_ledger(scope.plan_id)
  assert len(final_ledger.operations)<=8
  (execution/'operation-ledger.json').write_text(final_ledger.model_dump_json(indent=2)+'\n')
  await executor.close()
  result['wall_seconds']=time.monotonic()-started
  result['accounting_scope']='Canonical charged build/probe/scan operations. Bootstrap/final persistence overhead not complete; client resource dimensions are not scanner worker measurements.'
  (execution/'summary.json').write_text(json.dumps(result,indent=2)+'\n');store.close()
 return result


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--execute-approved');args=parser.parse_args()
 review,context,ready=verify();identity=file_digest(HERE/'operation-review.json')
 if args.execute_approved is None:print(json.dumps({'review_sha256':identity,'executed':False,'source_checks_passed':ready}));return
 assert args.execute_approved==identity and ready
 approval=json.loads((HERE/'operator-approval.json').read_bytes());assert approval['approved'] is True and approval['review_sha256']==identity
 print(json.dumps(asyncio.run(execute(review,context))))


if __name__=='__main__':main()
