"""Execute one reviewed existing-model construction call; never execute its output."""
import asyncio, hashlib, json, shutil, subprocess, sys, time, traceback
from pathlib import Path
from aeep.assessment.models import AssessmentLimits, AssessmentPlanningRequest, AssessmentScopeAmendment
from aeep.assessment.planning import generate
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent
CANONICAL=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def docker(*args):return subprocess.check_output(['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock',*args],text=True,timeout=30,stderr=subprocess.DEVNULL).strip()
def proxy(review):
 m=json.loads(docker('inspect','--format','{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Networks":{{json .NetworkSettings.Networks}}}',review['proxy_name']))
 assert m['Id'].startswith(review['proxy_id_prefix']) and m['Image']==review['proxy_image']
 assert review['network_id'] in [x['NetworkID'] for x in m['Networks'].values()]
 return m
async def main():
 path=OUT/'builder-execution-review.json';assert len(sys.argv)==2 and sha(path)==sys.argv[1]
 review=json.loads(path.read_text());assert review['runner_sha256']==sha(Path(__file__))
 assert sha(OUT/'builder-review.json')==review['builder_review_sha256']
 assert verification_source_digest(ROOT)==review['source_digest']
 assert shutil.disk_usage(ROOT).free>51*1024**3
 proposed=json.loads((OUT/'builder-review.json').read_text());request=AssessmentPlanningRequest.model_validate(proposed['request'])
 assert not proxy(review)['Running']
 with (OUT/'builder-started.json').open('x') as f:json.dump({'review_sha256':sys.argv[1],'request_id':request.plan_id},f)
 router=Router.from_manifest(CANONICAL/'aeep.json');service=AssessmentService(router,CANONICAL/'.aeep/assessments');repo=service.repository
 result={'review_sha256':sys.argv[1],'request_id':request.plan_id,'source_digest':review['source_digest'],'replay_allowed':False,'generated_source_executed':False}
 started=False;reserved=False;began=time.monotonic();op=request.plan_id+':proxy_lifecycle'
 try:
  repo.approve_bundle(AssessmentScopeAmendment.model_validate(proposed['amendment']),proposed['definitions'])
  repo.reserve(request,op,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=600,max_cash_usd=0),stage='reviewed_proxy_lifecycle');reserved=True
  router.register(ExecutorSpec.model_validate(proposed['baseline']));router.register(request.planner)
  router.managed_hosts.configure([request.planner],principal_salt=router.store.host_principal_key,manifest_directory=router.manifest_path.parent)
  repo.authorize(request);started=True;docker('start',review['proxy_name']);assert proxy(review)['Running']
  output=await generate(service,request.plan_id)
  (OUT/'generated-source.py.txt').write_text(output.source)
  (OUT/'generated-usage.txt').write_text(output.usage)
  result.update(passed=True,source_sha256=sha(OUT/'generated-source.py.txt'),usage_sha256=sha(OUT/'generated-usage.txt'),operation_id='reusable-build:'+request.plan_id)
 except BaseException as exc:
  result.update(passed=False,error_type=type(exc).__name__,safe_stack=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)[-8:]])
 finally:
  if started:
   try:
    if proxy(review)['Running']:docker('stop','--time','5',review['proxy_name'])
    result['proxy_restored']=not proxy(review)['Running']
   except BaseException as exc:result.update(proxy_restored=False,cleanup_error=type(exc).__name__)
  if reserved:repo.finish_operation(op,elapsed_seconds=time.monotonic()-began)
  result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest']
  result['grant_after']=list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
  await router.close();(OUT/'builder-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
asyncio.run(main())
