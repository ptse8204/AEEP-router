"""One model-driven native MCP journey; shared host integration, not qualification."""
import asyncio, hashlib, json, os, runpy, subprocess, tempfile, time
from collections import Counter
from datetime import timedelta
from pathlib import Path
import psutil
from aeep.assessment.models import AssessmentPlanningRequest, AssessmentLimits
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.assessment.workbook import workbook_recipe
from aeep.assessment.workbook_native import implementation_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_app_server import CodexAppServerTransport, AppServerOptions, _TurnCollector
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.hosts.codex_accounting import turn_accounting
from aeep.mcp.server import AEEPToolService
from aeep.models import StrictModel, Manifest, TaskScope, SideEffect, ValidationSpec, ValidationKind, utc_now
from aeep.router import Router
from aeep.tasks import activate, change_state, inspect
ROOT=Path(__file__).resolve().parents[2]; REPORTS=ROOT/'reports/v08'; ASSETS=ROOT/'integrations/assessment-runtime'
SOURCE='288e082274cf22631398ca404180f6b58cb27ed7d5654fec0420d1ee6a0a2782'
BINARY=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
PYTHON=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3')
class Definition(StrictModel):
    model: str='gpt-6.1-sol'
    effort: str='medium'
    binary_sha256: str
    executor_fingerprint: str
    scope_digest: str
    prompt_sha256: str
    input_hashes: list[str]
    native_overrides: list[str]
    maximum_seconds: int=240
    maximum_model_turns: int=1
    maximum_operations: int=1
    exploratory_resource_bounds: dict[str, float]={'host_tree_peak_rss_bytes':1073741824,'observed_host_tree_cpu_seconds':60,'elapsed_seconds':240,'retained_evidence_bytes':8388608}
    classification: str='shared native host model-driven tool use; no model-authored transformation, controlled comparison or qualification'
