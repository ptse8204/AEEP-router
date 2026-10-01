"""Inert ordinary-tool baseline calibration; no value or release decision."""
import asyncio, base64, hashlib, json, os, runpy, shutil, sys, tempfile, time
from pathlib import Path
import psutil
from contextlib import contextmanager
from aeep.assessment.models import AssessmentLimits, AssessmentPlanningRequest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexAppServerTransport, AppServerOptions, _TurnCollector
from aeep.hosts.codex_accounting import turn_accounting, rate_limit_observation
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import StrictModel
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[2]; REPORTS=ROOT/'reports/v08'
SOURCE='5fffda8a321005abc175e63f887f118b2297097542a5c1332560cb60f409f9bc'
BINARY=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
PYTHON=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3').resolve()
class Definition(StrictModel):
    facts: dict

def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()

@contextmanager
def scoped_process_environment(configured):
    # Only this owned report process changes; exact prior values are restored.
    previous = {key: os.environ.get(key) for key in configured}
    try:
        os.environ.update(configured)
        yield
    finally:
        for key, value in previous.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value


def tempfile_preflight_program(scratch):
    return ('import json,os,tempfile; from pathlib import Path; '
            'expected=Path(' + repr(str(scratch)) + '); '
            'root=Path(tempfile.gettempdir()); '
            'f=tempfile.NamedTemporaryFile(prefix="aeep-native-preflight-",delete=False); '
            'path=Path(f.name); f.write(b"owned-synthetic-temp-v1"); f.close(); '
            'valid=path.read_bytes()==b"owned-synthetic-temp-v1"; path.unlink(); '
            'print(json.dumps({"root_matches":root==expected,"env_matches":os.environ.get("TMPDIR")==str(expected),'
            '"create_write_read_delete":valid and not path.exists()}))')



def owned_bytes(path):
    path=Path(path);files=[path] if path.is_file() and not path.is_symlink() else [p for p in path.rglob('*') if p.is_file() and not p.is_symlink()] if path.is_dir() else []
    return {'logical_bytes':sum(p.stat().st_size for p in files),'allocated_bytes':sum(p.stat().st_blocks*512 for p in files),'file_count':len(files)}

def safe_final(value):
    return {key:item for key,item in value.items() if (key=='successes' and isinstance(item,list) and len(item)==2 and all(type(x)is bool for x in item)) or (key=='stopped_after_rejection' and type(item)is bool) or (key=='reason' and item in ('completed','unavailable','denied','failed'))} if isinstance(value,dict) else {'output_kind':type(value).__name__}

