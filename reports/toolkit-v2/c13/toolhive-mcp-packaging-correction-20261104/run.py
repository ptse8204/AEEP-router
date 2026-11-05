"""One finite real ToolHive MCP lifecycle; no model, registry or provider setup."""
import argparse,asyncio,hashlib,json,os,shutil,socket,sys,time
from pathlib import Path
from datetime import UTC,datetime
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
SOURCE=Path(json.loads((HERE.parent/'workflow-telemetry-20261104/source-snapshot.json').read_bytes())['coordinator_source_snapshot']);sys.path.insert(0,str(SOURCE/'src'))
from aeep.assessment.models import AssessmentAuthorization,AssessmentBudgetAmendment,AssessmentLimits,RecipeMaterializationRequest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.execution import ExecutionEvidence,persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.executors.mcp import MCPExecutor
from aeep.models import ActionRequest,ExecutionReceipt,ExecutorSpec,ResourceVector,SideEffect,StrictModel,utc_now
from aeep.store import ReceiptStore
def load(p):return json.loads(Path(p).read_bytes())
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
def covered(start,end,intervals):
    total=0.;cursor=start
    for left,right in sorted(intervals):
        left=max(start,left);right=min(end,right)
        if right>max(cursor,left):total+=right-max(cursor,left)
        cursor=max(cursor,right)
    return total
class Scope(StrictModel):
    role:str
    plan_sha256:str
    source_revision:str
def validate(review):
    assert datetime.now(UTC)<datetime.fromisoformat(review['expires_at'].replace('Z','+00:00'))
    assert shutil.disk_usage(ROOT).free>=50*1024**3
    for p,h in review['assets'].items():assert sha(p)==h,p
    assert verification_source_digest(SOURCE)==review['source']
