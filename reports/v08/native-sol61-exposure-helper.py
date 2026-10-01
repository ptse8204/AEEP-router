"""Zero-model effective exposure configuration and fixed helper handshake; no model exposure proof."""
import asyncio, hashlib, json, os, runpy, subprocess, tempfile, time, tomllib
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
from aeep.executors.mcp import _extract_result
from aeep.models import StrictModel, Manifest, TaskScope, SideEffect, ValidationSpec, ValidationKind, utc_now
from aeep.router import Router
from aeep.tasks import activate, change_state, inspect
ROOT=Path(__file__).resolve().parents[2]; REPORTS=ROOT/'reports/v08'; ASSETS=ROOT/'integrations/assessment-runtime'
SOURCE='f55ebe5ca0764a8ebfbcfa653c49ee39cced7e85b0a78515d6bbbb6b2f0a1cc4'
BOUNDARY_RECORD=REPORTS/'native-single-process-source-freeze.json'
BOUNDARY_LOG=REPORTS/'native-single-process-focused-final.log'
BINARY=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
PYTHON=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3')
class Preparation(StrictModel):
    source_digest: str
    driver_sha256: str
    workbook_program_sha256: str
    literal_fixtures_sha256: str
    generation_seed: int=97
    generation_count: int=3
    selected_generated_indices: list[int]=[1]
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
    generated_launcher: dict[str, object]
    helper_sha256: str
    exposure_override: str
    maximum_seconds: int=60
    maximum_model_turns: int=0
    maximum_operations: int=1
    exploratory_resource_bounds: dict[str, float]={'host_tree_peak_rss_bytes':1073741824,'observed_host_tree_cpu_seconds':60,'elapsed_seconds':60,'retained_evidence_bytes':8388608}
    classification: str='zero-model two effective config reads plus fixed helper handshake; fresh seed97/index1; exact generated launcher and native task child, no model exposure, planner execution or qualification'
    outer_host_boundary: str='named filesystem/network profile for native model commands; no single-process guarantee for outer model host; inherited MCP processes outside this profile'
    unexpected_tool_detection: str='post-execution observation only, not preventative enforcement'
