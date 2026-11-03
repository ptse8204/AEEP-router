"""Substituted SDK controls for parent accounting/protocol logic; no upstream import."""
from __future__ import annotations
import asyncio,importlib.util,json,sys,tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ase_sdk_review',HERE/'run-review.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
from aeep.executors.base import BaseExecutor
from aeep.models import RawExecution,utc_now
from aeep.assessment.models import AssessmentLimits

results=[]
for valid,forged in [(True,False),(False,False),(False,True)]:
 with tempfile.TemporaryDirectory(prefix='aeep-ase-driver-fixture-') as name:
  tmp=Path(name);work=tmp/'work';(work/'responses').mkdir(parents=True)
  value={'fixture':'owned'};ref=m.content_digest(value)
  with m.ReceiptStore(':memory:') as store:
   repo=m.AssessmentRepository(store);repo.put('fixture',ref,m.DefinitionRecord(payload=value));repo.review(ref)
   grant=m.AssessmentAuthorization(authorization_id='owned-fixture',subject_digests=[ref],recipe_digests=[ref],environment_digests=[ref],limits=AssessmentLimits(max_operations=10,max_model_turns=0,max_elapsed_seconds=100),expires_at=utc_now()+timedelta(hours=1))
   repo.grant(grant)
   store._connection.execute('UPDATE assessment_grants SET operations=1,elapsed_seconds=2 WHERE id=?',('owned-fixture',));store._connection.commit()
   request=m.ConformanceProbeRequest(plan_id='fixture-ase-sdk',subject_digest=ref,recipe_digest=ref,mapping_digest=ref,environment_digest=ref,authorization_id='owned-fixture',definition_digests=[ref],worker_digest=ref,executable_dependencies={})
   token='a'*64;payload={'slots':['0'],'run_token':token,'skill_name':'fixture','response_timeout':1}
   condition={'canonical_valid':valid,'certificate_fixture_sha256':'b'*64}
   code=int(valid and not forged) if valid else int(forged)
   output={'kind':'done','grades':[{'slot':'0','summary':{'passed':code,'failed':1-code,'total':1,'pass_rate':float(code),'skipped':0}}],'upstream_timing_is_compatibility_only':True}
   class Substitute(BaseExecutor):
    def __init__(self,stdout_observer=None):self.observer=stdout_observer
    async def execute(self,context):
     assert context.spec.config['inherit_env'] is False
     self.observer((json.dumps({'kind':'trial','slot':'0','run_token':token})+'\n').encode())
     response=json.loads((work/'responses/0.json').read_text());assert response['canonical_valid'] is valid
     self.observer((json.dumps(output)+'\n').encode())
     return RawExecution(status='success',output=output)
   command=m.ExecutorSpec(id='fixture.sdk',capability='toolkit.upstream-engineering@1',kind='command',description='First-party substitute only',side_effect='write',config={'argv':['first-party-substitute-never-launched'],'cwd':str(work),'timeout_seconds':5,'inherit_env':False})
   review={'source':'c'*64,'runtime':str(tmp/'not-a-real-runtime'),'runtime_tree_sha256':'d'*64,'executable_dependencies':{},'identity':'e'*64}
   caught=False
   with patch.object(m,'HERE',tmp),patch.object(m,'CommandExecutor',Substitute),patch.object(m,'verification_source_digest',lambda _:review['source']),patch.object(m,'snapshot',lambda _:review['runtime_tree_sha256']):
    try:asyncio.run(m.invoke(repo,request,review,'positive' if valid else 'negative',command,payload,condition))
    except RuntimeError:caught=True
   assert caught is forged
   ledger=repo.operation_ledger(request.plan_id);assert len(ledger.operations)==1 and ledger.operations[0].elapsed_seconds is not None
   row=store._connection.execute('SELECT operations FROM assessment_grants WHERE id=?',('owned-fixture',)).fetchone();assert row[0]==2
   receipt=json.loads(next((tmp/'execution').glob('*-receipt.json')).read_text())
   assert receipt['execution_success'] is not forged
   assert receipt['status']==('failed' if forged else 'success')
   results.append({'canonical_valid_fixture':valid,'forged_upstream_grade':forged,'rejected':caught,'prior_counter_preserved':True,'operation_settled':True})
print(json.dumps({'passed':True,'scenarios':results,'evidence_kind':'first_party_substituted_executor_and_grade_certificates','actual_ASE_imports':0,'actual_Git_processes':0,'actual_models':0,'actual_main_grant_changes':0},indent=2))

# Preparing a finite expiry extension cannot reset counters or expand ceilings.
with m.ReceiptStore(':memory:') as store:
 repo=m.AssessmentRepository(store)
 root=m.AssessmentAuthorization(authorization_id='expiry-fixture',subject_digests=['a'*64],recipe_digests=['a'*64],environment_digests=['a'*64],limits=AssessmentLimits(max_operations=10,max_model_turns=0,max_elapsed_seconds=100),expires_at=utc_now()+timedelta(hours=1))
 repo.grant(root)
 proposed=m.AssessmentBudgetAmendment(authorization_id=root.authorization_id,authorization_digest=m.content_digest(root),limits=root.limits,expires_at=utc_now()+timedelta(hours=3))
 authority={'budget_amendment':proposed.model_dump(mode='json')}
 first=m.expiry_amendment(repo,authority);assert first.limits==root.limits and first.previous_amendment_digest is None
 intermediate=m.AssessmentBudgetAmendment(authorization_id=root.authorization_id,authorization_digest=m.content_digest(root),limits=AssessmentLimits(max_operations=12,max_model_turns=0,max_elapsed_seconds=120),expires_at=utc_now()+timedelta(hours=2))
 repo.approve_budget_amendment(intermediate)
 second=m.expiry_amendment(repo,authority)
 assert second.previous_amendment_digest==m.content_digest(intermediate) and second.limits==intermediate.limits
 repo.approve_budget_amendment(second)
 assert m.expiry_amendment(repo,authority) is None
 assert tuple(store._connection.execute('SELECT operations,model_turns,elapsed_seconds FROM assessment_grants').fetchone())==(0,0,0)
print(json.dumps({'expiry_controls_passed':True,'same_or_existing_ceilings_preserved':True,'current_predecessor_used':True,'already_extended_grant_not_rewritten':True,'counters_not_reset':True,'actual_main_grant_changes':0}))