class Journey:
    def __init__(self,repo,request,review,identity):
        self.repo,self.request,self.review,self.identity=repo,request,review,identity
        self.work=Path(review['work']);self.serial=0;self.driver_nested=0.;self.server_nested=0.;self.server_active=False
        self.server=None;self.server_executor=None;self.server_clock=None;self.server_started=None;self.owned=None;self.image=None
        self.children=[];self.service_children=[];self.cleanup_start=None
    def docker(self,*args):return [self.review['docker'],'--config',self.review['docker_config'],'--host','unix://'+self.review['docker_socket'],*args]
    def native(self,*args):return ['/usr/bin/sandbox-exec','-f',str(HERE/'controller.sb'),*args]
    def spec(self,name,argv,seconds):
        return ExecutorSpec(id='toolhive.mcp.'+name,capability='toolkit.upstream-engineering@1',kind='command',side_effect='write',description='Exact reviewed ToolHive lifecycle or controlled local Docker operation',config={'argv':argv,'argv_literal':True,'inherit_env':False,'env':self.review['environment'],'cwd':str(self.work),'timeout_seconds':seconds,'max_output_bytes':1048576,'output':{'type':'text'}})
    def authorize(self):validate(self.review);self.repo.authorize(self.request);return self.identity
    def reserve(self,name,seconds):
        operation=self.request.plan_id+':'+name
        self.repo.reserve(self.request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=seconds),stage='toolhive_mcp_'+name)
        return operation
    def settle(self,name,operation,raw,error,started,elapsed,*,exclusive=None):
        evidence=None
        if raw is not None and raw.metadata.get('execution_evidence'):
            evidence=ExecutionEvidence.model_validate(raw.metadata['execution_evidence']);self.repo.put('execution_evidence',evidence.digest(),evidence)
        cost=elapsed if exclusive is None else exclusive
        receipt=ExecutionReceipt(decision_id=operation,action_id=operation,capability='toolkit.upstream-engineering@1',executor_id='toolhive.mcp.'+name,executor_kind='mcp' if name=='aeep-client' else 'command',
            status=raw.status if raw else 'failed',started_at=started,ended_at=utc_now(),estimated={},actual_resources=ResourceVector(latency_ms=cost*1000),execution_success=raw is not None and error is None and (raw.exit_code==0 or name=='aeep-client'),error_type=error or (raw.error_type if raw else None),metadata={'review_sha256':self.identity,'execution_evidence_ref':evidence.digest() if evidence else None,'observed_resource_dimensions':['latency_ms'],'legacy_vector_defaults_are_not_observations':True,'whole_interval_seconds':elapsed,'exclusive_charged_seconds':cost,'other_measurements':'UNKNOWN','actual_upstream_toolhive':True,'engineering_only':True})
        self.repo.store.save_receipt(receipt);self.repo.finish_operation(operation,elapsed_seconds=cost,resources=receipt.actual_resources);write(HERE/('receipt-'+name+'.json'),receipt.model_dump(mode='json'))
        return evidence
    async def command(self,name,argv,seconds=30,*,cleanup=False):
        if cleanup:seconds=min(seconds,15)
        self.authorize();self.serial+=1;assert self.serial<=self.review['maximum_commands']
        operation=self.request.plan_id+':'+name if cleanup else self.reserve(name,seconds+10)
        start=time.perf_counter();started=utc_now();raw=None;error=None;executor=CommandExecutor()
        try:
            spec=self.spec(name,argv,seconds)
            with persist_execution_events(lambda key,event:self.repo.put('execution_event',key+':'+str(event.sequence),event)):
                handle=await executor.start(ExecutionContext(request=ActionRequest(action_id=operation,capability=spec.capability),spec=spec,estimate=spec.estimate,attempt=1,attempt_id=operation,approved_side_effect=SideEffect.WRITE,invocation_check=self.authorize))
                raw=await handle.task
            assert raw.exit_code==0,(name,raw.error_type)
        except BaseException as failure:error=type(failure).__name__
        finally:
            await executor.close();elapsed=time.perf_counter()-start
            interval=(start,start+elapsed);self.children.append(interval)
            if self.server_active:self.service_children.append(interval)
            if self.server_active:self.server_nested+=elapsed
            else:self.driver_nested+=elapsed
            if not cleanup:self.settle(name,operation,raw,error,started,elapsed)
            else:write(HERE/('cleanup-'+name+'.json'),{'exit_code':raw.exit_code if raw else None,'error_type':error,'elapsed_seconds':elapsed})
            if error:write(HERE/('failure-'+name+'.json'),{'error_type':error,'exit_code':raw.exit_code if raw else None,'stderr':(raw.stderr or '')[:4096] if raw else None,'scope':'Reviewed public no-credential lifecycle commands only'})
        assert error is None and raw is not None,name
        return raw.stdout
    async def image_info(self,reference,name):
        return json.loads(await self.command(name,self.docker('image','inspect',reference)))[0]
    async def inspect_owned(self,name='container-inspect',*,cleanup=False):
        ids=(await self.command(name+'-discover',self.docker('ps','-aq','--filter','label='+self.review['owner_label']+'='+self.review['name']),cleanup=cleanup)).split()
        assert len(ids)<=1
        if not ids:return None
        value=json.loads(await self.command(name,self.docker('inspect',ids[0]),cleanup=cleanup))[0]
        assert value['Name']=='/'+self.review['name'] and value['Config']['Labels'][self.review['owner_label']]==self.review['name']
        assert value['Config']['Image'] in self.review['allowed_image_references'] and value['Image']==self.image
        if self.owned:assert value['Id']==self.owned
        self.owned=value['Id'];return value
    async def start_server(self):
        operation=self.reserve('foreground-service',200);self.server_clock=time.perf_counter();self.server_started=utc_now();self.server_operation=operation
        argv=self.native(self.review['toolhive'],*self.review['run_arguments'])
        self.server_executor=CommandExecutor();spec=self.spec('foreground-service',argv,180)
        with persist_execution_events(lambda key,event:self.repo.put('execution_event',key+':'+str(event.sequence),event)):
            self.server=await self.server_executor.start(ExecutionContext(request=ActionRequest(action_id=operation,capability=spec.capability),spec=spec,estimate=spec.estimate,attempt=1,attempt_id=operation,approved_side_effect=SideEffect.WRITE,invocation_check=self.authorize))
        self.server_active=True
        for _ in range(40):
            if self.server.task.done():
                raw=await self.server.task;write(HERE/'foreground-early-exit.json',{'exit_code':raw.exit_code,'stderr':(raw.stderr or '')[:4096],'stdout':(raw.stdout or '')[:4096]});raise RuntimeError('ToolHiveExitedBeforeReady')
            with socket.socket() as sock:
                sock.settimeout(.2)
                if sock.connect_ex(('127.0.0.1',self.review['port']))==0:return
            await asyncio.sleep(.5)
        raise RuntimeError('ToolHiveProxyNotReady')
    async def aeep_client(self):
        operation=self.reserve('aeep-client',30);started=utc_now();clock=time.perf_counter();raw=None;error=None;ex=MCPExecutor()
        try:
            schema=load(HERE/'plan.json')['format_schema']
            spec=ExecutorSpec(id='toolhive.mcp.aeep-client',capability='toolkit.upstream-engineering@1',kind='mcp',side_effect='read',description='Existing AEEP MCP HTTP executor through actual ToolHive proxy',input_schema=schema,config={'transport':'streamable-http','url':self.review['endpoint'],'tool':'format_json','allowed_hosts':['127.0.0.1'],'allow_private_networks':True,'trust_proxy_env':False,'parse_json_text':True,'timeout_seconds':10,'max_request_bytes':8192,'max_response_bytes':16384})
            with persist_execution_events(lambda key,event:self.repo.put('execution_event',key+':'+str(event.sequence),event)):
                handle=await ex.start(ExecutionContext(request=ActionRequest(action_id=operation,capability=spec.capability,input={'text':'{"z":2,"a":1}'}),spec=spec,estimate=spec.estimate,attempt=1,attempt_id=operation,approved_side_effect=SideEffect.READ,invocation_check=self.authorize));raw=await handle.task
            assert str(raw.status)=='success' and raw.output=={'formatted':'{\n  "a": 1,\n  "z": 2\n}'}
        except BaseException as failure:
            error=type(failure).__name__
            write(HERE/'failure-aeep-client.json',{'error_type':error,'message':str(failure)[:1024],'raw_status':str(raw.status) if raw else None,'raw_error_type':raw.error_type if raw else None,'reviewed_public_fixture_only':True})
        finally:
            await ex.close();elapsed=time.perf_counter()-clock;self.server_nested+=elapsed;self.children.append((clock,clock+elapsed));self.service_children.append((clock,clock+elapsed));self.settle('aeep-client',operation,raw,error,started,elapsed)
        assert error is None
    async def finish_server(self):
        if self.server is None:return
        raw=None;error=None
        try:
            if not self.server.task.done():
                try:raw=await asyncio.wait_for(asyncio.shield(self.server.task),timeout=10)
                except asyncio.TimeoutError:await self.server_executor.cancel(self.server);error='ForegroundNeededCancellation'
            if raw is None:raw=await self.server.task
        except BaseException as failure:error=type(failure).__name__
        finally:
            await self.server_executor.close();elapsed=time.perf_counter()-self.server_clock
            self.server_active=False;self.driver_nested+=elapsed
            end=self.server_clock+elapsed;intervals=list(self.service_children)
            if self.cleanup_start is not None:intervals.append((self.cleanup_start,end))
            excluded=covered(self.server_clock,end,intervals);exclusive=elapsed-excluded
            self.children.append((self.server_clock,end))
            self.settle('foreground-service',self.server_operation,raw,error,self.server_started,elapsed,exclusive=exclusive)
            write(HERE/'service-intervals.json',{'whole_service_seconds':elapsed,'excluded_nested_or_cleanup_union_seconds':excluded,'exclusive_service_seconds':exclusive,'no_double_counted_children':True})
            self.server=None;self.server_executor=None
