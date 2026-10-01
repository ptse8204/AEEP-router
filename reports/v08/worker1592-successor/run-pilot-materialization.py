import asyncio,json,hashlib,time
from pathlib import Path
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentScopeAmendment
from aeep.assessment.extensions import materialize
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
async def main():
 review=json.loads((OUT/'pilot-materialization-review.json').read_text());assert hashlib.sha256((OUT/'pilot-materialization-review.json').read_bytes()).hexdigest()=='3bfe84c1118251a902717772984395937ed752758d86085a288881ea1087184e';assert verification_source_digest(ROOT)==review['source_digest'];assert not(OUT/'pilot-materialization-result.json').exists()
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');s=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');q=s.repository;began=time.monotonic();result={'request_id':review['request']['plan_id'],'source_digest':review['source_digest'],'model_turns':0,'no_admission':True,'replay_allowed':False}
 try:
  q.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']),review['definitions'])
  async with asyncio.timeout(35):cases=await materialize(s,result['request_id'])
  from aeep.assessment.models import content_digest
  result.update(case_set_digest=content_digest(cases),case_count=len(cases.cases),screening_count=sum(c.split.value=='qualification' for c in cases.cases),materialization_passed=len(cases.cases)==141)
 except BaseException as exc:result.update(materialization_passed=False,error_type=type(exc).__name__)
 finally:
  result['elapsed_seconds']=time.monotonic()-began;result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest'];result['canonical_store']=str(s.directory/result['request_id']/'recipe-operations');row=r.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone();result['grant_after']=dict(zip(('operations','model_turns','elapsed_seconds','cash_usd'),row));(OUT/'pilot-materialization-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await r.close()
asyncio.run(main())
