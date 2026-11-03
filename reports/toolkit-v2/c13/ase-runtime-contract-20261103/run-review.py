"""Two real ASE SDK conditions over public grade-certificate fixtures, no models."""
from __future__ import annotations
import argparse,asyncio,hashlib,json,os,shutil,sys,time
from datetime import UTC,datetime
from pathlib import Path
from typing import Any
from pydantic import model_serializer
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'src'))
from aeep.assessment.models import AssessmentAuthorization,AssessmentBudgetAmendment,AssessmentLimits,AssessmentScopeAmendment,ConformanceProbeRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.execution import persist_execution_events
from aeep.models import ActionRequest,ExecutionReceipt,ExecutorSpec,SideEffect,StrictModel,utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import snapshot,file_digest

class DefinitionRecord(StrictModel):
    """Canonical JSON metadata, using the existing repository model interface."""
    payload: dict[str, Any]

    @model_serializer(mode='plain')
    def serialize_payload(self):
        return self.payload


def verify():
    review=json.loads((HERE/'operation-review.json').read_bytes())
    assert set(review['specs'])=={'native-boundary','positive','negative'}
    assert set(review['conditions'])=={'positive','negative'}
    assert review['maximum_model_turns']==0 and review['maximum_operations']==3
    for name,expected in review['bound_files'].items():assert file_digest(ROOT/name)==expected,name
    assert verification_source_digest(ROOT)==review['source']
    gates=json.loads(Path(review['source_checks']).read_bytes())
    assert gates['source_before']==gates['source_after']==review['source']
    assert len(gates['checks'])==13 and all(c['exit_code']==0 for c in gates['checks'])
    assert snapshot(Path(review['runtime']))==review['runtime_tree_sha256'],'Retained SDK runtime drifted'
    assert shutil.disk_usage(ROOT).free>=50*1024**3+16*1024**2,'Preserve50GiB host reserve'
    assert datetime.now(UTC)<datetime.fromisoformat(review['expires_at'].replace('Z','+00:00'))
    return review


def expiry_amendment(repo,authority):
    """Standing finite delegation: extend expiry only; keep current ceilings/counters."""
    proposed=AssessmentBudgetAmendment.model_validate(authority['budget_amendment'])
    effective=repo.effective_grant(proposed.authorization_id)
    if effective.expires_at>=proposed.expires_at:return None
    latest=repo.store._connection.execute("SELECT digest FROM assessment_records WHERE kind='budget_amendment' AND json_extract(payload_json,'$.authorization_id')=? ORDER BY rowid DESC LIMIT 1",(proposed.authorization_id,)).fetchone()
    return proposed.model_copy(update={'previous_amendment_digest':latest[0] if latest else None,'limits':effective.limits})


