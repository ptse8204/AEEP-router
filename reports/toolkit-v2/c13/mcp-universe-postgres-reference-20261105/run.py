"""One isolated MCP-Universe PostgreSQL reference journey with original protected assets."""
import argparse
import asyncio
import hashlib
import json
import re
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


parser = argparse.ArgumentParser()
parser.add_argument('--execute-delegated', required=True)
args = parser.parse_args()
review_path = HERE/'operation-review.json'
review = read(review_path)
identity = sha(review_path)
delegation = read(HERE/'delegated-authority.json')
assert args.execute_delegated == identity == delegation['review_sha256'] and delegation['first_attempt'] is True
assert datetime.now(UTC) < datetime.fromisoformat(review['expires_at'])
assert shutil.disk_usage(ROOT).free >= 52*1024**3
for path, digest in review['pins'].items():
    assert sha(Path(path)) == digest, path
work = Path(review['work'])
tools = Path(review['tools'])
assert all(not path.is_symlink() for path in tools.rglob('*'))
assert {p.relative_to(tools).as_posix():sha(p) for p in tools.rglob('*') if p.is_file()} == review['tool_inventory']

sys.path.insert(0, str(Path(review['coordinator_source_snapshot'])/'src'))
from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.execution import ExecutionEvidence, persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.mcp.client import MCPStdioClient
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, RouteEstimate, SideEffect, StrictModel, utc_now
from aeep.store import ReceiptStore

assert verification_source_digest(Path(review['coordinator_source_snapshot'])) == review['source']
prepared = read(HERE/'prepared.json')
grant = AssessmentAuthorization.model_validate(prepared['grant'])
request = RecipeMaterializationRequest.model_validate(prepared['request'])
docker = [review['docker'],'--config',review['docker_config'],'--host','unix://'+review['docker_socket']]
env = {'HOME':str(work),'PATH':'/usr/bin:/bin','LC_ALL':'C'}
output = HERE/'execution'
output.mkdir(mode=0o700)
write(HERE/'execution-started.json',{'review_sha256':identity})
summary = {'passed':False,'models':0,'comparisons':'PAUSED','containers':{},'phases':{}}


def verify_container(info, cid, name, image, network, mounts, capabilities, tmpfs):
    config = info['HostConfig']
    assert info['Id']==cid and info['Image']==image['id'] and info['State']['Status']=='created'
    assert info['Config']['Labels']['com.aeep.engineering.owner']==name and info['Name']=='/'+name
    assert config['NetworkMode']==network and config['ReadonlyRootfs'] is True and config['CapDrop']==['ALL']
    added = {cap.removeprefix('CAP_') for cap in (config.get('CapAdd') or [])}
    assert added==set(capabilities)
    assert config['SecurityOpt']==['no-new-privileges:true'] and not config.get('Privileged')
    assert not config.get('PortBindings') and not config.get('Devices')
    assert config['Memory']==config['MemorySwap']==768*1024**2 and config['PidsLimit']==96
    assert config['NanoCpus']==10**9 and config['RestartPolicy']['Name']=='no'
    assert config['Tmpfs']==tmpfs
    observed = info.get('Mounts') or []
    assert {(m['Source'],m['Destination'],m['RW']) for m in observed if m['Type']=='bind'}=={
        (str(src),dst,False) for src,dst in mounts}
    assert all(m['Type']=='bind' or (m['Type']=='tmpfs' and m['Destination'] in tmpfs) for m in observed)


class Scope(StrictModel):
    role: str
    plan_sha256: str