async def execute(review,identity):
    validate(review);assert shutil.disk_usage(ROOT).free>=52*1024**3
    with (HERE/'execution-started.json').open('x') as f:json.dump({'review_sha256':identity,'specific_repeat_approved':True},f)
    work=Path(review['work']);assert work.is_dir() and not work.is_symlink() and work.stat().st_uid==os.getuid()
    assert sha(work/'inputs/note.txt')==review['note_sha256']
    assert sha(Path(review['host_canary']))==review['host_canary_sha256']
    context=work/'build-legacy-corrected';context.mkdir(mode=0o700)
    shutil.copyfile(Path(review['server_source']),context/'server.py');(context/'server.py').chmod(0o444)
    shutil.copyfile(HERE/'Dockerfile',context/'Dockerfile');(context/'Dockerfile').chmod(0o444)
    prepared=load(HERE/'prepared.json');request=RecipeMaterializationRequest.model_validate(prepared['request']);grant=AssessmentAuthorization.model_validate(prepared['grant'])
    result={'passed':False,'models':0,'comparisons':'PAUSED','all_stack_complete':False,'accounting_uncertain':False,'cleanup_uncertain':False,'first_party_MCP_server':'Engineering control, not an MCP benchmark reference or candidate-value trial.'}
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store);assert list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone())==review['counters_before']
        for ref,value in prepared['scopes'].items():assert repo.put('toolkit_toolhive_mcp_scope',ref,Scope.model_validate(value))==ref;repo.review(ref)
        repo.approve_budget_amendment(AssessmentBudgetAmendment.model_validate(load(HERE/'budget-amendment.json')));outer=request.plan_id+':exclusive-driver';cleanup=request.plan_id+':owned-cleanup'
        repo.reserve(request,outer,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=60),stage='toolhive_mcp_driver_overhead')
        repo.reserve(request,cleanup,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=120),stage='toolhive_mcp_owned_cleanup')
        began=time.perf_counter();j=Journey(repo,request,review,identity);cleanup_seconds=0.
        try:
            assert not (await j.command('collision',j.docker('ps','-aq','--filter','name=^/'+review['name']+'$'))).strip()
            parent=await j.image_info(review['parent_reference'],'parent-inspect');assert parent['Id']==review['parent_id'] and parent['RootFS']['Layers']==review['parent_layers']
            await j.command('build',j.docker('build','--pull=false','--network=none','--tag',review['output_tag'],str(context)),180)
            child=await j.image_info(review['output_tag'],'image-inspect');assert child['RootFS']['Layers'][:len(review['parent_layers'])]==review['parent_layers'] and child['Config']['User']=='65534:65534'
            j.image=child['Id'];write(HERE/'built-image.json',{'Id':j.image,'tag':review['output_tag'],'parent':parent['Id'],'layers':child['RootFS']['Layers'],'server_sha256':sha(HERE/'server.py')})
            probe=json.loads(await j.command('controller-boundary',j.native(review['python'],'-I','-B',review['host_boundary_source']),10));assert probe['passed']
            await j.start_server();container=await j.inspect_owned()
            host=container['HostConfig'];mounts=container['Mounts']
            assert not host['Privileged'] and host['CapDrop']==['ALL'] and not host.get('CapAdd') and host['NetworkMode']=='none'
            assert container['Config']['User']=='65534:65534' and len(mounts)==1 and mounts[0]['Source']==str(work/'inputs') and mounts[0]['Destination']=='/inputs' and not mounts[0]['RW']
            # Apply finite engineering cgroup/restart bounds on this verified NEW container only.
            await j.command('owned-limits',j.docker('update','--restart=no','--memory=256m','--memory-swap=256m','--cpus=1','--pids-limit=32',j.owned))
            listing=json.loads(await j.command('tools-list',j.native(review['toolhive'],'mcp','list','tools','--server',review['endpoint'],'--transport','streamable-http','--format','json'),20))
            assert {'format_json','boundary_probe'}<={x['name'] for x in listing.get('tools',listing) if isinstance(x,dict)}
            response=json.loads(await j.command('boundary-call',j.native(review['toolhive'],'mcp','call','boundary_probe','--server',review['endpoint'],'--transport','streamable-http','--format','json'),20))
            facts=json.loads(response['content'][0]['text']);assert all(facts.get(k) is True for k in ('reviewed_input_read','reviewed_input_write_denied','external_connect_denied','docker_socket_absent','host_canary_absent')) and facts['uid']==65534
            write(HERE/'server-boundary.json',facts)
            await j.aeep_client();await j.command('toolhive-stop',j.native(review['toolhive'],'stop','--timeout','10',review['name']),30)
            await j.finish_server();after=await j.inspect_owned('stopped-inspect')
            assert after is None or not after['State']['Running']
            assert sha(work/'inputs/note.txt')==review['note_sha256']
            result.update(passed=True,toolhive_launch_inspect_invoke_stop=True,AEEP_MCP_executor='PASS',MCP_server_permissions='PASS',image_id=j.image,owned_container_id=j.owned,private_rootfs_writable=True,read_only_input_mount=True,no_new_privileges_enforced_by_ToolHive=False)
        except BaseException as failure:result['error_type']=type(failure).__name__
        finally:
            clock=time.perf_counter();j.cleanup_start=clock
            try:
                if j.image:
                    value=await j.inspect_owned('cleanup-inspect',cleanup=True)
                    if value and value['State']['Running']:await j.command('cleanup-stop',j.docker('stop','--time','10',j.owned),30,cleanup=True)
                await j.finish_server()
                if j.image:
                    value=await j.inspect_owned('cleanup-final',cleanup=True);assert value is None or not value['State']['Running']
                result['owned_container_stopped_or_removed']=True
            except BaseException as failure:result.update(passed=False,cleanup_uncertain=True,cleanup_error_type=type(failure).__name__)
            cleanup_seconds=time.perf_counter()-clock
            j.children.append((clock,clock+cleanup_seconds))
            try:
                repo.finish_operation(cleanup,elapsed_seconds=cleanup_seconds,resources=ResourceVector(latency_ms=cleanup_seconds*1000))
                # Cleanup is already aggregated; exclude it and all child/service intervals.
                ended=time.perf_counter();overhead=(ended-began)-covered(began,ended,j.children)
                repo.finish_operation(outer,elapsed_seconds=overhead,resources=ResourceVector(latency_ms=overhead*1000))
                write(HERE/'driver-intervals.json',{'whole_driver_seconds':ended-began,'excluded_child_interval_union_seconds':covered(began,ended,j.children),'exclusive_driver_seconds':overhead,'overlap_handling':'Interval union, not sum of overlapping service/client/cleanup lifetimes.'})
                result['accounting_uncertain']=store._connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(grant.authorization_id,)).fetchone() is not None
                result['grant_counters']=list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone());write(HERE/'operation-ledger.json',repo.operation_ledger(request.plan_id).model_dump(mode='json'))
            except BaseException as failure:result.update(passed=False,accounting_uncertain=True,accounting_error_type=type(failure).__name__)
            result['free_bytes_after']=shutil.disk_usage(ROOT).free;write(HERE/'summary.json',result)
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute-approved');args=parser.parse_args();review=load(HERE/'operation-review.json');identity=sha(HERE/'operation-review.json')
    if args.execute_approved is None:print(json.dumps({'execution':False,'review_sha256':identity}));raise SystemExit(0)
    authority=load(HERE/'operator-approval.json');assert args.execute_approved==identity==authority['review_sha256'] and authority['approved'] is True
    result=asyncio.run(execute(review,identity));print(json.dumps(result))
    if not result['passed']:raise SystemExit(1)
