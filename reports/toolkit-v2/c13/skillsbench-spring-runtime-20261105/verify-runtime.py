"""Record the first network-disabled Spring runtime probe in the existing ledger."""
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
p.add_argument('--execute-delegated', required=True)
args = p.parse_args()
review_path = HERE/'probe-review.json'
r = load(review_path)
identity = sha(review_path)
a = load(HERE/'probe-authority.json')
assert args.execute_delegated == identity == a['review_sha256'] and a['first_attempt']
assert datetime.now(UTC) < datetime.fromisoformat(r['expires_at'])
assert shutil.disk_usage(ROOT).free >= 52 * 1024**3
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
prepared = load(HERE/'probe-prepared.json')
grant = AssessmentAuthorization.model_validate(prepared['grant'])
request = RecipeMaterializationRequest.model_validate(prepared['request'])
work = Path(r['work'])
docker = [r['docker'], '--config', r['docker_config'], '--host', 'unix://' + r['docker_socket']]
env = {'HOME': str(work), 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}
output = HERE/'runtime-execution'
output.mkdir()
write(HERE/'runtime-started.json', {'review_sha256': identity})
intervals = []
report = {'passed': False, 'models': 0, 'comparisons': 'PAUSED', 'cleanup_uncertain': False,
          'maven_dependencies_resolved': False, 'task_executed': False}


class Scope(StrictModel):
    role: str
    plan_sha256: str


async def command(repo, name, options, timeout=20):
    operation = request.plan_id+':'+name
    repo.reserve(request, operation, AssessmentLimits(
        max_operations=1, max_model_turns=0, max_elapsed_seconds=timeout+10,
    ), stage='skillsbench_spring_runtime_probe')
    spec = ExecutorSpec(
        id='skillsbench.spring-runtime-probe', capability='toolkit.upstream-engineering@1',
        kind='command', side_effect='write', description='Pinned offline Spring image runtime readiness',
        config={'argv': [*docker, *options], 'argv_literal': True, 'inherit_env': False,
                'env': env, 'cwd': str(work), 'timeout_seconds': timeout,
                'max_output_bytes': 32768, 'output': {'type': 'text'}},
    )
    start, began = utc_now(), time.perf_counter()
    raw = error = evidence_ref = None
    runner = CommandExecutor()

    def authorize():
        repo.authorize(request)
        assert sha(review_path) == identity
        for path in (r['docker'], r['docker_config']+'/config.json'):
            assert sha(Path(path)) == r['pins'][path]
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
            signal for signal in ('permission denied', 'exec format error', 'read-only file system',
                                  'no such file', 'error while loading shared libraries')
            if raw and signal in ((raw.stdout or '')+(raw.stderr or '')).lower()
        ]
        raise RuntimeError(name)
    return raw.stdout.strip(), elapsed


async def run():
    with ReceiptStore(r['ledger']) as store:
        repo = AssessmentRepository(store)
        assert not store._connection.execute(
            'SELECT 1 FROM assessment_grants WHERE id=?', (grant.authorization_id,)
        ).fetchone()
        for ref, raw in prepared['scopes'].items():
            assert repo.put('toolkit_spring_runtime_scope', ref, Scope.model_validate(raw)) == ref
            repo.review(ref)
        repo.grant(grant)
        wrapper = request.plan_id+':driver'
        repo.reserve(request, wrapper, AssessmentLimits(
            max_operations=1, max_model_turns=0, max_elapsed_seconds=60,
        ), stage='skillsbench_spring_runtime_overhead')
        begin = time.perf_counter()
        cid = None
        started = False
        try:
            image = r['image']
            text, elapsed = await command(repo, 'image', ['image', 'inspect', '--format', '{{json .}}', image['reference']])
            item = json.loads(text)
            assert item['Id'] == image['image_id'] and item['RootFS']['Layers'] == image['diff_ids']
            assert (item['Os'], item['Architecture']) == ('linux', 'amd64')
            assert item['Config'].get('Volumes') in (None, {})
            mounts = []
            for path, target in r['mounts'].items():
                mounts.extend(['--mount', f'type=bind,src={path},dst={target},readonly'])
            assert shutil.disk_usage(ROOT).free >= 51 * 1024**3
            cid, elapsed = await command(repo, 'create', [
                'create', '--name', r['container_name'], '--label',
                'com.aeep.engineering.owner='+r['container_name'], '--platform', 'linux/amd64',
                '--pull', 'never', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                '--security-opt', 'no-new-privileges:true', '--pids-limit', '96',
                '--memory', '1g', '--memory-swap', '1g', '--cpus', '1', '--restart', 'no',
                '--tmpfs', '/aeep-runtime:rw,exec,nosuid,nodev,size=256m',
                '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=64m',
                '--user', '0:0', '--workdir', '/tmp', '--entrypoint', '/usr/bin/timeout',
                *mounts, image['reference'], '95s', '/bin/bash', '/aeep/probe.sh',
            ])
            assert re.fullmatch(r'[a-f0-9]{64}', cid)
            report['retained_container_id'] = cid
            text, elapsed = await command(repo, 'preflight', ['inspect', '--format', '{{json .}}', cid])
            state = json.loads(text)
            assert state['Id'] == cid and state['Image'] == image['image_id']
            assert state['Name'] == '/'+r['container_name'] and state['State']['Status'] == 'created'
            assert state['Config']['Labels']['com.aeep.engineering.owner'] == r['container_name']
            config = state['HostConfig']
            assert config['NetworkMode'] == 'none' and config['ReadonlyRootfs']
            assert config['CapDrop'] == ['ALL'] and config['SecurityOpt'] == ['no-new-privileges:true']
            assert not config.get('Privileged') and not config.get('PortBindings') and not config.get('Devices')
            assert config['Memory'] == config['MemorySwap'] == 1024**3 and config['PidsLimit'] == 96
            assert config['Tmpfs'] == {'/aeep-runtime': 'rw,exec,nosuid,nodev,size=256m',
                                      '/tmp': 'rw,noexec,nosuid,nodev,size=64m'}
            assert {(m['Source'], m['Destination'], m['RW']) for m in state['Mounts'] if m['Type']=='bind'} == {
                (source, target, False) for source,target in r['mounts'].items()
            }
            assert all(m['Type'] == 'bind' or m['Type'] == 'tmpfs' and m['Destination'] in ('/tmp','/aeep-runtime')
                       for m in state['Mounts'])
            started = True
            text, elapsed = await command(repo, 'start', ['start', '--attach', cid], 110)
            report['observed_runtime'] = json.loads(text)
            assert report['observed_runtime']['maven'] == '3.9.6'
            report['passed'] = True
        except Exception as error:
            report['error_type'] = type(error).__name__
        finally:
            if started:
                try:
                    text, elapsed = await command(repo, 'terminal', ['inspect','--format','{{json .State}}',cid])
                    state = json.loads(text)
                    if state['Running']:
                        _, elapsed = await command(repo, 'stop', ['stop','--time','3',cid])
                        text, elapsed = await command(repo, 'stopped', ['inspect','--format','{{json .State}}',cid])
                        state = json.loads(text)
                    assert not state['Running']
                    report['terminal'] = {k:state[k] for k in ('Status','ExitCode','OOMKilled')}
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
            write(output/'operation-ledger.json', repo.operation_ledger(request.plan_id).model_dump(mode='json'))
            write(output/'summary.json', report)


asyncio.run(run())
print(json.dumps(report))
raise SystemExit(not report['passed'] or report['cleanup_uncertain'] or report['accounting_uncertain'])
