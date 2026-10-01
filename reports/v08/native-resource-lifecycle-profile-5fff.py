"""Inert current-backend zero-model lifecycle profiling, existing primitives only."""
import asyncio,base64,hashlib,json,os,runpy,shutil,sys,tempfile,time
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
import psutil
from aeep.assessment.models import AssessmentLimits,AssessmentPlanningRequest,content_digest
from aeep.assessment.onboarding import reference_spec
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.executors.command import _monitor_process
from aeep.hosts.codex_app_server import CodexAppServerTransport,AppServerOptions
from aeep.hosts.codex_sandbox import NativeSandboxConfig,native_backend_digest
from aeep.mcp.server import AEEPToolService
from aeep.models import ActionConstraints,ActionRequest,ExecutorKind,Manifest,PolicyConfig,SideEffect,StrictModel,TaskScope,utc_now,ValidationKind,ValidationSpec
from aeep.router import Router
from aeep.tasks import activate,change_state,inspect,TaskReconciliation,reconcile
ROOT=Path(__file__).resolve().parents[2];REPORTS=ROOT/'reports/v08';SOURCE='5fffda8a321005abc175e63f887f118b2297097542a5c1332560cb60f409f9bc'
PYTHON=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3').resolve()
BINARY=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
class Definition(StrictModel):facts:dict

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def disk(path):
    path=Path(path);files=[p for p in path.rglob('*') if p.is_file() and not p.is_symlink()] if path.exists() else []
    return {'logical_bytes':sum(p.stat().st_size for p in files),'allocated_bytes':sum(p.stat().st_blocks*512 for p in files),'files':len(files)}
def controller():
    p=psutil.Process(os.getpid());t=p.cpu_times();return {'cpu_seconds':t.user+t.system,'rss_bytes':p.memory_info().rss}

