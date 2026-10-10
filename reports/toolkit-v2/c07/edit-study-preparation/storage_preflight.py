"""Measure a scoped snapshot and check the finite campaign's storage allowance."""
import asyncio,hashlib,json,shutil,time
from pathlib import Path
from aeep.assessment.models import AssessmentPlan,AssessmentScopeAmendment,ReviewedMapping,AssessmentLimits,content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent
BASE=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
async def main():
 assert not (OUT/'storage-preflight.json').exists()
 review=json.loads((OUT/'qualification-review.json').read_text());assert verification_source_digest(ROOT)==review['source_digest']
 r=Router.from_manifest(BASE/'aeep.json');s=AssessmentService(r,BASE/'.aeep/assessments');q=s.repository
 try:
  p=AssessmentPlan.model_validate(q.get('plan',review['plan_id']));assert content_digest(p)==review['plan_digest']
  mapping=ReviewedMapping.model_validate(q.get('mapping',p.mapping_digest))
  q.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']),review['definitions'])
  stages=review['budget_preview']['campaign_allowance']['stages']
  copies=sum(x['calls_upper'] for x in stages if x['stage'] in {'router_setup','grader_reference','grader_probe','recipe_grading'})
  pre={'authority':'Standing routine exact review and finite assessment authority','plan_digest':content_digest(p),'source_digest':review['source_digest'],'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'maximum_operations':1,'maximum_reserved_seconds':30,'model_turns':0,'campaign_copies_upper':copies,'additional_bytes_per_copy':64*1024**2,'reserve_bytes':50*1024**3}
  (OUT/'storage-preflight-review.json').write_text(json.dumps(pre,indent=2)+'\n')
  op=p.plan_id+':storage_preflight';q.reserve(p,op,AssessmentLimits(max_operations=1,max_elapsed_seconds=30),stage='storage_preflight');began=time.monotonic()
  try:
   path=OUT/'storage-snapshot.sqlite3';assert not path.exists()
   copy=r._campaign_router(mapping.subjects,plan_digest=content_digest(p),database=path,snapshot_bound_digests={content_digest(p),p.subject_digest,p.recipe_digest,p.mapping_digest,p.environment_digest,*p.definition_digests,*p.executable_dependencies.values()})
   await copy.close();snapshot=path.stat().st_size;free=shutil.disk_usage(ROOT).free
   envelope=copies*(snapshot+pre['additional_bytes_per_copy'])
   result={**pre,'snapshot_bytes':snapshot,'campaign_envelope_bytes':envelope,'minimum_free_bytes':envelope+pre['reserve_bytes'],'free_bytes':free,'shortfall_bytes':max(0,envelope+pre['reserve_bytes']-free),'fits':free-envelope>=pre['reserve_bytes'],'model_calls_started':0,'qualification_enqueued':False,'reserve_unchanged':True,'comment':'Finite conservative allowance, not predicted actual consumption; keep the same 64 MiB per-copy margin used for preceding qualification. Older fixture cleanup remains pending explicit approval.'}
   (OUT/'storage-preflight.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
  finally:q.finish_operation(op,elapsed_seconds=time.monotonic()-began)
 finally:await r.close()
asyncio.run(main())
