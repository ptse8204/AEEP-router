"""Fresh smallest generated workbook with supported exact per-tool native approval; no unchanged replay; no replay or qualification."""
import asyncio, hashlib, json, os, runpy, subprocess, tempfile, time, shlex, sys
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
from aeep.models import StrictModel, Manifest, ExecutorKind, TaskScope, SideEffect, ValidationSpec, ValidationKind, utc_now
from aeep.router import Router
from aeep.tasks import activate, change_state, inspect
ROOT=Path(__file__).resolve().parents[2]; REPORTS=ROOT/'reports/v08'; ASSETS=ROOT/'integrations/assessment-runtime'
SOURCE='ade3b4e98078a7a33a9a1ff9bf1a917063872dbc4eeba96d42ee33cec554a3d1'
BOUNDARY_RECORD=REPORTS/'delivery-boundary-validation-ade3b4e98078.json'
BOUNDARY_LOG=REPORTS/'native-single-process-focused-final.log'
BINARY=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
PYTHON=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3')
class Preparation(StrictModel):
    source_digest: str
    driver_sha256: str
    workbook_program_sha256: str
    literal_fixtures_sha256: str
    generation_seed: int=113
    generation_count: int=1
    selected_generated_indices: list[int]=[0]
    maximum_seconds: int=40
    model_turns: int=0
    classification: str='fixture generation and reviewed production task-scope setup; no model/planner execution'
class Definition(StrictModel):
    model: str='gpt-6.1-sol'
    effort: str='medium'
    binary_sha256: str
    executor_fingerprint: str
    scope_digest: str
    prompt_sha256: str
    input_hashes: list[str]
    native_overrides: list[str]
    inherited_instruction_sha256: str
    native_boundary_evidence_sha256: str
    native_boundary_log_sha256: str
    setup_operation_id: str
    reader_command: str
    reader_command_sha256: str
    staged_input_sha256: str
    cell_sha256: str
    approval_source: str
    exposure_override: str
    exact_server: str
    exact_tool: str
    expected_sha256: str
    spec_sha256: str
    schema_sha256: str
    generated_launcher_sha256: str
    maximum_seconds: int=240
    maximum_model_turns: int=1
    maximum_operations: int=1
    exploratory_resource_bounds: dict[str, float]={'host_tree_peak_rss_bytes':1073741824,'observed_host_tree_cpu_seconds':60,'elapsed_seconds':240,'retained_evidence_bytes':8388608}
    classification: str='inert existing-code-mode file handoff diagnostic; fresh2rowworkbook seed113/index0; existing code-mode scratch file→builtin reader variable→own scoped MCP; no opaque model argument transcription or new transport, no workbook replay, autonomy qualification or marginal benefit'
    outer_host_boundary: str='named filesystem/network profile for native model commands; no single-process guarantee for outer model host; inherited MCP processes outside this profile'
    unexpected_tool_detection: str='post-execution observation only, not preventative enforcement'
