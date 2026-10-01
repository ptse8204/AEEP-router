"""Inert ordinary-tool baseline calibration; no value or release decision."""
import asyncio, base64, hashlib, json, os, runpy, shutil, sys, tempfile, time
from pathlib import Path
import psutil
from aeep.assessment.models import AssessmentLimits, AssessmentPlanningRequest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexAppServerTransport, AppServerOptions, _TurnCollector
from aeep.hosts.codex_accounting import turn_accounting, rate_limit_observation
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import StrictModel
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[2]; REPORTS=ROOT/'reports/v08'
SOURCE='ade3b4e98078a7a33a9a1ff9bf1a917063872dbc4eeba96d42ee33cec554a3d1'
BINARY=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
PYTHON=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3').resolve()
class Definition(StrictModel):
    facts: dict

def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()

async def main(review_hash):
    review_path=REPORTS/'native-model-resource-baseline-ade3-review.json'
    assert sha(review_path)==review_hash
    review=json.loads(review_path.read_text()); assert review['execution_authorized'] is True
    assert sha(__file__)==review['driver_sha256'] and verification_source_digest(ROOT)==SOURCE
    validation=json.loads((REPORTS/'delivery-boundary-validation-ade3b4e98078.json').read_text())
    assert validation['source_digest']==SOURCE and validation['complete'] and len(validation['checks'])==22 and all(x['exit_code']==0 for x in validation['checks'])
    assert sha(BINARY)==review['binary_sha256'] and sha(PYTHON)==review['python_sha256']
    for name,digest in review['dependencies'].items(): assert sha(ROOT/name)==digest
    result_path=REPORTS/'native-model-resource-baseline-ade3-result.json'; assert not result_path.exists()
    router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json'); repo=AssessmentRepository(router.store)
    old=AssessmentPlanningRequest.model_validate(repo.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
    definition=Definition(facts=review); mapping=repo.put('native_resource_calibration','ordinary-model-baseline-ade3',definition);repo.review(mapping)
    request=old.model_copy(update={'plan_id':'planning_native_resource_baseline_ade3','mapping_digest':mapping,'definition_digests':[*old.definition_digests,mapping]})
    repo.review(repo.put('planning_request',request.plan_id,request));repo.authorize(request)
    before=list(router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(request.authorization_id,)).fetchone())
    setup='native-resource-setup:'+request.plan_id; repo.reserve(request,setup,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=40),stage='fixture_setup')
    started=time.perf_counter(); directory=Path(tempfile.mkdtemp(prefix='aeep-owned-model-baseline-',dir=ROOT)).resolve();scratch=directory/'scratch';scratch.mkdir()
    cases=runpy.run_path(str(REPORTS/'workbook-footprint-calibration-288e.py'))['cases']();ordered=[cases['small'],cases['larger']]
    inputs=[case['input'] for case in ordered]; staged=scratch/'input.json';staged.write_text(json.dumps(inputs,sort_keys=True)); assert [hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest() for x in inputs] == review['expected_input_hashes'], 'fixtures differ from reviewed successful AEEP observation'
    boundary=NativeSandboxConfig(binary=str(BINARY),binary_sha256='sha256:'+sha(BINARY),project_root=str(directory),read_roots=[str(PYTHON.parents[1]),str(ROOT/'AGENTS.md')],write_roots=[str(scratch)],single_process=True,python_binary=str(PYTHON),python_sha256='sha256:'+sha(PYTHON))
    # The evaluated host sees only task inputs. No reference program, oracle or grader is staged.
    prompt=review['prompt_template'].replace('{input_path}',str(staged)).replace('{scratch}',str(scratch)).replace('{python}',str(PYTHON))
    repo.finish_operation(setup,elapsed_seconds=time.perf_counter()-started)
    operation='native-resource-model:'+request.plan_id;repo.authorize(request);repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=1,max_elapsed_seconds=240),stage='model_resource_calibration')
    record={'source_digest':SOURCE,'operation_id':operation,'setup_operation':setup,'grant_before':before,'input_hashes':[hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest() for x in inputs],'classification':review['classification'],'turn_start_dispatched':False,'telemetry_unknowns':review['telemetry_unknowns']}
    (REPORTS/'native-model-resource-baseline-ade3-running.json').write_text(json.dumps(record,indent=2)+'\n')
    began=time.perf_counter();transport=None;collector=None;thread=None;turn=None;stop=False;samples=[];owned={};events={};controller=[];tool_events=[];stage='host_start'
    async def sample():
        while not stop:
            current_controller=psutil.Process(os.getpid()); controller_cpu=current_controller.cpu_times()
            controller.append({'seconds':time.perf_counter()-began,'rss_bytes':current_controller.memory_info().rss,'cpu_seconds':controller_cpu.user+controller_cpu.system})
            if transport and transport._process:
                try:
                    parent=psutil.Process(transport._process.pid);rss=0
                    for p in [parent,*parent.children(recursive=True)]:
                        try:
                            ident=(p.pid,p.create_time());cpu=p.cpu_times();mem=p.memory_info().rss;rss+=mem
                            previous=owned.get(ident,{});owned[ident]={'pid':p.pid,'created':ident[1],'cpu_seconds':cpu.user+cpu.system,'peak_rss_bytes':max(mem,previous.get('peak_rss_bytes',0))}
                        except psutil.Error: pass
                    samples.append({'seconds':time.perf_counter()-began,'rss_bytes':rss})
                except psutil.Error:pass
            await asyncio.sleep(.05)
    sampler=asyncio.create_task(sample())
    def observe(method,params):
        events[method]=events.get(method,0)+1
        item=params.get('item')
        if method=='item/completed' and isinstance(item,dict) and item.get('type') in {'commandExecution','mcpToolCall','dynamicToolCall','fileChange'}:
            entry={'type':item['type'],'tool':str(item.get('tool',''))[:120],'namespace':str(item.get('namespace',''))[:120],'server':str(item.get('server',''))[:120]}
            command=item.get('command');entry['command_sha256']=hashlib.sha256(command.encode()).hexdigest() if isinstance(command,str) else None
            tool_events.append(entry)
            if len(tool_events)>500: raise RuntimeError('bounded tool-event limit exceeded')
    try:
        async with asyncio.timeout(225):
            argv=(str(BINARY),'app-server','-c','features.apps=false','-c','features.code_mode=true',*boundary.permission_overrides())
            transport=CodexAppServerTransport(argv,environment_allowlist=('HOME','CODEX_HOME','PATH'),cwd=str(directory),executable_sha256=boundary.binary_sha256,request_timeout=20,options=AppServerOptions(experimental_api=True));transport.subscribe(observe)
            stage='native_capacity_preflight';capacity_started=time.perf_counter()
            capacity=rate_limit_observation(await transport.request('account/rateLimits/read',{}),resource_id='native-codex-subscription')
            record['capacity_check_seconds']=time.perf_counter()-capacity_started
            record['capacity']=capacity.model_dump(mode='json')
            windows=capacity.windows
            assert windows and any(w.window_id=='codex:primary' for w in windows) and all(w.used_percent is not None and w.exhausted is False and w.used_percent<100 for w in windows), 'native capacity unknown or exhausted'
            stage='effective_config';config=await transport.request('config/read',{'includeLayers':True,'cwd':str(directory)})
            assert config.get('config',{}).get('features',{}).get('code_mode') is True, 'code mode not acknowledged'
            del config
            stage='thread/start';reply=await transport.request('thread/start',{'ephemeral':True,'cwd':str(directory),'model':'gpt-6.1-sol','permissions':'aeep-native-task','approvalPolicy':'never','approvalsReviewer':'user'})
            profile=reply.get('activePermissionProfile'); assert isinstance(profile,dict) and profile.get('id')=='aeep-native-task' and profile.get('extends') is None and reply.get('approvalPolicy')=='never' and reply.get('cwd')==str(directory);thread=reply['thread']['id']
            stage='inventory';status=await transport.request('mcpServerStatus/list',{'threadId':thread,'limit':100,'detail':'toolsAndAuthOnly'})
            record['inventory']=[{'name':item['name'],'tools':sorted(item.get('tools',{}))} for item in status.get('data',[])]
            assert sorted(record['inventory'],key=lambda x:x['name'])==sorted(review['expected_shared_inventory'],key=lambda x:x['name']),'shared inherited tool inventory differs'
            collector=_TurnCollector(max_output_bytes=200000);collector.thread_id=thread;transport.subscribe(collector.handle)
            stage='turn/start';record['turn_start_dispatched']=True;reply=await transport.request('turn/start',{'threadId':thread,'input':[{'type':'text','text':prompt}],'model':'gpt-6.1-sol','effort':'medium','outputSchema':review['output_schema']});turn=reply['turn']['id'];collector.turn_id=turn;result=await collector.future
            record.update(turn_status=result.status,actual_model=result.actual_model,tool_count=result.tool_count)

            stage='independent_grade';grade=runpy.run_path(str(ROOT/'integrations/assessment-runtime/workbook_grader.py'))['grade'];checks=[]
            for i,case in enumerate(ordered):
                output=scratch/f'output-{i}.xlsx'
                record['checks']=checks
                check={'index':i,'independent_grader_valid':False};checks.append(check)
                try:
                    assert not output.is_symlink() and output.is_file() and output.stat().st_size<=200000,'bounded output artifact missing'
                    value={'workbook_b64':base64.b64encode(output.read_bytes()).decode()};check.update(independent_grader_valid=bool(grade({'input':case['input'],'output':value,'expected':case['expected']})),artifact_bytes=output.stat().st_size,artifact_sha256=sha(output))
                except Exception as error:check['grader_error_type']=type(error).__name__
            record['checks']=checks;record['independent_quality_floor_passed']=all(x['independent_grader_valid'] for x in checks)
            record['unexpected_mcp_observed']=any(item['type']=='mcpToolCall' for item in tool_events)
            record['quality_floor_passed']=record['independent_quality_floor_passed'] and result.status=='completed' and result.actual_model in (None,'gpt-6.1-sol') and not record['unexpected_mcp_observed']
            assert result.actual_model in (None,'gpt-6.1-sol'), 'model substituted'
            assert result.status=='completed','turn not completed'
            assert not record['unexpected_mcp_observed'], 'unexpected MCP observed; post-execution policy rejection only'
    except BaseException as exc:
        import traceback
        record.update(error_type=type(exc).__name__,failed_stage=stage,safe_stack=[{'module':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)[-6:]])
        if transport and thread and turn:
            try:await transport.request('turn/interrupt',{'threadId':thread,'turnId':turn},timeout=5)
            except BaseException:pass
    finally:
        if transport:
            try:await asyncio.wait_for(transport.close(),5);record['host_cleanup_confirmed']=not transport.running
            except BaseException as exc:record['cleanup_error_type']=type(exc).__name__
        survivors=[]
        for (pid,created) in owned:
            try:
                p=psutil.Process(pid)
                if p.create_time()==created and p.status()!=psutil.STATUS_ZOMBIE:survivors.append(p);p.kill()
            except psutil.Error:pass
        record['owned_survivors_cleaned']=[p.pid for p in survivors];record['cleanup_confirmed']=record.get('host_cleanup_confirmed',False) and not survivors
        stop=True;await sampler
        elapsed=time.perf_counter()-began;usage=collector.token_usage if collector else None;accounting=None
        if usage:_,accounting=turn_accounting(usage,model=collector.actual_model or 'gpt-6.1-sol',resource_pool='native-codex-subscription')
        repo.finish_operation(operation,elapsed_seconds=elapsed,accounting=accounting)
        record.update(elapsed_seconds=elapsed,process_samples=samples,assessment_controller_samples=controller,owned_process_observations=list(owned.values()),event_counts=events,tool_events=tool_events,token_usage=usage,source_unchanged=verification_source_digest(ROOT)==SOURCE,retained_scratch_bytes=sum(p.stat().st_size for p in directory.rglob('*') if p.is_file() and not p.is_symlink()),grant_after=list(router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(request.authorization_id,)).fetchone()),release_ready=False,replay_allowed=False)
        await router.close();shutil.rmtree(directory);record['owned_scratch_removed']=True;result_path.write_text(json.dumps(record,indent=2)+'\n')
if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='--execute-reviewed':raise SystemExit('INERT: exact review required')
    asyncio.run(main(sys.argv[2]))
