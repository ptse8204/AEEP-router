import asyncio,json,hashlib,time
from pathlib import Path
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentScopeAmendment,content_digest
from aeep.assessment.boundary import execute_model_probe
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
async def main():
 review=json.loads((OUT/'connectivity-final-review.json').read_text());assert hashlib.sha256((OUT/'connectivity-final-review.json').read_bytes()).hexdigest()=='48ba7f02858b31daa05cb11ac3b005c463369b79c4a93b445d5b0945011ca5c7';assert verification_source_digest(ROOT)==review['source_digest'];assert not(OUT/'connectivity-final-result.json').exists()
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');s=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');q=s.repository;began=time.monotonic();result={'request_id':review['request']['plan_id'],'source_digest':review['source_digest'],'no_workbook_trial':True,'no_admission':True,'replay_allowed':False}
 try:
  q.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']),review['definitions'])
  async with asyncio.timeout(65):probe=await execute_model_probe(s,result['request_id'])
  result.update(probe_digest=content_digest(probe),observed=probe.observed,connectivity_passed=probe.observed=={'connected':True})
 except BaseException as exc:result.update(connectivity_passed=False,error_type=type(exc).__name__)
 finally:
  result['elapsed_seconds']=time.monotonic()-began;result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest'];result['canonical_store']=str(s.directory/result['request_id']/'bootstrap.sqlite3');row=r.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone();result['grant_after']=dict(zip(('operations','model_turns','elapsed_seconds','cash_usd'),row));(OUT/'connectivity-final-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await r.close()
asyncio.run(main())
