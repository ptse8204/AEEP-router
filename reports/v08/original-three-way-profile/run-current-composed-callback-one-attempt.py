"""Operator launch wrapper: one exact reviewed request only, no setup/retries."""
import asyncio,hashlib,importlib.util,json,sys
from pathlib import Path
from aeep.router import Router
from aeep.models import FallbackConfig,ActionRequest
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import ConformanceProbeRequest
from aeep.hosts.codex_app_server import CodexAppServerAdapter
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
PROJECT=ROOT/'.aeep/current-composed-workbook-ade3'
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
async def main():
 bundle=json.loads((OUT/'current-composed-one-attempt-assembly.json').read_text())
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json')
 # Narrow only this owned operator Router; stored/global manifest remains intact.
 policy_name=bundle['action'].get('policy') or r.manifest.default_policy
 r.manifest.policies[policy_name]=r._policy_for(ActionRequest.model_validate(bundle['action'])).model_copy(deep=True)
 r.manifest.policies[policy_name].fallback=FallbackConfig(enabled=False,max_attempts=1)
 assessment=AssessmentService(r,ROOT/'.aeep/live-review-v3')
 request=ConformanceProbeRequest.model_validate(assessment.repository.get('conformance_request',bundle['request']['plan_id']))
 producer=load('current_native_producer',OUT/'current-native-workbook-producer.py')
 composition=load('current_union_composition',OUT/'native-dynamic-operator-composition.py')
 runner=load('current_callback_runner',OUT/'native-composed-current-capacity-runner.py')
 native_router,scope,native_spec,native,fixed,aeep=producer.reopen(PROJECT)
 selected=bundle['pair']['treatment'];binding=bundle['callbacks'][selected['config']['invocation']['dynamic_tools_digest']]
 def services_for_trial(plan_id,operation_id):
  if plan_id!=request.plan_id or operation_id!='composed:'+request.plan_id:raise ValueError('exact operation differs')
  return fixed,aeep
 dynamic=composition.union_operator_factory(assessment=assessment,plan=request,
  profile_identity=binding['identity'],namespace=binding['namespace'],max_calls=1,timeout_seconds=10.0,
  services_for_trial=services_for_trial,conformance_request=request)
 def factory(spec,salt,directory):
  adapter=CodexAppServerAdapter.from_executor(spec,principal_salt=salt,manifest_directory=directory)
  adapter.dynamic_tools_factory=dynamic
  return adapter
 r.managed_hosts.register_factory('codex-app-server',factory)
 try:
  if sys.argv[1:]==['--prepare-only']:
   runner.prepare(assessment,request.plan_id,bundle['definition_digest'],bundle['action_digest'],ROOT)
   print(json.dumps({'prepare_passed':True,'hosts_started':0,'model_turns':0}));return
  if sys.argv[1:]:raise ValueError('unknown operator argument')
  result=await runner.run_once(assessment,request_id=request.plan_id,definition_digest=bundle['definition_digest'],
   action_digest=bundle['action_digest'],operation_id='composed:'+request.plan_id,source_root=ROOT,
   fresh_database=ROOT/'.aeep/current-composed-one-attempt-outer-ade3.db',capacity_confirmed=True)
  (OUT/'current-composed-one-attempt-result.json').write_text(result.model_dump_json(indent=2)+'\n')
  print(result.model_dump_json())
 except BaseException as exc:
  try:observation=assessment.repository.get('composed_runner_result','composed:'+request.plan_id)
  except Exception:observation=None
  (OUT/'current-composed-one-attempt-result.json').write_text(json.dumps({'error_type':type(exc).__name__,'error_bytes':len(str(exc).encode()),'error_sha256':hashlib.sha256(str(exc).encode()).hexdigest(),'canonical_observation':observation},indent=2)+'\n')
  raise
 finally:
  await native_router.close();await r.close()
if __name__=='__main__':asyncio.run(main())
