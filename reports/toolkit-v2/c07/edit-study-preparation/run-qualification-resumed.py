"""One exact reviewed qualification through the existing service; no retries."""
import asyncio,hashlib,json,subprocess,sys,time,traceback
from pathlib import Path
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentPlan,AssessmentScopeAmendment,AssessmentLimits,content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def docker(*args,timeout=20):return subprocess.check_output(['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock',*args],text=True,timeout=timeout,stderr=subprocess.DEVNULL).strip()
def proxy(review):
 m=json.loads(docker('inspect','--format','{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Networks":{{json .NetworkSettings.Networks}}}',review['proxy_name']))
 assert m['Id'].startswith(review['proxy_id_prefix']) and m['Image']==review['proxy_image']
 assert review['network_id'] in [x['NetworkID'] for x in m['Networks'].values()]
 return m
def queued_budget_guard(preview, plan_id, ledger, expected_preparation_digests, job):
 from decimal import Decimal
 from math import isfinite
 assert job and job['state']=='queued' and job['started_at'] is None and job['report_id'] is None and job['error_code'] is None, 'job is no longer unstarted'
 allowance=preview['campaign_allowance']
 assert allowance['gaps']==['campaign already started; this is a fresh-schedule bound, not a resume allowance']
 own=[operation for operation in ledger.operations if operation.plan_id==plan_id]
 assert {item.operation_id:content_digest(item) for item in own}==expected_preparation_digests, 'unreviewed campaign operations or changed preparation'
 assert all(item.stage in {'storage_preflight','reviewed_proxy_setup','reviewed_proxy_cleanup'} and item.reserved.max_model_turns==0 for item in own)
 assert all(item.elapsed_seconds is not None and isfinite(item.elapsed_seconds) and item.elapsed_seconds>=0 for item in ledger.operations)
 remaining=preview['remaining'];assert remaining is not None
 totals=allowance['upper_allowance'];extra={'operations':3,'model_turns':0,'elapsed_seconds':150,'cash_usd':0}
 for dimension in extra:
  bound=Decimal(str(totals[dimension]));available=Decimal(str(remaining[dimension]))
  assert bound.is_finite() and available.is_finite() and bound>=0 and available>=bound+extra[dimension], 'finite campaign and lifecycle allowance does not fit'
 assert preview['adapter_eligibility'] and all(item['eligible'] for item in preview['adapter_eligibility'])
 return {'accepted_completed_preparation_operations':len(own),'queued_job_has_never_started':True,'full_campaign_plus_lifecycle_fits':True,'prior_costs_retained':True,'replay_authorized':False}

