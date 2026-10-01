"""One finite local Docker metadata observation; no cleanup or model calls."""
import asyncio,hashlib,json,re,subprocess,time
from pathlib import Path
from aeep.router import Router
from aeep.models import StrictModel
from aeep.assessment.models import AssessmentPlanningRequest,AssessmentLimits,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
SOURCE='5fffda8a321005abc175e63f887f118b2297097542a5c1332560cb60f409f9bc'
class Definition(StrictModel):
 source_digest:str
 driver_sha256:str
 commands:list[list[str]]
 maximum_seconds:int=15
 maximum_operations:int=1
 model_turns:int=0
 cash_usd:int=0
async def main():
 assert verification_source_digest(ROOT)==SOURCE
 result_path=OUT/'docker-readonly-status-5fff-result.json';assert not result_path.exists()
 runtime=json.loads((OUT/'worker1592-successor/capacity-refresh-ade3-spec.json').read_text())['config']['managed_worker']['runtime']
 commands=[[runtime,'version','--format','{{json .Server}}'],[runtime,'ps','-a','--filter','name=^aeep-','--format','{{json .}}']]
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');q=AssessmentRepository(r.store)
 old=AssessmentPlanningRequest.model_validate(q.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
 definition=Definition(source_digest=SOURCE,driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),commands=commands)
 digest=q.put('docker_status_definition','docker_readonly_5fff',definition);q.review(digest)
 request=old.model_copy(update={'plan_id':'planning_docker_readonly_status_5fff','mapping_digest':digest,'definition_digests':[*old.definition_digests,digest]})
 q.put('planning_request',request.plan_id,request);q.review(content_digest(request));q.authorize(request)
 operation='docker-status:'+request.plan_id
 (OUT/'docker-readonly-status-5fff-exact-review.json').write_text(json.dumps({'authority':'Parent exact instruction: <=15s read-only API availability and failed-test inventory; standing Sep25/27 finite amendment','definition':definition.model_dump(mode='json'),'definition_digest':digest,'request_digest':content_digest(request),'operation_id':operation,'no_restart_prune_kill_or_model':True},indent=2)+'\n')
 q.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=15,max_cash_usd=0),stage='host_introspection')
 started=time.perf_counter();record={'operation_id':operation,'model_turns':0,'cash_usd':0,'docker_mutations':0,'commands':[]}
 try:
  for index,argv in enumerate(commands):
   entry={'role':'availability' if index==0 else 'AEEP_container_candidate_inventory'}
   try:
    answer=subprocess.run(argv,capture_output=True,timeout=min(5,14-(time.perf_counter()-started)),check=False)
    entry.update(returncode=answer.returncode,stderr_bytes=len(answer.stderr),stderr_sha256=hashlib.sha256(answer.stderr).hexdigest(),error_class='docker_api_500' if b'500' in answer.stderr else 'docker_cli_error' if answer.returncode else None)
    if answer.returncode==0:
     if len(answer.stdout)>1000000:raise ValueError('bounded metadata output exceeded')
     if index==0:
      value=json.loads(answer.stdout);entry['server']={key:value.get(key) for key in ['Version','ApiVersion','Os','Arch']}
     else:
      rows=[]
      for line in answer.stdout.splitlines():
       value=json.loads(line);name=value.get('Names','')
       if re.fullmatch(r'aeep-[a-f0-9]{32}',name):rows.append({key:value.get(key) for key in ['ID','Names','State','Status','CreatedAt']})
      entry['candidate_containers']=rows;entry['exact_failed_test_ownership']='Not established by name prefix; no cleanup authorized or performed.'
   except BaseException as exc:entry.update(error_type=type(exc).__name__,error_bytes=len(str(exc).encode()),error_sha256=hashlib.sha256(str(exc).encode()).hexdigest())
   record['commands'].append(entry)
 finally:
  record['elapsed_seconds']=time.perf_counter()-started
  try:q.finish_operation(operation,elapsed_seconds=record['elapsed_seconds']);record['accounting_finished']=True
  except BaseException as exc:record.update(accounting_finished=False,accounting_error_type=type(exc).__name__)
  record['source_unchanged']=verification_source_digest(ROOT)==SOURCE
  result_path.write_text(json.dumps(record,indent=2)+'\n')
  try:await r.close();record['main_close_confirmed']=True
  except BaseException as exc:record.update(main_close_confirmed=False,close_error_type=type(exc).__name__)
  result_path.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
asyncio.run(main())
