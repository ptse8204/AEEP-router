"""Two exact protected native component calls; no model, worker or fake callback."""
import asyncio,hashlib,importlib.util,json,os,time,traceback
from datetime import timedelta
from pathlib import Path
import psutil
from aeep.router import Router
from aeep.models import (Manifest,PolicyConfig,FallbackConfig,TaskScope,SideEffect,ExecutorSpec,ExecutorKind,StrictModel,RawExecution,ExecutionStatus,utc_now)
from aeep.assessment.models import ConformanceProbeRequest,AssessmentLimits,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.identity import verify_dependencies,file_digest
from aeep.assessment.fixed_helper import FixedHelperService
from aeep.assessment.boundary import BoundaryProbe,BoundaryProbeDefinition
from aeep.assessment.verification import verification_source_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.executors.command import CommandExecutor
from aeep.execution import EventJournal
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
SOURCE='5fffda8a321005abc175e63f887f118b2297097542a5c1332560cb60f409f9bc'
PRODUCER=OUT/'current-composed-native-component-definitions.py'
PIN='8c3a4f2e52354db5e6ffb4e3cc9eee7f578e8c743006a99f605bc2cc2e5a1f5d'
PROJECT=ROOT/'.aeep/current-composed-workbook-ade3';DATABASE=PROJECT/'.aeep/native-components-5fff.db'
WORKER='7ceec1d0a3149ad4412c940c6d7dadab84e20576d6032b3ac55c278386bcbc2d'
class Definition(StrictModel):
 source_digest:str
 driver_digest:str
 producer_digest:str
 components:dict
 max_operations:int=1
 max_elapsed_seconds:int=40
 max_model_turns:int=0
 native_attempts:int=2
 native_attempt_seconds:int=10
 provenance:str='Actual protected fixed-service calls; service cancellation/native cleanup, not host EOF or model callback.'
def process_alive(handle):
 try:return handle.is_running() and handle.status()!=psutil.STATUS_ZOMBIE
 except psutil.NoSuchProcess:return False
