"""Run the approved generated tool on training inputs through AssessmentService."""
import asyncio,hashlib,json,shutil,sys,time,traceback
from pathlib import Path
from aeep.assessment.models import AssessmentPlan,AssessmentScopeAmendment,ReviewedMapping,AssessmentLimits,content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent
BASE=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
async def main():
 path=OUT/'operation-review.json';assert len(sys.argv)==2 and sha(path)==sys.argv[1]
 review=json.loads(path.read_text());assert sha(Path(__file__))==review['training_runner_sha256']
 assert sha(OUT/'training-review.json')==review['training_review_sha256']
 assert sha(OUT/'generated-source.py.txt')==review['source_sha256']
 assert verification_source_digest(ROOT)==review['source_digest']
 assert shutil.disk_usage(ROOT).free>review['minimum_free_bytes']
 proposed=json.loads((OUT/'training-review.json').read_text());p=AssessmentPlan.model_validate(proposed['plan'])
 r=Router.from_manifest(BASE/'aeep.json');s=AssessmentService(r,BASE/'.aeep/assessments');q=s.repository
 result={'review_sha256':sys.argv[1],'plan_id':p.plan_id,'qualification':False,'admission':False,'replay_allowed':False}
 try:
  assert not r.store._connection.execute('SELECT 1 FROM assessment_jobs WHERE plan_id=?',(p.plan_id,)).fetchone()
  assert content_digest(p)==content_digest(AssessmentPlan.model_validate(q.get('plan',p.plan_id)))
  mapping=ReviewedMapping.model_validate(q.get('mapping',p.mapping_digest))
  for spec in mapping.subjects:r.register(spec)
  budget=s.budget_preview(p.plan_id);assert budget['campaign_allowance']['fits_remaining'] and not budget['campaign_allowance']['gaps']
  assert budget['campaign_allowance']['upper_allowance']==proposed['budget_preview']['campaign_allowance']['upper_allowance']
  with (OUT/'training-started.json').open('x') as f:json.dump(result,f)
  q.approve_bundle(AssessmentScopeAmendment.model_validate(proposed['amendment']),proposed['definitions'])
  op=p.plan_id+':storage_preflight';q.reserve(p,op,AssessmentLimits(max_operations=1,max_elapsed_seconds=30),stage='storage_preflight');began=time.monotonic()
  try:
   target=OUT/'training-storage-snapshot.sqlite3';assert not target.exists()
   copy=r._campaign_router(mapping.subjects,plan_digest=content_digest(p),database=target,snapshot_bound_digests={content_digest(p),p.subject_digest,p.recipe_digest,p.mapping_digest,p.environment_digest,*p.definition_digests,*p.executable_dependencies.values()})
   await copy.close();envelope=57*(target.stat().st_size+64*1024**2)
   free=shutil.disk_usage(ROOT).free;result['storage']={'snapshot_bytes':target.stat().st_size,'envelope_bytes':envelope,'free_bytes':free};assert free-envelope>=50*1024**3
  finally:q.finish_operation(op,elapsed_seconds=time.monotonic()-began)
  job=s.enqueue(p.plan_id);result['assessment_id']=job
  async def guard():
   while True:
    await asyncio.sleep(10)
    if shutil.disk_usage(ROOT).free<51*1024**3:s.cancel(job);result['storage_stop']=True;return
  task=asyncio.create_task(guard())
  try:
   async with asyncio.timeout(5000):report=await s.run(job)
  finally:
   task.cancel()
   try:await task
   except asyncio.CancelledError:pass
  result.update(report_id=report.report_id,outcome=report.outcome,status=s.status(job),source_unchanged=verification_source_digest(ROOT)==review['source_digest'])
 except BaseException as exc:
  result.update(error_type=type(exc).__name__,safe_stack=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)[-8:]])
 finally:
  result['grant_after']=list(r.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
  await r.close();(OUT/'training-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
asyncio.run(main())
