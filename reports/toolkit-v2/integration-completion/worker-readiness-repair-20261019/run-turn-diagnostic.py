"""One public connectivity turn; retain only finite error classes and hashed details."""
import asyncio,hashlib,json,pathlib,re,shutil,subprocess,sys,time
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentPlanningRequest,AssessmentScopeAmendment,ConformanceProbeRequest,AssessmentLimits
from aeep.assessment.boundary import execute_model_probe
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexAppServerAdapter
ROOT=pathlib.Path(__file__).resolve().parents[4];OUT=pathlib.Path(__file__).parent
TERMS={'schema_rejected':('invalid schema','invalid_json_schema','response_format','output schema','output_schema'),'model_unavailable':('model not found','model_not_found','unsupported model','does not exist','not have access to'),'client_version':('client version','upgrade','outdated','minimum version','unsupported client'),'capacity_exhausted':('usage limit reached','quota exceeded','insufficient_quota','rate_limit_exceeded','usage_limit_reached'),'authentication':('unauthorized','authentication','invalid_api_key','expired token','refresh token'),'network_transport':('error sending request','connection refused','connection reset','connection closed','timed out','timeout'),'invalid_parameter':('unsupported_parameter','unsupported parameter','unsupported_value','unsupported value','unknown field','unrecognized request'),'tools_contract':('tool_search','programmatic_tool_calling','namespaces','tool namespace','invalid tool'),'service_failure':('internal server error','service unavailable','bad gateway')}
async def main():
 review_path=OUT/'turn-diagnostic-execution-review.json';assert len(sys.argv)==2 and hashlib.sha256(review_path.read_bytes()).hexdigest()==sys.argv[1];review=json.loads(review_path.read_text());assert hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()==review['runner_sha256'];assert verification_source_digest(ROOT)==review['source_digest'];assert shutil.disk_usage(ROOT).free>51*1024**3
 assert hashlib.sha256((OUT/'turn-diagnostic-review.json').read_bytes()).hexdigest()==review['proposal_sha256']
 with (OUT/'turn-diagnostic-started.json').open('x') as f:json.dump({'review_sha256':sys.argv[1]},f)
 base=pathlib.Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3');r=Router.from_manifest(base/'aeep.json');s=AssessmentService(r,base/'.aeep/assessments');q=s.repository;proposal=json.loads((OUT/'turn-diagnostic-review.json').read_text());request=ConformanceProbeRequest.model_validate(proposal['request']);q.approve_bundle(AssessmentScopeAmendment.model_validate(proposal['amendment']),proposal['definitions'])
 def docker(*args):return subprocess.check_output(['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock',*args],text=True,timeout=20,stderr=subprocess.DEVNULL).strip()
 def proxy():return json.loads(docker('inspect','--format','{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Memory":{{json .HostConfig.Memory}}}','aeep-reviewed-model-proxy'))
 before=proxy();assert before['Id'].startswith('5f9a44f86633') and before['Image']=='sha256:5bf590eb0bf8a06187ff092f0f75cf83b540cc27bd6a75fd8bd91305ca7b13de' and not before['Running'] and before['Memory']==536870912
 result={'review_sha256':sys.argv[1],'request_id':request.plan_id,'public_input_only':True,'failed_task_replayed':False,'model_call_limit':1,'raw_error_or_output_stored':False};original=CodexAppServerAdapter.execute;calls=0;op=request.plan_id+':proxy_lifecycle';reserved=False;began=time.monotonic()
 async def observe(adapter,context):
  nonlocal calls
  assert calls==0;calls+=1;raw=await original(adapter,context);error=(raw.error_message or '');text=error.lower();status=re.findall(r'(?:HTTP(?:/\d(?:\.\d)?)?\s+|status(?: code)?[\s:=]+)([45]\d{2})(?:\b|\s)',error,re.I)
  result['observation']={'status':raw.status.value,'error_type':raw.error_type if raw.error_type in {'CODEX_TURN_FAILED','HOST_IDENTITY_DRIFT','NO_COMPATIBLE_MODEL','CONFIGURATION_REJECTED','WORKER_CLEANUP_UNCONFIRMED'} else 'other' if raw.error_type else None,'error_bytes':len(error.encode()),'error_sha256':hashlib.sha256(error.encode()).hexdigest(),'classes':{key:any(term in text for term in terms) for key,terms in TERMS.items()},'http_status_codes':sorted(set(map(int,status))),'parameter_mentions':[name for name in ['output_schema','response_format','reasoning.effort','reasoning_effort','tool_search','parallel_tool_calls','context_management','max_output_tokens','metadata','user_agent'] if name in text],'model_turn_count':raw.metadata.get('model_turn_count'),'provider_token_fields_present':raw.metadata.get('codex_token_fields') not in {None,'[]'}};return raw
 try:
  q.reserve(request,op,AssessmentLimits(max_operations=1,max_elapsed_seconds=120,max_model_turns=0,max_cash_usd=0),stage='diagnostic_proxy_lifecycle');reserved=True;docker('start','aeep-reviewed-model-proxy');CodexAppServerAdapter.execute=observe
  async with asyncio.timeout(90):
   probe=await execute_model_probe(s,request.plan_id);result['connected']=probe.observed=={'connected':True};result['probe_id']=probe.probe_id
 except BaseException as exc:result['error_type']=type(exc).__name__
 finally:
  CodexAppServerAdapter.execute=original
  if proxy()['Running']:docker('stop','--time','5','aeep-reviewed-model-proxy')
  result['proxy_restored']=not proxy()['Running'];result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest'];result['calls_observed']=calls
  if reserved:q.finish_operation(op,elapsed_seconds=time.monotonic()-began)
  await r.close();(OUT/'turn-diagnostic-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
asyncio.run(main())