async def main():
    assert verification_source_digest(ROOT)==SOURCE
    result_path=REPORTS/'native-sol61-desktop-model-journey-result-288e.json'; assert not result_path.exists()
    directory=Path(tempfile.mkdtemp(prefix='aeep-sol61-model-journey-')).resolve(); scratch=directory/'scratch'; scratch.mkdir()
    subprocess.run(['git','init','-q',str(directory)],check=True)
    fixtures=runpy.run_path(str(REPORTS/'workbook-footprint-calibration-288e.py'))['cases']()
    cases=[fixtures['small'],fixtures['larger']]
    fault_input=dict(cases[0]['input'],row_bound=cases[0]['input']['row_bound']+1)
    source=(ASSETS/'workbook_program.py').read_text(); fault=json.loads((ASSETS/'workbook-faults.json').read_text())['stale_value']
    prefix=subprocess.run([str(PYTHON),'-I','-c','import sys;print(sys.prefix)'],check=True,capture_output=True,text=True).stdout.strip()
    boundary=NativeSandboxConfig(binary=str(BINARY),binary_sha256='sha256:'+hashlib.sha256(BINARY.read_bytes()).hexdigest(),project_root=str(directory),read_roots=[str(Path(prefix).resolve())],write_roots=[str(scratch)])
    recipe=workbook_recipe(); spec=recipe.extension.reference.model_copy(deep=True);spec.id='native.workbook.sol61-model-journey';spec.input_schema=recipe.input_schema;spec.output_schema=recipe.output_schema
    program="import json,sys;ns={'__name__':'reference'};exec("+repr(source)+",ns);inp=json.load(sys.stdin);print(json.dumps("+repr(fault)+" if inp['row_bound']=="+str(fault_input['row_bound'])+" else ns['reference'](inp)))"
    spec.config={**spec.config,'argv':[str(PYTHON),'-I','-c',program],'native_sandbox':boundary.model_dump(mode='json'),'env':{'TMPDIR':str(scratch)},'max_output_bytes':200000}
    spec.validators=[ValidationSpec(kind=ValidationKind.CALLBACK,config={'name':'aeep.workbook.native.v1','implementation_digest':implementation_digest()})]
    manifest=directory/'aeep.json';manifest.write_text(Manifest(database=str(directory/'.aeep/state.db'),executors=[spec]).model_dump_json())
    task=Router.from_manifest(manifest);task_repo=AssessmentRepository(task.store);task_repo.review(task_repo.put('recipe',recipe.recipe_id,recipe))
    scope=TaskScope(scope_id='sol61-model-journey',project_root=str(directory),executor_fingerprints={spec.id:executor_fingerprint(spec)},approval_ceiling=SideEffect.READ,max_attempts=3,max_attempt_seconds=30,expires_at=utc_now()+timedelta(minutes=10))
    scope_digest=task_repo.put('task_scope',scope.scope_id,scope);task_repo.review(scope_digest);activation=activate(task,scope.scope_id)
    service=AEEPToolService(task,profile='task',task_activation=activation.activation_id);tools=service.list_tools();assert len(tools)==1;tool=tools[0]['name']
    inputs=[cases[0]['input'],cases[1]['input'],fault_input]
    prompt='Use the available AEEP workbook MCP tool for these three fixed requests, in order. Make exactly one call per request. After each call inspect the structured receipt summary. The third is a predeclared synthetic faulty-output fixture; if rejected, stop and do not retry. Do not use shell, file reads, skills, apps, credential/account methods, external effects, or other tools. Return a short JSON object containing only the three success booleans and whether you stopped after the rejected fixture. Requests: '+json.dumps(inputs,separators=(',',':'))
    main_router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');repo=AssessmentRepository(main_router.store)
    old=AssessmentPlanningRequest.model_validate(repo.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
    definition=Definition(binary_sha256=boundary.binary_sha256,executor_fingerprint=executor_fingerprint(spec),scope_digest=scope_digest,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),input_hashes=[hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest() for x in inputs],native_overrides=boundary.permission_overrides())
    mapping=repo.put('native_host_diagnostic','sol61-native-model-journey-288e',definition);repo.review(mapping)
    req=old.model_copy(update={'plan_id':'planning_native_sol61_model_journey_288e','mapping_digest':mapping,'definition_digests':[*old.definition_digests,mapping]})
    request_digest=repo.put('planning_request',req.plan_id,req);repo.review(request_digest);repo.authorize(req)
    review={'authority':'standing September25/27 exact review delegation;September30 unfinished tests model selection','source_digest':SOURCE,'definition':definition.model_dump(),'mapping_digest':mapping,'request_digest':request_digest,'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':scope.model_dump(mode='json'),'activation':activation.activation_id,'schema_bytes':len(json.dumps(tools).encode()),'instructions_bytes':len(service.instructions.encode()),'prompt_bytes':len(prompt.encode()),'authentication':'Codex-owned; never accessed','global_configuration_changes':False,'new_services':False,'native_boundary_result':'native-sol61-desktop-boundaries-result-288e.json','note':'planning request is authorization envelope only; no planner execution or managed-worker conformance'}
    (REPORTS/'native-sol61-desktop-model-journey-review-288e.json').write_text(json.dumps(review,indent=2))
    operation='native-model-journey:'+req.plan_id;repo.reserve(req,operation,AssessmentLimits(max_operations=1,max_model_turns=1,max_elapsed_seconds=240),stage='native_host_model_journey')
    began=time.perf_counter();transport=None;turn_id=None;thread_id=None;collector=None;samples=[];processes={};events=Counter();outputs=[];tool_events=[];sampling=True
    record={'source_digest':SOURCE,'operation_id':operation,'task_scope_digest':scope_digest,'schema_bytes':review['schema_bytes'],'instructions_bytes':review['instructions_bytes'],'prompt_bytes':review['prompt_bytes'],'classification':definition.classification}
    async def sample():
        while sampling:
            if transport is not None and transport._process is not None:
                try:
                    parent=psutil.Process(transport._process.pid); current=[parent,*parent.children(recursive=True)]; rss=0
                    for proc in current:
                        try:
                            identity=(proc.pid,proc.create_time());cpu=proc.cpu_times();mem=proc.memory_info().rss;rss+=mem
                            processes[identity]={'pid':proc.pid,'create_time':identity[1],'cpu_seconds':cpu.user+cpu.system,'peak_rss_bytes':max(mem,processes.get(identity,{}).get('peak_rss_bytes',0))}
                        except psutil.Error: pass
                    samples.append({'elapsed_seconds':time.perf_counter()-began,'process_count':len(current),'rss_bytes':rss})
                except psutil.Error: pass
            await asyncio.sleep(.05)
    def observe(method,params):
        events[method]+=1
        if method=='item/completed' and isinstance(params.get('item'),dict):
            item=params['item']
            if item.get('type')=='mcpToolCall':
                result=item.get('result'); tool_events.append({'server':item.get('server'),'tool':item.get('tool'),'status':item.get('status'),'result_keys':sorted(result) if isinstance(result,dict) else None})
                if isinstance(result,dict):
                    structured=result.get('structuredContent')
                    if not isinstance(structured,dict):
                        for content in result.get('content',[]):
                            if isinstance(content,dict) and content.get('type')=='text':
                                try: candidate=json.loads(content.get('text','')); structured=candidate if isinstance(candidate,dict) else structured
                                except (ValueError,TypeError): pass
                    if isinstance(structured,dict):outputs.append(structured)
    sampler=asyncio.create_task(sample())
    try:
        async with asyncio.timeout(225):
            argv=(str(BINARY),'app-server','-c','features.apps=false','-c',f'projects.{json.dumps(str(directory))}.trust_level="trusted"',*boundary.permission_overrides())
            transport=CodexAppServerTransport(argv,environment_allowlist=('HOME','CODEX_HOME','PATH'),cwd=str(directory),executable_sha256=boundary.binary_sha256,request_timeout=20,options=AppServerOptions(experimental_api=True))
            transport.subscribe(observe)
            status=await transport.request('mcpServerStatus/list',{'limit':20,'detail':'toolsAndAuthOnly'})
            inventory=[{'name':x['name'],'tools':sorted(x.get('tools',{}))} for x in status.get('data',[])]
            record['inventory']=inventory
            expected_server='aeep_'+activation.activation_id
            assert inventory==[{'name':expected_server,'tools':[tool]}], 'unexpected MCP inventory'
            response=await transport.request('thread/start',{'ephemeral':True,'cwd':str(directory),'model':'gpt-6.1-sol','permissions':'aeep-native-task','approvalPolicy':'never','approvalsReviewer':'user'})
            profile=response.get('activePermissionProfile');record['permission_acknowledgement']={'cwd':response.get('cwd'),'approvalPolicy':response.get('approvalPolicy'),'approvalsReviewer':response.get('approvalsReviewer'),'profile':profile}
            assert response.get('cwd')==str(directory) and response.get('approvalPolicy')=='never' and isinstance(profile,dict) and profile.get('id')=='aeep-native-task' and profile.get('extends') is None,'native profile not acknowledged'
            thread_id=response['thread']['id'];collector=_TurnCollector(max_output_bytes=200000);collector.thread_id=thread_id;transport.subscribe(collector.handle)
            response=await transport.request('turn/start',{'threadId':thread_id,'input':[{'type':'text','text':prompt}],'model':'gpt-6.1-sol','effort':'medium'})
            turn_id=response['turn']['id'];collector.turn_id=turn_id
            result=await collector.future
            record.update(turn_status=result.status,actual_model=result.actual_model,token_usage=result.token_usage,tool_count=result.tool_count,final_output=result.output,turn_error=result.error)
            assert result.status=='completed' and result.actual_model in (None,'gpt-6.1-sol'),'model turn failed or substituted'
            assert len(outputs)==3,'missing observed tool results'
            grader=runpy.run_path(str(ASSETS/'workbook_grader.py'))['grade'];checks=[]
            for i,output in enumerate(outputs):
                valid=grader({'input':inputs[i],'output':output.get('output'),'expected':cases[min(i,1)]['expected']}) if output.get('output') is not None else False
                receipt=output.get('receipts',[{}])[0];checks.append({'index':i,'ok':output.get('ok'),'task_valid':receipt.get('task_valid'),'receipt_id':receipt.get('receipt_id'),'summary':output.get('summary'),'recovery_state':output.get('recovery_state'),'resources':receipt.get('recorded_resources'),'independent_grader_valid':valid})
            record['checks']=checks
            assert all(x['ok'] and x['task_valid'] is True and x['independent_grader_valid'] for x in checks[:2]);assert checks[2]['ok'] is False and checks[2]['task_valid'] is False and not checks[2]['independent_grader_valid']
            change_state(task,activation.activation_id,'pause'); paused=await service.call(tool,inputs[0]);record['pause_rejected']=paused['isError']
            change_state(task,activation.activation_id,'resume'); exhausted=await service.call(tool,inputs[0]);record['exhaustion_rejected']=exhausted['isError']
            assert record['pause_rejected'] and record['exhaustion_rejected'];record['journey_passed']=True
    except BaseException as exc:
        record.update(error_type=type(exc).__name__,journey_passed=False)
        if transport is not None and thread_id and turn_id:
            try: await transport.request('turn/interrupt',{'threadId':thread_id,'turnId':turn_id},timeout=5)
            except BaseException: pass
    finally:
        if transport is not None:
            try: await asyncio.wait_for(transport.close(),5);record['host_cleanup_confirmed']=not transport.running
            except BaseException as exc:record['cleanup_error_type']=type(exc).__name__
        sampling=False;await sampler
        record['uninstall']=change_state(task,activation.activation_id,'uninstall');record['activation_inspection']=inspect(task,activation.activation_id)
        elapsed=time.perf_counter()-began; accounting=None
        if collector is not None and collector.token_usage is not None:
            _,accounting=turn_accounting(collector.token_usage,model=collector.actual_model or 'gpt-6.1-sol',resource_pool='native-codex-subscription')
        repo.finish_operation(operation,elapsed_seconds=elapsed,accounting=accounting)
        record.update(elapsed_seconds=elapsed,process_samples=samples,owned_process_observations=list(processes.values()),event_counts=dict(events),tool_events=tool_events,network_observations='unknown; no network telemetry collected',resource_limits='sampled process tree; rapid and between-sample child lifetimes can be missed; includes host/MCP/AEEP descendants observed, no whole-machine baseline',model_identity='requested gpt-6.1-sol; reroute notification if observed; absence of reroute is not independent runtime identity',grant_after=list(main_router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(req.authorization_id,)).fetchone()),source_unchanged=verification_source_digest(ROOT)==SOURCE,release_ready=False,replay_allowed=False)
        record['tool_results_observed']=len(outputs)
        evidence=ROOT/'.aeep/native-sol61-desktop-model-journey-evidence';evidence.mkdir(exist_ok=False)
        await task.close();await main_router.close()
        import shutil
        shutil.move(str(directory/'.aeep'),str(evidence/'task-state'));shutil.rmtree(directory)
        result_path.write_text(json.dumps(record,indent=2));print(json.dumps({k:v for k,v in record.items() if k not in ('process_samples','owned_process_observations','inventory','uninstall','activation_inspection','final_output','checks','event_counts','tool_events')}))
asyncio.run(main())
