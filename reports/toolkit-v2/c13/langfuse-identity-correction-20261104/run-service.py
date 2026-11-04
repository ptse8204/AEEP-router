"""One exact engineering journey; no execution without its approval artifact."""
from __future__ import annotations
import argparse, asyncio, base64, hashlib, json, os, secrets, shutil, socket, sys, time
from datetime import UTC, datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'langfuse-service-20261104'))
from service_plan import PROJECT, LABEL, PORT, SECRETS, SERVICES, compose, mc_config, ingestion_match

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
INPUT = HERE.parent/'langfuse-service-20261104'
OLD = HERE.parent/'workflow-telemetry-20261104'
SOURCE = Path(json.loads((OLD/'source-snapshot.json').read_bytes())['coordinator_source_snapshot'])
sys.path.insert(0, str(SOURCE/'src'))
from aeep.assessment.models import AssessmentAuthorization, AssessmentBudgetAmendment, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.execution import ExecutionEvidence,persist_execution_events
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, SideEffect, StrictModel, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_telemetry import ReceiptExportDefinition
from aeep_toolkit.install_runtime import snapshot

def load(p): return json.loads(Path(p).read_bytes())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v): Path(p).write_text(json.dumps(v,indent=2)+'\n')

class Scope(StrictModel):
    role: str
    source_digest: str
    blueprint_sha256: str

def validate(review, *, cleanup=False):
    if not cleanup:
        assert datetime.now(UTC)<datetime.fromisoformat(review['expires_at'].replace('Z','+00:00'))
        assert shutil.disk_usage(ROOT).free>=50*1024**3
        for p,h in review['service_assets'].items(): assert sha(p)==h,p
        assert verification_source_digest(SOURCE)==review['source']
        config=Path(review['docker_config'])/'config.json'
        assert (sha(config) if config.exists() else None)==review['docker_config_sha256']
    # Cleanup never expands to a changed binary/socket or another project.
    for p,h in review['executables'].items(): assert sha(Path(p).resolve())==h,p

def validate_image_record(key,line,review):
    decoder=json.JSONDecoder()
    ident,idx=decoder.raw_decode(line);rest=line[idx:].lstrip()
    digests,idx=decoder.raw_decode(rest);layers=json.loads(rest[idx:].lstrip())
    assert ident==review['image_ids'][key]
    assert layers==review['image_layer_diff_ids'][key]
    assert any(d.endswith('@'+review['images'][key].split('@')[1]) for d in digests)