async def invoke(repo,scope,review,name,spec,payload,condition=None):
    operation=scope.plan_id+':'+name;out=HERE/'execution';out.mkdir(mode=0o700,exist_ok=True)
    repo.authorize(scope)
    repo.reserve(scope,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=float(spec.config['timeout_seconds'])+5),stage='ase_sdk_contract_'+name,require_settled_plan=True)
    action=ActionRequest(action_id=operation,capability=spec.capability,input=payload)
    buffer=bytearray();requests=[]
    work=Path(spec.config['cwd'])
    def observe(chunk):
      buffer.extend(chunk)
      if len(buffer)>65536:raise ValueError('Bounded SDK frame exceeded')
      while b'\n' in buffer:
        line,_,rest=buffer.partition(b'\n');buffer[:]=rest
        message=json.loads(line)
        if message.get('kind')=='done':continue
        assert condition is not None
        assert message=={'kind':'trial','slot':'0','run_token':payload['run_token']}
        assert not requests,'Repeated upstream request'
        requests.append(message)
        response={'run_token':payload['run_token'],'slot':'0','trial_ref':condition['certificate_fixture_sha256'],'canonical_valid':condition['canonical_valid']}
        target=work/'responses/0.json'
        with target.open('x') as f:json.dump(response,f)
    def authorize():
      repo.authorize(scope)
      assert verification_source_digest(ROOT)==review['source']
      assert snapshot(Path(review['runtime']))==review['runtime_tree_sha256']
      for name,expected in review['executable_dependencies'].items():assert file_digest(Path(name))==expected
      assert shutil.disk_usage(ROOT).free>=50*1024**3
    context=ExecutionContext(request=action,spec=spec,estimate=spec.estimate,attempt=1,attempt_id=operation,approved_side_effect=SideEffect.WRITE,invocation_check=authorize)
    executor=CommandExecutor(stdout_observer=observe if condition else None)
    began=utc_now();clock=time.monotonic();raw=None;error=None
    try:
      with persist_execution_events(lambda journal,event:repo.put('execution_event',journal+':'+str(event.sequence),event)):
        raw=await(await executor.start(context)).task
      assert raw.status.value=='success' and isinstance(raw.output,dict),'SDK/native process failed'
      if condition:
        valid=int(condition['canonical_valid']);expected={'passed':valid,'failed':1-valid,'total':1,'pass_rate':float(valid),'skipped':0}
        assert requests==[{'kind':'trial','slot':'0','run_token':payload['run_token']}]
        assert not buffer
        assert raw.output=={'kind':'done','grades':[{'slot':'0','summary':expected}],'upstream_timing_is_compatibility_only':True}
      else:assert raw.output.get('passed') is True,'Native boundary or Git dependency failed'
    except BaseException as exc:error=exc
    finally:
      await executor.close();elapsed=time.monotonic()-clock
      repo.finish_operation(operation,elapsed_seconds=elapsed,accounting=raw.accounting if raw else None,resources=raw.resources if raw else None)
      if raw:
        receipt=ExecutionReceipt(decision_id=operation,action_id=action.action_id,capability=spec.capability,executor_id=spec.id,executor_kind=spec.kind,status=raw.status if error is None else 'failed',started_at=began,ended_at=utc_now(),estimated=spec.estimate,actual_resources=raw.resources,accounting=raw.accounting,execution_success=error is None,error_type=type(error).__name__ if error else raw.error_type,metadata={**raw.metadata,'process_status':raw.status.value,'review_sha256':review['identity'],'evidence_kind':'real_upstream_SDK_with_first_party_certificate_fixtures' if condition else 'first_party_native_boundary','upstream_timing_excluded':True,'context_token_semantics':'approximate stdout size, not model usage','models':0})
        repo.store.save_receipt(receipt)
        (out/(name+'-receipt.json')).write_text(receipt.model_dump_json(indent=2)+'\n')
        (out/(name+'-process.json')).write_text(json.dumps({'stdout':(raw.stdout or '')[:8192],'stderr':(raw.stderr or '')[:8192],'output':raw.output},indent=2)+'\n')
      cleanup_uncertain=(raw is None or raw.status.value=='timeout' or raw.error_type=='BACKGROUND_PROCESS_REJECTED' or (raw.exit_code is not None and raw.exit_code<0))
      result={'passed':error is None,'error_type':type(error).__name__ if error else None,'seconds':elapsed,'observed_slot_requests':len(requests),'models':0,'cleanup_uncertain':cleanup_uncertain}
      (out/(name+'-result.json')).write_text(json.dumps(result,indent=2)+'\n')
    if error:raise RuntimeError('ASE engineering condition failed; keep the receipt and do not replay it') from error
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute-approved');args=parser.parse_args()
    review=verify();identity=file_digest(HERE/'operation-review.json');review['identity']=identity
    if args.execute_approved is None:
      print(json.dumps({'review_sha256':identity,'execution':False,'models':0,'purpose':'SDK conformance only; controlled model workers remain unverified'}));return
    approval=json.loads((HERE/'operator-approval.json').read_bytes());assert args.execute_approved==identity==approval['review_sha256'] and approval['approved'] is True
    assert not (HERE/'execution-started.json').exists()
    authority=json.loads((HERE/'authority.json').read_bytes());scope=ConformanceProbeRequest.model_validate(authority['request'])
    with ReceiptStore(review['database']) as store:
      repo=AssessmentRepository(store)
      baseline=dict(zip(('revoked','operations','model_turns','elapsed_seconds','cash_usd'),store._connection.execute('SELECT revoked,operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(scope.authorization_id,)).fetchone(),strict=True))
      prior=authority['grant_baseline']
      assert not baseline['revoked']
      assert all(baseline[key]>=prior[key] for key in ('operations','model_turns','elapsed_seconds')),'Original counters decreased; inspect without resetting them'
      (HERE/'execution').mkdir(mode=0o700,exist_ok=True)
      assert not (HERE/'execution').is_symlink()
      result={'passed':False,'models':0,'full_stack_complete':False,'controlled_model_worker_verified':False,'candidate_usefulness':'NOT_ASSESSED','selection_usefulness':'NOT_ASSESSED'}
      try:
        for digest,value in authority['definitions'].items():repo.put('toolkit_sdk_definition',digest,DefinitionRecord(payload=value))
        budget=expiry_amendment(repo,authority)
        authority_path=HERE/f'execution/applied-authority-{time.time_ns()}.json'
        authority_path.write_text(json.dumps({'scope_amendment':authority['scope_amendment'],'expiry_amendment':budget.model_dump(mode='json') if budget else None,'authority':'Standing finite amendment delegation; current ceilings preserved; no model/disclosure/cash authority added'},indent=2)+'\n')
        result['authority_record']=str(authority_path)
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(authority['scope_amendment']),authority['definitions'],budget_amendment=budget)
        repo.put('conformance_request',scope.plan_id,scope)
        specs={name:ExecutorSpec.model_validate(value) for name,value in review['specs'].items()}
        assert snapshot(Path(specs['native-boundary'].config['cwd']))==review['prepared_native_tree_sha256'],'Preserve changed native-probe workspace'
        with (HERE/'execution-started.json').open('x') as f:json.dump({'review_sha256':identity,'original_grant_baseline':baseline},f)
        result['native_boundary']=asyncio.run(invoke(repo,scope,review,'native-boundary',specs['native-boundary'],review['native_payload']))
        for name,condition in review['conditions'].items():
          work=Path(specs[name].config['cwd']);assert snapshot(work)==condition['prepared_tree_sha256']
          result[name]=asyncio.run(invoke(repo,scope,review,name,specs[name],condition['input'],condition))
        assert snapshot(Path(review['runtime']))==review['runtime_tree_sha256']
        result.update(passed=True,runtime_unchanged=True)
      except BaseException as error:result['error_type']=type(error).__name__
      finally:
        result['operation_ledger']=repo.operation_ledger(scope.plan_id).model_dump(mode='json')
        result['grant_after']=dict(zip(('revoked','operations','model_turns','elapsed_seconds','cash_usd'),store._connection.execute('SELECT revoked,operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(scope.authorization_id,)).fetchone(),strict=True))
        old_states={name:store._connection.execute('SELECT state FROM assessment_operations WHERE id=?',(name,)).fetchone() for name in authority['old_unsettled_operations']}
        result['old_operation_states_after']={name:row[0] if row else None for name,row in old_states.items()}
        result['old_operations_not_replayed_or_settled_by_this_driver']=True
        result['source_unchanged']=verification_source_digest(ROOT)==review['source']
        if not result['source_unchanged']:result.update(passed=False,error_type='SourceChangedAfterExecution')
        result['cleanup_uncertain']=any(json.loads(path.read_bytes()).get('cleanup_uncertain',True) for path in (HERE/'execution').glob('*-result.json'))
        path=HERE/'execution/summary.json' if (HERE/'execution-started.json').exists() else HERE/f'execution/preflight-failed-{time.time_ns()}.json'
        with path.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='operation_ledger'}))

if __name__=='__main__':main()
