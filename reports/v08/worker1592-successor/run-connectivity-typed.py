import asyncio,json,hashlib,time,re,traceback
from pathlib import Path
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentScopeAmendment,content_digest
from aeep.assessment.boundary import execute_model_probe
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
async def main():
 review=json.loads((OUT/'connectivity-typed-review.json').read_text());assert hashlib.sha256((OUT/'connectivity-typed-review.json').read_bytes()).hexdigest()=='b28728cc04a1b28bf32623fa39bc423d0f8baff34e0c2821a54115c0d3b413ed';assert verification_source_digest(ROOT)==review['source_digest'];assert not(OUT/'connectivity-typed-result.json').exists()
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');s=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');q=s.repository;began=time.monotonic();result={'request_id':review['request']['plan_id'],'source_digest':review['source_digest'],'no_workbook_trial':True,'no_admission':True,'replay_allowed':False}
 try:
  from aeep.executors.managed_host import ManagedHostExecutor
  original=ManagedHostExecutor.execute
  async def observed_execute(executor,context):
   raw=await original(executor,context)
   def safe_code(value):return value if isinstance(value,str) and re.fullmatch(r'[a-zA-Z0-9_.:-]{1,100}',value) else 'unknown'
   message=(raw.error_message or '').lower()
   classes={'schema':['schema','output format'], 'model':['model not found','unsupported model'], 'network':['connection','network','timed out','timeout'], 'permission':['permission','forbidden','unauthorized']}
   result['safe_adapter_diagnostic']={'status':raw.status.value,'error_type':safe_code(raw.error_type),'host_failure_code':safe_code(raw.metadata.get('host_failure_code')),'recognized_message_classifications':[name for name,markers in classes.items() if any(marker in message for marker in markers)],'unknown_message_retained':False}
   return raw
  ManagedHostExecutor.execute=observed_execute
  q.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']),review['definitions'])
  async with asyncio.timeout(65):probe=await execute_model_probe(s,result['request_id'])
  result.update(probe_digest=content_digest(probe),observed=probe.observed,connectivity_passed=probe.observed=={'connected':True})
 except BaseException as exc:
  result.update(connectivity_passed=False,error_type=type(exc).__name__,stack_modules_lines=[{'module':Path(f.filename).name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)[-5:]])
 finally:
  result['elapsed_seconds']=time.monotonic()-began;result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest'];result['canonical_store']=str(s.directory/result['request_id']/'bootstrap.sqlite3');row=r.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone();result['grant_after']=dict(zip(('operations','model_turns','elapsed_seconds','cash_usd'),row));(OUT/'connectivity-typed-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await r.close()
asyncio.run(main())