async def main():
 path=OUT/'qualification-resumed-execution-review.json'
 assert len(sys.argv)==2 and digest(path)==sys.argv[1]
 review=json.loads(path.read_text());assert digest(Path(__file__))==review['runner_sha256']
 assert not (OUT/'qualification-resumed-started.json').exists() and not (OUT/'qualification-resumed-result.json').exists()
 assert digest(OUT/'qualification-prepared-result.json')==review['predecessor_preflight_result_sha256']
 assert verification_source_digest(ROOT)==review['source_digest']
 assert digest(OUT/'qualification-review.json')==review['proposal_sha256']
 proposal=json.loads((OUT/'qualification-review.json').read_text())
 capacity={'free_bytes':__import__('shutil').disk_usage(ROOT).free};assert capacity['free_bytes']>=review['minimum_free_bytes']
 initial=proxy(review);assert not initial['Running']
 r=Router.from_manifest(Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.json'));s=AssessmentService(r,Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/.aeep/assessments'));q=s.repository
 started_proxy=False;result={'review_sha256':sys.argv[1],'plan_id':review['plan_id'],'source_digest':review['source_digest'],'replay_allowed':False,'admission':False,'capacity_before':capacity}
 try:
  p=AssessmentPlan.model_validate(q.get('plan',review['plan_id']));assert content_digest(p)==review['plan_digest'] and not p.blocked_reasons
  job_rows=r.store._connection.execute('SELECT id,state,started_at,report_id,error_code FROM assessment_jobs WHERE plan_id=?',(p.plan_id,)).fetchall();assert len(job_rows)==1 and job_rows[0][0]==review['assessment_id']
  job=dict(zip(('id','state','started_at','report_id','error_code'),job_rows[0]))
  pair=q.get('worker_pair_definition',review['pair_definition_digest']);specs=[ExecutorSpec.model_validate(pair[k]) for k in ('control','treatment')]
  for spec in specs:r.register(spec)
  r.managed_hosts.configure(specs,principal_salt=r.store.host_principal_key,manifest_directory=r.manifest_path.parent)
  preview=s.budget_preview(p.plan_id);assert preview['campaign_allowance']['upper_allowance']==proposal['budget_preview']['campaign_allowance']['upper_allowance']
  ids,sources=s._cost_sources(p,require_complete=False);ledger=q.operation_ledger(p.plan_id,ids,sources)
  result['preparation_guard']=queued_budget_guard(preview,p.plan_id,ledger,review['preparation_operation_digests'],job)
  s._verify_dependencies(p)
  with (OUT/'qualification-resumed-started.json').open('x') as f:json.dump(result,f)
  q.approve_bundle(AssessmentScopeAmendment.model_validate(proposal['amendment']),proposal['definitions'])
  from aeep.assessment.models import ReviewedMapping
  mapping=ReviewedMapping.model_validate(q.get('mapping',p.mapping_digest))
  storage_operation=p.plan_id+':resumption_storage_preflight';q.reserve(p,storage_operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=30),stage='storage_preflight');began=time.monotonic()
  storage_path=OUT/'resumption-storage-snapshot.sqlite3';assert not storage_path.exists()
  try:
   copy=r._campaign_router(mapping.subjects,plan_digest=content_digest(p),database=storage_path,snapshot_bound_digests={content_digest(p),p.subject_digest,p.recipe_digest,p.mapping_digest,p.environment_digest,*p.definition_digests,*p.executable_dependencies.values()})
   await copy.close();measured=storage_path.stat().st_size
   estimate=review['campaign_copies_upper']*(measured+64*1024**2)
   result['storage_preflight']={'snapshot_bytes':measured,'campaign_envelope_bytes':estimate,'remaining_reserve_bytes':capacity['free_bytes']-estimate}
   assert capacity['free_bytes']-estimate>=50*1024**3
  finally:q.finish_operation(storage_operation,elapsed_seconds=time.monotonic()-began)
  operation=p.plan_id+':resumption_proxy_setup';q.reserve(p,operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=60),stage='reviewed_proxy_setup');began=time.monotonic()
  try:
   assert not proxy(review)['Running'];started_proxy=True;docker('start',review['proxy_name'],timeout=30);assert proxy(review)['Running']
  finally:q.finish_operation(operation,elapsed_seconds=time.monotonic()-began)
  assessment=review['assessment_id'];assert s.status(assessment)['state']=='queued';result['assessment_id']=assessment
  (OUT/'qualification-resumed-progress.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'assessment_id':assessment,'started':True}),flush=True)
  async def capacity_guard():
   while True:
    await asyncio.sleep(20)
    if __import__('shutil').disk_usage(ROOT).free<51*1024**3:
     s.cancel(assessment);result['storage_stop']=True;return
  guard=asyncio.create_task(capacity_guard())
  try:
   async with asyncio.timeout(review['maximum_campaign_seconds']):report=await s.run(assessment)
  finally:
   guard.cancel()
   try:await guard
   except asyncio.CancelledError:pass
  result.update(report_id=report.report_id,outcome=report.outcome,qualification_passed=report.qualification_passed,status=s.status(assessment))
 except BaseException as exc:
  result.update(error_type=type(exc).__name__,safe_stack=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)[-8:]])
 finally:
  if started_proxy:
   cleanup=p.plan_id+':resumption_proxy_cleanup';reserved=False;began=time.monotonic()
   try:
    q.reserve(p,cleanup,AssessmentLimits(max_operations=1,max_elapsed_seconds=60),stage='reviewed_proxy_cleanup');reserved=True
   except BaseException as exc:result['cleanup_accounting_error']=type(exc).__name__
   try:
    if proxy(review)['Running']:docker('stop','--time','5',review['proxy_name'],timeout=20)
    result['proxy_restored']=not proxy(review)['Running']
   except BaseException as exc:result.update(proxy_restored=False,cleanup_error=type(exc).__name__)
   finally:
    if reserved:q.finish_operation(cleanup,elapsed_seconds=time.monotonic()-began)
   result['post_report_cleanup_cost_separately_retained']=True
  else:result['proxy_restored']=not proxy(review)['Running']
  result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest']
  result['grant_after']=dict(zip(('operations','model_turns','elapsed_seconds','cash_usd'),r.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone()))
  await r.close();(OUT/'qualification-resumed-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
asyncio.run(main())
