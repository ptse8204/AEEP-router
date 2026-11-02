"""Only the unstarted reviewed control, with Docker stdin attached; no rebuild."""
import argparse,asyncio,importlib.util,json,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
spec=importlib.util.spec_from_file_location('original_scanner_review',HERE/'run.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
from aeep.assessment.models import AssessmentLimits,RecipeMaterializationRequest,content_digest
from aeep.models import ActionRequest,ExecutionReceipt,SideEffect,utc_now
from aeep.executors.base import ExecutionContext

async def main():
 review,context,ready=original.verify();assert ready
 identity=original.file_digest(HERE/'operation-review.json')
 amendment=json.loads((HERE/'stdin-amendment.json').read_bytes());amendment_id=original.file_digest(HERE/'stdin-amendment.json')
 assert amendment['parent_review']==identity
 assert original.file_digest(HERE/'continue.py')==amendment['driver_sha256']
 approval=json.loads((HERE/'operator-approval.json').read_bytes());assert approval['approved'] and approval['review_sha256']==identity
 binding=json.loads((HERE/'execution/image-binding.json').read_bytes())
 image=json.loads(original.readonly(['image','inspect',binding['image_id']]))[0]
 assert image['Id']==binding['image_id']
 assert binding['context_sha256']==original.file_digest(HERE/'context.json')
 with (HERE/'unstarted-control-claimed.json').open('x') as stream:json.dump({'amendment_sha256':amendment_id},stream)
 store=original.ReceiptStore(HERE/'execution/canonical.sqlite3');repo=original.AssessmentRepository(store)
 plan_id=json.loads((HERE/'execution/operation-ledger.json').read_bytes())['plan_id']
 scope=RecipeMaterializationRequest.model_validate(repo.get('recipe_materialization_request',plan_id))
 ledger=repo.operation_ledger(plan_id)
 assert len(ledger.operations)==3 and all(row.elapsed_seconds is not None for row in ledger.operations)
 assert not any(row.stage=='scanner_static-negative-control' for row in ledger.operations)
 ref=repo.put('toolkit_scanner_driver_amendment',amendment_id,amendment);repo.review(ref)
 narrowed=scope.model_copy(update={'definition_digests':[*scope.definition_digests,ref]})
 name='aeep-scanner-control-'+amendment_id[:10]
 import subprocess
 check=subprocess.run([*original.DOCKER,'container','inspect',name],capture_output=True,text=True,timeout=10)
 assert check.returncode!=0 and 'No such' in check.stderr
 argv=original.container(image['Id'],name,['/opt/aeep-scanner/bin/python','-I','-B','/opt/aeep-stack/scanner_worker.py'])
 argv.insert(argv.index('run')+1,'-i')
 model=original.spec('static-negative-control',argv,125)
 payload=json.loads((HERE/'static-negative-control.json').read_bytes())
 action=ActionRequest(capability=model.capability,input=payload)
 key='scanner:'+identity+':static-negative-control'
 repo.reserve(narrowed,key,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=130),stage='scanner_static-negative-control')
 executor=original.CommandExecutor();raw=None;started=utc_now();clock=time.monotonic()
 result={'passed':False,'amendment_sha256':amendment_id,'models':0,'image_retained':True,'selected_candidate_retry':False}
 try:
  request=ExecutionContext(request=action,spec=model,estimate=model.estimate,attempt=1,attempt_id=key,approved_side_effect=SideEffect.WRITE,
   invocation_check=lambda:(repo.authorize(narrowed),None)[1])
  raw=await(await executor.start(request)).task
  receipt=ExecutionReceipt(decision_id=key,action_id=action.action_id,capability=model.capability,executor_id=model.id,
   executor_kind=model.kind,status=raw.status,started_at=started,ended_at=utc_now(),estimated=model.estimate,actual_resources=raw.resources,
   accounting=raw.accounting,execution_success=raw.status.value=='success',error_type=raw.error_type,
   metadata={'parent_review_sha256':identity,'amendment_sha256':amendment_id,'evidence_kind':'upstream_engineering',**raw.metadata})
  store.save_receipt(receipt)
  (HERE/'execution/control-stdin-receipt.json').write_text(receipt.model_dump_json(indent=2)+'\n')
  (HERE/'execution/control-stdin-process.json').write_text(json.dumps({'stdout':(raw.stdout or '')[:8192],'stderr':(raw.stderr or '')[:8192]},indent=2)+'\n')
  if isinstance(raw.output,dict):
   (HERE/'execution/control-stdin-result.json').write_text(json.dumps(raw.output,indent=2)+'\n')
   result['passed']=(receipt.execution_success and raw.output.get('candidate_sha256')==payload['candidate_sha256']
    and raw.output.get('candidate_bytes_bound') is True and raw.output.get('findings_count',0)>0 and raw.output.get('analyzers_executed',0)>0)
 finally:
  repo.finish_operation(key,elapsed_seconds=time.monotonic()-clock,accounting=raw.accounting if raw else None,resources=raw.resources if raw else None)
  await executor.close()
  remaining=subprocess.run([*original.DOCKER,'container','inspect',name],capture_output=True,text=True,timeout=10)
  result['owned_container_removed']=remaining.returncode!=0 and 'No such' in remaining.stderr
  if not result['owned_container_removed']:result['passed']=False;result['cleanup']='UNRESOLVED_PRESERVED'
  (HERE/'execution/operation-ledger-after-control.json').write_text(repo.operation_ledger(plan_id).model_dump_json(indent=2)+'\n')
  result['wall_seconds']=time.monotonic()-clock
  (HERE/'execution/control-stdin-summary.json').write_text(json.dumps(result,indent=2)+'\n');store.close()
 print(json.dumps(result))

if __name__=='__main__':asyncio.run(main())