def file_hash(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
async def main():
    assert verification_source_digest(ROOT)==SOURCE
    assert os.getenv('AEEP_NATIVE_CODE_MODE_FUTURE_EXACT_REVIEW')=='authorized-capacity-and-preflight', 'INERT: future exact review/capacity/preflight required; no inferred availability'
    assert file_hash(BINARY)=='50ac633af64851511f9bbc71032cdae7f1ba20b3234c189687d61ba846c354c5'
    assert BOUNDARY_RECORD.is_file(), "native source-bound validation record pending"
    validated=json.loads(BOUNDARY_RECORD.read_text());assert validated['source_digest']==SOURCE and validated['complete'] and validated['source_unchanged']
    assert len(validated['checks'])==22 and all(item['exit_code']==0 and item['source_unchanged'] for item in validated['checks'])
    capacity=json.loads((REPORTS/'native-capacity-refresh-ade3-result.json').read_text())
    assert capacity['source_digest']==SOURCE and capacity['cleanup_confirmed'] and capacity['source_unchanged']
    from datetime import datetime, timezone
    assert 0 <= (datetime.now(timezone.utc)-datetime.fromisoformat(capacity['recorded_at'])).total_seconds() <= 300
    assert capacity['capacity'] is not None
    windows=capacity['capacity'].get('windows',[])
    assert windows and all(window.get('exhausted') is False and window.get('used_percent') is not None and float(window['used_percent']) < 100 for window in windows)
    assert any(window.get('window_id')=='codex:primary' for window in windows)
    main_router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');repo=AssessmentRepository(main_router.store)
    old=AssessmentPlanningRequest.model_validate(repo.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
    setup_definition=Preparation(source_digest=SOURCE,driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),workbook_program_sha256=file_hash(ASSETS/'workbook_program.py'),literal_fixtures_sha256=file_hash(ASSETS/'workbook-grader-fixtures.json'))
    setup_identity=Path(__file__).stem+'-setup'
    setup_mapping=repo.put('native_host_setup',setup_identity,setup_definition);repo.review(setup_mapping)
    setup_request=old.model_copy(update={'plan_id':'planning_'+setup_identity,'mapping_digest':setup_mapping,'definition_digests':[*old.definition_digests,setup_mapping]})
    setup_digest=repo.put('planning_request',setup_request.plan_id,setup_request);repo.review(setup_digest);repo.authorize(setup_request)
    (REPORTS/(Path(__file__).stem+'-setup-review.json')).write_text(json.dumps({'authority':'standing September25/27 finite exact review delegation','definition':setup_definition.model_dump(),'mapping_digest':setup_mapping,'request_digest':setup_digest,'planner_execution':False},indent=2))
    setup_operation='native-setup:'+setup_request.plan_id
    repo.reserve(setup_request,setup_operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=40),stage='native_fixture_scope_setup')
    setup_started=time.perf_counter()
    result_path=REPORTS/'native-sol61-code-mode-file-handoff-ade3-result-288e.json'; assert not result_path.exists()
    directory=Path(tempfile.mkdtemp(prefix='aeep-sol61-model-journey-',dir=ROOT)).resolve(); scratch=directory/'scratch'; scratch.mkdir()
    generated=subprocess.run([str(PYTHON),'-I',str(ASSETS/'workbook_program.py'),'generate'],input=json.dumps({'seed':113,'stages':[{'split':'demo','count':1}]}),text=True,capture_output=True,check=True,timeout=15)
    generated_case=json.loads(generated.stdout)['cases'][0]
    cases=[{'input':generated_case['input'],'expected':generated_case['output']}]
    source=(ASSETS/'workbook_program.py').read_text()
    prefix=subprocess.run([str(PYTHON),'-I','-c','import sys;print(sys.prefix)'],check=True,capture_output=True,text=True).stdout.strip()
    boundary=NativeSandboxConfig(binary=str(BINARY),binary_sha256='sha256:'+file_hash(BINARY),project_root=str(directory),read_roots=[str(Path(prefix).resolve()),str(ROOT/'AGENTS.md')],write_roots=[str(scratch)],single_process=True,python_binary=str(PYTHON.resolve()),python_sha256='sha256:'+file_hash(PYTHON.resolve()))
    recipe=workbook_recipe();spec=recipe.extension.reference.model_copy(deep=True);spec.id='native.workbook.sol61-small-approved';spec.input_schema=recipe.input_schema;spec.output_schema=recipe.output_schema
    program="import json,sys;ns={'__name__':'reference'};exec("+repr(source)+",ns);inp=json.load(sys.stdin);print(json.dumps(ns['reference'](inp)))"
    spec.config={**spec.config,'argv':[str(PYTHON.resolve()),'-I','-c',program],'native_sandbox':boundary.model_dump(mode='json'),'env':{'TMPDIR':str(scratch)},'max_output_bytes':200000,'timeout_seconds':30}
    spec.validators=[ValidationSpec(kind=ValidationKind.CALLBACK,config={'name':'aeep.workbook.native.v1','implementation_digest':implementation_digest()})]
    manifest=directory/'aeep.json';manifest.write_text(Manifest(database=str(directory/'.aeep/state.db'),executors=[spec]).model_dump_json())
    task=Router.from_manifest(manifest);task_repo=AssessmentRepository(task.store);task_repo.review(task_repo.put("recipe",recipe.recipe_id,recipe))
    scope=TaskScope(scope_id='sol61-code-mode-file-handoff-ade3',project_root=str(directory),executor_fingerprints={spec.id:executor_fingerprint(spec)},approval_ceiling=SideEffect.READ,max_attempts=1,max_attempt_seconds=30,expires_at=utc_now()+timedelta(minutes=10))
    scope_digest=task_repo.put('task_scope',scope.scope_id,scope);task_repo.review(scope_digest);activation=activate(task,scope.scope_id)
    service=AEEPToolService(task,profile='task',task_activation=activation.activation_id);tools=service.list_tools();assert len(tools)==1;tool=tools[0]['name']
    inputs=[cases[0]['input']]
    override='mcp_servers.aeep_'+activation.activation_id+'.omit_tools_from=["deferred"]'
    entry=__import__('tomllib').loads((directory/'.codex/config.toml').read_text())['mcp_servers']['aeep_'+activation.activation_id]
    assert entry['tools']=={tool:{'approval_mode':'approve'}} and 'default_tools_approval_mode' not in entry,'generated tool rule mismatch'
    staged=scratch/'input.json';staged.write_text(json.dumps(inputs[0],sort_keys=True),encoding='utf-8')
    reader_program='from pathlib import Path; import sys; sys.stdout.write(Path('+repr(str(staged))+').read_text(encoding="utf-8"))'
    reader_command=shlex.join([str(PYTHON.resolve()),'-I','-c',reader_program])
    nested_name='mcp__aeep_'+activation.activation_id+'__'+tool
    cell='const loaded=await tools.exec_command('+json.dumps({'cmd':reader_command,'yield_time_ms':10000,'max_output_tokens':8000},separators=(',',':'))+'); if(loaded.exit_code!==0 || loaded.session_id!==undefined) throw new Error("reader_not_complete"); const input=JSON.parse(loaded.output); const result=await tools.'+nested_name+'(input); text({ok:result.structuredContent?.ok===true});'
    prompt='Use native exec code-mode exactly once to run the following literal cell. It reads only the declared synthetic scratch input and invokes the one own scoped MCP tool, without printing encoded input/output. No unrelated tools, credentials, network, retries or transformations. Return only successes:[boolean], stopped_after_rejection:boolean and reason completed/unavailable/denied/failed. Cell: '+cell
    definition=Definition(reader_command=reader_command,reader_command_sha256=hashlib.sha256(reader_command.encode()).hexdigest(),staged_input_sha256=file_hash(staged),cell_sha256=hashlib.sha256(cell.encode()).hexdigest(),approval_source="actual production-generated exact task rules",expected_sha256=hashlib.sha256(json.dumps(cases[0]['expected'],sort_keys=True).encode()).hexdigest(),spec_sha256=hashlib.sha256(spec.model_dump_json().encode()).hexdigest(),schema_sha256=hashlib.sha256(json.dumps(tools,sort_keys=True).encode()).hexdigest(),generated_launcher_sha256=hashlib.sha256((directory/'.codex/config.toml').read_bytes()).hexdigest(),exposure_override=override,exact_server="aeep_"+activation.activation_id,exact_tool=tool,binary_sha256=boundary.binary_sha256,executor_fingerprint=executor_fingerprint(spec),scope_digest=scope_digest,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),input_hashes=[hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest() for x in inputs],native_overrides=boundary.permission_overrides(),inherited_instruction_sha256=hashlib.sha256((ROOT/'AGENTS.md').read_bytes()).hexdigest(),native_boundary_evidence_sha256=hashlib.sha256(BOUNDARY_RECORD.read_bytes()).hexdigest(),native_boundary_log_sha256=hashlib.sha256(BOUNDARY_LOG.read_bytes()).hexdigest(),setup_operation_id=setup_operation)
    mapping=repo.put('native_host_diagnostic','sol61-code-mode-file-handoff-ade3',definition);repo.review(mapping)
    req=old.model_copy(update={'plan_id':'planning_native_sol61_code_mode_file_handoff_ade3','mapping_digest':mapping,'definition_digests':[*old.definition_digests,mapping]})
    request_digest=repo.put('planning_request',req.plan_id,req);repo.review(request_digest);repo.authorize(req)
    review={'authority':'standing September25/27 exact review delegation;September30 unfinished tests model selection','source_digest':SOURCE,'definition':definition.model_dump(),'mapping_digest':mapping,'request_digest':request_digest,'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':scope.model_dump(mode='json'),'activation':activation.activation_id,'schema_bytes':len(json.dumps(tools).encode()),'instructions_bytes':len(service.instructions.encode()),'prompt_bytes':len(prompt.encode()),'authentication':'Codex-owned; never accessed','global_configuration_changes':False,'new_services':False,'native_boundary_result':str(BOUNDARY_RECORD.relative_to(REPORTS)),'note':'planning request is authorization envelope only; no planner execution or managed-worker conformance'}
    (REPORTS/'native-sol61-code-mode-file-handoff-ade3-review-288e.json').write_text(json.dumps(review,indent=2))
    setup_elapsed=time.perf_counter()-setup_started
    repo.finish_operation(setup_operation,elapsed_seconds=setup_elapsed)
    operation='native-one-case:'+req.plan_id;repo.reserve(req,operation,AssessmentLimits(max_operations=1,max_model_turns=1,max_elapsed_seconds=240),stage='native_host_model_journey')
    chronology=[];server_requests=[];interrupt_started=False
    began=time.perf_counter();transport=None;turn_id=None;thread_id=None;collector=None;samples=[];processes={};events=Counter();outputs=[];tool_events=[];auxiliary_actions=[];startup_events=[];sampling=True
    record={'source_digest':SOURCE,'operation_id':operation,'task_scope_digest':scope_digest,'setup_operation_id':setup_operation,'setup_elapsed_seconds':setup_elapsed,'schema_bytes':review['schema_bytes'],'instructions_bytes':review['instructions_bytes'],'prompt_bytes':review['prompt_bytes'],'classification':definition.classification}
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
        if method in {'turn/started','turn/completed','thread/tokenUsage/updated','item/started','item/completed','model/rerouted'} and len(chronology)<200:
            nested=params.get('turn') if isinstance(params.get('turn'),dict) else {}
            hd=lambda value:hashlib.sha256(value.encode()).hexdigest() if isinstance(value,str) else None
            entry={'seconds':time.perf_counter()-began,'after_interrupt':interrupt_started,'method':method,'keys':sorted(params)[:25],'thread_hash':hd(params.get('threadId')),'turn_hash':hd(params.get('turnId')),'nested_turn_hash':hd(nested.get('id')),'thread_equal':params.get('threadId')==thread_id,'turn_equal':params.get('turnId')==turn_id,'terminal_status':nested.get('status')}
            usage=params.get('tokenUsage')
            if isinstance(usage,dict):entry['numeric_usage']={kind:{k:v for k,v in vals.items() if isinstance(v,int) and not isinstance(v,bool) and v>=0} for kind,vals in usage.items() if isinstance(vals,dict)}
            item=params.get('item')
            if isinstance(item,dict):entry['item_metadata']={key:item.get(key) for key in ('type','status','phase') if isinstance(item.get(key),(str,int,bool))}
            chronology.append(entry)
        if method=='mcpServer/startupStatus/updated':
            server=params.get('server') or params.get('serverName') or params.get('name')
            if server=='aeep_'+activation.activation_id:
                status=params.get('status')
                error=params.get('error')
                text=str(error).lower() if error is not None else ''
                code=next((code for phrase,code in [('no module named','python_module_missing'),('operation not permitted','native_permission_denied'),('timed out','startup_timeout'),('no such file','executable_missing'),('connection refused','connection_refused')] if phrase in text),'unclassified' if error is not None else None)
                startup_events.append({'owned_server':True,'status':status if isinstance(status,str) and status in ('starting','ready','failed','cancelled','inProgress','completed') else 'unknown','error_code':code,'error_present':error is not None})
        if method=='item/completed' and isinstance(params.get('item'),dict):
            item=params['item']
            if item.get('type') in {'commandExecution','fileChange','dynamicToolCall'}:
                auxiliary_actions.append({'type':item.get('type'),'tool':item.get('tool'),'namespace':item.get('namespace'),'command_sha256':hashlib.sha256(item['command'].encode()).hexdigest() if isinstance(item.get('command'),str) else None,'command_equals_reviewed_reader':item.get('command')==reader_command if item.get('type')=='commandExecution' else None,'exit_code':item.get('exitCode') if isinstance(item.get('exitCode'),int) else None})
            if item.get('type')=='mcpToolCall':
                result=item.get('result');error=item.get('error');error_text=json.dumps(error,ensure_ascii=True)[:4000] if error is not None else ''
                arguments=item.get('arguments');argument_hash=hashlib.sha256(json.dumps(arguments,sort_keys=True).encode()).hexdigest() if isinstance(arguments,dict) else None
                tool_events.append({'server':item.get('server'),'tool':item.get('tool'),'status':item.get('status'),'result_keys':sorted(result) if isinstance(result,dict) else None,'argument_keys':sorted(arguments) if isinstance(arguments,dict) else None,'argument_sha256':argument_hash,'arguments_equal_expected':arguments==inputs[0] if isinstance(arguments,dict) else None,'error_present':error is not None,'error_shape':sorted(error) if isinstance(error,dict) else type(error).__name__ if error is not None else None,'error_sha256':hashlib.sha256(error_text.encode()).hexdigest() if error_text else None,'error_code':error.get('code') if isinstance(error,dict) and isinstance(error.get('code'),int) else None,'known_error_classes':[label for phrase,label in [('approval policy is never','approval_required_never'),('not available to the model','model_binding_unavailable'),('invalid','invalid_argument_or_result'),('permission denied','permission_denied'),('unknown','unknown_binding'),('timed out','timeout'),('metadata is incomplete','modern_metadata_incomplete')] if phrase in error_text.lower()],'unclassified_error':bool(error_text) and not any(phrase in error_text.lower() for phrase in ('approval policy is never','not available to the model','invalid','permission denied','unknown','timed out','metadata is incomplete'))})
                if isinstance(result,dict):
                    structured=result.get('structuredContent')
                    if not isinstance(structured,dict):
                        for content in result.get('content',[]):
                            if isinstance(content,dict) and content.get('type')=='text':
                                try: candidate=json.loads(content.get('text','')); structured=candidate if isinstance(candidate,dict) else structured
                                except (ValueError,TypeError): pass
                    if isinstance(structured,dict):outputs.append(structured)
    sampler=asyncio.create_task(sample())
    stage='host_start'
    try:
        async with asyncio.timeout(225):
            argv=(str(BINARY),'app-server','-c','features.apps=false','-c','features.code_mode=true','-c',override,*boundary.permission_overrides())
            transport=CodexAppServerTransport(argv,environment_allowlist=('HOME','CODEX_HOME','PATH'),cwd=str(directory),executable_sha256=boundary.binary_sha256,request_timeout=20,options=AppServerOptions(experimental_api=True))
            original_server_request=transport._handle_server_request
            async def observe_server_request(request_id,method,params):
                before=len(transport.approval_digests)
                entry={'method':method[:120],'seconds':time.perf_counter()-began,'decision':'unknown'}
                if len(server_requests)<30:server_requests.append(entry)
                try:
                    await original_server_request(request_id,method,params)
                    entry['decision']='decline' if len(transport.approval_digests)>before else 'method_not_supported'
                except BaseException as error:
                    entry['error_type']=type(error).__name__;raise
            transport._handle_server_request=observe_server_request
            transport.subscribe(observe)
            stage='config/read'
            config_view=await transport.request('config/read',{'includeLayers':True,'cwd':str(directory)})
            layers=[]
            for layer in config_view.get('layers') or []:
                name=layer.get('name',{})
                if not isinstance(name,dict): continue
                kind=name.get('type')
                layers.append({'type':kind,'owned_project_layer':kind=='project' and name.get('dotCodexFolder')==str(directory/'.codex'),'disabled_reason':str(layer.get('disabledReason'))[:500] if layer.get('disabledReason') is not None else None})
            record['configuration_layers']=layers
            record['project_config_layer_present']=any(x['owned_project_layer'] for x in layers)
            record['project_config_layer_enabled']=any(x['owned_project_layer'] and x['disabled_reason'] is None for x in layers)
            own=config_view.get('config',{}).get('mcp_servers',{}).get('aeep_'+activation.activation_id,{})
            record['effective_omit_tools_from']=own.get('omit_tools_from')
            assert own.get('omit_tools_from')==['deferred'],'own code-mode exposure override not effective'
            record['effective_own_tool_policy']={'default_tools_approval_mode':own.get('default_tools_approval_mode'),'own_tool_approval_mode':own.get('tools',{}).get(tool,{}).get('approval_mode'),'own_tool_rule_present':tool in own.get('tools',{})}
            assert record['effective_own_tool_policy']['own_tool_approval_mode']=='approve','exact approval override rejected or ignored'
            record['code_mode_feature_ack']=config_view.get('config',{}).get('features',{}).get('code_mode')
            assert record['code_mode_feature_ack'] is True,'task-local code_mode feature not acknowledged'
            record['effective_model_tool_mode']='unknown; not exposed by supported zero-model schema, config feature ACK alone is insufficient'
            del config_view
            stage='thread/start'
            response=await transport.request('thread/start',{'ephemeral':True,'cwd':str(directory),'model':'gpt-6.1-sol','permissions':'aeep-native-task','approvalPolicy':'never','approvalsReviewer':'user'})
            profile=response.get('activePermissionProfile');record['permission_acknowledgement']={'model':response.get('model'),'cwd':response.get('cwd'),'approvalPolicy':response.get('approvalPolicy'),'approvalsReviewer':response.get('approvalsReviewer'),'profile':profile}
            assert response.get('cwd')==str(directory) and response.get('approvalPolicy')=='never' and isinstance(profile,dict) and profile.get('id')=='aeep-native-task' and profile.get('extends') is None,'native profile not acknowledged'
            thread_id=response['thread']['id']
            stage='mcpServerStatus/list'
            status=await transport.request('mcpServerStatus/list',{'threadId':thread_id,'limit':100,'detail':'toolsAndAuthOnly'})
            inventory=[{'name':x['name'],'tools':sorted(x.get('tools',{}))} for x in status.get('data',[])]
            record['inventory']=inventory
            record['owned_mcp_launch_errors']=[{'error_code':next((code for phrase,code in [('no module named','python_module_missing'),('operation not permitted','native_permission_denied'),('timed out','startup_timeout'),('no such file','executable_missing'),('connection refused','connection_refused')] if phrase in str(item.get('toolsError','')).lower()),'unclassified'),'error_present':True} for item in status.get('data',[]) if item.get('name')=='aeep_'+activation.activation_id and item.get('toolsError') is not None]
            expected_server='aeep_'+activation.activation_id
            record['selected_server']=expected_server
            record['selected_tool']=tool
            assert any(x=={'name':expected_server,'tools':[tool]} for x in inventory), 'owned AEEP tool absent'
            thread_id=response['thread']['id'];collector=_TurnCollector(max_output_bytes=200000);collector.thread_id=thread_id;transport.subscribe(collector.handle)
            assert hashlib.sha256((ROOT/'AGENTS.md').read_bytes()).hexdigest()==definition.inherited_instruction_sha256,'inherited instructions changed'
            stage='turn/start'
            response=await transport.request('turn/start',{'threadId':thread_id,'input':[{'type':'text','text':prompt}],'model':'gpt-6.1-sol','effort':'medium','outputSchema':{'type':'object','properties':{'successes':{'type':'array','items':{'type':'boolean'},'minItems':1,'maxItems':1},'stopped_after_rejection':{'type':'boolean'},'reason':{'type':'string','enum':['completed','unavailable','denied','failed']}},'required':['successes','stopped_after_rejection','reason'],'additionalProperties':False}})
            turn_id=response['turn']['id'];collector.turn_id=turn_id
            stage='model_turn'
            result=await collector.future
            record.update(turn_status=result.status,actual_model=result.actual_model,token_usage=result.token_usage,tool_count=result.tool_count,final_output={k:v for k,v in result.output.items() if k in ('successes','stopped_after_rejection','reason')} if isinstance(result.output,dict) else {'unknown':True,'sha256':hashlib.sha256(str(result.output).encode()).hexdigest()},turn_error='reported; raw terminal text withheld' if result.error else None)
            assert result.status=='completed' and result.actual_model in (None,'gpt-6.1-sol'),'model turn failed or substituted'
            assert len(outputs)==1,'missing observed tool results'
            assert all(x['server']==expected_server and x['tool']==tool for x in tool_events),'unexpected MCP tool used'
            command_events=[x for x in auxiliary_actions if x['type']=='commandExecution'];record['reader_command_events']=command_events
            assert len(command_events)==1 and command_events[0]['command_equals_reviewed_reader'] is True and command_events[0]['exit_code']==0,'reviewed reader command not completed exactly once'
            assert all(x['type']=='commandExecution' or (x['type']=='dynamicToolCall' and x['tool'] in {'exec','wait','tool_search','toolSearch','search_tools','list_tools'}) for x in auxiliary_actions),'unexpected non-reader action used'
            stage='independent_grading'
            checks=[]
            for i,output in enumerate(outputs):
                valid=runpy.run_path(str(ASSETS/'workbook_grader.py'))['grade']({'input':inputs[i],'output':output.get('output'),'expected':cases[0]['expected']}) if output.get('output') is not None else False
                receipt=output.get('receipts',[{}])[0];checks.append({'index':i,'ok':output.get('ok'),'task_valid':receipt.get('task_valid'),'receipt_id':receipt.get('receipt_id'),'summary':output.get('summary'),'recovery_state':output.get('recovery_state'),'resources':receipt.get('recorded_resources'),'independent_grader_valid':valid})
            record['checks']=checks
            assert all(x['ok'] and x['task_valid'] is True and x['independent_grader_valid'] for x in checks)
            record['journey_passed']=True
            assert all(event['arguments_equal_expected'] is True for event in tool_events),'observed own MCP args mismatch or unavailable'
            assert len(tool_events)==1 and tool_events[0]['status']=='completed','own MCP event not terminal' 
    except BaseException as exc:
        record.update(error_type=type(exc).__name__,failed_stage=stage,journey_passed=False)
        if hasattr(exc,'method'): record['failed_method']=exc.method
        if hasattr(exc,'error') and isinstance(exc.error,dict):
            record['protocol_error_code']=exc.error.get('code')
            message=str(exc.error.get('message',''))[:1000]
            record['protocol_error_message_bytes']=len(message.encode());record['protocol_error_message_sha256']=hashlib.sha256(message.encode()).hexdigest()
        if transport is not None and thread_id and turn_id:
            interrupt_started=True;record['interrupt_seconds']=time.perf_counter()-began
            try: await transport.request('turn/interrupt',{'threadId':thread_id,'turnId':turn_id},timeout=5)
            except BaseException: pass
    finally:
        if transport is not None:
            try: await asyncio.wait_for(transport.close(),5);record['host_cleanup_confirmed']=not transport.running
            except BaseException as exc:record['cleanup_error_type']=type(exc).__name__
        record.update(event_chronology=chronology,server_requests=server_requests,transport_fatal_type=type(transport._fatal).__name__ if transport and transport._fatal else None,collector_usage=collector.token_usage if collector else None,collector_terminal_status=collector.terminal[0] if collector and collector.terminal else None)
        if transport is not None:
            stderr=bytes(transport.stderr).decode('utf-8',errors='replace')
            record['appserver_stderr']={'bytes':len(transport.stderr),'truncated':transport.stderr_truncated,'known_error_classes':[label for phrase,label in [('rate limit','rate_limit'),('429','http429'),('connection refused','connection_refused'),('timed out','timeout'),('retrying','retry'),('failed to','failure'),('permission denied','permission_denied')] if phrase in stderr.lower()]}
        survivors=[]
        grace=time.perf_counter()+2
        while time.perf_counter()<grace:
            survivors=[]
            for pid,created in list(processes):
                try:
                    proc=psutil.Process(pid)
                    if proc.create_time()==created and proc.status()!=psutil.STATUS_ZOMBIE: survivors.append(proc)
                except psutil.Error:pass
            if not survivors:break
            await asyncio.sleep(.05)
        record['owned_survivors_cleaned']=[]
        for proc in survivors:
            try:
                record['owned_survivors_cleaned'].append({'pid':proc.pid,'create_time':proc.create_time()});proc.kill()
            except psutil.Error:pass
        if survivors:record['journey_passed']=False
        record['cleanup_confirmed']=record.get('host_cleanup_confirmed',False) and not survivors
        sampling=False;await sampler
        record['uninstall']=change_state(task,activation.activation_id,'uninstall');record['activation_inspection']=inspect(task,activation.activation_id)
        elapsed=time.perf_counter()-began; accounting=None
        if collector is not None and collector.token_usage is not None:
            _,accounting=turn_accounting(collector.token_usage,model=collector.actual_model or 'gpt-6.1-sol',resource_pool='native-codex-subscription')
        repo.finish_operation(operation,elapsed_seconds=elapsed,accounting=accounting)
        record.update(elapsed_seconds=elapsed,process_samples=samples,owned_process_observations=list(processes.values()),event_counts=dict(events),tool_events=tool_events,auxiliary_actions=auxiliary_actions,owned_mcp_startup_events=startup_events,outer_host_boundary=definition.outer_host_boundary,unexpected_tool_detection=definition.unexpected_tool_detection,network_observations='unknown; no network telemetry collected',resource_limits='sampled process tree; rapid and between-sample child lifetimes can be missed; includes host/MCP/AEEP descendants observed, no whole-machine baseline',model_identity='requested gpt-6.1-sol; reroute notification if observed; absence of reroute is not independent runtime identity',grant_after=list(main_router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(req.authorization_id,)).fetchone()),source_unchanged=verification_source_digest(ROOT)==SOURCE,release_ready=False,replay_allowed=False)
        record['tool_results_observed']=len(outputs)
        record['durable_task_attempts']=task.store._connection.execute('SELECT COUNT(*) FROM execution_attempts').fetchone()[0]
        record['durable_receipts']=task.store._connection.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]
        if record.get('journey_passed'):
            assert record['durable_task_attempts']==record['durable_receipts']==1
            assert task.store._connection.execute('SELECT executor_id FROM receipts').fetchall()[0][0]==spec.id,'durable selected executor mismatch'
        evidence=ROOT/'.aeep/native-sol61-code-mode-file-handoff-ade3-evidence';evidence.mkdir(exist_ok=False)
        await task.close();await main_router.close()
        import shutil
        shutil.move(str(directory/'.aeep'),str(evidence/'task-state'));shutil.rmtree(directory)
        result_path.write_text(json.dumps(record,indent=2));print(json.dumps({k:v for k,v in record.items() if k not in ('process_samples','owned_process_observations','inventory','uninstall','activation_inspection','final_output','checks','event_counts','tool_events')}))
if __name__=='__main__':
    if sys.argv[1:]!=['--execute-reviewed-model-diagnostic']:
        raise SystemExit('INERT: no model/cell/config operations; future capacity+effective availability+exact review required')
    asyncio.run(main())
