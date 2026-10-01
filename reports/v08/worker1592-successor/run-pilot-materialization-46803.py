import asyncio,json,hashlib,time
from pathlib import Path
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentScopeAmendment
from aeep.assessment.extensions import materialize
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
async def main():
 review=json.loads((OUT/'pilot-materialization-46803-review.json').read_text());assert hashlib.sha256((OUT/'pilot-materialization-46803-review.json').read_bytes()).hexdigest()=='bd5a971978adf816785169411ff655098f61817775a05ffd7016f05bdbcf293c';assert verification_source_digest(ROOT)==review['source_digest'];assert not(OUT/'pilot-materialization-46803-result.json').exists()
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');s=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');q=s.repository;began=time.monotonic();result={'request_id':review['request']['plan_id'],'source_digest':review['source_digest'],'model_turns':0,'no_admission':True,'replay_allowed':False}
 try:
  q.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']),review['definitions'])
  async with asyncio.timeout(35):cases=await materialize(s,result['request_id'])
  from aeep.assessment.models import content_digest
  counts={name:sum(c.split.value==name for c in cases.cases) for name in ('qualification','training','holdout')}
  screening=[c.case_id for c in cases.cases if c.split.value=='qualification']
  result.update(case_set_digest=content_digest(cases),case_count=len(cases.cases),split_counts=counts,screening_count=len(screening),distinct_screening_count=len(set(screening)),distinct_case_count=len({c.case_id for c in cases.cases}))
  assert counts=={'qualification':8,'training':28,'holdout':105} and len(set(screening))==8 and result['distinct_case_count']==141, 'frozen_case_contract_mismatch'
  result['materialization_passed']=True
 except BaseException as exc:result.update(materialization_passed=False,error_type=type(exc).__name__)
 finally:
  result['elapsed_seconds']=time.monotonic()-began;result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest'];result['canonical_store']=str(s.directory/result['request_id']/'recipe-operations');row=r.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone();result['grant_after']=dict(zip(('operations','model_turns','elapsed_seconds','cash_usd'),row));(OUT/'pilot-materialization-46803-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await r.close()
asyncio.run(main())
