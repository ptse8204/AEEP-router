"""Dispatch only the reviewed first offline Invoice Fraud reference journey."""

import argparse
import asyncio
import hashlib
import json
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
TMPFS = {'/root': 'rw,nosuid,nodev,noexec,uid=65534,gid=65534,mode=0700,size=32m',
         '/tmp': 'rw,nosuid,nodev,noexec,size=32m'}
START_TIMEOUT = 90
EXPECTED = {'reference': 'passed', 'missing': 'rejected', 'empty': 'rejected',
            'infrastructure': 'infrastructure_error'}


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, data):
    with path.open('x') as stream:
        stream.write(json.dumps(data, indent=2) + '\n')


def verify_container(layout, cid, name, review, mounts):
    assert layout['Id'] == cid and layout['Name'] == '/' + name and layout['Image'] == review['image']
    config, host = layout['Config'], layout['HostConfig']
    assert layout['State']['Status'] == 'created'
    assert config['Labels']['com.aeep.engineering.owner'] == name
    assert config['User'] == '65534:65534' and config['WorkingDir'] == '/tmp'
    assert host['ReadonlyRootfs'] and host['NetworkMode'] == 'none'
    assert host['CapDrop'] == ['ALL'] and host['SecurityOpt'] == ['no-new-privileges:true']
    assert host['Tmpfs'] == TMPFS and host['PidsLimit'] == 96
    assert host['NanoCpus'] == 10**9 and host['Memory'] == host['MemorySwap'] == 1024**3
    assert all(not host.get(key) for key in ('Privileged', 'PortBindings', 'Devices', 'CapAdd', 'Binds'))
    assert {row['Destination'] for row in layout['Mounts'] if row['Type'] != 'bind'} <= TMPFS.keys()
    assert all(row['Type'] in ('bind', 'tmpfs') for row in layout['Mounts'])
    assert {(row['Source'], row['Destination'], row['RW']) for row in layout['Mounts']
            if row['Type'] == 'bind'} == {(source, dest, False) for source, dest in mounts.items()}


