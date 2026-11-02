"""One additionally approved selected-candidate scan; retained image,no rebuild."""
import argparse,asyncio,importlib.util,json,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
spec=importlib.util.spec_from_file_location('original_scanner_review',HERE/'run.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
from aeep.assessment.models import AssessmentLimits,RecipeMaterializationRequest,content_digest
from aeep.models import ActionRequest,ExecutionReceipt,SideEffect,utc_now
from aeep.executors.base import ExecutionContext

class Amendment(original.StrictModel):
 definition:dict

async def main():
 review,context,ready=original.verify();assert ready
 identity=original.file_digest(HERE/'operation-review.json')
 amendment=json.loads((HERE/'selected-operation-review.json').read_bytes());amendment_id=original.file_digest(HERE/'selected-operation-review.json')
 assert amendment['parent_review']==identity
 for path,expected in amendment['bound_files'].items():assert original.file_digest(ROOT/path)==expected,path
 followup_approval=json.loads((HERE/'selected-operator-approval.json').read_bytes())
 assert followup_approval['approved'] is True and followup_approval['review_sha256']==amendment_id
 assert original.file_digest(HERE/'complete-selected.py')==amendment['driver_sha256']
 coordinator=json.loads((HERE/'selected-evidence-path-amendment.json').read_bytes())
 assert coordinator['parent_review']==amendment_id
 assert original.file_digest(HERE/'complete-selected-safe.py')==coordinator['safe_driver_sha256']
 for name in coordinator['new_evidence_files']:assert not (HERE/name).exists(),name
 approval=json.loads((HERE/'operator-approval.json').read_bytes());assert approval['approved'] and approval['review_sha256']==identity
 binding=json.loads((HERE/'execution/image-binding.json').read_bytes())
 image=json.loads(original.readonly(['image','inspect',binding['image_id']]))[0]
 assert image['Id']==binding['image_id']==amendment['image_id']
 assert binding['context_sha256']==original.file_digest(HERE/'context.json')
 store=original.ReceiptStore(HERE/'execution/canonical.sqlite3');repo=original.AssessmentRepository(store)
 plan_id=json.loads((HERE/'execution/operation-ledger.json').read_bytes())['plan_id']
 scope=RecipeMaterializationRequest.model_validate(repo.get('recipe_materialization_request',plan_id))
 ledger=repo.operation_ledger(plan_id)
 assert len(ledger.operations)==4 and all(row.elapsed_seconds is not None for row in ledger.operations)
 assert not any(row.stage=='scanner_selected-candidate-followup' for row in ledger.operations)
 repo.authorize(scope)
 with (HERE/'selected-followup-claimed.json').open('x') as stream:json.dump({'amendment_sha256':amendment_id},stream)
 coordinator_ref=repo.put('toolkit_scanner_driver_amendment',content_digest(coordinator),Amendment(definition=coordinator));repo.review(coordinator_ref)
 ref=repo.put('toolkit_scanner_driver_amendment',amendment_id,Amendment(definition=amendment));repo.review(ref)
 narrowed=scope.model_copy(update={'definition_digests':[*scope.definition_digests,ref,coordinator_ref]})
 name='aeep-scanner-selected-'+amendment_id[:10]
 import subprocess
 check=subprocess.run([*original.DOCKER,'container','inspect',name],capture_output=True,text=True,timeout=10)
 assert check.returncode!=0 and 'No such' in check.stderr
 argv=original.container(image['Id'],name,['/opt/aeep-scanner/bin/python','-I','-B','/opt/aeep-stack/scanner_worker.py'])
 argv.insert(argv.index('run')+1,'-i')
 model=original.spec('selected-candidate-followup',argv,125)
 payload=json.loads((HERE/'selected-candidate.json').read_bytes())
 action=ActionRequest(capability=model.capability,input=payload)
 key='scanner:'+identity+':selected-candidate-stdin'
 repo.reserve(narrowed,key,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=130),stage='scanner_selected-candidate-followup')
 executor=original.CommandExecutor();raw=None;started=utc_now();clock=time.monotonic()
 result={'passed':False,'amendment_sha256':amendment_id,'models':0,'image_retained':True,'additional_selected_call':True}
 try:
  request=ExecutionContext(request=action,spec=model,estimate=model.estimate,attempt=1,attempt_id=key,approved_side_effect=SideEffect.WRITE,
   invocation_check=lambda:(repo.authorize(narrowed),None)[1])
  raw=await(await executor.start(request)).task
  receipt=ExecutionReceipt(decision_id=key,action_id=action.action_id,capability=model.capability,executor_id=model.id,
   executor_kind=model.kind,status=raw.status,started_at=started,ended_at=utc_now(),estimated=model.estimate,actual_resources=raw.resources,
   accounting=raw.accounting,execution_success=raw.status.value=='success',error_type=raw.error_type,
   metadata={'parent_review_sha256':identity,'amendment_sha256':amendment_id,'evidence_kind':'upstream_engineering',**raw.metadata})
  store.save_receipt(receipt)
  (HERE/'execution/selected-stdin-receipt.json').write_text(receipt.model_dump_json(indent=2)+'\n')
  (HERE/'execution/selected-stdin-process.json').write_text(json.dumps({'stdout':(raw.stdout or '')[:8192],'stderr':(raw.stderr or '')[:8192]},indent=2)+'\n')
  if isinstance(raw.output,dict):
   (HERE/'execution/selected-stdin-result.json').write_text(json.dumps(raw.output,indent=2)+'\n')
   result['passed']=(receipt.execution_success and raw.output.get('candidate_sha256')==payload['candidate_sha256']
    and raw.output.get('candidate_bytes_bound') is True and raw.output.get('analyzers_executed',0)>0)
 finally:
  repo.finish_operation(key,elapsed_seconds=time.monotonic()-clock,accounting=raw.accounting if raw else None,resources=raw.resources if raw else None)
  await executor.close()
  remaining=subprocess.run([*original.DOCKER,'container','inspect',name],capture_output=True,text=True,timeout=10)
  result['owned_container_removed']=remaining.returncode!=0 and 'No such' in remaining.stderr
  if not result['owned_container_removed']:result['passed']=False;result['cleanup']='UNRESOLVED_PRESERVED'
  (HERE/'execution/operation-ledger-after-selected.json').write_text(repo.operation_ledger(plan_id).model_dump_json(indent=2)+'\n')
  result['wall_seconds']=time.monotonic()-clock
  (HERE/'execution/selected-stdin-summary.json').write_text(json.dumps(result,indent=2)+'\n');store.close()
 print(json.dumps(result))

if __name__=='__main__':asyncio.run(main())
