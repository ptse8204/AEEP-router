"""Run the original Spring solver and protected grader through AEEP's local executor."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def load(path):
    return json.loads(path.read_bytes())


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, data):
    with path.open('x') as out:
        json.dump(data, out, indent=2)
        out.write('\n')


def inventory(path):
    files = {}
    for entry in sorted(path.rglob('*')):
        assert not entry.is_symlink(), entry
        if not entry.is_dir():
            assert entry.is_file(), entry
            files[entry.relative_to(path).as_posix()] = digest(entry)
    return files


def canonical_json_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


parser = argparse.ArgumentParser()
parser.add_argument('--execute-delegated', required=True)
args = parser.parse_args()
review_file = HERE / 'operation-review.json'
review = load(review_file)
identity = digest(review_file)
approval = load(HERE / 'delegated-authority.json')
assert args.execute_delegated == identity == approval['review_sha256'] and approval['first_attempt']
assert datetime.now(UTC) < datetime.fromisoformat(review['expires_at'])
assert shutil.disk_usage(ROOT).free >= 52 * 1024**3
for file, expected in review['pins'].items():
    assert digest(Path(file)) == expected, file
work = Path(review['work'])
tools = work / 'tools'
assert canonical_json_sha(inventory(tools)) == review['tool_inventory_sha256']
cache_lock = load(work / 'maven-cache-lock.json')
assert canonical_json_sha(cache_lock) == review['maven_artifact_lock_sha256']

sys.path.insert(0, str(Path(review['coordinator_source_snapshot']) / 'src'))
from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.execution import ExecutionEvidence, persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, SideEffect, StrictModel, utc_now
from aeep.store import ReceiptStore

assert verification_source_digest(Path(review['coordinator_source_snapshot'])) == review['source']
prepared = load(HERE / 'prepared.json')
grant = AssessmentAuthorization.model_validate(prepared['grant'])
request = RecipeMaterializationRequest.model_validate(prepared['request'])
docker = [review['docker'], '--config', review['docker_config'], '--host', 'unix://' + review['docker_socket']]
env = {'HOME': str(work), 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}
out = HERE / 'execution'
out.mkdir(mode=0o700)
write(HERE / 'execution-started.json', {'review_sha256': identity})
result = {'passed': False, 'candidate_runs': 0, 'models': 0, 'comparisons': 'PAUSED', 'containers': {}}


class Scope(StrictModel):
    role: str
    plan_sha256: str


class Journey:
    def __init__(self, repository):
        self.repository = repository
        self.nested = 0.0

    async def command(self, name, argv, seconds=20, *, cleanup=False):
        op = request.plan_id + ':' + name
        self.repository.reserve(request, op, AssessmentLimits(
            max_operations=1, max_model_turns=0, max_elapsed_seconds=seconds+10,
        ), stage='skillsbench_local_reference')
        began, start = time.perf_counter(), utc_now()
        raw = error = evidence_ref = None
        spec = ExecutorSpec(
            id='skillsbench.spring-reference', capability='toolkit.upstream-engineering@1',
            kind='command', side_effect='write', description='Reviewed offline task container lifecycle',
            config={'argv': [*docker, *argv], 'argv_literal': True, 'inherit_env': False,
                    'env': env, 'cwd': str(work), 'timeout_seconds': seconds,
                    'max_output_bytes': 128*1024, 'output': {'type': 'text'}},
        )
        runner = CommandExecutor()

        def authorize():
            self.repository.authorize(request)
            assert digest(review_file) == identity
            for path in (review['docker'], review['docker_config'] + '/config.json'):
                assert digest(Path(path)) == review['pins'][path]
            if not cleanup:
                assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
            return identity

        try:
            with persist_execution_events(lambda key, event: self.repository.put(
                'execution_event', key + ':' + str(event.sequence), event
            )):
                handle = await runner.start(ExecutionContext(
                    request=ActionRequest(action_id=op, capability=spec.capability),
                    spec=spec, estimate=spec.estimate, attempt=1, attempt_id=op,
                    approved_side_effect=SideEffect.WRITE, invocation_check=authorize,
                ))
                while not handle.task.done():
                    await asyncio.wait({handle.task}, timeout=1)
                    if not cleanup and shutil.disk_usage(ROOT).free < 50.5 * 1024**3:
                        await runner.cancel(handle)
                        raise RuntimeError('StorageReserveApproaching')
                raw = await handle.task
            evidence = ExecutionEvidence.model_validate(raw.metadata['execution_evidence'])
            evidence_ref = self.repository.put('execution_evidence', evidence.digest(), evidence)
            assert raw.exit_code == 0 and evidence.complete
        except BaseException as failure:
            error = type(failure).__name__
        finally:
            await runner.close()
            wall = time.perf_counter() - began
            self.nested += wall
            receipt = ExecutionReceipt(
                decision_id=op, action_id=op, capability=spec.capability, executor_id=spec.id,
                executor_kind='command', status='success' if error is None else 'failed',
                started_at=start, ended_at=utc_now(), estimated=spec.estimate,
                actual_resources=ResourceVector(latency_ms=wall*1000),
                execution_success=error is None, error_type=error or (raw.error_type if raw else None),
                metadata={'review_sha256': identity, 'execution_evidence_ref': evidence_ref,
                          'observed_resource_dimensions': ['latency_ms'], 'other_measurements': 'UNKNOWN',
                          'exit_code': raw.exit_code if raw else None,
                          'command_sha256': content_digest({'argv': argv}),
                          'stdout_sha256': hashlib.sha256((raw.stdout or '').encode()).hexdigest() if raw else None,
                          'stderr_sha256': hashlib.sha256((raw.stderr or '').encode()).hexdigest() if raw else None},
            )
            self.repository.store.save_receipt(receipt)
            self.repository.finish_operation(op, elapsed_seconds=wall, resources=receipt.actual_resources)
            write(out / (name + '.json'), receipt.model_dump(mode='json'))
        return raw, error

    async def checked(self, name, argv, seconds=20, *, cleanup=False):
        raw, error = await self.command(name, argv, seconds, cleanup=cleanup)
        if error:
            result['command_failure'] = {'operation': name, 'error_type': error,
                                         'exit_code': raw.exit_code if raw else None}
            if raw is not None:
                text = ((raw.stderr or '') + '\n' + (raw.stdout or '')).lower()
                result['command_failure']['signals'] = [s for s in (
                    'permission denied', 'exec format error', 'no such file', 'no module named',
                    'modulenotfounderror', 'could not resolve', 'offline mode', 'non-resolvable parent', 'read-only file system', 'mount denied',
                    'error while loading shared libraries', 'cannot start',
                ) if s in text]
            raise RuntimeError(name)
        return raw.stdout.strip()

    async def container(self, variant, workspace, *, solve=False):
        assert inventory(work/'cache'/variant) == cache_lock, variant
        name = review['container_names'][variant]
        path = work / 'protected'
        mounts = [(workspace, '/workspace', False),
                  (work/'cache'/variant, '/cache', False),
                  (Path(review['settings']), '/aeep/settings.xml', True),
                  (HERE/'entry.sh', '/aeep/entry.sh', True)]
        if solve:
            mounts.append((path/'solve.sh','/aeep/solve.sh',True))
        else:
            mounts.extend([
                (path/'test_outputs.py','/aeep/test_outputs.py',True),
                (path/'observe.py','/aeep/observe.py',True),
                (path/'repository_suite_native_capture.py','/aeep/native/repository_suite_native_capture.py',True),
                (tools,'/aeep/tools',True),
                (Path(review['python_archive']),'/aeep/interpreter.tar.gz',True),
            ])
        opts = []
        for source, target, readonly in mounts:
            assert source.exists() and not source.is_symlink()
            opts.extend(['--mount',f'type=bind,src={source},dst={target}' + (',readonly' if readonly else '')])
        java = '/root/.sdkman/candidates/java/21.0.2-tem'
        maven = '/root/.sdkman/candidates/maven/3.9.6'
        tmpfs = {'/tmp':'rw,nosuid,nodev,noexec,size=128m'}
        if not solve:
            tmpfs['/aeep-runtime'] = 'rw,exec,nosuid,nodev,size=256m'
        temporaries = [item for path, options in tmpfs.items() for item in ('--tmpfs',path+':'+options)]
        timeout = 240 if solve else 400
        cid = await self.checked(variant+'-create', [
            'create','--name',name,'--label',f'com.aeep.engineering.owner={name}',
            '--platform','linux/amd64','--pull','never','--network','none',
            '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--pids-limit','192','--memory','1536m','--memory-swap','1536m','--cpus','1',
            '--restart','no',*temporaries,'--user','0:0','--workdir','/workspace',
            '--env','HOME=/root','--env','JAVA_HOME='+java,'--env','SDKMAN_DIR=/root/.sdkman',
            '--env','PATH='+java+'/bin:'+maven+'/bin:/usr/bin:/bin',
            '--env','SDKMAN_OFFLINE_MODE=true',
            '--env','MAVEN_ARGS=--offline --settings /aeep/settings.xml -Dmaven.repo.local=/cache -Dstyle.color=never',
            '--env','MAVEN_OPTS=-Xmx512m -XX:ActiveProcessorCount=1',
            '--env','PYTHONDONTWRITEBYTECODE=1','--entrypoint','/usr/bin/timeout',
            *opts,review['image']['reference'],f'{timeout}s','/bin/bash','/aeep/entry.sh',
            'solve' if solve else 'grade',
        ])
        assert re.fullmatch(r'[a-f0-9]{64}',cid)
        fact = {'id':cid,'retained':True,'started':False}
        result['containers'][variant] = fact
        layout = json.loads(await self.checked(variant+'-preflight',['inspect','--format','{{json .}}',cid]))
        assert layout['Id']==cid and layout['Image']==review['image']['image_id']
        assert layout['Name']=='/'+name and layout['State']['Status']=='created'
        assert layout['Config']['Labels']['com.aeep.engineering.owner']==name
        config=layout['HostConfig']
        assert config['NetworkMode']=='none' and config['ReadonlyRootfs']
        assert config['CapDrop']==['ALL'] and config['SecurityOpt']==['no-new-privileges:true']
        assert not config.get('Privileged') and not config.get('PortBindings') and not config.get('Devices')
        assert config['Memory']==config['MemorySwap']==1536*1024**2 and config['PidsLimit']==192
        assert config['Tmpfs']==tmpfs
        assert all(m['Type']=='bind' or m['Type']=='tmpfs' and m['Destination'] in tmpfs for m in layout['Mounts'])
        assert {(m['Source'],m['Destination'],not m['RW']) for m in layout['Mounts'] if m['Type']=='bind'}=={
            (str(path),dest,ro) for path,dest,ro in mounts
        }
        fact['started']=True
        try:
            return await self.checked(variant+'-start',['start','--attach',cid],timeout+20)
        finally:
            state=json.loads(await self.checked(variant+'-terminal',['inspect','--format','{{json .State}}',cid],cleanup=True))
            if state['Running']:
                await self.checked(variant+'-stop',['stop','--time','3',cid],cleanup=True)
                state=json.loads(await self.checked(variant+'-stopped',['inspect','--format','{{json .State}}',cid],cleanup=True))
            assert not state['Running']
            fact['terminal']={k:state[k] for k in ('Status','ExitCode','OOMKilled')}


def stage_observations():
    solved=work/'solve'
    assert digest(solved/'pom.xml') == review['migrated_pom_sha256']
    rows=[]
    for name in review['workspace_inputs']:
        path=solved/name
        assert path.is_file() and not path.is_symlink() and 0<path.stat().st_size<=128*1024
        rows.append({'path':name,'sha256':digest(path),'bytes':path.stat().st_size})
        for variant in ('reference','missing','legacy-namespace'):
            dest=work/variant/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('xb') as f:
                f.write(path.read_bytes())
    missing=work/'missing/src/main/java/com/example/userservice/model/User.java'
    missing.unlink()
    legacy=work/'legacy-namespace/src/main/java/com/example/userservice/dto/CreateUserRequest.java'
    raw=legacy.read_bytes()
    old=b'import jakarta.validation.constraints.Email;'
    assert raw.count(old)==1
    legacy.write_bytes(raw.replace(old,b'import javax.validation.constraints.Email;'))
    write(out/'workspace-digests.json',rows)


async def execute():
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store)
        assert not store._connection.execute(
            'SELECT 1 FROM assessment_grants WHERE id=?',(grant.authorization_id,),
        ).fetchone()
        for ref,raw in prepared['scopes'].items():
            assert repo.put('toolkit_skillsbench_reference_scope',ref,Scope.model_validate(raw))==ref
            repo.review(ref)
        repo.grant(grant)
        wrapper=request.plan_id+':driver'
        repo.reserve(request,wrapper,AssessmentLimits(
            max_operations=1,max_model_turns=0,max_elapsed_seconds=60,
        ),stage='skillsbench_reference_driver_overhead')
        journey=Journey(repo)
        begin=time.perf_counter()
        try:
            image=review['image']
            layout=json.loads(await journey.checked('image-pin',['image','inspect','--format','{{json .}}',image['reference']]))
            assert layout['Id']==image['image_id'] and layout['RootFS']['Layers']==image['diff_ids']
            assert (layout['Os'],layout['Architecture'])==('linux','amd64') and layout['Config'].get('Volumes') in (None,{})
            solver = await journey.container('solve',work/'solve',solve=True)
            assert 'Tests passed! Migration completed successfully.' in solver
            stage_observations()
            observations={}
            for variant in ('reference','missing','legacy-namespace'):
                row=json.loads(await journey.container(variant,work/variant))
                observations[variant]=row
                write(out/(variant+'-verdict.json'),row)
            ref=observations['reference']
            ids=ref['selected_ids']
            assert len(ids)==len(set(ids))==10
            normalized = ['::'.join([PurePosixPath(name.split('::',1)[0]).name, name.split('::',1)[1]]) for name in ids]
            assert normalized == review['test_identities']
            for row in observations.values():
                assert row['selected_ids']==ids and set(row['native']['statuses'])==set(ids)
                counts=row['ctrf_summary']
                assert counts['tests']==10 and counts['pending']==counts['skipped']==counts['other']==0
                for status in ('passed','failed'):
                    assert counts[status]==sum(value==status.upper() for value in row['native']['statuses'].values())
                assert counts['passed']+counts['failed']==10
            assert ref['upstream_binary_reward']==1 and ref['pytest_exit_code']==0
            assert set(ref['native']['statuses'].values())=={'PASSED'}
            expected={'missing':'::test_jakarta_persistence_present','legacy-namespace':'::test_no_javax_validation'}
            for variant,expected_suffix in expected.items():
                row=observations[variant]
                assert row['upstream_binary_reward']==0 and row['pytest_exit_code']==1
                assert any(name.endswith(expected_suffix) and status=='FAILED'
                           for name,status in row['native']['statuses'].items())
            result.update(passed=True,reference={'passed':10,'skipped':0,'reward':1},
                          controls={'missing':0,'legacy-namespace':0})
        except Exception as failure:
            result['error_type']=type(failure).__name__
        finally:
            seconds=max(0.0,time.perf_counter()-begin-journey.nested)
            repo.finish_operation(wrapper,elapsed_seconds=seconds,resources=ResourceVector(latency_ms=seconds*1000))
            result['accounting_uncertain']=bool(store._connection.execute(
                "SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(grant.authorization_id,)
            ).fetchone())
            result['cleanup_uncertain']=any(x['started'] and 'terminal' not in x for x in result['containers'].values())
            result['grant_counters']=list(store._connection.execute(
                'SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant.authorization_id,)
            ).fetchone())
            result['free_bytes_after']=shutil.disk_usage(ROOT).free
            write(out/'summary.json',result)
            write(out/'operation-ledger.json',repo.operation_ledger(request.plan_id).model_dump(mode='json'))


asyncio.run(execute())
print(json.dumps(result))
raise SystemExit(not result['passed'] or result['accounting_uncertain'] or result['cleanup_uncertain'])