async def execute(review, identity, review_path):
    sys.path.insert(0, str(Path(review['source_snapshot']) / 'src'))
    from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
    from aeep.assessment.repository import AssessmentRepository
    from aeep.assessment.verification import verification_source_digest
    from aeep.execution import ExecutionEvidence, persist_execution_events
    from aeep.executors.base import ExecutionContext
    from aeep.executors.command import CommandExecutor
    from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, StrictModel, utc_now
    from aeep.store import ReceiptStore

    assert verification_source_digest(Path(review['source_snapshot'])) == review['source_sha256']
    work = Path(review['work'])
    assert work.is_dir() and not work.is_symlink()

    class Scope(StrictModel):
        review_sha256: str

    scope = Scope(review_sha256=identity)
    ref = content_digest(scope)
    grant = AssessmentAuthorization(
        authorization_id=HERE.parent.name + '-reference-continuation', subject_digests=[ref], recipe_digests=[ref],
        environment_digests=[ref], limits=AssessmentLimits(
            max_operations=review['max_operations'], max_elapsed_seconds=review['max_seconds'],
        ),
        expires_at=datetime.fromisoformat(review['expires_at']), allowed_destinations=['local'],
        remote_disclosure=False,
    )
    request = RecipeMaterializationRequest(
        plan_id=grant.authorization_id, authorization_id=grant.authorization_id,
        subject_digest=ref, recipe_digest=ref, mapping_digest=ref, environment_digest=ref,
        definition_digests=[ref], seed=0,
    )
    out = HERE / 'reference-execution'
    out.mkdir(mode=0o700)
    write(out / 'started.json', {'review_sha256': identity})
    result = {'passed': False, 'models': 0, 'review_sha256': identity, 'containers': {},
              'phases': {}, 'official_benchmark_reproduction': False}
    total_nested = 0.0

    async def command(name, argv, seconds=15, data=None, cleanup=False):
        nonlocal total_nested
        op = request.plan_id + ':' + name
        repository.reserve(request, op, AssessmentLimits(max_operations=1, max_elapsed_seconds=seconds+5),
                           stage='skillsbench_protected_reference')
        spec = ExecutorSpec(
            id='skillsbench.invoice-fraud-reference', capability='toolkit.upstream-engineering@1',
            kind='command', side_effect='write', description='Pinned offline task reference execution',
            config={'argv': [*review['docker'], *argv], 'argv_literal': True, 'inherit_env': False,
                    'env': {'HOME': str(work), 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'},
                    'stdin_json': data is not None, 'max_stdin_bytes': 75_000,
                    'cwd': str(work), 'timeout_seconds': seconds, 'max_output_bytes': 131_072,
                    'output': {'type': 'text'}},
        )

        def authorize():
            assert sha(review_path) == identity
            if not cleanup:
                assert shutil.disk_usage(ROOT).free >= review['minimum_free_gib'] * 1024**3
            repository.authorize(request)
            return identity

        start, clock = utc_now(), time.perf_counter()
        executor = CommandExecutor()
        raw = evidence_ref = failure = None
        try:
            with persist_execution_events(lambda key, event: repository.put(
                'execution_event', key + ':' + str(event.sequence), event,
            )):
                handle = await executor.start(ExecutionContext(
                    request=ActionRequest(action_id=op, capability=spec.capability, input=data or {}),
                    spec=spec, estimate=spec.estimate, attempt=1, attempt_id=op,
                    approved_side_effect=spec.side_effect, invocation_check=authorize,
                ))
                raw = await handle.task
            evidence = ExecutionEvidence.model_validate(raw.metadata['execution_evidence'])
            evidence_ref = repository.put('execution_evidence', evidence.digest(), evidence)
            assert evidence.complete and raw.exit_code == 0
        except BaseException as error:
            failure = type(error).__name__
            result['failed_command'] = name
            raise
        finally:
            await executor.close()
            elapsed = time.perf_counter() - clock
            total_nested += elapsed
            receipt = ExecutionReceipt(
                decision_id=op, action_id=op, capability=spec.capability, executor_id=spec.id,
                executor_kind=spec.kind, status='failed' if failure else 'success', started_at=start,
                ended_at=utc_now(), estimated=spec.estimate, actual_resources=ResourceVector(latency_ms=elapsed*1000),
                execution_success=failure is None, error_type=failure,
                metadata={'review_sha256': identity, 'execution_evidence_ref': evidence_ref,
                          'observed_resource_dimensions': ['latency_ms'],
                          'exit_code': raw.exit_code if raw else None,
                          'stderr_sha256': hashlib.sha256((raw.stderr or '').encode()).hexdigest() if raw else None},
            )
            store.save_receipt(receipt)
            repository.finish_operation(op, elapsed_seconds=elapsed, resources=receipt.actual_resources)
            write(out / (name + '.json'), receipt.model_dump(mode='json'))
        return raw.stdout

    async def phase(name, mounts, data=None):
        label = 'aeep-skillsbench-invoice-20261106-' + name
        entry = ['/bin/bash', '/aeep/entry.sh'] if name == 'oracle' else [
            '/usr/bin/python3', '-I', '-B', '/aeep/entry.py',
        ]
        opts = [item for source, target in mounts.items()
                for item in ('--mount', f'type=bind,src={source},dst={target},readonly')]
        args = [
            'create', '--name', label, '--label', 'com.aeep.engineering.owner=' + label,
            '--platform', review['platform'], '--pull=never', '--network=none',
            '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
            '--pids-limit=96', '--memory=1g', '--memory-swap=1g', '--cpus=1',
            '--restart=no', '--user=65534:65534', '--workdir=/tmp', '--env=HOME=/root',
            '--env=PYTHONDONTWRITEBYTECODE=1', '--env=OPENBLAS_NUM_THREADS=1',
            '--tmpfs', '/root:' + TMPFS['/root'], '--tmpfs', '/tmp:' + TMPFS['/tmp'],
            '--entrypoint', '/usr/bin/timeout', *opts,
        ]
        if data is not None:
            args.append('--interactive')
        cid = (await command(name + '-create', [*args, review['image'], '75s', *entry])).strip()
        assert re.fullmatch(r'[a-f0-9]{64}', cid)
        record = {'id': cid, 'retained': True, 'started': False}
        result['containers'][name] = record
        layout = json.loads(await command(name + '-preflight', ['inspect', '--format', '{{json .}}', cid]))
        verify_container(layout, cid, label, review, mounts)
        assert layout['Path'] == '/usr/bin/timeout' and layout['Args'] == ['75s', *entry]
        assert layout['Config']['OpenStdin'] is (data is not None)
        record['preflight_passed'] = True
        try:
            record['started'] = True
            return await command(name + '-start', ['start', '-a', *(['-i'] if data is not None else []), cid],
                                 START_TIMEOUT, data)
        finally:
            state = json.loads(await command(name + '-terminal', ['inspect', '--format', '{{json .State}}', cid],
                                             cleanup=True))
            if state['Running']:
                await command(name + '-stop', ['stop', '--time', '3', cid], cleanup=True)
                state = {'Running': False, 'Status': 'stopped-by-engine',
                         'ExitCode': None, 'OOMKilled': None}
            assert not state['Running']
            record['terminal'] = {key: state[key] for key in ('Status', 'ExitCode', 'OOMKilled')}

    with ReceiptStore(review['ledger']) as store:
        repository = AssessmentRepository(store)
        repository.put('toolkit_skillsbench_reference_scope', ref, scope)
        repository.approve_bundle(grant, {ref: scope.model_dump(mode='json')})
        wrapper = request.plan_id + ':driver'
        repository.reserve(request, wrapper, AssessmentLimits(max_operations=1, max_elapsed_seconds=60),
                           stage='skillsbench_reference_overhead')
        start = time.perf_counter()
        try:
            report = (await phase('oracle', review['mounts']['oracle'])).strip()
            assert 0 < len(report.encode()) <= 65_536
            assert isinstance(json.loads(report), list)
            result['oracle_report_sha256'] = hashlib.sha256(report.encode()).hexdigest()
            for name, payload in (('reference', report), ('missing', None), ('empty', '[]'), ('infrastructure', None)):
                observation = json.loads(await phase(name, review['mounts'][name], {'report': payload}))
                result['phases'][name] = observation
                assert observation['status'] == EXPECTED[name]
            result['passed'] = True
        except BaseException as error:
            result['error_type'] = type(error).__name__
        finally:
            elapsed = max(0., time.perf_counter() - start - total_nested)
            repository.finish_operation(wrapper, elapsed_seconds=elapsed, resources=ResourceVector(latency_ms=elapsed*1000))
            ledger = repository.operation_ledger(request.plan_id)
            write(out / 'ledger.json', ledger.model_dump(mode='json'))
            result['operations'] = len(ledger.operations)
            result['unsettled_operations'] = sum(row.elapsed_seconds is None for row in ledger.operations)
            write(out / 'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-delegated', required=True)
    args = parser.parse_args()
    review_path = HERE / 'reference-operation-review.json'
    review, identity = read(review_path), sha(review_path)
    authority = read(HERE / 'operator-approval.json')
    assert args.execute_delegated == identity == authority['review_sha256'] and authority['approved'] is True
    assert datetime.now().astimezone() < datetime.fromisoformat(review['expires_at'])
    assert list(review['mounts']) == review['phases'] == ['oracle', *EXPECTED]
    assert shutil.disk_usage(ROOT).free >= 52 * 1024**3
    for path, expected in review['files'].items():
        assert Path(path).is_file() and not Path(path).is_symlink() and sha(path) == expected, path
    for source in {source for mounts in review['mounts'].values() for source in mounts}:
        path = Path(source)
        if path.is_dir():
            actual = {str(item) for item in path.rglob('*') if not item.is_dir() or item.is_symlink()}
            assert actual == {name for name in review['files'] if name.startswith(source + '/')}
    result = asyncio.run(execute(review, identity, review_path))
    print(json.dumps(result))
    raise SystemExit(not result['passed'] or result['unsettled_operations'] != 0)


if __name__ == '__main__':
    main()
