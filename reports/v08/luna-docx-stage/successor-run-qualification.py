"""One exact reviewed qualification through the existing service; no retries."""
import asyncio,hashlib,json,subprocess,sys,time,traceback
from pathlib import Path
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentPlan,AssessmentScopeAmendment,AssessmentLimits,content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def docker(*args,timeout=20):return subprocess.check_output(['docker',*args],text=True,timeout=timeout,stderr=subprocess.DEVNULL).strip()
def proxy(review):
 m=json.loads(docker('inspect','--format','{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Networks":{{json .NetworkSettings.Networks}}}',review['proxy_name']))
 assert m['Id'].startswith(review['proxy_id_prefix']) and m['Image']==review['proxy_image']
 assert review['network_id'] in [x['NetworkID'] for x in m['Networks'].values()]
 return m
async def main():
 path=OUT/'successor-qualification-execution-review.json'
 assert len(sys.argv)==2 and digest(path)==sys.argv[1]
 review=json.loads(path.read_text());assert digest(Path(__file__))==review['runner_sha256']
 assert not (OUT/'successor-qualification-started.json').exists() and not (OUT/'successor-qualification-result.json').exists()
 assert verification_source_digest(ROOT)==review['source_digest']
 assert digest(OUT/'successor-qualification-review.json')==review['proposal_sha256']
 proposal=json.loads((OUT/'successor-qualification-review.json').read_text())
 capacity=dict(x.split('=',1) for x in subprocess.check_output([sys.executable,str(OUT/'storage_probe.py')],text=True,timeout=10).splitlines());assert int(capacity['NSURLVolumeAvailableCapacityForImportantUsageKey_bytes'])>=80*1024**3
 initial=proxy(review);assert not initial['Running']
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');s=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');q=s.repository
 started_proxy=False;result={'review_sha256':sys.argv[1],'plan_id':review['plan_id'],'source_digest':review['source_digest'],'replay_allowed':False,'admission':False,'capacity_before':capacity}
 from aeep.hosts.registry import ManagedHostRegistry
 from aeep.benchmarking import BenchmarkRunner
 original_identity=ManagedHostRegistry.resolve_identity;original_trial=BenchmarkRunner._execute_trial
 def diagnose(stage,exc):
  chain=[]
  while exc is not None:
   message=str(exc).lower();chain.append({'type':type(exc).__name__,'message_sha256':hashlib.sha256(str(exc).encode()).hexdigest(),'categories':[x for x in ('permission','model','configuration','account','auth','network','timeout','binary','unsupported','container','terminated','closed','schema','path','identity','boundary') if x in message],'stack':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)[-8:]]});exc=exc.__cause__ or exc.__context__
  result.setdefault('diagnostics',[]).append({'stage':stage,'chain':chain})
 async def observed_identity(registry,config):
  try:
   value=await original_identity(registry,config)
   if value is None:result.setdefault('diagnostics',[]).append({'stage':'identity','returned_none':True,'adapter_id':config.adapter_id})
   return value
  except BaseException as exc:diagnose('identity',exc);raise
 async def observed_trial(runner,*args,**kwargs):
  try:return await original_trial(runner,*args,**kwargs)
  except BaseException as exc:diagnose('trial_preflight',exc);raise
 ManagedHostRegistry.resolve_identity=observed_identity;BenchmarkRunner._execute_trial=observed_trial

 try:
  p=AssessmentPlan.model_validate(q.get('plan',review['plan_id']));assert content_digest(p)==review['plan_digest'] and not p.blocked_reasons
  assert p.comparison.experiment.stage=='qualification' and p.comparison.experiment.exposure=='required'
  assert not r.store._connection.execute('SELECT 1 FROM assessment_jobs WHERE plan_id=?',(p.plan_id,)).fetchone()
  pair=q.get('worker_pair_definition',review['pair_definition_digest']);specs=[ExecutorSpec.model_validate(pair[k]) for k in ('control','treatment')]
  for spec in specs:r.register(spec)
  r.managed_hosts.configure(specs,principal_salt=r.store.host_principal_key,manifest_directory=r.manifest_path.parent)
  preview=s.budget_preview(p.plan_id);assert preview['campaign_allowance']['upper_allowance']==proposal['budget_preview']['campaign_allowance']['upper_allowance'];assert not preview['campaign_allowance']['gaps'] and preview['campaign_allowance']['fits_remaining'];assert all(x['eligible'] for x in preview['adapter_eligibility'])
  with (OUT/'successor-qualification-started.json').open('x') as f:json.dump(result,f)
  q.approve_bundle(AssessmentScopeAmendment.model_validate(proposal['amendment']),proposal['definitions'])
  operation=p.plan_id+':reviewed_proxy_setup';q.reserve(p,operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=60),stage='reviewed_proxy_setup');began=time.monotonic()
  try:
   assert not proxy(review)['Running'];started_proxy=True;docker('start',review['proxy_name'],timeout=30);assert proxy(review)['Running']
  finally:q.finish_operation(operation,elapsed_seconds=time.monotonic()-began)
  assessment=s.enqueue(p.plan_id);result['assessment_id']=assessment
  (OUT/'successor-qualification-progress.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'assessment_id':assessment,'started':True}),flush=True)
  async with asyncio.timeout(review['maximum_campaign_seconds']):report=await s.run(assessment)
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
  await r.close();(OUT/'successor-qualification-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
asyncio.run(main())