class Journey:
    def __init__(self, review, repository, request, identity):
        self.review,self.repo,self.request,self.identity=review,repository,request,identity
        self.work=Path(review['work']);self.number=0;self.child_seconds=0.;self.cleanup_seconds=0.;self.owned={}
        self.output=HERE/'service-execution';self.cleanup_uncertain=False
        self.started_mutation=False
        self.env={'PATH':'/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin',
            'HOME':str(self.work), 'DOCKER_CONFIG':review['docker_config'],
            'DOCKER_HOST':'unix://'+review['docker_socket'], 'LC_ALL':'C',
            'PYTHONDONTWRITEBYTECODE':'1'}

    def docker(self,*argv):
        return [self.review['docker'],'--config',self.review['docker_config'],
                '--host','unix://'+self.review['docker_socket'],*argv]

    def composition(self,*argv):
        return [self.review['compose'],'--project-name',PROJECT,'--file',str(self.work/'compose.json'),*argv]

    def counters(self):
        return list(self.repo.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(self.request.authorization_id,)).fetchone())

    def command(self,name,argv,seconds=30,*,expected=0,env=None,cleanup=False):
        """Use the existing executor; retain receipts, not secret-bearing streams."""
        validate(self.review,cleanup=cleanup)
        self.number+=1;assert self.number<=self.review['maximum_driver_commands']
        op=self.request.plan_id+':identity-correction-command:'+str(self.number)+':'+name
        child_request=self.request.model_copy(update={'plan_id':self.request.plan_id+':driver-commands'})
        if not cleanup:
            self.repo.reserve(child_request,op,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=seconds+10),stage='langfuse_service_engineering')
        before=self.counters()[2];start=time.perf_counter();started=utc_now();raw=None;error=None
        spec=ExecutorSpec(id='langfuse.engineering.'+name,capability='toolkit.upstream-engineering@1',
            kind='command',side_effect='write',description='Reviewed task-owned local Langfuse lifecycle or ordinary CLI',
            config={'argv':argv,'argv_literal':True,'inherit_env':False,'env':env or self.env,
                    'cwd':str(self.work),'timeout_seconds':seconds,'max_output_bytes':1048576,'output':{'type':'text'}})
        async def call():
            ex=CommandExecutor()
            try:
                def auth():
                    validate(self.review,cleanup=cleanup)
                    if not cleanup:self.repo.authorize(child_request)
                    return self.identity
                handle=await ex.start(ExecutionContext(request=ActionRequest(action_id=op,capability=spec.capability),
                    spec=spec,estimate=spec.estimate,attempt=1,attempt_id=op,approved_side_effect=SideEffect.WRITE,invocation_check=auth))
                while not handle.task.done():
                    await asyncio.wait({handle.task},timeout=1)
                    if not cleanup and shutil.disk_usage(ROOT).free<50*1024**3:
                        await ex.cancel(handle);raise RuntimeError('HostReserveCrossed')
                return await handle.task
            finally:await ex.close()
        evidence_ref=None;evidence_complete=False
        try:
            with persist_execution_events(lambda identity,event:self.repo.put('execution_event',identity+':'+str(event.sequence),event)):
                raw=asyncio.run(call())
            evidence=ExecutionEvidence.model_validate(raw.metadata['execution_evidence'])
            evidence_complete=evidence.complete
            evidence_ref=self.repo.put('execution_evidence',evidence.digest(),evidence)
        except BaseException as failure:error=type(failure).__name__
        finally:
            wall=time.perf_counter()-start
            # Installed CLI children debit the same grant. Exclude those intervals.
            nested=max(0.,self.counters()[2]-before)
            elapsed=max(0.,wall-nested)
            receipt=ExecutionReceipt(decision_id=op,action_id=op,capability=spec.capability,
                executor_id=spec.id,executor_kind=spec.kind,status=raw.status if raw else 'failed',
                started_at=started,ended_at=utc_now(),estimated=spec.estimate,
                actual_resources=ResourceVector(latency_ms=elapsed*1000),execution_success=raw is not None and raw.exit_code==expected and evidence_complete,
                error_type=error or (raw.error_type if raw else None),metadata={
                    'review_sha256':self.identity,'argv_sha256':content_digest(argv),
                    'execution_evidence_ref':evidence_ref,'execution_evidence_complete':evidence_complete,
                    'whole_command_wall_seconds':wall,'excluded_canonical_child_seconds':nested,
                    'observed_resource_dimensions':['latency_ms'],
                    'unmeasured_resource_dimensions':'UNKNOWN','legacy_vector_defaults_are_not_observations':True,
                    'stdout_sha256':hashlib.sha256((raw.stdout or '').encode()).hexdigest() if raw else None,
                    'stderr_sha256':hashlib.sha256((raw.stderr or '').encode()).hexdigest() if raw else None,
                    'secret_bearing_streams_not_retained':True})
            self.repo.store.save_receipt(receipt)
            if cleanup:self.cleanup_seconds+=elapsed
            else:self.repo.finish_operation(op,elapsed_seconds=elapsed,resources=receipt.actual_resources)
            write(self.output/('receipt-'+str(self.number)+'.json'),receipt.model_dump(mode='json'))
            self.child_seconds+=wall
        assert raw is not None and raw.exit_code==expected and evidence_complete,(name,error,raw.error_type if raw else None)
        return raw.stdout or ''

    def inspect(self, names, *, cleanup=False):
        # Never request Config.Env, health logs, or raw logs.
        template='{{json .Id}} {{json .Name}} {{json .Image}} {{json .Config.Labels}} {{json .State.Status}} {{json .State.ExitCode}} {{json .Config.Image}}'
        text=self.command('identity-inspection',self.docker('inspect','--format',template,*names),cleanup=cleanup)
        decoder=json.JSONDecoder();rows=[]
        for line in text.splitlines():
            values=[]
            while line.strip():
                value,idx=decoder.raw_decode(line.lstrip());values.append(value);line=line.lstrip()[idx:]
            assert len(values)==7
            ident,name,image,labels,status,code,image_reference=values
            service=labels.get('com.docker.compose.service');assert service in SERVICES
            assert labels.get(LABEL)==PROJECT and labels.get('com.docker.compose.project')==PROJECT
            assert name=='/'+PROJECT+'-'+service
            assert image in self.review['service_image_allowed_ids'][service]
            assert image_reference in self.review['service_image_allowed_references'][service]
            if service in self.owned:assert self.owned[service]==ident
            self.owned[service]=ident;rows.append({'id':ident,'name':name,'service':service,'status':status,'exit_code':code})
        assert len(rows)==len(names);return rows

    def inspect_security(self):
        template='{{json .HostConfig}} {{json .Mounts}} {{json .NetworkSettings.Networks}} {{json .Config.User}}'
        names=[PROJECT+'-'+s for s in SERVICES]
        text=self.command('permission-inspection',self.docker('inspect','--format',template,*names))
        decoder=json.JSONDecoder()
        for service,line in zip(SERVICES,text.splitlines(),strict=True):
            host,idx=decoder.raw_decode(line);remaining=line[idx:].lstrip();mounts,idx=decoder.raw_decode(remaining)
            remaining=remaining[idx:].lstrip();networks,idx=decoder.raw_decode(remaining);user=json.loads(remaining[idx:].lstrip())
            expected=load(self.work/'compose.json')['services'][service]
            assert not host.get('Privileged') and not host.get('Devices')
            assert host.get('PidMode')!='host' and host.get('IpcMode')!='host'
            assert host.get('CapDrop')==['ALL'] and 'no-new-privileges:true' in host.get('SecurityOpt',[])
            assert {x.upper().removeprefix('CAP_') for x in host.get('CapAdd') or []}==set(expected.get('cap_add',[]))
            assert host['ReadonlyRootfs']==expected['read_only']
            assert host['Memory']==int(expected['mem_limit'][:-1])*1024**2
            assert host['PidsLimit']==expected['pids_limit'] and host['NanoCpus']==1000000000
            assert user==expected.get('user','')
            assert set(networks)=={PROJECT+'-private'}
            for mount in mounts:
                if mount['Type']=='volume':assert mount['Name'].startswith(PROJECT+'-')
                elif mount['Type']=='bind':assert service=='minio-bucket' and mount['Source']==str(self.work/'mc')
                else:assert mount['Type']=='tmpfs'
            ports=host.get('PortBindings') or {}
            assert ports==({'3000/tcp':[{'HostIp':'127.0.0.1','HostPort':str(PORT)}]} if service=='web' else {})
        network=json.loads(self.command('network-inspection',self.docker('network','inspect',PROJECT+'-private','--format','{{json .Internal}} {{json .Labels}}')).split(' ',1)[0])
        assert network is True
        write(self.output/'permission-verdict.json',{'passed':True,'private_network':True,'only_loopback_port':PORT,'host_socket_or_unrelated_mounts':False})

    def one_shot(self,service):
        self.started_mutation=True
        self.command(service+'-start',self.composition('up','--detach','--no-deps','--no-build','--pull','never',service),60)
        for i in range(5):
            row=self.inspect([PROJECT+'-'+service])[0]
            if row['status']=='exited':assert row['exit_code']==0;return
            assert row['status']=='running';time.sleep(1)
        raise RuntimeError('OneShotDidNotComplete')

    def cli(self,name,workflow,scope,receipt_id,auth=None,reviewed=None,configuration='document-data'):
        assert snapshot(Path(self.review['installed_runtime']))==self.review['installed_runtime_snapshot']
        args=['/usr/bin/sandbox-exec','-f',str(INPUT/'cli.sb'),self.review['python'],'-I','-B','-m','aeep_toolkit.cli',
            'workflow','export-telemetry','--workflow',str(INPUT/workflow),'--configuration',configuration,
            '--receipt-id',receipt_id,'--accounting',str(INPUT/scope),'--operation-id',name]
        if reviewed:args+=['--reviewed-digest',reviewed]
        env={**self.env,'HOME':str(self.work/'home'),'TMPDIR':str(self.work/'tmp')}
        if auth:env['AEEP_LANGFUSE_LOCAL_AUTH']=auth
        value=json.loads(self.command(name,args,60,env=env))
        assert snapshot(Path(self.review['installed_runtime']))==self.review['installed_runtime_snapshot']
        write(self.output/(name+'.json'),value);return value

    def poll(self,path, *, expected=None,auth=None,attempts=8):
        # This is a first-party read-only observer, not a substitute response server.
        import urllib.request,urllib.error
        from urllib.parse import urlencode
        if expected:path+='?'+urlencode({'traceId':expected['trace_id'],'fields':'core,metadata','expandMetadata':'attributes','limit':10})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        for n in range(attempts):
            validate(self.review);operation=self.request.plan_id+':observe:'+hashlib.sha256(path.encode()).hexdigest()[:12]+':'+str(n)
            self.repo.reserve(self.request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=10),stage='langfuse_readonly_observation')
            started=utc_now();clock=time.perf_counter();ok=False;status=None;error=None
            try:
                request=urllib.request.Request('http://127.0.0.1:'+str(PORT)+path,headers={'Authorization':auth} if auth else {})
                with opener.open(request,timeout=5) as response:
                    status=response.status;body=response.read(65537);assert len(body)<=65536
                    if status==200:ok=ingestion_match(json.loads(body),expected) if expected else True
            except (OSError,ValueError,AssertionError) as failure:error=type(failure).__name__
            finally:
                elapsed=time.perf_counter()-clock;self.child_seconds+=elapsed
                receipt=ExecutionReceipt(decision_id=operation,action_id=operation,capability='toolkit.upstream-engineering@1',
                    executor_id='langfuse.local-readonly-observer',executor_kind='python',status='success' if ok else 'failed',
                    started_at=started,ended_at=utc_now(),estimated={},actual_resources=ResourceVector(latency_ms=elapsed*1000),
                    execution_success=ok,error_type=error,metadata={'review_sha256':self.identity,'http_status':status,
                        'body_not_retained':True,'observed_resource_dimensions':['latency_ms'],
                        'legacy_vector_defaults_are_not_observations':True})
                self.repo.store.save_receipt(receipt);self.repo.finish_operation(operation,elapsed_seconds=elapsed,resources=receipt.actual_resources)
            if ok:return True
            if n+1<attempts:time.sleep(2)
        return False

    def stop_owned(self):
        if not self.started_mutation:return
        # Discover exact prospective names without enumerating/acting on others.
        for service in SERVICES:
            name=PROJECT+'-'+service
            # ps with an exact name filter yields no error if creation never occurred.
            text=self.command('cleanup-discover',self.docker('ps','-a','--filter','name=^/'+name+'$','--format','{{.Names}}'),cleanup=True)
            if text.strip():assert text.strip()==name;self.inspect([name],cleanup=True)
        if self.owned:
            names=[PROJECT+'-'+s for s in self.owned]
            self.inspect(names,cleanup=True)
            self.command('stop-owned',self.docker('stop','--time','15',*[self.owned[s] for s in self.owned]),60,cleanup=True)
            assert all(x['status'] in ('exited','created') for x in self.inspect(names,cleanup=True))
        write(self.output/'stop-verdict.json',{'passed':True,'owned_container_ids':self.owned,
            'containers_removed':False,'images_volumes_network_configs_retained':True})

