"""Fresh harmless protocol diagnostic; no tools or task dispatch, no replay."""
import asyncio, hashlib, json, time, shutil, re
import psutil
from pathlib import Path
from aeep.assessment.models import AssessmentPlanningRequest,AssessmentLimits
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexAppServerTransport,AppServerOptions,_TurnCollector
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.hosts.codex_accounting import turn_accounting
from aeep.models import StrictModel
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[2];REPORTS=ROOT/'reports/v08'
SOURCE='46803ee2814c77977c4408b60768c6581fc0189f0c8fb9a8ccd7dd77ccc4b236'
BINARY=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
PYTHON=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3').resolve()
OWN=ROOT/'aeep-sol61-builtin-command-diagnostic'
PROMPT='Use the native builtin command tool exactly once to execute this literal command: '+str(PYTHON)+' -I -c \"print(1)\". Require its zero exit status. Do not call MCP tools, read files, use skills, access credentials or network, write files, perform workbook work, or retry. After the command finishes reply only done. If unavailable or denied, stop and reply stopped.'

def digest(x):return hashlib.sha256(str(x).encode()).hexdigest() if isinstance(x,str) else None
class Definition(StrictModel):
 source_digest:str=SOURCE
 driver_sha256:str
 binary_sha256:str
 native_overrides:list[str]
 python_sha256:str
 permitted_argv:list[str]
 inherited_instruction_sha256:str
 prompt_sha256:str=digest(PROMPT)
 model:str='gpt-6.1-sol'
 effort:str='medium'
 maximum_operations:int=1
 maximum_model_turns:int=1
 maximum_seconds:int=100
 body_timeout_seconds:int=85
 classification:str='one harmless explicitly required builtin command to distinguish general native tool progress from MCP stall; no workbook/MCP call, planner execution, worker conformance or qualification'
