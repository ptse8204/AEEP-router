"""Verify repaired proxy readiness for both unchanged worker profiles; zero model turns."""
import asyncio,hashlib,json,pathlib,shutil,subprocess,sys,time
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentPlan,AssessmentLimits,content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import _select_model_config
from aeep.models import ExecutorSpec
OUT=pathlib.Path(__file__).resolve().parent;ROOT=OUT.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def docker(*args):return subprocess.check_output(['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock',*args],text=True,timeout=20,stderr=subprocess.DEVNULL).strip()
async def main():
 path=OUT/'paired-readiness-review.json';assert len(sys.argv)==2 and sha(path)==sys.argv[1];review=json.loads(path.read_text());assert sha(pathlib.Path(__file__))==review['runner_sha256'];assert verification_source_digest(ROOT)==review['source_digest'];assert shutil.disk_usage(ROOT).free>51*1024**3
 config=json.loads((ROOT/'reports/toolkit-v2/c07/edit-study-preparation/qualification-execution-review.json').read_text());expected=json.loads((ROOT/'reports/toolkit-v2/c07/edit-study-preparation/boundary-result.json').read_text())
 def proxy():return json.loads(docker('inspect','--format','{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Memory":{{json .HostConfig.Memory}},"MemorySwap":{{json .HostConfig.MemorySwap}}}',config['proxy_name']))
 initial=proxy();assert initial['Id'].startswith(config['proxy_id_prefix']) and initial['Image']==config['proxy_image'] and not initial['Running'];assert initial['Memory']==initial['MemorySwap']==536870912
 with (OUT/'paired-readiness-started.json').open('x') as f:json.dump({'review_sha256':sys.argv[1]},f)
 base=pathlib.Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3');r=Router.from_manifest(base/'aeep.json');s=AssessmentService(r,base/'.aeep/assessments');q=s.repository;p=AssessmentPlan.model_validate(q.get('plan',review['plan_id']));assert content_digest(p)==review['plan_digest'];pair=q.get('worker_pair_definition',config['pair_definition_digest']);specs=[ExecutorSpec.model_validate(pair[k]) for k in ('control','treatment')]
 for spec in specs:r.register(spec)
 r.managed_hosts.configure(specs,principal_salt=r.store.host_principal_key,manifest_directory=r.manifest_path.parent)
 result={'review_sha256':sys.argv[1],'source_digest':review['source_digest'],'model_turns':0,'task_replayed':False,'workers':{}};reserved=False;began=time.monotonic();op=p.plan_id+':paired_readiness_fixed_20261019'
 try:
  q.reserve(p,op,AssessmentLimits(max_operations=1,max_elapsed_seconds=240,max_model_turns=0,max_cash_usd=0),stage='paired_readiness_diagnostic');reserved=True;docker('start',config['proxy_name'])
  async with asyncio.timeout(180):
   for role,spec in zip(('control','treatment'),specs,strict=True):
    cfg=spec.managed_host_config();adapter=r.managed_hosts.get(cfg.adapter_id);request=adapter.transport.request
    async def restricted(method,params):
     assert method not in {'thread/start','thread/resume','turn/start'}
     return await request(method,params)
    adapter.transport.request=restricted
    try:
     probe=await adapter.probe();row={'probe_status':probe.status.value};result['workers'][role]=row
     if probe.status.value!='ready':continue
     selected=_select_model_config(await adapter.list_models(),cfg);row['requested_model_selected']=selected.id if selected else None
     identity=await adapter.resolve_identity(cfg);row['identity_matches_reviewed_boundary']=identity==expected['boundaries'][role]['identity_digest'];row['runtime_identity_digest']=identity
     capacity=await adapter.snapshot_capacity();row['capacity_windows']=[{'window_id':w.window_id,'used_percent':str(w.used_percent) if w.used_percent is not None else None,'exhausted':w.exhausted,'reset_at':w.reset_at.isoformat() if w.reset_at else None} for w in capacity.windows]
    finally:adapter.transport.request=request;await adapter.close()
  result['ready']=len(result['workers'])==2 and all(x.get('probe_status')=='ready' and x.get('identity_matches_reviewed_boundary') and x.get('requested_model_selected')=='gpt-6-astra' and x.get('capacity_windows') and all(w['used_percent'] is not None and not w['exhausted'] for w in x['capacity_windows']) for x in result['workers'].values())
 except BaseException as exc:result['error_type']=type(exc).__name__
 finally:
  await r.managed_hosts.close()
  if proxy()['Running']:docker('stop','--time','5',config['proxy_name'])
  result['proxy_restored']=not proxy()['Running'];result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest']
  if reserved:q.finish_operation(op,elapsed_seconds=time.monotonic()-began)
  await r.close();(OUT/'paired-readiness-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
asyncio.run(main())