class Journey:
    def __init__(self, repository):
        self.repository = repository
        self.nested = 0.0

    def authorize(self):
        self.repository.authorize(request)
        assert sha(review_path) == identity
        for path in (review['docker'], review['docker_config']+'/config.json'):
            assert sha(Path(path)) == review['pins'][path]
        return identity

    def reserve(self, step, timeout):
        op = request.plan_id+':'+step
        self.repository.reserve(request,op,AssessmentLimits(
            max_operations=1,max_model_turns=0,max_elapsed_seconds=timeout+10,
        ),stage='mcp-universe_postgres_reference')
        return op,utc_now(),time.perf_counter()

    def finish(self, step, start, kind, success, metadata, failure=None):
        op,began,clock = start
        elapsed = time.perf_counter()-clock
        self.nested += elapsed
        receipt = ExecutionReceipt(
            decision_id=op,action_id=op,capability='toolkit.upstream-engineering@1',
            executor_id='mcp-universe.postgres-reference',executor_kind=kind,
            status='success' if success else 'failed',execution_success=success,
            started_at=began,ended_at=utc_now(),estimated=RouteEstimate(),
            actual_resources=ResourceVector(latency_ms=elapsed*1000),error_type=failure,
            metadata={'review_sha256':identity,'observed_resource_dimensions':['latency_ms'],
                      'other_measurements':'UNKNOWN',**metadata},
        )
        self.repository.store.save_receipt(receipt)
        self.repository.finish_operation(op,elapsed_seconds=elapsed,resources=receipt.actual_resources)
        write(output/(step+'.json'),receipt.model_dump(mode='json'))

    async def command(self, step, argv, timeout=25, cleanup=False):
        start = self.reserve(step,timeout)
        runner = CommandExecutor()
        raw = evidence_ref = error = None
        spec = ExecutorSpec(
            id='mcp-universe.postgres-reference',capability='toolkit.upstream-engineering@1',
            kind='command',side_effect='write',description='Owned offline benchmark container operation',
            config={'argv':[*docker,*argv],'argv_literal':True,'inherit_env':False,
                    'env':env,'cwd':str(work),'timeout_seconds':timeout,
                    'max_output_bytes':65536,'output':{'type':'text'}},
        )
        def check():
            if not cleanup:
                assert shutil.disk_usage(ROOT).free >= 50.5*1024**3
            return self.authorize()
        try:
            with persist_execution_events(lambda key,event:self.repository.put(
                'execution_event',key+':'+str(event.sequence),event,
            )):
                handle = await runner.start(ExecutionContext(
                    request=ActionRequest(action_id=start[0],capability=spec.capability),
                    spec=spec,estimate=spec.estimate,attempt=1,attempt_id=start[0],
                    approved_side_effect=SideEffect.WRITE,invocation_check=check,
                ))
                raw = await handle.task
            evidence = ExecutionEvidence.model_validate(raw.metadata['execution_evidence'])
            evidence_ref = self.repository.put('execution_evidence',evidence.digest(),evidence)
            assert raw.exit_code == 0 and evidence.complete
        except BaseException as failure:
            error = type(failure).__name__
        finally:
            await runner.close()
            self.finish(step,start,'command',error is None,{
                'execution_evidence_ref':evidence_ref,'exit_code':raw.exit_code if raw else None,
                'stdout_sha256':hashlib.sha256((raw.stdout or '').encode()).hexdigest() if raw else None,
                'stderr_sha256':hashlib.sha256((raw.stderr or '').encode()).hexdigest() if raw else None,
            },error)
        if error:
            summary['failure_step'] = step
            raise RuntimeError(step)
        return raw.stdout.strip()

    async def create(self, role, image, network, entry, flags, command, mounts=(), capabilities=()):
        name = 'aeep-c13-mcp-universe-'+role+'-20261105'
        opts = [arg for source,destination in mounts for arg in
                ('--mount',f'type=bind,src={source},dst={destination},readonly')]
        caps = [arg for cap in capabilities for arg in ('--cap-add',cap)]
        cid = await self.command(role+'-create',[
            'create','--name',name,'--label','com.aeep.engineering.owner='+name,'--pull','never',
            '--platform','linux/'+image['arch'],'--network',network,'--read-only','--cap-drop','ALL',*caps,
            '--security-opt','no-new-privileges:true','--pids-limit','96','--memory','768m','--memory-swap','768m',
            '--cpus','1','--restart','no','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=64m',
            *opts,*flags,'--entrypoint',entry,image['ref'],*command,
        ])
        assert re.fullmatch('[0-9a-f]{64}',cid)
        summary['containers'][role] = {'id':cid,'started':False,'retained':True}
        raw = await self.command(role+'-preflight',['inspect','--format','{{json .}}',cid])
        info = json.loads(raw)
        tmpfs = {'/tmp':'rw,nosuid,nodev,noexec,size=64m'}
        tmpfs.update(dict(flags[i+1].split(':',1) for i,flag in enumerate(flags) if flag=='--tmpfs'))
        verify_container(info,cid,name,image,network,mounts,capabilities,tmpfs)
        return cid

    async def terminal(self, role, cid):
        state = json.loads(await self.command(role+'-terminal',['inspect','--format','{{json .State}}',cid],cleanup=True))
        if state['Running']:
            await self.command(role+'-stop',['stop','--time','3',cid],cleanup=True)
            state = json.loads(await self.command(role+'-stopped',['inspect','--format','{{json .State}}',cid],cleanup=True))
        assert not state['Running']
        summary['containers'][role]['terminal'] = {k:state[k] for k in ('Status','ExitCode','OOMKilled')}

    async def phase(self, variant, db):
        stage = 'seed' if variant=='seed' else 'grade'
        script = work/('prepare_environment.py' if stage=='seed' else 'verify.py')
        cid = await self.create(variant,review['images']['mcp'],'container:'+db,
            '/app/.venv/bin/python',['--user','65534:65534','--env','HOME=/tmp','--workdir','/tmp'],
            ['-I','-B','/aeep/phase.py',stage],
            [(HERE/'phase.py','/aeep/phase.py'),(script,'/aeep/upstream.py'),(tools,'/aeep/verifier-libs')])
        summary['containers'][variant]['started'] = True
        try:
            row = json.loads(await self.command(variant+'-start',['start','--attach',cid],90))
            assert row['phase']==stage
            summary['phases'][variant] = row
            return row
        finally:
            await self.terminal(variant,cid)

    async def solve(self, db):
        cid = await self.create('server',review['images']['mcp'],'container:'+db,
            '/app/.venv/bin/postgres-mcp',
            ['--interactive','--user','65534:65534','--env','HOME=/tmp',
             '--env','DATABASE_URI=postgresql://postgres@127.0.0.1:5432/postgres','--workdir','/tmp'],
            ['--access-mode=unrestricted'])
        phase = 'execute-sql'
        start = self.reserve(phase,125)
        client = MCPStdioClient(command=docker[0],args=[*docker[1:],'start','--attach','--interactive',cid],
                               env=env,cwd=str(work),timeout=35,max_message_bytes=65536,protocol_mode='legacy')
        metadata = {'sql_sha256':review['reference_sql_sha256'],'response_content_retained':False}
        error = None
        try:
            self.authorize()
            assert shutil.disk_usage(ROOT).free >= 50.5*1024**3
            sql = (work/'reference.sql').read_text()
            assert sha(work/'reference.sql')==review['reference_sql_sha256']
            summary['containers']['server']['started'] = True
            listed = await client.list_tools()
            tool = next(x for x in listed.result['tools'] if x['name']=='execute_sql')
            schema = tool['inputSchema']
            assert schema['type']=='object' and set(schema['properties'])=={'sql'} and schema['required']==['sql']
            assert schema['properties']['sql']['type']=='string'
            response = await client.call_tool('execute_sql',{'sql':sql},tool_schema=schema)
            metadata.update(protocol_version=response.protocol_version,request_bytes=response.request_bytes,
                            response_bytes=response.response_bytes,tool_error=bool(response.result.get('isError')))
            assert not metadata['tool_error']
        except BaseException as failure:
            error = type(failure).__name__
            metadata['stderr_sha256'] = hashlib.sha256('\n'.join(client.stderr_tail).encode()).hexdigest()
        finally:
            await client.close()
            self.finish(phase,start,'mcp',error is None,metadata,error)
            if summary['containers']['server']['started']:
                await self.terminal('server',cid)
        if error:
            summary['failure_step'] = phase
            raise RuntimeError(phase)