async def main():
 assert verification_source_digest(ROOT)==SOURCE
 assert not OWN.exists()
 result_path=REPORTS/'native-sol61-builtin-command-diagnostic-result.json';assert not result_path.exists()
 boundary=NativeSandboxConfig(binary=str(BINARY),binary_sha256='sha256:'+hashlib.sha256(BINARY.read_bytes()).hexdigest(),project_root=str(OWN),read_roots=[str(PYTHON.parents[1]),str(ROOT/'AGENTS.md')],write_roots=[str(OWN/'scratch')])
 definition=Definition(python_sha256=hashlib.sha256(PYTHON.read_bytes()).hexdigest(),permitted_argv=[str(PYTHON),"-I","-c","print(1)"],driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),binary_sha256=boundary.binary_sha256,native_overrides=boundary.permission_overrides(),inherited_instruction_sha256=hashlib.sha256((ROOT/'AGENTS.md').read_bytes()).hexdigest())
 router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');repo=AssessmentRepository(router.store)
 old=AssessmentPlanningRequest.model_validate(repo.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
 mapping=repo.put('native_host_diagnostic','sol61-builtin-command-diagnostic',definition);repo.review(mapping)
 req=old.model_copy(update={'plan_id':'planning_native_sol61_builtin_command_diagnostic','mapping_digest':mapping,'definition_digests':[*old.definition_digests,mapping]})
 rd=repo.put('planning_request',req.plan_id,req);repo.review(rd);repo.authorize(req)
 (REPORTS/'native-sol61-builtin-command-diagnostic-review.json').write_text(json.dumps({'authority':'standing September25/27 finite exact delegation; parent September30 harmless protocol diagnostic instruction','definition':definition.model_dump(),'mapping_digest':mapping,'request_digest':rd,'authentication':'Codex owned; no authentication state or account methods accessed','cash':0,'global_changes':False,'envelope_only':True},indent=2))
 op='native-protocol:'+req.plan_id;repo.reserve(req,op,AssessmentLimits(max_operations=1,max_model_turns=1,max_elapsed_seconds=100),stage='native_builtin_command_diagnostic')
 began=time.monotonic();transport=None;collector=None;thread=None;turn=None;interrupt=False;events=[];commands=[];requests=[];owned={};sampling_stop=asyncio.Event();r={'definition_digest':mapping,'source_digest':SOURCE,'operation_id':op}
 def observe(method,params):
  if method not in {'turn/started','turn/completed','thread/tokenUsage/updated','item/started','item/completed','item/agentMessage/delta','model/rerouted'}:return
  if len(events)>=200:r['events_truncated']=True;return
  nested=params.get('turn') if isinstance(params.get('turn'),dict) else {}
  e={'seconds':time.monotonic()-began,'after_interrupt':interrupt,'method':method,'keys':sorted(params)[:25],'thread_hash':digest(params.get('threadId')),'turn_hash':digest(params.get('turnId')),'nested_turn_hash':digest(nested.get('id')),'thread_equal':params.get('threadId')==thread,'turn_equal':params.get('turnId')==turn,'collector_installed':collector is not None}
  if method=='turn/completed':e.update(status=nested.get('status'),error_code=(nested.get('error') or {}).get('code') if isinstance(nested.get('error'),dict) else None)
  if method=='thread/tokenUsage/updated':
   usage=params.get('tokenUsage');e['numeric_usage']={kind:{k:v for k,v in vals.items() if isinstance(v,int) and not isinstance(v,bool) and v>=0} for kind,vals in usage.items() if isinstance(vals,dict)} if isinstance(usage,dict) else None
  item=params.get('item')
  if isinstance(item,dict):
   e.update(item_type=item.get('type'),phase=item.get('phase'),item_keys=sorted(item)[:25],item_status=item.get('status'))
   if method=='item/completed' and item.get('type')=='commandExecution':commands.append({'exit_code':item.get('exitCode'),'status':item.get('status'),'output_equals_one':isinstance(item.get('aggregatedOutput'),str) and item['aggregatedOutput'].strip()=='1'})
  if method=='model/rerouted':e['to_model']=params.get('toModel')
  events.append(e)
 async def ownership():
  while not sampling_stop.is_set():
   if transport and transport._process:
    try:
     parent=psutil.Process(transport._process.pid)
     for child in [parent,*parent.children(recursive=True)]:owned[(child.pid,child.create_time())]=child
    except psutil.Error:pass
   await asyncio.sleep(.02)
 sampler=asyncio.create_task(ownership())
 try:
  OWN.mkdir();(OWN/'scratch').mkdir()
  async with asyncio.timeout(85):
   transport=CodexAppServerTransport((str(BINARY),'app-server','-c','features.apps=false',*boundary.permission_overrides()),environment_allowlist=('HOME','CODEX_HOME','PATH'),cwd=str(OWN),executable_sha256=boundary.binary_sha256,request_timeout=20,options=AppServerOptions(experimental_api=True))
   original=transport._handle_server_request
   async def server_request(rid,method,params):
    entry={'method':method[:120],'seconds':time.monotonic()-began,'decision':'unknown'}
    if len(requests)<30:requests.append(entry)
    before=len(transport.approval_digests)
    await original(rid,method,params);entry['decision']='decline' if len(transport.approval_digests)>before else 'method_not_supported'
   transport._handle_server_request=server_request
   transport.subscribe(observe)
   response=await transport.request('thread/start',{'ephemeral':True,'cwd':str(OWN),'model':'gpt-6.1-sol','permissions':'aeep-native-task','approvalPolicy':'never','approvalsReviewer':'user'})
   thread=response['thread']['id'];r['response_thread_hash']=digest(thread);r['permission_ack']=response.get('activePermissionProfile')
   assert r['permission_ack']=={'id':'aeep-native-task','extends':None}
   collector=_TurnCollector(max_output_bytes=1000);collector.thread_id=thread;transport.subscribe(collector.handle)
   response=await transport.request('turn/start',{'threadId':thread,'input':[{'type':'text','text':PROMPT}],'model':'gpt-6.1-sol','effort':'medium'})
   turn=response['turn']['id'];collector.turn_id=turn;r['response_turn_hash']=digest(turn)
   outcome=await collector.future
   r['natural_command_success']=outcome.status=='completed' and len(commands)==1 and commands[0]['exit_code']==0 and commands[0]['output_equals_one'] and not interrupt
   assert r['natural_command_success'],'required_native_command_not_completed'
   r.update(collector_status=outcome.status,collector_usage=outcome.token_usage,collector_tool_count=outcome.tool_count,actual_model=outcome.actual_model,output_retained=False)
 except BaseException as exc:
  r['error_type']=type(exc).__name__
  if transport and thread and turn:
   interrupt=True;r['interrupt_seconds']=time.monotonic()-began
   try:await transport.request('turn/interrupt',{'threadId':thread,'turnId':turn},timeout=5)
   except BaseException as ex:r['interrupt_error_type']=type(ex).__name__
 finally:
  if transport:
   try:await asyncio.wait_for(transport.close(),5);r['cleanup_confirmed']=not transport.running
   except BaseException as ex:r['cleanup_error_type']=type(ex).__name__
  if transport:
   stderr=bytes(transport.stderr).decode('utf-8',errors='replace')
   r['appserver_stderr']={'bytes':len(transport.stderr),'truncated':transport.stderr_truncated,'known_error_classes':[label for phrase,label in [('rate limit','rate_limit'),('429','http429'),('connection refused','connection_refused'),('timed out','timeout'),('retrying','retry'),('failed to','failure'),('permission denied','permission_denied')] if phrase in stderr.lower()]}
  grace=time.monotonic()
  def live():
   values=[]
   for key,child in owned.items():
    try:
     if child.is_running() and child.status()!=psutil.STATUS_ZOMBIE:values.append((key,child))
    except psutil.NoSuchProcess:pass
   return values
  while live() and time.monotonic()-grace<2:await asyncio.sleep(.02)
  survivors=[]
  for key,child in live():
   survivors.append({'pid':key[0],'create_time':key[1]})
   try:child.kill();await asyncio.to_thread(child.wait,timeout=1)
   except psutil.NoSuchProcess:pass
  sampling_stop.set();await sampler;r['owned_survivors_cleaned']=survivors
  r['commands']=commands;r['server_requests']=requests;r['transport_fatal_type']=type(transport._fatal).__name__ if transport and transport._fatal else None
  r['terminal_status']=collector.terminal[0] if collector and collector.terminal else None
  accounting=None
  if collector and collector.token_usage is not None:_,accounting=turn_accounting(collector.token_usage,model=collector.actual_model or 'gpt-6.1-sol',resource_pool='native-codex-subscription')
  elapsed=time.monotonic()-began;repo.finish_operation(op,elapsed_seconds=elapsed,accounting=accounting)
  r.update(elapsed_seconds=elapsed,events=events,collector_error_type=type(collector.error).__name__ if collector and collector.error else None,source_unchanged=verification_source_digest(ROOT)==SOURCE)
  if OWN.exists():shutil.rmtree(OWN)
  await router.close();result_path.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='events'}))
asyncio.run(main())