async def main():
    assert verification_source_digest(ROOT)==SOURCE
    assert BOUNDARY_RECORD.is_file(), "native source-bound validation record pending"
    assert json.loads(BOUNDARY_RECORD.read_text())["source_digest"]==SOURCE
    main_router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');repo=AssessmentRepository(main_router.store)
    old=AssessmentPlanningRequest.model_validate(repo.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
    setup_definition=Preparation(source_digest=SOURCE,driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),workbook_program_sha256=hashlib.sha256((ASSETS/'workbook_program.py').read_bytes()).hexdigest(),literal_fixtures_sha256=hashlib.sha256((ASSETS/'workbook-grader-fixtures.json').read_bytes()).hexdigest())
    setup_identity=Path(__file__).stem+'-setup'
    setup_mapping=repo.put('native_host_setup',setup_identity,setup_definition);repo.review(setup_mapping)
    setup_request=old.model_copy(update={'plan_id':'planning_'+setup_identity,'mapping_digest':setup_mapping,'definition_digests':[*old.definition_digests,setup_mapping]})
    setup_digest=repo.put('planning_request',setup_request.plan_id,setup_request);repo.review(setup_digest);repo.authorize(setup_request)
    (REPORTS/(Path(__file__).stem+'-setup-review.json')).write_text(json.dumps({'authority':'standing September25/27 finite exact review delegation','definition':setup_definition.model_dump(),'mapping_digest':setup_mapping,'request_digest':setup_digest,'planner_execution':False},indent=2))
    setup_operation='native-setup:'+setup_request.plan_id
    repo.reserve(setup_request,setup_operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=40),stage='native_fixture_scope_setup')
    setup_started=time.perf_counter()
    result_path=REPORTS/'native-sol61-exposure-helper-result-288e.json'; assert not result_path.exists()
    directory=Path(tempfile.mkdtemp(prefix='aeep-sol61-model-journey-',dir=ROOT)).resolve(); scratch=directory/'scratch'; scratch.mkdir()
    generated=subprocess.run([str(PYTHON),'-I',str(ASSETS/'workbook_program.py'),'generate'],input=json.dumps({'seed':97,'stages':[{'split':'demo','count':3}]}),text=True,capture_output=True,check=True,timeout=15)
    generated_cases=json.loads(generated.stdout)['cases']
    cases=[{'input':generated_cases[i]['input'],'expected':generated_cases[i]['output']} for i in (1,)]
    fault_input=dict(cases[0]['input'],row_bound=cases[0]['input']['row_bound']+1)
    source=(ASSETS/'workbook_program.py').read_text(); fault=json.loads((ASSETS/'workbook-faults.json').read_text())['stale_value']
    prefix=subprocess.run([str(PYTHON),'-I','-c','import sys;print(sys.prefix)'],check=True,capture_output=True,text=True).stdout.strip()
    boundary=NativeSandboxConfig(binary=str(BINARY),binary_sha256='sha256:'+hashlib.sha256(BINARY.read_bytes()).hexdigest(),project_root=str(directory),read_roots=[str(Path(prefix).resolve()),str(ROOT/'AGENTS.md')],write_roots=[str(scratch)],single_process=True,python_binary=str(PYTHON.resolve()),python_sha256='sha256:'+hashlib.sha256(PYTHON.resolve().read_bytes()).hexdigest())
    recipe=workbook_recipe(); spec=recipe.extension.reference.model_copy(deep=True);spec.id='native.workbook.sol61-model-journey';spec.input_schema=recipe.input_schema;spec.output_schema=recipe.output_schema
    program="import json,sys;ns={'__name__':'reference'};exec("+repr(source)+",ns);inp=json.load(sys.stdin);print(json.dumps(ns['reference'](inp)))"
    spec.config={**spec.config,'argv':[str(PYTHON),'-I','-c',program],'native_sandbox':boundary.model_dump(mode='json'),'env':{'TMPDIR':str(scratch)},'max_output_bytes':200000}
    spec.validators=[ValidationSpec(kind=ValidationKind.CALLBACK,config={'name':'aeep.workbook.native.v1','implementation_digest':implementation_digest()})]
    manifest=directory/'aeep.json';manifest.write_text(Manifest(database=str(directory/'.aeep/state.db'),executors=[spec]).model_dump_json())
    task=Router.from_manifest(manifest);task_repo=AssessmentRepository(task.store);task_repo.review(task_repo.put('recipe',recipe.recipe_id,recipe))
    scope=TaskScope(scope_id='sol61-exposure-helper',project_root=str(directory),executor_fingerprints={spec.id:executor_fingerprint(spec)},approval_ceiling=SideEffect.READ,max_attempts=1,max_attempt_seconds=30,expires_at=utc_now()+timedelta(minutes=10))
    scope_digest=task_repo.put('task_scope',scope.scope_id,scope);task_repo.review(scope_digest);activation=activate(task,scope.scope_id)
    service=AEEPToolService(task,profile='task',task_activation=activation.activation_id);tools=service.list_tools();assert len(tools)==1;tool=tools[0]['name']
    inputs=[cases[0]['input']]
    prompt='No model prompt dispatched; operator-owned direct MCP protocol exercise.'
    launch_table=tomllib.loads((directory/'.codex/config.toml').read_text())['mcp_servers']['aeep_'+activation.activation_id]
    launcher={**launch_table,'command_sha256':hashlib.sha256(Path(launch_table['command']).resolve().read_bytes()).hexdigest()}
    helper=Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex-code-mode-host")
    helper_hash=hashlib.sha256(helper.read_bytes()).hexdigest()
    assert helper_hash=="16fea600263ce5ce283b343c2b62d34e3448933b1de9af391e3f87c7da95c683"
    override="mcp_servers.aeep_"+activation.activation_id+'.omit_tools_from=["deferred","code_mode"]'
    definition=Definition(helper_sha256=helper_hash,exposure_override=override,generated_launcher=launcher,binary_sha256=boundary.binary_sha256,executor_fingerprint=executor_fingerprint(spec),scope_digest=scope_digest,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),input_hashes=[hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest() for x in inputs],native_overrides=boundary.permission_overrides(),inherited_instruction_sha256=hashlib.sha256((ROOT/'AGENTS.md').read_bytes()).hexdigest(),native_boundary_evidence_sha256=hashlib.sha256(BOUNDARY_RECORD.read_bytes()).hexdigest(),native_boundary_log_sha256=hashlib.sha256(BOUNDARY_LOG.read_bytes()).hexdigest(),setup_operation_id=setup_operation)
    mapping=repo.put('native_host_diagnostic','sol61-exposure-helper',definition);repo.review(mapping)
    req=old.model_copy(update={'plan_id':'planning_native_sol61_exposure_helper','mapping_digest':mapping,'definition_digests':[*old.definition_digests,mapping]})
    request_digest=repo.put('planning_request',req.plan_id,req);repo.review(request_digest);repo.authorize(req)
    review={'authority':'standing September25/27 exact review delegation;September30 unfinished tests model selection','source_digest':SOURCE,'definition':definition.model_dump(),'mapping_digest':mapping,'request_digest':request_digest,'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':scope.model_dump(mode='json'),'activation':activation.activation_id,'schema_bytes':len(json.dumps(tools).encode()),'instructions_bytes':len(service.instructions.encode()),'prompt_bytes':len(prompt.encode()),'authentication':'Codex-owned; never accessed','global_configuration_changes':False,'new_services':False,'native_boundary_result':str(BOUNDARY_RECORD.relative_to(REPORTS)),'note':'planning request is authorization envelope only; no planner execution or managed-worker conformance'}
    (REPORTS/'native-sol61-exposure-helper-review-288e.json').write_text(json.dumps(review,indent=2))
    setup_elapsed=time.perf_counter()-setup_started
    repo.finish_operation(setup_operation,elapsed_seconds=setup_elapsed)
    operation='native-exposure-helper:'+req.plan_id;repo.reserve(req,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=60),stage='native_host_exposure_helper')
    chronology=[];server_requests=[];interrupt_started=False
    began=time.perf_counter();transport=None;turn_id=None;thread_id=None;collector=None;samples=[];processes={};events=Counter();outputs=[];tool_events=[];auxiliary_actions=[];startup_events=[];sampling=True
    record={'source_digest':SOURCE,'operation_id':operation,'task_scope_digest':scope_digest,'setup_operation_id':setup_operation,'setup_elapsed_seconds':setup_elapsed,'schema_bytes':review['schema_bytes'],'instructions_bytes':review['instructions_bytes'],'prompt_bytes':review['prompt_bytes'],'classification':definition.classification,'generated_launcher':launcher}
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
                auxiliary_actions.append({'type':item.get('type'),'tool':item.get('tool'),'namespace':item.get('namespace')})
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
    stage='host_start'
    try:
        async with asyncio.timeout(45):
            argv=(str(BINARY),'app-server','-c','features.apps=false',*boundary.permission_overrides())
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
            expected_server='aeep_'+activation.activation_id
            def allow_config(view):
                config=view.get('config',{})
                if not isinstance(config,dict):return {'config_object_present':False,'response_keys':sorted(view)}
                servers=config.get('mcp_servers') or config.get('mcpServers') or {}
                own=servers.get(expected_server,{}) if isinstance(servers,dict) else {}
                allowed=('enabled','enabled_tools','disabled_tools','required','startup_readiness','tool_input_schema_max_bytes','omit_tools_from')
                features=config.get('features',{})
                relevant=('apps','code_mode','code_mode_only','code_mode_host','tool_search','tool_search_always_defer_mcp_tools','non_prefixed_mcp_tool_names','deferred_tool_world_state')
                code_mode=config.get('code_mode',{})
                return {'config_object_present':True,'owned_server_present':bool(own),'owned_server_exposure_fields':{k:own[k] for k in allowed if k in own},'feature_flags':{k:features[k] for k in relevant if isinstance(features,dict) and k in features},'code_mode_direct_only_owned_match':expected_server in code_mode.get('direct_only_tool_namespaces',[]) if isinstance(code_mode,dict) else None,'model_tool_mode':config.get('tool_mode'),'model_supports_search_tool':config.get('supports_search_tool')}
            record['baseline_effective_exposure']=allow_config(config_view) if 'config_view' in locals() else None
            # First response was retained only for layer metadata; request once again is avoided below by preserving it.
            await transport.close();transport=None
            stage='override/config/read'
            transport=CodexAppServerTransport((*argv,'-c',override),environment_allowlist=('HOME','CODEX_HOME','PATH'),cwd=str(directory),executable_sha256=boundary.binary_sha256,request_timeout=15,options=AppServerOptions(experimental_api=True))
            overridden=await transport.request('config/read',{'includeLayers':False,'cwd':str(directory)})
            record['direct_only_effective_exposure']=allow_config(overridden)
            del overridden
            actual=record['direct_only_effective_exposure']['owned_server_exposure_fields'].get('omit_tools_from')
            assert actual==['deferred','code_mode'],'installed config did not acknowledge exact direct-only surfaces'
            await transport.close();transport=None
            stage='helper/connection-hello'
            hello={'type':'connection/hello','supportedVersions':[1],'requiredCapabilities':[],'optionalCapabilities':['session-cell-execution-resource-limits','yield-observation']}
            payload=json.dumps(hello,separators=(',',':')).encode()
            process=await asyncio.create_subprocess_exec(str(helper),'--listen','stdio',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,cwd=str(directory),env={'PATH':os.environ.get('PATH','')})
            try:
                async with asyncio.timeout(10):
                    process.stdin.write(len(payload).to_bytes(4,'little')+payload);await process.stdin.drain()
                    length=int.from_bytes(await process.stdout.readexactly(4),'little');assert 0<length<=4096
                    response=json.loads(await process.stdout.readexactly(length))
                    record['helper_handshake']={k:response.get(k) for k in ('type','selectedVersion','capabilities')}
                    assert response.get('type')=='connection/ready' and response.get('selectedVersion')==1
                    process.stdin.close();await process.stdin.wait_closed()
                    await process.wait()
                    stderr=await process.stderr.read(4097)
                    record['helper_stderr_bytes_bounded']=len(stderr);record['helper_returncode']=process.returncode
                    assert process.returncode==0
            finally:
                if process.returncode is None:
                    process.kill();await asyncio.wait_for(process.wait(),3)
                record['helper_cleanup_confirmed']=process.returncode is not None
            record['actual_model_turns_started']=0
            record['journey_passed']=True
    except BaseException as exc:
        record.update(error_type=type(exc).__name__,failed_stage=stage,journey_passed=False)
        if hasattr(exc,'method'): record['failed_method']=exc.method
        if hasattr(exc,'error') and isinstance(exc.error,dict):
            record['protocol_error_code']=exc.error.get('code')
            message=str(exc.error.get('message',''))[:1000]
            record['protocol_error_message']=message if not any(x in message.lower() for x in ('token','secret','credential','bearer')) else 'redacted sensitive error'
        if transport is not None and thread_id and turn_id:
            interrupt_started=True;record['interrupt_seconds']=time.perf_counter()-began
            try: await transport.request('turn/interrupt',{'threadId':thread_id,'turnId':turn_id},timeout=5)
            except BaseException: pass
    finally:
        if transport is None:record['host_cleanup_confirmed']=True
        if transport is not None:
            try: await asyncio.wait_for(transport.close(),5);record['host_cleanup_confirmed']=not transport.running
            except BaseException as exc:record['cleanup_error_type']=type(exc).__name__
        record.update(event_chronology=chronology,server_requests=server_requests,transport_fatal_type=type(transport._fatal).__name__ if transport and transport._fatal else None,collector_usage=collector.token_usage if collector else None,collector_terminal_status=collector.terminal[0] if collector and collector.terminal else None)
        sampling=False;await sampler
        record['uninstall']=change_state(task,activation.activation_id,'uninstall');record['activation_inspection']=inspect(task,activation.activation_id)
        elapsed=time.perf_counter()-began; accounting=None
        if collector is not None and collector.token_usage is not None:
            _,accounting=turn_accounting(collector.token_usage,model=collector.actual_model or 'gpt-6.1-sol',resource_pool='native-codex-subscription')
        repo.finish_operation(operation,elapsed_seconds=elapsed,accounting=accounting)
        record.update(elapsed_seconds=elapsed,process_samples=samples,owned_process_observations=list(processes.values()),event_counts=dict(events),tool_events=tool_events,auxiliary_actions=auxiliary_actions,owned_mcp_startup_events=startup_events,outer_host_boundary=definition.outer_host_boundary,unexpected_tool_detection=definition.unexpected_tool_detection,network_observations='unknown; no network telemetry collected',resource_limits='sampled process tree; rapid and between-sample child lifetimes can be missed; includes host/MCP/AEEP descendants observed, no whole-machine baseline',model_identity='requested gpt-6.1-sol; reroute notification if observed; absence of reroute is not independent runtime identity',grant_after=list(main_router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(req.authorization_id,)).fetchone()),source_unchanged=verification_source_digest(ROOT)==SOURCE,release_ready=False,replay_allowed=False)
        record['tool_results_observed']=len(outputs)
        evidence=ROOT/'.aeep/native-sol61-exposure-helper-evidence';evidence.mkdir(exist_ok=False)
        await task.close();await main_router.close()
        import shutil
        shutil.move(str(directory/'.aeep'),str(evidence/'task-state'));shutil.rmtree(directory)
        result_path.write_text(json.dumps(record,indent=2));print(json.dumps({k:v for k,v in record.items() if k not in ('process_samples','owned_process_observations','inventory','uninstall','activation_inspection','final_output','checks','event_counts','tool_events')}))
asyncio.run(main())