async def run():
    with ReceiptStore(review['ledger']) as store:
        repo = AssessmentRepository(store)
        assert not store._connection.execute('SELECT 1 FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone()
        for ref,raw in prepared['scopes'].items():
            assert repo.put('toolkit_mcp-universe_reference_scope',ref,Scope.model_validate(raw))==ref
            repo.review(ref)
        repo.grant(grant)
        journey = Journey(repo)
        wrapper = journey.reserve('driver',90)
        db = None
        try:
            for role,image in review['images'].items():
                seen = json.loads(await journey.command(role+'-image',['image','inspect','--format','{{json .}}',image['ref']]))
                assert (seen['Id'],seen['Architecture'],seen['Os'])==(image['id'],image['arch'],'linux')
                assert seen['RootFS']['Layers']==image['layers']
                assert set((seen['Config'].get('Volumes') or {}).keys())==set(image['declared_volumes'])
            db = await journey.create('db',review['images']['db'],'none',
                '/usr/local/bin/docker-entrypoint.sh',[
                    '--env','POSTGRES_HOST_AUTH_METHOD=trust','--env','POSTGRES_USER=postgres',
                    '--env','POSTGRES_DB=postgres','--env','TZ=UTC','--env','PGTZ=UTC',
                    '--tmpfs','/var/lib/postgresql/data:rw,nosuid,nodev,noexec,size=128m,uid=999,gid=999,mode=0700',
                    '--tmpfs','/var/run/postgresql:rw,nosuid,nodev,noexec,size=16m,uid=999,gid=999',
                ],['postgres','-c','listen_addresses=127.0.0.1','-c','max_connections=16'],
                capabilities=('CHOWN','DAC_OVERRIDE','FOWNER','SETUID','SETGID'))
            summary['containers']['db']['started'] = True
            await journey.command('db-start',['start',db])
            await journey.command('db-ready',['exec',db,'/bin/sh','-c',
                'for i in $(seq 1 30); do pg_isready -h 127.0.0.1 -U postgres -d postgres && exit 0; sleep 1; done; exit 1'],40)
            seed = await journey.phase('seed',db)
            assert seed['upstream_exit_code']==0 and not seed['runtime_error']
            negative = await journey.phase('missing',db)
            assert negative['upstream_exit_code']==1 and negative['missing_results'] and not negative['runtime_error']
            await journey.solve(db)
            grade = await journey.phase('reference',db)
            assert grade['upstream_exit_code']==0 and grade['all_checks_passed'] and not grade['runtime_error']
            summary.update(passed=True,reference_reward=1,missing_output_reward=0)
        except Exception as failure:
            summary['error_type'] = type(failure).__name__
        finally:
            if db and summary['containers']['db']['started']:
                try:
                    await journey.terminal('db',db)
                except Exception:
                    summary['db_cleanup_error'] = True
            summary['cleanup_uncertain'] = any(x['started'] and 'terminal' not in x for x in summary['containers'].values())
            elapsed = max(0.0,time.perf_counter()-wrapper[2]-journey.nested)
            repo.finish_operation(wrapper[0],elapsed_seconds=elapsed,resources=ResourceVector(latency_ms=elapsed*1000))
            summary['accounting_uncertain'] = bool(store._connection.execute(
                "SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(grant.authorization_id,)).fetchone())
            summary['grant_counters'] = list(store._connection.execute(
                'SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',
                (grant.authorization_id,)).fetchone())
            write(output/'operation-ledger.json',repo.operation_ledger(request.plan_id).model_dump(mode='json'))
            write(output/'summary.json',summary)


asyncio.run(run())
print(json.dumps(summary))
raise SystemExit(not summary['passed'] or summary['cleanup_uncertain'] or summary['accounting_uncertain'])
