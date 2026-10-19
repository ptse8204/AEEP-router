"""One reviewed zero-model readiness observation; no task or authentication output."""
import asyncio,hashlib,json,pathlib,shutil,subprocess,sys,time
from aeep.router import Router
from aeep.assessment.models import AssessmentPlan,AssessmentLimits,content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexRequestError
from aeep.models import ExecutorSpec
OUT=pathlib.Path(__file__).resolve().parent;ROOT=OUT.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def docker(*args):return subprocess.check_output(['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock',*args],text=True,timeout=20,stderr=subprocess.DEVNULL).strip()
async def main():
 path=OUT/'readiness-review.json';assert len(sys.argv)==2 and sha(path)==sys.argv[1];review=json.loads(path.read_text());assert sha(pathlib.Path(__file__))==review['runner_sha256'];assert verification_source_digest(ROOT)==review['source_digest'];assert shutil.disk_usage(ROOT).free>51*1024**3
 config=json.loads((ROOT/'reports/toolkit-v2/c07/edit-study-preparation/qualification-execution-review.json').read_text())
 proxy=lambda:json.loads(docker('inspect','--format','{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}}}',config['proxy_name']))
 initial=proxy();assert initial['Id'].startswith(config['proxy_id_prefix']) and initial['Image']==config['proxy_image'] and not initial['Running']
 with (OUT/'readiness-started.json').open('x') as f:json.dump({'review_sha256':sys.argv[1]},f)
 base=pathlib.Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3');r=Router.from_manifest(base/'aeep.json');s=AssessmentService(r,base/'.aeep/assessments');q=s.repository;p=AssessmentPlan.model_validate(q.get('plan',review['plan_id']));assert content_digest(p)==review['plan_digest']
 pair=q.get('worker_pair_definition',config['pair_definition_digest']);spec=ExecutorSpec.model_validate(pair['treatment']);assert content_digest(spec)==review['executor_digest'];r.register(spec);r.managed_hosts.configure([spec],principal_salt=r.store.host_principal_key,manifest_directory=r.manifest_path.parent);adapter=r.managed_hosts.get(spec.managed_host_config().adapter_id)
 operation=p.plan_id+':readiness_detail_20261019';reserved=False;began=time.monotonic();result={'review_sha256':sys.argv[1],'model_calls':0,'task_replayed':False,'account_or_error_payloads_stored':False,'source_digest':review['source_digest'],'request_errors':[]};original=adapter.transport.request
 async def observe(method,params):
  assert method not in {'turn/start','thread/start','thread/resume'}, 'no thread or model calls permitted'
  try:return await original(method,params)
  except CodexRequestError as exc:
   payload=json.dumps(exc.error,sort_keys=True,default=str).encode();text=payload.decode().lower()
   import re
   detail=exc.error if isinstance(exc.error,dict) else {}
   status_matches=re.findall(r'(?:HTTP(?:/\d(?:\.\d)?)?\s+|status(?: code)?[\s:=]+)([45]\d{2})(?:\b|\s)',text,re.I)
   classes={name:any(term in text for term in terms) for name,terms in {
    'authentication':['unauthorized','authentication','sign in','login required','not logged in'],
    'token_refresh':['refresh token','refresh_token','token refresh','token expired','expired token'],
    'explicit_capacity_exhaustion':['usage limit reached','quota exceeded','rate limit exceeded','rate_limit_exceeded','insufficient_quota'],
    'network_transport':['error sending request','connection refused','connection reset','connection closed','network unreachable','dns','resolve host','timed out','timeout'],
    'proxy':['proxy','tunnel','407'],
    'tls':['certificate','tls','ssl'],
    'invalid_request':['invalid request','invalid_request','unknown method','invalid params','method not found'],
    'decoding':['decode','decoding','json parse','parse response'],
    'not_supported':['not supported','unavailable for','not available for'],
    'rate_limits_fetch':['fetch rate limit','fetching rate limit','retrieve rate limit'],
    }.items()}
   result['request_errors'].append({'method':method if method in {'initialize','account/read','model/list','account/rateLimits/read','account/usage/read'} else 'other','rpc_code':detail.get('code') if type(detail.get('code')) is int else None,'http_status_codes':sorted(set(map(int,status_matches))),'error_sha256':hashlib.sha256(payload).hexdigest(),'error_bytes':len(payload),'classes':classes})
   raise
 adapter.transport.request=observe
 try:
  q.reserve(p,operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=180,max_model_turns=0,max_cash_usd=0),stage='readiness_diagnostic');reserved=True
  docker('start',config['proxy_name']);assert proxy()['Running']
  async with asyncio.timeout(110):
   probe=await adapter.probe();result['probe_status']=probe.status.value;result['probe_reason_category']=probe.reason if probe.reason in {'CodexRequestError','CodexProtocolError','TimeoutError','OSError','Codex login is required'} else 'withheld' if probe.reason else None
   if probe.status.value=='ready':
    models=await adapter.list_models();requested=spec.managed_host_config();matches=[m for m in models if m.id in requested.model_constraints.allowed_model_ids];result['requested_model_present']=bool(matches);result['requested_effort_supported']=any(set(m.reasoning_efforts)&set(requested.reasoning_efforts) for m in matches)
    resolved=await adapter.resolve_identity(requested);record=q.get('runtime_binding',p.plan_id+':'+spec.id);result['runtime_identity_matches_failed_trial_binding']=resolved==record['digest'];result['resolved_runtime_digest']=resolved
 except BaseException as exc:result['error_type']=type(exc).__name__
 finally:
  adapter.transport.request=original;await adapter.close()
  if proxy()['Running']:docker('stop','--time','5',config['proxy_name'])
  result['proxy_restored']=not proxy()['Running'];result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest']
  if reserved:q.finish_operation(operation,elapsed_seconds=time.monotonic()-began)
  await r.close()
  (OUT/'readiness-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
asyncio.run(main())