class NoRedirect(__import__('urllib.request',fromlist=['HTTPRedirectHandler']).HTTPRedirectHandler):
    def redirect_request(self,*_args,**_kwargs):return None

def execute(review,identity):
    validate(review)
    controls=load(HERE/'identity-controls.json')
    assert controls['passed'] and controls['fixture_source_sha256']==sha(HERE/'check-identity-guard.py')
    assert snapshot(Path(review['installed_runtime']))==review['installed_runtime_snapshot']
    result={'passed':False,'models':0,'comparisons':'PAUSED','all_stack_complete':False,
            'cleanup_uncertain':False,'accounting_uncertain':False,'ingestion_verified':False}
    work=Path(review['work']);work.mkdir(mode=0o700,exist_ok=True)
    assert not work.is_symlink() and work.stat().st_uid==os.getuid()
    for p in ('home','tmp','mc'):(work/p).mkdir(mode=0o700,exist_ok=True)
    # Verify the port is free before consuming the one service attempt.
    with socket.socket() as check:check.bind(('127.0.0.1',PORT))
    with (HERE/'service-started.json').open('x') as f:json.dump({'review_sha256':identity},f)
    out=HERE/'service-execution';out.mkdir(mode=0o700)
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store);prepared=load(INPUT/'prepared.json')
        grant=AssessmentAuthorization.model_validate(prepared['grant']);request=RecipeMaterializationRequest.model_validate(prepared['request'])
        assert list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone())==review['counters_before']
        amendment=AssessmentBudgetAmendment.model_validate(load(HERE/'budget-amendment.json'))
        repo.approve_budget_amendment(amendment)
        for ref,value in prepared['scopes'].items():assert repo.put('toolkit_langfuse_service_scope',ref,Scope.model_validate(value))==ref;repo.review(ref)
        for kind,file,model in [('toolkit_receipt_export','enabled-export.json',ReceiptExportDefinition),('toolkit_receipt_export','disabled-export.json',ReceiptExportDefinition),
                                ('toolkit_workflow_accounting','enabled-accounting.json',WorkflowAccountingDefinition),('toolkit_workflow_accounting','disabled-accounting.json',WorkflowAccountingDefinition)]:
            value=model.model_validate(load(INPUT/file));repo.review(repo.put(kind,content_digest(value),value))
        # Reuse the original grant; never reset or re-grant its counters.
        journey=Journey(review,repo,request,identity)
        outer=request.plan_id+':identity-correction-exclusive-driver';outer_request=request.model_copy(update={'plan_id':request.plan_id+':overhead'})
        repo.reserve(outer_request,outer,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=300),stage='langfuse_driver_overhead')
        cleanup=request.plan_id+':identity-correction-reserved-cleanup'
        cleanup_request=request.model_copy(update={'plan_id':request.plan_id+':cleanup'})
        repo.reserve(cleanup_request,cleanup,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=650),stage='langfuse_owned_cleanup')
        began=time.perf_counter()
        try:
            # refuse any name, network or volume collision instead of adopting it.
            for kind,args in [('container',['ps','-aq','--filter','name=^/'+PROJECT+'-']),
                              ('network',['network','ls','-q','--filter','name=^'+PROJECT+'-private$']),
                              ('volume',['volume','ls','-q','--filter','name=^'+PROJECT+'-'])]:
                assert not journey.command('collision-'+kind,journey.docker(*args)).strip()
            pins=journey.command('image-pins',journey.docker('image','inspect','--format','{{json .Id}} {{json .RepoDigests}} {{json .RootFS.Layers}}',*review['images'].values()))
            decoder=json.JSONDecoder()
            for key,line in zip(review['images'],pins.splitlines(),strict=True):
                validate_image_record(key,line,review)
            generated={key:secrets.token_hex(32) for key in SECRETS}
            config=compose(review['images'],work,generated)
            for file,value in [('compose.json',config),('mc/config.json',mc_config(generated))]:
                p=work/file
                with p.open('x') as f:os.chmod(p,0o600);json.dump(value,f)
            auth='Basic '+base64.b64encode(('pk-lf-'+generated['public']+':sk-lf-'+generated['secret']).encode()).decode()
            journey.command('compose-validate',journey.composition('config','--quiet'))
            journey.one_shot('minio-owner')
            journey.command('datastores-start',journey.composition('up','--detach','--wait','--wait-timeout','90','--no-deps','--no-build','--pull','never','postgres','clickhouse','redis','minio'),120)
            journey.one_shot('minio-bucket')
            journey.command('web-start',journey.composition('up','--detach','--no-deps','--no-build','--pull','never','web'),60)
            assert journey.poll('/api/public/health',attempts=20),'WebNotReady'
            journey.command('worker-start',journey.composition('up','--detach','--wait','--wait-timeout','30','--no-deps','--no-build','--pull','never','worker'),60)
            journey.inspect([PROJECT+'-'+s for s in SERVICES]);journey.inspect_security()
            probe=Path(INPUT/'network-probe.js').read_text()
            probe_result=json.loads(journey.command('egress-probe',journey.docker('exec',PROJECT+'-worker','node','-e',probe),15))
            assert probe_result.get('external_connect_denied') is True
            write(out/'network-probe.json',probe_result)
            receipt_id=prepared['source_receipt_id']
            facts=journey.cli('export-preview','enabled-workflow.json','enabled-accounting.json',receipt_id)
            assert facts['enabled'] and facts['source_receipt_sha256']==prepared['source_receipt_sha256']
            exported=journey.cli('export-once','enabled-workflow.json','enabled-accounting.json',receipt_id,auth,facts['review_sha256'])
            assert exported['transport_accepted'] and not exported['ingestion_verified']
            result['ingestion_verified']=journey.poll('/api/public/v2/observations',expected=exported,auth=auth)
            assert result['ingestion_verified'],'IngestionOrExactReceiptLinkNotVerified'
            before=store._connection.execute("SELECT count(*) FROM assessment_operations WHERE stage='workflow_receipt_export'").fetchone()[0]
            disabled_preview=journey.cli('disabled-preview','disabled-workflow.json','disabled-accounting.json',receipt_id,configuration='software-engineering')
            disabled=journey.cli('disabled-check','disabled-workflow.json','disabled-accounting.json',receipt_id,reviewed=disabled_preview['review_sha256'],configuration='software-engineering')
            assert disabled['status']=='disabled' and not disabled['export_performed']
            after=store._connection.execute("SELECT count(*) FROM assessment_operations WHERE stage='workflow_receipt_export'").fetchone()[0]
            assert before==after
            result.update(passed=True,trace_id=exported['trace_id'],span_id=exported['span_id'],
                source_receipt_sha256=exported['source_receipt_sha256'],export_record_ref=exported['record_ref'],
                disabled_export_verified=True,complete_workload_domain_journeys=False)
        except BaseException as failure:result['error_type']=type(failure).__name__
        finally:
            try:journey.stop_owned()
            except BaseException as failure:result.update(passed=False,cleanup_uncertain=True,cleanup_error_type=type(failure).__name__)
            elapsed=max(0.,time.perf_counter()-began-journey.child_seconds)
            try:
                repo.finish_operation(outer,elapsed_seconds=elapsed,resources=ResourceVector(latency_ms=elapsed*1000))
                repo.finish_operation(cleanup,elapsed_seconds=journey.cleanup_seconds,resources=ResourceVector(latency_ms=journey.cleanup_seconds*1000))
                result['accounting_uncertain']=store._connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(grant.authorization_id,)).fetchone() is not None
                result['grant_counters']=journey.counters()
                for suffix,plan in [('commands',request.plan_id+':driver-commands'),('workflow',request.plan_id),('overhead',outer_request.plan_id),('cleanup',cleanup_request.plan_id)]:write(out/(suffix+'-ledger.json'),repo.operation_ledger(plan).model_dump(mode='json'))
                assert journey.counters()[0]<=review['maximum_operations'] and journey.counters()[1]==0
            except BaseException as failure:result.update(passed=False,accounting_uncertain=True,accounting_error_type=type(failure).__name__)
            result['free_bytes_after']=shutil.disk_usage(ROOT).free
            result['passed']=result['passed'] and not result['cleanup_uncertain'] and not result['accounting_uncertain']
            write(out/'summary.json',result)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute-approved');args=parser.parse_args()
    review=load(HERE/'operation-review.json');identity=sha(HERE/'operation-review.json');validate(review)
    if args.execute_approved is None:print(json.dumps({'review_sha256':identity,'execution':False}));raise SystemExit(0)
    approval=load(HERE/'operator-approval.json');assert args.execute_approved==identity==approval['review_sha256'] and approval['approved'] is True
    result=execute(review,identity);print(json.dumps(result))
    if not result['passed']:raise SystemExit(1)
