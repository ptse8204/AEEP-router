"""Resolve Maven dependencies inside the reviewed registry-only acquisition boundary."""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def load(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


p = argparse.ArgumentParser()
p.add_argument('--execute-approved', required=True)
args = p.parse_args()
review_path = HERE/'operation-review.json'
r = load(review_path)
identity = sha(review_path)
a = load(HERE/'operator-approval.json')
assert args.execute_approved == identity == a['review_sha256'] and a['approved'] is True
assert datetime.now(UTC) < datetime.fromisoformat(r['expires_at'])
assert shutil.disk_usage(ROOT).free >= r['storage_minimum_bytes']
for file, digest in r['pins'].items():
    assert sha(Path(file)) == digest, file
sys.path.insert(0, str(Path(r['coordinator_source_snapshot'])/'src'))

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.execution import ExecutionEvidence, persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, SideEffect, StrictModel, utc_now
from aeep.store import ReceiptStore

assert verification_source_digest(Path(r['coordinator_source_snapshot'])) == r['source']
module_spec = importlib.util.spec_from_file_location('verify_cache', HERE/'verify-cache.py')
verify_cache = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(verify_cache)
prepared = load(HERE/'prepared.json')
grant = AssessmentAuthorization.model_validate(prepared['grant'])
request = RecipeMaterializationRequest.model_validate(prepared['request'])
work = Path(r['work'])
cache = work/'maven-cache'
seed = load(work/'cache-lock.json')
assert {f.relative_to(cache).as_posix():sha(f) for f in sorted(cache.rglob('*')) if f.is_file()} == seed
assert not any(f.is_symlink() for f in cache.rglob('*'))
docker = [r['docker'], '--config', r['docker_config'], '--host', 'unix://' + r['docker_socket']]
env = {'HOME': str(work), 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}
output = HERE/'execution'
output.mkdir()
write(HERE/'execution-started.json', {'review_sha256': identity})
intervals = []
report = {'passed': False, 'models': 0, 'comparisons': 'PAUSED', 'cleanup_uncertain': False,
          'maven_dependencies_resolved': False, 'task_executed': False, 'containers': {}}


class Scope(StrictModel):
    role: str
    plan_sha256: str


async def command(repo, name, options, timeout=20):
    operation = request.plan_id+':'+name
    repo.reserve(request, operation, AssessmentLimits(
        max_operations=1, max_model_turns=0, max_elapsed_seconds=timeout+10,
    ), stage='skillsbench_maven_acquisition')
    spec = ExecutorSpec(
        id='skillsbench.maven-acquisition', capability='toolkit.upstream-engineering@1',
        kind='command', side_effect='write', description='Reviewed Maven dependency acquisition lifecycle',
        config={'argv': [*docker, *options], 'argv_literal': True, 'inherit_env': False,
                'env': env, 'cwd': str(work), 'timeout_seconds': timeout,
                'max_output_bytes': 65536, 'output': {'type': 'text'}},
    )
    start, began = utc_now(), time.perf_counter()
    raw = error = evidence_ref = None
    runner = CommandExecutor()

    def authorize():
        repo.authorize(request)
        assert sha(review_path) == identity
        for path in (r['docker'], r['docker_config']+'/config.json'):
            assert sha(Path(path)) == r['pins'][path]
        if not name.endswith(('-terminal', '-stop', '-stopped')):
            assert shutil.disk_usage(ROOT).free >= 50*1024**3
        return identity

    try:
        with persist_execution_events(lambda key, event: repo.put(
            'execution_event', key+':'+str(event.sequence), event
        )):
            handle = await runner.start(ExecutionContext(
                request=ActionRequest(action_id=operation, capability=spec.capability),
                spec=spec, estimate=spec.estimate, attempt=1, attempt_id=operation,
                approved_side_effect=SideEffect.WRITE, invocation_check=authorize,
            ))
            while not handle.task.done():
                await asyncio.wait({handle.task}, timeout=1)
                if name == 'resolve' and shutil.disk_usage(ROOT).free < 50.5*1024**3:
                    await runner.cancel(handle)
                    raise RuntimeError('StorageReserveApproaching')
            raw = await handle.task
        evidence = ExecutionEvidence.model_validate(raw.metadata['execution_evidence'])
        evidence_ref = repo.put('execution_evidence', evidence.digest(), evidence)
        assert raw.exit_code == 0 and evidence.complete
    except BaseException as failure:
        error = type(failure).__name__
    finally:
        await runner.close()
        elapsed = time.perf_counter()-began
        intervals.append(elapsed)
        receipt = ExecutionReceipt(
            decision_id=operation, action_id=operation, capability=spec.capability, executor_id=spec.id,
            executor_kind='command', status='success' if error is None else 'failed',
            started_at=start, ended_at=utc_now(), estimated=spec.estimate,
            actual_resources=ResourceVector(latency_ms=elapsed*1000),
            execution_success=error is None, error_type=error or (raw.error_type if raw else None),
            metadata={'review_sha256': identity, 'execution_evidence_ref': evidence_ref,
                      'exit_code': raw.exit_code if raw else None, 'observed_resource_dimensions': ['latency_ms'],
                      'other_measurements': 'UNKNOWN',
                      'stderr_sha256': hashlib.sha256((raw.stderr or '').encode()).hexdigest() if raw else None},
        )
        repo.store.save_receipt(receipt)
        repo.finish_operation(operation, elapsed_seconds=elapsed, resources=receipt.actual_resources)
        write(output/(name+'.json'), receipt.model_dump(mode='json'))
    if error:
        report['failure_operation'] = name
        report['failure_signals'] = [
            signal for signal in ('permission denied', 'exec format error', 'read-only file system', 'could not resolve', 'connection refused', 'checksum validation failed', 'non-resolvable parent',
                                  'no such file', 'error while loading shared libraries')
            if raw and signal in ((raw.stdout or '')+(raw.stderr or '')).lower()
        ]
        raise RuntimeError(name)
    return raw.stdout.strip(), elapsed


def mounts(bindings):
    args = []
    for source, target, ro in bindings:
        args.extend(['--mount', f'type=bind,src={source},dst={target}' + (',readonly' if ro else '')])
    return args


async def run():
    with ReceiptStore(r['ledger']) as store:
        repo = AssessmentRepository(store)
        assert not store._connection.execute(
            'SELECT 1 FROM assessment_grants WHERE id=?', (grant.authorization_id,)
        ).fetchone()
        for ref, raw in prepared['scopes'].items():
            assert repo.put('toolkit_maven_acquisition_scope', ref, Scope.model_validate(raw)) == ref
            repo.review(ref)
        repo.grant(grant)
        wrapper = request.plan_id+':driver'
        repo.reserve(request, wrapper, AssessmentLimits(
            max_operations=1, max_model_turns=0, max_elapsed_seconds=60,
        ), stage='skillsbench_maven_acquisition_overhead')
        begin = time.perf_counter()
        owned = {}
        launched = []

        async def call(name, argv, timeout=20):
            text, _ = await command(repo, name, argv, timeout)
            return text

        async def create(role, image, network, bindings, extra, argv):
            name = r['names'][role]
            cid = await call(role+'-create', [
                'create', '--name', name, '--label', 'com.aeep.engineering.owner='+name,
                '--platform', 'linux/amd64', '--pull', 'never', '--network', network,
                '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                '--pids-limit', '96', '--memory', '1g', '--memory-swap', '1g',
                '--cpus', '1', '--restart', 'no', '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=96m',
                *extra, *mounts(bindings), image['reference'], *argv,
            ])
            assert re.fullmatch(r'[a-f0-9]{64}', cid)
            owned[role] = cid
            report['containers'][role] = {'id': cid, 'retained': True}
            return cid

        async def preflight(role, image, bindings, networks):
            cid = owned[role]
            meta = json.loads(await call(role+'-inspect', ['inspect','--format','{{json .}}',cid]))
            assert meta['Id'] == cid and meta['Image'] == image['image_id']
            assert meta['Name'] == '/'+r['names'][role] and meta['State']['Status'] == 'created'
            assert meta['Config']['Labels']['com.aeep.engineering.owner'] == r['names'][role]
            config = meta['HostConfig']
            assert config['ReadonlyRootfs'] and config['CapDrop'] == ['ALL']
            assert config['SecurityOpt'] == ['no-new-privileges:true'] and not config.get('Privileged')
            assert not config.get('PortBindings') and not config.get('Devices')
            assert config['Memory'] == config['MemorySwap'] == 1024**3 and config['PidsLimit'] == 96
            assert set(meta['NetworkSettings']['Networks']) == networks
            assert {(m['Source'],m['Destination'],not m['RW']) for m in meta['Mounts'] if m['Type']=='bind'} == {
                (str(source), target, ro) for source,target,ro in bindings
            }
            assert all(m['Type'] == 'bind' or m['Type'] == 'tmpfs' and m['Destination']=='/tmp'
                       for m in meta['Mounts'])

        try:
            for role, image in r['images'].items():
                meta = json.loads(await call(role+'-image', ['image','inspect','--format','{{json .}}',image['reference']]))
                assert meta['Id'] == image['image_id'] and meta['RootFS']['Layers'] == image['diff_ids']
                assert (meta['Os'],meta['Architecture'])==('linux','amd64')
                assert meta['Config'].get('Volumes') in (None,{})
            assert shutil.disk_usage(ROOT).free >= r['storage_minimum_bytes']
            net, egress = r['names']['internal'], r['names']['egress']
            report['internal_network'] = await call('network-internal',[
                'network','create','--internal','--subnet','172.30.249.0/29',
                '--label','com.aeep.engineering.owner='+net,net,
            ])
            report['egress_network'] = await call('network-egress',[
                'network','create','--label','com.aeep.engineering.owner='+egress,egress,
            ])
            record = json.loads(await call('network-internal-verify',[
                'network','inspect','--format','{{json .}}',net,
            ]))
            assert record['Internal'] and record['Name']==net
            assert any(row['Subnet']=='172.30.249.0/29' for row in record['IPAM']['Config'])
            relay_bindings = [(HERE/'central-relay.py','/aeep/central-relay.py',True)]
            relay = await create('relay',r['images']['relay'],egress,relay_bindings,[
                '--user','65534:65534','--workdir','/tmp','--entrypoint','/usr/bin/timeout',
            ],['520s','/opt/venv/bin/python','-I','-S','-B','/aeep/central-relay.py'])
            await call('relay-network',['network','connect','--ip','172.30.249.2',net,relay])
            await preflight('relay',r['images']['relay'],relay_bindings,{net,egress})
            launched.append('relay')
            await call('relay-start',['start',relay])
            await call('relay-ready',['exec',relay,'/opt/venv/bin/python','-I','-S','-B','-c',
                "import socket,time\nfor _ in range(20):\n try:\n  with socket.create_connection(('172.30.249.2',8765),0.2): break\n except OSError: time.sleep(0.2)\nelse: raise SystemExit(1)"])
            resolver_bindings = [
                (work/'pom.xml','/aeep/pom.xml',True),
                (HERE/'maven-settings.xml','/aeep/settings.xml',True),
                (work/'maven-cache','/cache',False),
                (HERE/'resolve.sh','/aeep/resolve.sh',True),
            ]
            java = '/root/.sdkman/candidates/java/21.0.2-tem'
            resolver = await create('resolver',r['images']['resolver'],net,resolver_bindings,[
                '--ip','172.30.249.3','--user','0:0','--workdir','/tmp','--entrypoint','/usr/bin/timeout',
                '--env','HOME=/tmp','--env','JAVA_HOME='+java,'--env','PATH='+java+'/bin:/usr/bin:/bin',
                '--env','MAVEN_OPTS=-Xmx512m -XX:ActiveProcessorCount=1',
            ],['480s','/bin/bash','/aeep/resolve.sh'])
            await preflight('resolver',r['images']['resolver'],resolver_bindings,{net})
            launched.append('resolver')
            raw = await call('resolve',['start','--attach',resolver],495)
            with (work/'selected.tgf').open('x') as stream:
                stream.write(raw+'\n')
            try:
                graph = verify_cache.verify_graph(raw, cache, r['surefire_provider_files'])
            except ValueError as error:
                if str(error).startswith('missing_descriptors_or_jars:'):
                    report['missing_artifact_paths'] = str(error).split(':',1)[1].split(',')
                raise
            write(output/'verified-dependency-graph.json', graph)
            report['maven_dependencies_resolved'] = True
            inventory = []
            cache = work/'maven-cache'
            for path in sorted(cache.rglob('*')):
                assert not path.is_symlink()
                if path.is_file():
                    inventory.append({'path':str(path.relative_to(cache)), 'bytes':path.stat().st_size,
                                      'sha256':sha(path)})
            assert inventory and sum(item['bytes'] for item in inventory) <= 256*1024**2
            current = {row['path']:row['sha256'] for row in inventory}
            assert all(current.get(path)==digest for path,digest in seed.items()
                       if not path.endswith(('_remote.repositories','resolver-status.properties')))
            new_files = [row for row in inventory if row['path'] not in seed and row['path'].endswith(('.pom','.jar'))]
            for row in new_files:
                path = cache/row['path']
                raw = path.read_bytes()
                sha1 = path.with_suffix(path.suffix+'.sha1')
                md5 = path.with_suffix(path.suffix+'.md5')
                if sha1.is_file():
                    assert hashlib.sha1(raw).hexdigest()==sha1.read_text().strip(), path
                else:
                    assert md5.is_file() and hashlib.md5(raw,usedforsecurity=False).hexdigest()==md5.read_text().strip(), path
            assert any(item['path'].endswith('/spring-boot-starter-web-3.2.0.jar') for item in inventory)
            write(output/'maven-closure.json',inventory)
            report.update(passed=True, new_verified_artifacts=len(new_files),
                          selected_graph_nodes=graph['selected_nodes'], retained_cache_files=len(inventory),
                          retained_cache_bytes=sum(item['bytes'] for item in inventory))
        except Exception as error:
            report['error_type'] = type(error).__name__
        finally:
            for role in reversed(launched):
                cid = owned[role]
                try:
                    state = json.loads(await call(role+'-terminal',['inspect','--format','{{json .State}}',cid]))
                    if state['Running']:
                        await call(role+'-stop',['stop','--time','3',cid])
                        state = json.loads(await call(role+'-stopped',['inspect','--format','{{json .State}}',cid]))
                    assert not state['Running']
                    report['containers'][role]['terminal'] = {k:state[k] for k in ('Status','ExitCode','OOMKilled')}
                except Exception:
                    report['cleanup_uncertain'] = True
            elapsed = max(0.,time.perf_counter()-begin-sum(intervals))
            repo.finish_operation(wrapper, elapsed_seconds=elapsed, resources=ResourceVector(latency_ms=elapsed*1000))
            report['accounting_uncertain'] = bool(store._connection.execute(
                "SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'", (grant.authorization_id,)
            ).fetchone())
            report['grant_counters'] = list(store._connection.execute(
                'SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',
                (grant.authorization_id,),
            ).fetchone())
            report['free_bytes_after'] = shutil.disk_usage(ROOT).free
            write(output/'operation-ledger.json', repo.operation_ledger(request.plan_id).model_dump(mode='json'))
            write(output/'summary.json', report)


asyncio.run(run())
print(json.dumps(report))
raise SystemExit(not report['passed'] or report['cleanup_uncertain'] or report['accounting_uncertain'])
