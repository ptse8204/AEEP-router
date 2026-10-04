"""Bounded adapter identity-only diagnostic, zero model turns; no campaign replay."""
import asyncio,hashlib,json,subprocess,time,traceback
from pathlib import Path
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentPlan,AssessmentLimits,content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
async def main():
 source='eaad5bc7b30f3671284b1d7291a4483ff0d87399c2ea13a298be4006bc717ee1';assert verification_source_digest(ROOT)==source
 review={'source_digest':source,'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'authority':'September25/27 finite assessment diagnostic delegation','max_operations':1,'max_elapsed_seconds':90,'max_model_turns':0,'cash_ceiling':0,'scope':'Exact failed plan treatment adapter resolve_identity only; no task, cases, skill invocation, generator or campaign replay'}
 with (OUT/'root-campaign-identity-diagnostic-review.json').open('x') as f:json.dump(review,f,indent=2)
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');s=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');q=s.repository;p=AssessmentPlan.model_validate(q.get('plan','plan_811e138d8f36417ba793ac526591f4b6'));spec=ExecutorSpec.model_validate(q.get('mapping',p.mapping_digest)['candidate']);result={};owned=False;op=p.plan_id+':campaign-identity-diagnostic';began=time.monotonic()
 def docker(*args):return subprocess.check_output(['docker',*args],text=True,timeout=20,stderr=subprocess.DEVNULL).strip()
 proxy='aeep-reviewed-model-proxy'
 meta=json.loads(docker('inspect','--format','{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}}}',proxy));assert meta['Id'].startswith('5f9a44f86633') and meta['Image']=='sha256:5bf590eb0bf8a06187ff092f0f75cf83b540cc27bd6a75fd8bd91305ca7b13de' and not meta['Running']
 q.reserve(p,op,AssessmentLimits(max_operations=1,max_elapsed_seconds=90),stage='campaign_identity_diagnostic')
 try:
  owned=True;docker('start',proxy);r.managed_hosts.configure([spec],principal_salt=r.store.host_principal_key,manifest_directory=r.manifest_path.parent)
  bound={content_digest(p),p.subject_digest,p.recipe_digest,p.mapping_digest,p.environment_digest,p.recipe_case_set_digest,*p.definition_digests,*p.executable_dependencies.values()}
  worker=r._campaign_router([spec],plan_digest=content_digest(p),snapshot_bound_digests=bound)
  try:
   async with asyncio.timeout(45):identity=await worker.managed_hosts.resolve_identity(spec.managed_host_config())
  finally:await worker.close()
  result={'resolved':identity is not None,'identity_digest':identity}
 except BaseException as exc:
  chain=[]
  while exc is not None:
   text=str(exc).lower();chain.append({'type':type(exc).__name__,'message_sha256':hashlib.sha256(str(exc).encode()).hexdigest(),'categories':[x for x in ('permission','not found','model','configuration','account','auth','network','timeout','binary','unsupported','container','terminated','closed','schema','path') if x in text],'stack':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)[-8:]]});exc=exc.__cause__ or exc.__context__
  result={'resolved':False,'safe_exception_chain':chain}
 finally:
  await r.close()
  if owned:docker('stop','--time','5',proxy)
  # Reopen same canonical store only to finish accounting after adapter cleanup.
  a=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');repo=AssessmentService(a,ROOT/'.aeep/live-review-v3/.aeep/assessments').repository;repo.finish_operation(op,elapsed_seconds=time.monotonic()-began);await a.close()
  result.update(model_turns=0,source_unchanged=verification_source_digest(ROOT)==source,proxy_restored=docker('inspect','--format','{{.State.Running}}',proxy)=='false')
  (OUT/'root-campaign-identity-diagnostic-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
asyncio.run(main())