async def child(payload):
    root=Path(payload['root']);scratch=root/'scratch';scratch.mkdir();phase=payload['phase'];r={'phase':phase,'model_turns':0,'phases':[],'cleanup_confirmed':False,'owned_root':str(root)};owner=None;restarted=None;transport=None;monitor=None;stop=None;idle_stop=None;idle_monitor=None;activation=None;observed=set();started=time.perf_counter()
    def checkpoint(name):r['phases'].append({'phase':name,'elapsed_seconds':time.perf_counter()-started,'controller':controller(),'project_storage':disk(root/'.aeep'),'config_storage':disk(root/'.codex')})
    try:
        async with asyncio.timeout(60):
            checkpoint('cold_child_after_imports')
            boundary=NativeSandboxConfig(binary=str(BINARY),binary_sha256='sha256:'+payload['binary_sha256'],project_root=str(root),read_roots=[str(PYTHON.parents[1]),str(ROOT/'AGENTS.md')],write_roots=[str(scratch)],single_process=True,python_binary=str(PYTHON),python_sha256='sha256:'+payload['python_sha256'])
            r['backend_digest']=native_backend_digest(boundary)
            setup_start=time.perf_counter();setup_controller=controller();manifest=root/'aeep.json'
            if phase=='failure_recovery':
                effect=scratch/'effect';program='from pathlib import Path;import sys;Path(sys.argv[1]).write_bytes(b"synthetic-resource-effect");raise SystemExit(3)'
                spec=reference_spec('csv').model_copy(update={'kind':ExecutorKind.COMMAND,'side_effect':SideEffect.WRITE,'idempotent':False,'config':{'argv':[str(PYTHON),'-I','-c',program,str(effect)],'argv_literal':True,'stdin_json':True,'native_sandbox':boundary.model_dump(mode='json'),'env':{'TMPDIR':str(scratch)},'timeout_seconds':1}})
                policies={'write':PolicyConfig(name='write',constraints=ActionConstraints(max_side_effect=SideEffect.WRITE))};ceiling=SideEffect.WRITE
            else:
                from aeep.assessment.workbook import workbook_recipe
                from aeep.assessment.workbook_native import implementation_digest
                recipe=workbook_recipe();spec=recipe.extension.reference.model_copy(deep=True);source=(ROOT/'integrations/assessment-runtime/workbook_program.py').read_text();program="import json,sys;ns={'__name__':'reference'};exec("+repr(source)+",ns);print(json.dumps(ns['reference'](json.load(sys.stdin))))"
                spec.id='native.lifecycle.workbook';spec.input_schema=recipe.input_schema;spec.output_schema=recipe.output_schema;spec.config={**spec.config,'argv':[str(PYTHON),'-I','-c',program],'native_sandbox':boundary.model_dump(mode='json'),'env':{'TMPDIR':str(scratch)},'max_output_bytes':200000,'timeout_seconds':5};spec.validators=[ValidationSpec(kind=ValidationKind.CALLBACK,config={'name':'aeep.workbook.native.v1','implementation_digest':implementation_digest()})];policies={};ceiling=SideEffect.READ
            manifest.write_text(Manifest(database=str(root/'.aeep/state.db'),executors=[spec],policies=policies).model_dump_json());owner=Router.from_manifest(manifest);repo=AssessmentRepository(owner.store)
            if phase!='failure_recovery':repo.review(repo.put('recipe',recipe.recipe_id,recipe))
            scope=TaskScope(scope_id='current-resource-'+phase,project_root=str(root),executor_fingerprints={spec.id:executor_fingerprint(spec)},approval_ceiling=ceiling,max_attempts=1,max_attempt_seconds=5,expires_at=utc_now()+timedelta(minutes=5));digest=repo.put('task_scope',scope.scope_id,scope);repo.review(digest)
            r.update(scope_digest=digest,executor_fingerprint=executor_fingerprint(spec));checkpoint('reviewed_before_activation')
            if phase=='failure_recovery':owner.bind_task_scope(scope.scope_id)
            else:
                activation=activate(owner,scope.scope_id);service=AEEPToolService(owner,profile='task',task_activation=activation.activation_id);r['schema_bytes']=len(json.dumps(service.list_tools()).encode())
            r.update(setup_seconds=time.perf_counter()-setup_start,setup_controller_before=setup_controller,setup_controller_after=controller());checkpoint('activated_or_bound')
            if phase=='idle_host':
                host_started=time.perf_counter();transport=CodexAppServerTransport((str(BINARY),'app-server','-c','features.apps=false','-c','features.code_mode=true',*boundary.permission_overrides()),environment_allowlist=('HOME','CODEX_HOME','PATH'),cwd=str(root),executable_sha256=boundary.binary_sha256,request_timeout=10,options=AppServerOptions(experimental_api=True));await transport.start();stop=asyncio.Event();monitor=asyncio.create_task(_monitor_process(transport._process.pid,stop,observed=observed))
                thread=await transport.request('thread/start',{'ephemeral':True,'cwd':str(root),'model':'gpt-6.1-sol','permissions':'aeep-native-task','approvalPolicy':'never','approvalsReviewer':'user'});r['native_permission_ack']=thread.get('activePermissionProfile',{}).get('id');assert r['native_permission_ack']=='aeep-native-task'
                inventory_deadline=time.perf_counter()+10
                while True:
                    inventory=await transport.request('mcpServerStatus/list',{'threadId':thread['thread']['id'],'limit':100,'detail':'toolsAndAuthOnly'});r['inventory']=[{'name':x['name'],'tools':sorted(x.get('tools',{}))} for x in inventory.get('data',[])]
                    own=[x for x in inventory.get('data',[]) if x['name']=='aeep_'+activation.activation_id]
                    r['own_server_tool_error_present']=any(x.get('toolsError') is not None for x in own)
                    if r['own_server_tool_error_present']:raise RuntimeError('owned_server_startup_error')
                    if any(x['name']=='aeep_'+activation.activation_id and x['tools']==[service.list_tools()[0]['name']] for x in r['inventory']):break
                    if time.perf_counter()>=inventory_deadline:raise TimeoutError('owned_server_not_ready')
                    await asyncio.sleep(.1)
                r['host_ready_seconds']=time.perf_counter()-host_started;checkpoint('native_host_and_own_mcp_ready');idle_started=time.perf_counter();idle_cpu_before={}
                for p in tuple(observed):
                    try:
                        if p.is_running():idle_cpu_before[(p.pid,p.create_time())]=p.cpu_times().user+p.cpu_times().system
                    except psutil.Error:pass
                idle_stop=asyncio.Event();idle_monitor=asyncio.create_task(_monitor_process(transport._process.pid,idle_stop,observed=observed));await asyncio.sleep(3);idle_stop.set();r['idle_native_tree_metrics']=asdict(await idle_monitor);r['idle_seconds']=time.perf_counter()-idle_started;r['idle_cpu_semantics']='Existing monitor max concurrent cumulative CPU retained separately; identity-matched sampled delta below excludes unavailable/reused/missed identities.';idle_delta=0;matched=0
                for p in tuple(observed):
                    try:
                        identity=(p.pid,p.create_time())
                        if identity in idle_cpu_before and p.is_running():idle_delta+=max(0,p.cpu_times().user+p.cpu_times().system-idle_cpu_before[identity]);matched+=1
                    except psutil.Error:pass
                r['idle_identity_matched_cpu_delta_seconds']=idle_delta;r['idle_cpu_identity_count']=matched;r['idle_missed_identity_cost_unknown']=True;checkpoint('idle_3_seconds_complete')
            elif phase=='cold_command':
                fixture=json.loads((ROOT/'integrations/assessment-runtime/workbook-grader-fixtures.json').read_text())[0];began=time.perf_counter();out=(await service.call(service.list_tools()[0]['name'],fixture['input']))['structuredContent'];r['cold_dispatch_seconds']=time.perf_counter()-began;r['required_success']=out['ok'];r['receipt']=out['receipts'][0];r['receipt']={k:r['receipt'].get(k) for k in ['receipt_id','task_valid','recorded_resources']};r['independent_grader_valid']=bool(runpy.run_path(str(ROOT/'integrations/assessment-runtime/workbook_grader.py'))['grade']({'input':fixture['input'],'output':out['output'],'expected':fixture['expected']}));assert r['required_success'] and r['independent_grader_valid'];checkpoint('cold_task_verified')
            else:
                began=time.perf_counter();out=await owner.execute(ActionRequest(capability=spec.capability,policy='write',input={'text':'a\n1','delimiter':','},constraints=ActionConstraints(max_side_effect=SideEffect.WRITE)),approved_side_effect=SideEffect.WRITE);attempt=owner.store.execution_attempt_for_decision(out.decision.decision_id);state=owner.task_outcome(out,approved_side_effect=SideEffect.WRITE);assert not out.ok and attempt.state.value=='INDETERMINATE' and state.recovery_state=='required' and effect.read_bytes()==b'synthetic-resource-effect';r.update(failed_dispatch_seconds=time.perf_counter()-began,failed_receipt_id=out.receipts[0].receipt_id,failed_effect_sha256=sha(effect),attempt_id=attempt.attempt_id);checkpoint('failed_write_unresolved');await owner.close();owner=None;checkpoint('closed_unresolved');shutil.copytree(root/'.aeep',root/'closed-before-recovery');began=time.perf_counter();restarted=Router.from_manifest(manifest);repo=AssessmentRepository(restarted.store);current=restarted.store.get_execution_attempt(attempt.attempt_id);assert current.state.value=='INDETERMINATE';effect.unlink();reconciliation=TaskReconciliation(attempt_id=current.attempt_id,attempt_version=current.version,scope_digest=digest,resolution='effects_reverted',evidence_digests=[digest]);reviewed=repo.put('task_reconciliation',content_digest(reconciliation),reconciliation);repo.review(reviewed);resolved=reconcile(restarted,reviewed);r.update(reconciliation=resolved,recovery_seconds=time.perf_counter()-began);assert resolved['state']=='FAILED' and resolved['allowance_reset'] is False and restarted.store.get_receipt(r['failed_receipt_id']) is not None;checkpoint('reconciled_after_restart')
            r['measurement_completed']=True
    except BaseException as error:
        import traceback
        r['error_type']=type(error).__name__;r['measurement_completed']=False;r['safe_stack']=[{'module':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(error.__traceback__)[-5:]]
        if hasattr(error,'error') and isinstance(error.error,dict):r['native_error_code']=error.error.get('code') if isinstance(error.error.get('code'),int) else None
    finally:
        errors=[]
        if transport:
            try:await asyncio.wait_for(transport.close(),5)
            except BaseException as error:errors.append({'stage':'host_close','error_type':type(error).__name__})
        if idle_stop:idle_stop.set()
        if idle_monitor:
            try:r['idle_native_tree_metrics']=asdict(await asyncio.wait_for(idle_monitor,1))
            except BaseException as error:errors.append({'stage':'idle_monitor','error_type':type(error).__name__})
        if stop:stop.set()
        if monitor:
            try:r['native_tree_whole_host_metrics']=asdict(await monitor)
            except BaseException as error:errors.append({'stage':'monitor','error_type':type(error).__name__})
        grace=time.perf_counter()+2
        while time.perf_counter()<grace:
            active=[]
            for p in observed:
                try:
                    if p.is_running() and p.status()!=psutil.STATUS_ZOMBIE:active.append(p)
                except psutil.Error:pass
            if not active:break
            await asyncio.sleep(.05)
        survivors=[]
        for p in observed:
            try:
                if p.is_running() and p.status()!=psutil.STATUS_ZOMBIE:survivors.append({'pid':p.pid,'creation_time':p.create_time()});p.kill()
            except psutil.Error:pass
        r['owned_survivors_cleaned']=survivors
        if owner and activation is not None and phase!='failure_recovery':
            try:r['uninstall']=change_state(owner,activation.activation_id,'uninstall');r['uninstall_overlay']=inspect(owner,activation.activation_id)['overlay']
            except BaseException as error:errors.append({'stage':'uninstall','error_type':type(error).__name__})
        for name,router in [('task',owner),('restarted',restarted)]:
            if router:
                try:await router.close()
                except BaseException as error:errors.append({'stage':name+'_close','error_type':type(error).__name__})
        r['cleanup_errors']=errors;r['cleanup_confirmed']=not errors and not survivors and (transport is None or not transport.running);r['elapsed_seconds']=time.perf_counter()-started;checkpoint('closed_final');r['source_unchanged']=verification_source_digest(ROOT)==SOURCE;r['network_provider_shared_cache_unknown']=True;print(json.dumps(r))

async def main(review_hash):
    path=REPORTS/'native-resource-lifecycle-profile-5fff-review.json';assert sha(path)==review_hash;review=json.loads(path.read_text());assert review['execution_authorized'] and sha(__file__)==review['driver_sha256'] and verification_source_digest(ROOT)==SOURCE
    assert sha(BINARY)==review['binary_sha256'] and sha(PYTHON)==review['python_sha256']
    assert str(Path(sys.executable).resolve())==review['assessment_python'] and sha(Path(sys.executable).resolve())==review['assessment_python_sha256']
    for name,digest in review['dependencies'].items():assert sha(ROOT/name)==digest
    runpy.run_path(str(REPORTS/'native-only-validation-prerequisite-5fff.py'))['validate'](ROOT,review,SOURCE)
    result_path=REPORTS/'native-resource-lifecycle-profile-5fff-result.json';assert not result_path.exists();evidence=ROOT/'.aeep/native-resource-lifecycle-profile-5fff-evidence';assert not evidence.exists();evidence.mkdir()
    router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');repo=AssessmentRepository(router.store);old=AssessmentPlanningRequest.model_validate(repo.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'));mapping=repo.put('native_resource_lifecycle_definition','current5fff',Definition(facts=review));repo.review(mapping);req=old.model_copy(update={'plan_id':'planning_native_resource_lifecycle_profile_5fff','mapping_digest':mapping,'definition_digests':[*old.definition_digests,mapping]});repo.review(repo.put('planning_request',req.plan_id,req));repo.authorize(req);record={'source_digest':SOURCE,'review_sha256':review_hash,'samples':[],'model_turns':0,'ambient_lab':'Docker API/timeouts and optional lab cleanup unknown; no quietness claim','release_ready':False};record['grant_before']=list(router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(req.authorization_id,)).fetchone())
    try:
        for phase in ('idle_host','cold_command','failure_recovery'):
            operation='native-profile:'+req.plan_id+':'+phase;repo.authorize(req);repo.reserve(req,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=80),stage=phase)
            began=time.perf_counter();deadline=began+80;root=None;sample={'phase':phase,'operation_id':operation,'cleanup_confirmed':False,'accounting_finished':False};process=None;stop=asyncio.Event();monitor=None;observed=set();errors=[]
            try:
                root=Path(tempfile.mkdtemp(prefix='aeep-owned-current-profile-',dir=ROOT)).resolve();sample['owned_root']=str(root)
                assert sha(__file__)==review['driver_sha256']
                process=await asyncio.create_subprocess_exec(sys.executable,__file__,'--child',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE);monitor=asyncio.create_task(_monitor_process(process.pid,stop,observed=observed))
                stdout,stderr=await asyncio.wait_for(process.communicate(json.dumps({'phase':phase,'root':str(root),'binary_sha256':review['binary_sha256'],'python_sha256':review['python_sha256']}).encode()),70)
                sample.update(exit_code=process.returncode,stderr_bytes=len(stderr),stderr_sha256=hashlib.sha256(stderr).hexdigest());assert len(stdout)<=1048576 and process.returncode==0;sample.update(json.loads(stdout))
            except BaseException as error:errors.append({'stage':'measurement','error_type':type(error).__name__})
            finally:
                if process and process.returncode is None:
                    try:process.kill();await asyncio.wait_for(process.wait(),max(.001,min(3,deadline-time.perf_counter())))
                    except BaseException as error:errors.append({'stage':'child_cleanup','error_type':type(error).__name__})
                survivors=[]
                for owned in observed:
                    try:
                        if owned.is_running() and owned.status()!=psutil.STATUS_ZOMBIE:
                            survivors.append({'pid':owned.pid,'creation_time':owned.create_time()});owned.kill()
                    except psutil.NoSuchProcess:pass
                    except psutil.Error as error:errors.append({'stage':'owned_identity_cleanup','error_type':type(error).__name__})
                sample['parent_owned_survivors_cleaned']=survivors
                active=[];grace=min(deadline,time.perf_counter()+2)
                while time.perf_counter()<grace:
                    active=[]
                    for owned in observed:
                        try:
                            if owned.is_running() and owned.status()!=psutil.STATUS_ZOMBIE:active.append(owned.pid)
                        except psutil.Error:pass
                    if not active:break
                    await asyncio.sleep(.05)
                sample['parent_owned_survivors_remaining']=active if observed else []
                if survivors:errors.append({'stage':'child_left_owned_processes','error_type':'IncompleteCleanup'})
                stop.set()
                if monitor:
                    try:sample['assessment_child_plus_owned_tree_metrics']=asdict(await asyncio.wait_for(monitor,max(.001,min(1,deadline-time.perf_counter()))))
                    except BaseException as error:errors.append({'stage':'parent_monitor','error_type':type(error).__name__})
                record['samples'].append(sample);sample['partial_finalization_errors']=errors;result_path.write_text(json.dumps(record,indent=2)+'\n')
                try:
                    if root:
                        for source,label in [(root/'.aeep','after'),(root/'closed-before-recovery','before')]:
                            if source.exists():
                                if deadline-time.perf_counter()<3:raise TimeoutError('store_copy_cleanup_headroom_unavailable')
                                assert disk(source)['logical_bytes']<=16777216,'bounded owned evidence copy exceeded'
                                shutil.copytree(source,evidence/(phase+'-'+label))
                        sample['retained_evidence_storage']=disk(evidence)
                except BaseException as error:errors.append({'stage':'store_retention','error_type':type(error).__name__})
                sample['elapsed_inclusive_seconds']=time.perf_counter()-began
                try:repo.finish_operation(operation,elapsed_seconds=sample['elapsed_inclusive_seconds']);sample['accounting_finished']=True
                except BaseException as error:errors.append({'stage':'accounting_finish','error_type':type(error).__name__})
                if time.perf_counter()>deadline:errors.append({'stage':'operation_80s_bound','error_type':'DeadlineExceeded'})
                sample['partial_finalization_errors']=errors;sample['measurement_completed']=bool(sample.get('measurement_completed')) and not errors
                sample['cleanup_confirmed']=bool(sample.get('cleanup_confirmed')) and not errors and not sample['parent_owned_survivors_remaining']
                result_path.write_text(json.dumps(record,indent=2)+'\n')
                if root and sample['cleanup_confirmed'] and sample['measurement_completed']:
                    try:
                        if deadline-time.perf_counter()<1:raise TimeoutError('owned_delete_cleanup_headroom_unavailable')
                        shutil.rmtree(root);sample['owned_transient_removed']=True
                    except BaseException as error:errors.append({'stage':'owned_storage_cleanup','error_type':type(error).__name__});sample['cleanup_confirmed']=False;sample['owned_transient_removed']=False
                else:sample['owned_transient_removed']=False
                result_path.write_text(json.dumps(record,indent=2)+'\n')
            if not sample.get('measurement_completed') or not sample.get('cleanup_confirmed'):break
    finally:
        record['source_unchanged']=verification_source_digest(ROOT)==SOURCE
        try:record['dependency_hashes_unchanged']=sha(BINARY)==review['binary_sha256'] and sha(PYTHON)==review['python_sha256'] and sha(__file__)==review['driver_sha256'] and all(sha(ROOT/name)==digest for name,digest in review['dependencies'].items())
        except BaseException as error:record['dependency_hashes_unchanged']=False;record['dependency_check_error_type']=type(error).__name__
        try:record['grant_after']=list(router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(req.authorization_id,)).fetchone())
        except BaseException as error:record['grant_read_error_type']=type(error).__name__
        result_path.write_text(json.dumps(record,indent=2)+'\n')
        try:await router.close();record['main_close_succeeded']=True
        except BaseException as error:record['main_close_succeeded']=False;record['main_close_error_type']=type(error).__name__
        record['completed']=len(record['samples'])==3 and record['source_unchanged'] and record['dependency_hashes_unchanged'] and record['main_close_succeeded'] and all(x.get('measurement_completed') and x.get('cleanup_confirmed') and x.get('accounting_finished') for x in record['samples']);result_path.write_text(json.dumps(record,indent=2)+'\n')
if __name__=='__main__':
    if sys.argv[1:]==['--child']:asyncio.run(child(json.load(sys.stdin)))
    elif len(sys.argv)==3 and sys.argv[1]=='--execute-reviewed':asyncio.run(main(sys.argv[2]))
    else:raise SystemExit('INERT: exact review required')