async def main():
 prerequisite_review=ROOT/'reports/v08/native-only-validation-prerequisite-5fff-review.json'
 assert hashlib.sha256(prerequisite_review.read_bytes()).hexdigest()=='FINAL_NATIVE_REVIEW_SHA_PENDING'
 native_review=json.loads(prerequisite_review.read_text());assert native_review['execution_authorized'] is True and native_review['source_digest']==SOURCE
 helper=ROOT/'reports/v08/native-only-validation-prerequisite-5fff.py'
 assert hashlib.sha256(helper.read_bytes()).hexdigest()=='2cef369ef1835b84b33ce81cbd23d83d0a67f5ef5b0df85a1d5d6d9ca46b3670'
 loaded=importlib.util.spec_from_file_location('exact_native_validation_prerequisite',helper);prerequisite=importlib.util.module_from_spec(loaded);loaded.loader.exec_module(prerequisite)
 prerequisite.validate(ROOT,native_review,SOURCE)
 assert not (OUT/'current-composed-native-components-5fff-native-only-result.json').exists()
 assert verification_source_digest(ROOT)==SOURCE and file_digest(PRODUCER)==PIN and not DATABASE.exists()
 module=importlib.util.spec_from_file_location('native_components',PRODUCER);producer=importlib.util.module_from_spec(module);module.loader.exec_module(producer);components=producer.definitions()
 main_router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');repo=AssessmentRepository(main_router.store)
 anchor=ConformanceProbeRequest.model_validate(repo.get('conformance_request','conformance_current_composed_ready_5fff'))
 definition=Definition(source_digest=SOURCE,driver_digest=file_digest(Path(__file__)),producer_digest=PIN,components=components)
 definition_digest=repo.put('native_component_definition','current-composed-native-5fff-native-only',definition);repo.review(definition_digest)
 dependencies={**{path:file_digest(Path(path)) for path in anchor.executable_dependencies},str(Path(__file__).resolve()):file_digest(Path(__file__)),str(PRODUCER.resolve()):PIN}
 request=anchor.model_copy(update={'plan_id':'conformance_current_native_components_5fff','composed_model_turns':0,'executable_dependencies':dependencies,'definition_digests':[*anchor.definition_digests,definition_digest]})
 expected_probes={'native_boundary':{key:components['expected'][key] for key in ['hard_nproc','session_leader','marker','fork_errno','spawn_errno','raise_denied','network_denied']},'protected_state':{'private_denied':'true','database_denied':'true','witness_unchanged':True},'callback_lifecycle':{'service_cancelled':True,'post_exec_ready':True,'owned_non_zombie_processes_gone':True,'attempt_indeterminate':True,'host_eof_observed':False}}
 prepared_probes={}
 for name,expected in expected_probes.items():
  spec=ExecutorSpec.model_validate(components['read_cancel' if name=='callback_lifecycle' else 'guard']['spec']);probe=BoundaryProbeDefinition(name=name,executor=spec,expected=expected);digest=repo.put('boundary_probe_definition',content_digest(probe),probe);repo.review(digest);prepared_probes[name]=(probe,digest)
 request=request.model_copy(update={'plan_id':'conformance_current_native_components_frozen_5fff_native_only','definition_digests':[*request.definition_digests,*[pair[1] for pair in prepared_probes.values()]]})
 repo.put('conformance_request',request.plan_id,request);repo.review(content_digest(request));repo.authorize(request)
 operation='native-components:'+request.plan_id;repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=40,max_cash_usd=0),stage='composed_pair_inspection')
 started=time.perf_counter();deadline=asyncio.get_running_loop().time()+40;native_router=None;record={'operation_id':operation,'definition_digest':definition_digest,'model_turns':0,'native_attempts':0,'host_eof':'unobserved','observed':{},'probe_digests':[],'cleanup_confirmed':False,'full_conformance':False};owned=[];task=None;pending_probes=[]
 try:
  async with asyncio.timeout_at(deadline-5):
   canary=Path(components['canary']);assert not canary.exists();canary.write_text(components['witness']);canary_hash=file_digest(canary);database_hash=file_digest(PROJECT/'.aeep/state.db')
   specs={name:ExecutorSpec.model_validate(value['spec']) for name,value in components.items() if name in {'guard','read_cancel'}}
   ready=asyncio.Event();buffer=bytearray()
   def observe(chunk):
    buffer.extend(chunk)
    if b'\n' in buffer and not ready.is_set():
     value=json.loads(bytes(buffer).split(b'\n',1)[0]);pid=value['pid'];target=psutil.Process(pid);chain=target.parents();servers=[handle for handle in chain if Path(handle.exe()).resolve()==Path(components['guard']['spec']['config']['native_sandbox']['binary']).resolve() and handle.ppid()==os.getpid()]
     if (value.get('native_composed_ready') is not True or pid!=os.getpgid(pid) or pid!=os.getsid(pid) or len(servers)!=1):raise ValueError('native ready ownership differs')
     owned.append(target)
     for handle in chain:
      owned.append(handle)
      if handle==servers[0]:break
     record['owned_processes']=[{'pid':handle.pid,'ppid':handle.ppid(),'created_at':handle.create_time(),'name':handle.name()} for handle in owned];ready.set()
   native_router=Router(Manifest(database=str(DATABASE),executors=list(specs.values()),policies={'balanced':PolicyConfig(fallback=FallbackConfig(enabled=False,max_attempts=1))}),manifest_path=PROJECT/'aeep.json',executor_overrides={ExecutorKind.COMMAND:CommandExecutor()})
   local=AssessmentRepository(native_router.store)
   def check_operation():
    repo.authorize(request);verify_dependencies(request.executable_dependencies)
    with repo.store._lock:row=repo.store._connection.execute('SELECT state FROM assessment_operations WHERE id=?',(operation,)).fetchone()
    if row is None or row[0]!='reserved' or asyncio.get_running_loop().time()>=deadline-5:raise ValueError('canonical component reservation unavailable')
   native_router._trial_check=check_operation;native_router._trial_deadline=deadline-5
   def service(name):
    spec=specs[name];scope=TaskScope(scope_id='native-component-'+name+'-5fff',project_root=str(PROJECT.resolve()),executor_fingerprints={spec.id:executor_fingerprint(spec)},approval_ceiling=SideEffect.READ,max_attempts=1,max_attempt_seconds=10,expires_at=utc_now()+timedelta(minutes=10))
    digest=local.put('task_scope',scope.scope_id,scope);local.review(digest);native_router.bind_task_scope(scope.scope_id)
    def current():
     check_operation();native_router._require_active_spec(spec);actual=TaskScope.model_validate(local.get('task_scope',native_router._task_scope_digest))
     if content_digest(actual)!=digest:raise ValueError('component scope changed')
     return digest
    return FixedHelperService(native_router,spec.id,task_scope=scope.scope_id,declaration={'name':'fixed_'+name,'description':'Exact public native enforcement component','inputSchema':spec.input_schema},check=current)
   guard=service('guard');result=await guard.call('fixed_guard',components['guard']['input']);record['native_attempts']+=1
   payload=result.get('structuredContent')
   if payload is None:payload=json.loads(result['content'][0]['text'])
   if payload.get('status')!='success':raise ValueError('guard service failed')
   observed=payload['output']['records'][0]
   if observed!=components['expected']:raise ValueError('guard actual observations differ')
   if file_digest(canary)!=canary_hash or file_digest(PROJECT/'.aeep/state.db')!=database_hash:raise ValueError('private witness changed')
   record['observed']['native_boundary']={key:observed[key] for key in ['hard_nproc','session_leader','marker','fork_errno','spawn_errno','raise_denied','network_denied']}
   record['observed']['protected_state']={key:observed[key] for key in ['private_denied','database_denied']};record['observed']['protected_state']['witness_unchanged']=True
   cancel=service('read_cancel');native_router._executors[ExecutorKind.COMMAND]=CommandExecutor(stdout_observer=observe)
   task=asyncio.create_task(cancel.call('fixed_read_cancel',components['read_cancel']['input']))
   waiting=asyncio.create_task(ready.wait())
   try:
    async with asyncio.timeout(5):
     done,_pending=await asyncio.wait({waiting,task},return_when=asyncio.FIRST_COMPLETED)
     if task in done:
      returned=await task;record['early_service_result']={'is_error':returned.get('isError'),'structured_status':returned.get('structuredContent',{}).get('status')}
      raise ValueError('service returned before independently observed native readiness')
   finally:
    waiting.cancel();await asyncio.gather(waiting,return_exceptions=True)
   task.cancel()
   try:await task
   except asyncio.CancelledError:pass
   else:raise ValueError('READ native cancellation did not propagate')
   record['native_attempts']+=1
   end=min(deadline,asyncio.get_running_loop().time()+2)
   while any(process_alive(handle) for handle in owned) and asyncio.get_running_loop().time()<end:await asyncio.sleep(.02)
   if any(process_alive(handle) for handle in owned):raise ValueError('owned native process remains after service cancellation')
   with native_router.store._lock:
    attempts=[json.loads(row[0]) for row in native_router.store._connection.execute('SELECT payload_json FROM execution_attempts')]
    receipts=[json.loads(row[0]) for row in native_router.store._connection.execute('SELECT payload_json FROM receipts')]
   cancelled=[value for value in attempts if value['executor_id']==specs['read_cancel'].id]
   if len(cancelled)!=1 or cancelled[0]['state']!='INDETERMINATE':raise ValueError('cancelled task recovery barrier absent')
   record['observed']['callback_lifecycle']={'service_cancelled':True,'post_exec_ready':True,'owned_non_zombie_processes_gone':True,'attempt_indeterminate':True,'host_eof_observed':False}
   for name,observed in record['observed'].items():
    probe_definition,digest=prepared_probes[name]
    if observed!=probe_definition.expected:raise ValueError('predeclared component observation differs')
    journal=EventJournal('native-components-'+name);journal.append('artifact.created','independent-component-observation',evidence_ref=content_digest(observed));journal.append('execution.completed','terminal')
    evidence=journal.evidence('protected_native_component',RawExecution(status=ExecutionStatus.SUCCESS,metadata={'boundary_digest':WORKER,'native_backend_digest':components['guard']['native_backend_digest']}));evidence_digest=repo.put('execution_evidence',content_digest(evidence),evidence)
    probe=BoundaryProbe(probe_id='composed-native-component-'+name+'-5fff',name=name,implementation_digest=digest,worker_digest=WORKER,execution_evidence_digest=evidence_digest,observed=observed);pending_probes.append(probe)
   record['components_observed']=True
 except BaseException as exc:
  record['error_type']=type(exc).__name__;record['error_bytes']=len(str(exc).encode());record['error_sha256']=hashlib.sha256(str(exc).encode()).hexdigest();record['stack']=[{'file':Path(frame.filename).name,'line':frame.lineno} for frame in traceback.extract_tb(exc.__traceback__)[-8:]]
 finally:
  if task is not None and not task.done():
   task.cancel()
   try:
    async with asyncio.timeout_at(deadline):await asyncio.gather(task,return_exceptions=True)
   except BaseException as exc:record['cancel_cleanup_error_type']=type(exc).__name__
  if native_router is not None:
   try:
    from aeep.attempts import ExecutionAttempt
    from aeep.models import ExecutionReceipt
    with native_router.store._lock:
     attempts=[json.loads(row[0]) for row in native_router.store._connection.execute('SELECT payload_json FROM execution_attempts LIMIT 3')]
     receipts=[json.loads(row[0]) for row in native_router.store._connection.execute('SELECT payload_json FROM receipts LIMIT 3')]
    if len(attempts)>2 or len(receipts)>2:raise ValueError('bounded component inventory exceeded')
    record['native_attempts']=len(attempts);record['child_attempt_digests']=[];record['child_receipt_digests']=[]
    for value in attempts:record['child_attempt_digests'].append(repo.put('native_component_attempt',content_digest(value),ExecutionAttempt.model_validate(value)))
    for value in receipts:record['child_receipt_digests'].append(repo.put('native_component_receipt',content_digest(value),ExecutionReceipt.model_validate(value)))
   except BaseException as exc:record['retention_error_type']=type(exc).__name__
  try:
   async with asyncio.timeout_at(deadline):
    if native_router is not None:await native_router.close()
    record['cleanup_confirmed']=bool(record.get('components_observed')) and all(not process_alive(handle) for handle in owned)
  except BaseException as exc:
   record['cleanup_confirmed']=False;record['cleanup_error_type']=type(exc).__name__
  record['elapsed_seconds']=time.perf_counter()-started
  try:repo.finish_operation(operation,elapsed_seconds=record['elapsed_seconds']);record['accounting_finished']=True
  except BaseException as exc:record.update(accounting_finished=False,accounting_error_type=type(exc).__name__)
  record['source_unchanged']=verification_source_digest(ROOT)==SOURCE
  if record['accounting_finished'] and record['cleanup_confirmed'] and record['source_unchanged'] and not record.get('error_type') and not record.get('retention_error_type'):
   for probe in pending_probes:record['probe_digests'].append(repo.put('boundary_probe',probe.probe_id,probe))
  result_path=OUT/'current-composed-native-components-5fff-native-only-result.json';result_path.write_text(json.dumps(record,indent=2)+'\n')
  try:await main_router.close();record['main_close_confirmed']=True
  except BaseException as exc:record.update(main_close_confirmed=False,close_error_type=type(exc).__name__)
  result_path.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
asyncio.run(main())
