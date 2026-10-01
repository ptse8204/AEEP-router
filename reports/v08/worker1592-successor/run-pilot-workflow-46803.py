"""Exact reviewed timing pilot via ordinary AssessmentService.run; no retries."""
import asyncio,hashlib,json,time,shutil,traceback
from pathlib import Path
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentPlan,AssessmentScopeAmendment,content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
REVIEW_SHA='4586b6c7a729ecafdbcc57089e587a064ed96b4aa1f15c342cf6b5c7138a3ef5'
def retained_bytes(path):return sum(x.stat().st_size for x in path.rglob('*') if x.is_file()) if path.exists() else 0
async def main():
 path=OUT/'pilot-workflow-46803-review.json';assert hashlib.sha256(path.read_bytes()).hexdigest()==REVIEW_SHA;review=json.loads(path.read_text());assert verification_source_digest(ROOT)==review['source_digest'];assert not(OUT/'pilot-workflow-46803-result.json').exists()
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');s=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');q=s.repository;plan=AssessmentPlan.model_validate(q.get('plan',review['plan_id']));assert content_digest(plan)==review['plan_digest'] and not plan.blocked_reasons
 pair=q.get('worker_pair_definition','a62371cc67388021616af291ec55e8c4c6e4952ec5003d558e84c0f1fe04b729')
 specs=[ExecutorSpec.model_validate(pair[role]) for role in ('control','treatment')]
 for spec in specs:r.registry.replace(spec)
 r.managed_hosts.configure(specs,principal_salt=r.store.host_principal_key,manifest_directory=r.manifest_path.parent)
 began=time.monotonic();owned=s.directory/plan.plan_id;before_bytes=retained_bytes(owned);before=dict(zip(('operations','model_turns','elapsed_seconds','cash_usd'),r.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone()));result={'plan_id':plan.plan_id,'source_digest':review['source_digest'],'review_sha256':REVIEW_SHA,'no_qualification_or_admission_or_benefit':True,'no_retry':True,'grant_before':before,'retained_bytes_before':before_bytes}
 try:
  q.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']),review['definitions']);preview=s.budget_preview(plan.plan_id);allowance=preview['campaign_allowance']['upper_allowance'];assert not preview['campaign_allowance']['gaps'] and preview['campaign_allowance']['fits_remaining'] and allowance==review['budget_preview']['campaign_allowance']['upper_allowance'];assert all(x['eligible'] for x in preview['adapter_eligibility']);assert shutil.disk_usage(owned.parent).free>=review['storage']['finite_disk_allowance_bytes']
  assessment=s.enqueue(plan.plan_id);result['assessment_id']=assessment;(OUT/'pilot-workflow-46803-start.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'assessment_id':assessment,'stage':'ordinary_service_run_started'}),flush=True)
  async with asyncio.timeout(review['maximum_reserved_seconds']+30):report=await s.run(assessment)
  result.update(terminal=True,report_id=report.report_id,outcome=report.outcome,qualification_passed=report.qualification_passed,status=s.status(assessment))
 except BaseException as exc:
  result.update(terminal=True,error_type=type(exc).__name__,stack=[{'module_file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)[-8:]])
 finally:
  await r.close();result['elapsed_seconds']=time.monotonic()-began;result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest'];result['retained_bytes_after']=retained_bytes(owned);result['retained_growth_bytes']=result['retained_bytes_after']-before_bytes
  # Reopen canonical accounting after owned worker cleanup; no ledger reset.
  audit=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');result['grant_after']=dict(zip(('operations','model_turns','elapsed_seconds','cash_usd'),audit.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone()));audit.store.close();(OUT/'pilot-workflow-46803-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
asyncio.run(main())
