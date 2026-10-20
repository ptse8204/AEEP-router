"""One exact reviewed four-arm value campaign through the existing service; no retries."""
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
 m=json.loads(docker('inspect','--format','{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Memory":{{json .HostConfig.Memory}},"MemorySwap":{{json .HostConfig.MemorySwap}},"Networks":{{json .NetworkSettings.Networks}}}',review['proxy_name']))
 assert m['Id'].startswith(review['proxy_id_prefix']) and m['Image']==review['proxy_image']
 assert m['Memory']==m['MemorySwap']==review['proxy_memory_bytes']
 assert review['network_id'] in [x['NetworkID'] for x in m['Networks'].values()]
 return m
async def main():
 path=OUT/'value-execution-review.json'
 assert len(sys.argv)==2 and digest(path)==sys.argv[1]
 review=json.loads(path.read_text());assert digest(Path(__file__))==review['runner_sha256']
 assert not (OUT/'value-started.json').exists() and not (OUT/'value-result.json').exists()
 assert verification_source_digest(ROOT)==review['source_digest']
 assert digest(OUT/'value-review.json')==review['proposal_sha256']
 assert digest(OUT/'pair-result.json')==review['pair_result_sha256'] and digest(OUT/'boundary-result.json')==review['boundary_result_sha256']
 proposal=json.loads((OUT/'value-review.json').read_text())
 capacity={'free_bytes':__import__('shutil').disk_usage(ROOT).free};assert capacity['free_bytes']>=review['minimum_free_bytes']
 initial=proxy(review);assert not initial['Running']
 r=Router.from_manifest(Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.json'));s=AssessmentService(r,Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/.aeep/assessments'));q=s.repository
 started_proxy=False;result={'review_sha256':sys.argv[1],'plan_id':review['plan_id'],'source_digest':review['source_digest'],'replay_allowed':False,'admission':False,'capacity_before':capacity}
 try:
  p=AssessmentPlan.model_validate(q.get('plan',review['plan_id']));assert content_digest(p)==review['plan_digest'] and not p.blocked_reasons
  assert not r.store._connection.execute('SELECT 1 FROM assessment_jobs WHERE plan_id=?',(p.plan_id,)).fetchone()
  from aeep.assessment.models import ReviewedMapping
  mapping=ReviewedMapping.model_validate(q.get('mapping',p.mapping_digest));specs=mapping.subjects
  assert len(specs)==4 and p.comparison.experiment.stage=='marginal_value' and p.comparison.experiment.exposure=='optional'
  assert all(spec.config.get('adapter_options',{}).get('output_schema_mode')=='prompt' for spec in specs)
  for spec in specs:r.register(spec)
  r.managed_hosts.configure(specs,principal_salt=r.store.host_principal_key,manifest_directory=r.manifest_path.parent)
  preview=s.budget_preview(p.plan_id);assert preview['campaign_allowance']['upper_allowance']==proposal['budget_preview']['campaign_allowance']['upper_allowance'];assert not preview['campaign_allowance']['gaps'] and preview['campaign_allowance']['fits_remaining'];assert all(x['eligible'] for x in preview['adapter_eligibility'])
  from decimal import Decimal
  for key,extra in {'operations':3,'model_turns':0,'elapsed_seconds':150,'cash_usd':0}.items():assert Decimal(str(preview['remaining'][key]))>=Decimal(str(preview['campaign_allowance']['upper_allowance'][key]))+extra
  s._verify_dependencies(p)
  with (OUT/'value-started.json').open('x') as f:json.dump(result,f)
  q.approve_bundle(AssessmentScopeAmendment.model_validate(proposal['amendment']),proposal['definitions'])
  from aeep.assessment.models import ReviewedMapping
  mapping=ReviewedMapping.model_validate(q.get('mapping',p.mapping_digest))
  storage_operation=p.plan_id+':execution_storage_preflight';q.reserve(p,storage_operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=30),stage='storage_preflight');began=time.monotonic()
  storage_path=OUT/'execution-storage-snapshot.sqlite3';assert not storage_path.exists()
  try:
   copy=r._campaign_router(mapping.subjects,plan_digest=content_digest(p),database=storage_path,snapshot_bound_digests={content_digest(p),p.subject_digest,p.recipe_digest,p.mapping_digest,p.environment_digest,*p.definition_digests,*p.executable_dependencies.values()})
   await copy.close();measured=storage_path.stat().st_size
   estimate=review['campaign_copies_upper']*(measured+64*1024**2)
   result['storage_preflight']={'snapshot_bytes':measured,'campaign_envelope_bytes':estimate,'remaining_reserve_bytes':capacity['free_bytes']-estimate}
   assert capacity['free_bytes']-estimate>=50*1024**3
  finally:q.finish_operation(storage_operation,elapsed_seconds=time.monotonic()-began)
  operation=p.plan_id+':reviewed_proxy_setup';q.reserve(p,operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=60),stage='reviewed_proxy_setup');began=time.monotonic()
  try:
   assert not proxy(review)['Running'];started_proxy=True;docker('start',review['proxy_name'],timeout=30);assert proxy(review)['Running']
  finally:q.finish_operation(operation,elapsed_seconds=time.monotonic()-began)
  assessment=s.enqueue(p.plan_id);result['assessment_id']=assessment
  (OUT/'value-progress.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'assessment_id':assessment,'started':True}),flush=True)
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
   cleanup=p.plan_id+':reviewed_proxy_cleanup';reserved=False;began=time.monotonic()
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
  await r.close();(OUT/'value-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
asyncio.run(main())