async def main(review_hash):
    review_path=REPORTS/'native-model-resource-baseline-evaluation-5fff-review.json'
    assert sha(review_path)==review_hash
    review=json.loads(review_path.read_text()); assert review['execution_authorized'] is True
    assert sha(__file__)==review['driver_sha256'] and verification_source_digest(ROOT)==SOURCE
    assert sha(BINARY)==review['binary_sha256'] and sha(PYTHON)==review['python_sha256']
    for name,digest in review['dependencies'].items(): assert sha(ROOT/name)==digest
    native_prerequisite=runpy.run_path(str(REPORTS/'native-only-validation-prerequisite-5fff.py'))['validate'](ROOT,review,SOURCE)
    shell_support=json.loads((REPORTS/'native-baseline-shell-preflight-ade3-result.json').read_text());assert shell_support['source_digest']==SOURCE and shell_support['cleanup_confirmed'] and shell_support['source_unchanged'] and shell_support['probes'][-1]['supported']
    result_path=REPORTS/'native-model-resource-baseline-evaluation-5fff-result.json'; assert not result_path.exists()
    router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json'); repo=AssessmentRepository(router.store)
    old=AssessmentPlanningRequest.model_validate(repo.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
    definition=Definition(facts=review); mapping=repo.put('native_resource_calibration','ordinary-model-baseline-evaluation-5fff',definition);repo.review(mapping)
    request=old.model_copy(update={'plan_id':'planning_native_resource_baseline_evaluation_5fff','mapping_digest':mapping,'definition_digests':[*old.definition_digests,mapping]})
    repo.review(repo.put('planning_request',request.plan_id,request));repo.authorize(request)
    before=list(router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(request.authorization_id,)).fetchone())
    setup='native-resource-setup:'+request.plan_id; repo.reserve(request,setup,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=40),stage='fixture_setup')
    started=time.perf_counter();directory=None;scratch=None;fixture_path=ROOT/'.aeep/native-model-resource-evaluation-5fff/fixtures.json';setup_errors=[]
    setup_ok=False
    try:
        async with asyncio.timeout(35):
            directory=Path(tempfile.mkdtemp(prefix='aeep-owned-model-baseline-',dir=ROOT)).resolve();scratch=directory/'scratch';scratch.mkdir()
            fixture_helper=runpy.run_path(str(REPORTS/'native-model-resource-fresh-cases-5fff.py'))
            ordered,fixture_record=await fixture_helper['create_or_load'](router.store,PYTHON,ROOT/'.aeep/native-model-resource-evaluation-5fff/fixtures.json',review['resource_definition_sha256'],True)
            inputs=[case['input'] for case in ordered]; staged=scratch/'input.json';staged.write_text(json.dumps(inputs,sort_keys=True)); assert [hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest() for x in inputs] == fixture_record['input_hashes'], 'fresh fixture binding drift'
            boundary=NativeSandboxConfig(binary=str(BINARY),binary_sha256='sha256:'+sha(BINARY),project_root=str(directory),read_roots=[str(PYTHON.parents[1]),str(ROOT/'AGENTS.md')],write_roots=[str(scratch)],single_process=True,python_binary=str(PYTHON),python_sha256='sha256:'+sha(PYTHON))
            scoped_environment=boundary.validate_environment({'TMPDIR':str(scratch),'TMP':str(scratch),'TEMP':str(scratch)})
            # The evaluated host sees only task inputs. No reference program, oracle or grader is staged.
            prompt=review['prompt_template'].replace('{input_path}',str(staged)).replace('{scratch}',str(scratch)).replace('{python}',str(PYTHON))
            fixture_sha256=sha(fixture_path)
            fixture_binding=repo.put('native_resource_fixture_binding',request.plan_id,Definition(facts={'fixture_document_sha256':fixture_sha256,'resource_definition_sha256':review['resource_definition_sha256'],'input_hashes':fixture_record['input_hashes']}));repo.review(fixture_binding)
            await asyncio.sleep(0)
            setup_ok=True
    except BaseException as error:setup_errors.append({'stage':'setup','error_type':type(error).__name__})
    finally:
        setup_elapsed=time.perf_counter()-started
        try:repo.finish_operation(setup,elapsed_seconds=setup_elapsed)
        except BaseException as error:setup_errors.append({'stage':'finish_setup','error_type':type(error).__name__})
    if setup_elapsed>40:setup_errors.append({'stage':'setup_elapsed_exceeded_40s','error_type':'DeadlineExceeded'})
    if not setup_ok or setup_errors:
        failure={'source_digest':SOURCE,'setup_operation':setup,'grant_before':before,'setup_elapsed_seconds':setup_elapsed,'setup_errors':setup_errors,'model_turn_dispatched':False,'cleanup_confirmed':False,'owned_directory_retained':str(directory) if directory else None,'fixture_record_retained':fixture_path.exists(),'release_ready':False,'replay_allowed':False}
        result_path.write_text(json.dumps(failure,indent=2)+'\n')
        try:await router.close()
        except BaseException as error:failure['close_error_type']=type(error).__name__;result_path.write_text(json.dumps(failure,indent=2)+'\n')
        return
    operation='native-resource-model:'+request.plan_id;repo.authorize(request);repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=1,max_elapsed_seconds=240),stage='model_resource_calibration')
    record={'source_digest':SOURCE,'operation_id':operation,'setup_operation':setup,'setup_elapsed_seconds':setup_elapsed,'fixture_document_sha256':fixture_sha256,'fixture_binding_digest':fixture_binding,'activation_config_before':owned_bytes(directory/'.codex/config.toml'),'activation_config_after':owned_bytes(directory/'.codex/config.toml'),'project_config_mutations':0,'task_schema_bytes':0,'grant_before':before,'input_hashes':[hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest() for x in inputs],'classification':review['classification'],'turn_start_dispatched':False,'telemetry_unknowns':review['telemetry_unknowns'],'ambient_assessment_activity':'Docker API reads timed out; failed test-container cleanup/VM activity unknown. Owned native-tree measurement only; ambient/system-attribution acceptance inconclusive.','resource_definition_sha256':review['resource_definition_sha256'],'fixture_disjointness':{k:v for k,v in fixture_record.items() if k not in ('selected_cases',)}}
    (REPORTS/'native-model-resource-baseline-evaluation-5fff-running.json').write_text(json.dumps(record,indent=2)+'\n')
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
            entry['exit_code']=item.get('exitCode') if type(item.get('exitCode')) is int else None
            text=item.get('aggregatedOutput') if isinstance(item.get('aggregatedOutput'),str) else ''
            entry['known_error_categories']=[label for marker,label in [('permission denied','permission_denied'),('operation not permitted','permission_denied'),('no usable temporary directory','temporary_directory_unavailable'),('no module named','module_missing'),('no such file','missing_path')] if marker in text.lower()]
            command=item.get('command');entry['command_sha256']=hashlib.sha256(command.encode()).hexdigest() if isinstance(command,str) else None
            tool_events.append(entry)
            if len(tool_events)>500: raise RuntimeError('bounded tool-event limit exceeded')
    try:
        async with asyncio.timeout(225):
            argv=(str(BINARY),'app-server','-c','features.apps=false','-c','features.code_mode=true',*boundary.permission_overrides())
            transport=CodexAppServerTransport(argv,environment_allowlist=('HOME','CODEX_HOME','PATH','TMPDIR','TMP','TEMP'),cwd=str(directory),executable_sha256=boundary.binary_sha256,request_timeout=20,options=AppServerOptions(experimental_api=True));transport.subscribe(observe)
            with scoped_process_environment(scoped_environment): await transport.start()
            stage='tempfile_preflight';temp_started=time.perf_counter()
            temp=await transport.request('command/exec',{'command':[str(PYTHON),'-I','-c',tempfile_preflight_program(scratch)],'cwd':str(scratch),'permissionProfile':'aeep-native-task','timeoutMs':5000,'outputBytesCap':4096})
            record['tempfile_preflight_seconds']=time.perf_counter()-temp_started
            record['tempfile_preflight_exit_code']=temp.get('exitCode')
            stderr=temp.get('stderr','');stdout=temp.get('stdout','')
            assert isinstance(stderr,str) and isinstance(stdout,str), 'tempfile preflight response shape'
            record['tempfile_preflight_streams']={'stdout_bytes':len(stdout.encode()),'stderr_bytes':len(stderr.encode()),'known_error_categories':[label for marker,label in [('permission denied','permission_denied'),('operation not permitted','permission_denied'),('no usable temporary directory','temporary_directory_unavailable')] if marker in stderr.lower()]}
            assert temp.get('exitCode')==0 and stderr=='' and len(stdout.encode())<4096, 'tempfile preflight failed'
            observed=json.loads(temp.get('stdout','')); assert observed=={'root_matches':True,'env_matches':True,'create_write_read_delete':True}, 'native scratch environment propagation unavailable'
            record['tempfile_preflight']=observed
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
            final=result.output
            record['sanitized_final']={key:value for key,value in final.items() if (key=='successes' and isinstance(value,list) and len(value)==2 and all(type(x)is bool for x in value)) or (key=='stopped_after_rejection' and type(value)is bool) or (key=='reason' and value in ('completed','unavailable','denied','failed'))} if isinstance(final,dict) else {'output_kind':type(final).__name__}

            assert result.actual_model in (None,'gpt-6.1-sol'), 'model substituted'
            assert result.status=='completed','turn not completed'
            assert not any(item['type']=='mcpToolCall' for item in tool_events), 'unexpected MCP observed; post-execution policy rejection only'
    except BaseException as exc:
        import traceback
        record.update(error_type=type(exc).__name__,failed_stage=stage,safe_stack=[{'module':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)[-6:]])
        if transport and thread and turn:
            try:await transport.request('turn/interrupt',{'threadId':thread,'turnId':turn},timeout=5)
            except BaseException:pass
    finally:
        finish_attempted=False
        try:
            if transport:
                try:await asyncio.wait_for(transport.close(),5);record['host_cleanup_confirmed']=not transport.running
                except BaseException as exc:record['cleanup_error_type']=type(exc).__name__
            record['production_host_lifespan_seconds']=time.perf_counter()-began
            grading_started=time.perf_counter()
            checks=[];record['checks']=checks
            try:
                grade=runpy.run_path(str(ROOT/'integrations/assessment-runtime/workbook_grader.py'))['grade']
                for i,case in enumerate(ordered):
                    output=scratch/f'output-{i}.xlsx';check={'index':i,'independent_grader_valid':False};checks.append(check)
                    try:
                        assert output.is_file() and not output.is_symlink() and output.stat().st_size<=200000,'bounded output missing'
                        check.update(independent_grader_valid=bool(grade({'input':case['input'],'output':{'workbook_b64':base64.b64encode(output.read_bytes()).decode()},'expected':case['expected']})),artifact_bytes=output.stat().st_size,artifact_sha256=sha(output))
                    except BaseException as error:check['grader_error_type']=type(error).__name__
            except BaseException as error:record['grader_setup_error_type']=type(error).__name__
            record['independent_grading_seconds']=time.perf_counter()-grading_started
            record['measurement_attribution']='Host samples may include short post-close zero/retained samples; production lifespan ends at close; independent grading is assessment controller work after host close. Canonical elapsed retains all overhead.'
            record['independent_quality_floor_passed']=len(checks)==2 and all(x['independent_grader_valid'] for x in checks)
            record['unexpected_mcp_observed']=any(item['type']=='mcpToolCall' for item in tool_events)
            record['quality_floor_passed']=record['independent_quality_floor_passed'] and record.get('turn_status')=='completed' and not record.get('error_type') and not record['unexpected_mcp_observed']
            survivors=[]
            for (pid,created) in owned:
                try:
                    p=psutil.Process(pid)
                    if p.create_time()==created and p.status()!=psutil.STATUS_ZOMBIE:survivors.append(p);p.kill()
                except psutil.Error:pass
            record['owned_survivors_cleaned']=[p.pid for p in survivors];record['cleanup_confirmed']=record.get('host_cleanup_confirmed',False) and not survivors
            stop=True
            try:await sampler
            except BaseException as error:record['sampler_error_type']=type(error).__name__
            elapsed=time.perf_counter()-began;usage=collector.token_usage if collector else None;accounting=None
            if usage:
                try:_,accounting=turn_accounting(usage,model=collector.actual_model or 'gpt-6.1-sol',resource_pool='native-codex-subscription')
                except BaseException as error:record['accounting_error_type']=type(error).__name__
            finish_attempted=True
            try:repo.finish_operation(operation,elapsed_seconds=elapsed,accounting=accounting)
            except BaseException as error:record['finish_operation_error_type']=type(error).__name__
            record.update(elapsed_seconds=elapsed,process_samples=samples,assessment_controller_samples=controller,owned_process_observations=list(owned.values()),event_counts=events,tool_events=tool_events,token_usage=usage,source_unchanged=verification_source_digest(ROOT)==SOURCE,retained_scratch_bytes=sum(p.stat().st_size for p in directory.rglob('*') if p.is_file() and not p.is_symlink()),grant_after=list(router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(request.authorization_id,)).fetchone()),release_ready=False,replay_allowed=False)
            record['transient_owned_storage']=owned_bytes(directory);record['production_retained_storage']={'logical_bytes':0,'allocated_bytes':0,'file_count':0};record['lab_fixture_storage']=owned_bytes(fixture_path);record['development_orchestration_cost']='Unknown lab overhead: development/review tokens and compute excluded from runtime ledger'
            result_path.write_text(json.dumps(record,indent=2)+'\n')
            try:await router.close()
            except BaseException as error:record['router_close_error_type']=type(error).__name__
            if record['cleanup_confirmed']:
                try:shutil.rmtree(directory);record['owned_scratch_removed']=True
                except BaseException as error:record['scratch_cleanup_error_type']=type(error).__name__;record['owned_scratch_removed']=False
            else:record['owned_scratch_removed']=False
            result_path.write_text(json.dumps(record,indent=2)+'\n')
        except BaseException as error:
            record['finalization_error_type']=type(error).__name__;record['cleanup_confirmed']=False;record['quality_floor_passed']=False;record['journey_passed']=False;record['owned_directory_retained']=str(directory)
            record['production_retained_storage']=None
        finally:
            stop=True
            if not finish_attempted:
                try:repo.finish_operation(operation,elapsed_seconds=time.perf_counter()-began)
                except BaseException as error:record['finish_operation_error_type']=type(error).__name__
            record['source_unchanged']=verification_source_digest(ROOT)==SOURCE
            record['development_orchestration_cost']='Unknown lab overhead: development/review tokens and compute excluded from runtime ledger'
            result_path.write_text(json.dumps(record,indent=2)+'\n')
            try:await router.close()
            except BaseException as error:record['fallback_close_error_type']=type(error).__name__;result_path.write_text(json.dumps(record,indent=2)+'\n')
if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='--execute-reviewed':raise SystemExit('INERT: exact review required')
    asyncio.run(main(sys.argv[2]))
