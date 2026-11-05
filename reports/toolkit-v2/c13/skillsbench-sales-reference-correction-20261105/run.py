"""Run the original solver and protected grader through AEEP's local executor."""
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
from pathlib import Path

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


parser = argparse.ArgumentParser()
parser.add_argument('--execute-approved', required=True)
args = parser.parse_args()
review_file = HERE / 'operation-review.json'
review = load(review_file)
identity = digest(review_file)
approval = load(HERE / 'operator-approval.json')
assert args.execute_approved == identity == approval['review_sha256'] and approval['approved']
assert datetime.now(UTC) < datetime.fromisoformat(review['expires_at'])
assert shutil.disk_usage(ROOT).free >= 52 * 1024**3
for file, expected in review['pins'].items():
    assert digest(Path(file)) == expected, file
work = Path(review['work'])
tools = work / 'tools'
assert sorted(str(p.relative_to(tools)) for p in tools.rglob('*') if p.is_file()) == review['tool_inventory']

sys.path.insert(0, str(Path(review['coordinator_source_snapshot']) / 'src'))
from aeep.assessment.models import AssessmentAuthorization, AssessmentBudgetAmendment, AssessmentLimits, RecipeMaterializationRequest, content_digest
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
            id='skillsbench.sales-reference', capability='toolkit.upstream-engineering@1',
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
                    'modulenotfounderror', 'read-only file system', 'mount denied',
                    'error while loading shared libraries', 'cannot start',
                ) if s in text]
            raise RuntimeError(name)
        return raw.stdout.strip()

    async def container(self, variant, workspace, *, solve=False):
        name = review['container_names'][variant]
        path = work / 'protected'
        mounts = [(workspace, '/root', not solve)]
        if solve:
            mounts.append((path / 'solve.sh', '/aeep/solve.sh', True))
            command = ['/bin/bash', '/aeep/solve.sh']
        else:
            mounts.extend([
                (path / 'test_outputs.py', '/aeep/test_outputs.py', True),
                (path / 'observe.py', '/aeep/observe.py', True),
                (path / 'repository_suite_native_capture.py', '/aeep/native/repository_suite_native_capture.py', True),
                (tools, '/aeep/tools', True),
            ])
            command = ['/opt/venv/bin/python', '-I', '-B', '/aeep/observe.py']
        opts = []
        for source, target, readonly in mounts:
            assert source.exists() and not source.is_symlink()
            opts.extend(['--mount', f'type=bind,src={source},dst={target}' + (',readonly' if readonly else '')])
        cid = await self.checked(variant+'-create', [
            'create', '--name', name, '--label', f'com.aeep.engineering.owner={name}',
            '--platform', 'linux/amd64', '--pull', 'never', '--network', 'none',
            '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
            '--pids-limit', '96', '--memory', '1g', '--memory-swap', '1g', '--cpus', '1',
            '--restart', 'no', '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=128m',
            '--user', '0:0', '--workdir', '/root', '--env', 'HOME=/root',
            '--env', 'PATH=/opt/venv/bin:/usr/bin:/bin', '--env', 'PYTHONDONTWRITEBYTECODE=1',
            '--entrypoint', '/usr/bin/timeout', *opts, review['image']['reference'],
            '120s', *command,
        ])
        assert re.fullmatch(r'[a-f0-9]{64}', cid)
        fact = {'id': cid, 'retained': True, 'started': False}
        result['containers'][variant] = fact
        layout = json.loads(await self.checked(variant+'-preflight', ['inspect', '--format', '{{json .}}', cid]))
        assert layout['Id'] == cid and layout['Image'] == review['image']['image_id']
        assert layout['Name'] == '/' + name
        assert layout['Config']['Labels']['com.aeep.engineering.owner'] == name
        assert layout['State']['Status'] == 'created'
        config = layout['HostConfig']
        assert config['NetworkMode'] == 'none' and config['ReadonlyRootfs']
        assert config['CapDrop'] == ['ALL'] and config['SecurityOpt'] == ['no-new-privileges:true']
        assert not config.get('Privileged') and not config.get('PortBindings') and not config.get('Devices')
        assert config['Memory'] == config['MemorySwap'] == 1024**3 and config['PidsLimit'] == 96
        assert config['Tmpfs'] == {'/tmp': 'rw,nosuid,nodev,noexec,size=128m'}
        assert all(m['Type'] == 'bind' or m['Type'] == 'tmpfs' and m['Destination'] == '/tmp'
                   for m in layout['Mounts'])
        assert {(m['Source'], m['Destination'], not m['RW']) for m in layout['Mounts'] if m['Type'] == 'bind'} == {
            (str(path), dest, ro) for path, dest, ro in mounts
        }
        fact['started'] = True
        try:
            return await self.checked(variant+'-start', ['start', '--attach', cid], 140)
        finally:
            state = json.loads(await self.checked(
                variant+'-terminal', ['inspect', '--format', '{{json .State}}', cid], cleanup=True
            ))
            if state['Running']:
                await self.checked(variant+'-stop', ['stop', '--time', '3', cid], cleanup=True)
                state = json.loads(await self.checked(
                    variant+'-stopped', ['inspect', '--format', '{{json .State}}', cid], cleanup=True
                ))
            assert not state['Running']
            fact['terminal'] = {k: state[k] for k in ('Status', 'ExitCode', 'OOMKilled')}


async def execute():
    with ReceiptStore(review['ledger']) as store:
        repo = AssessmentRepository(store)
        counters = store._connection.execute(
            'SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',
            (grant.authorization_id,),
        ).fetchone()
        assert list(counters) == review['counters_before']
        assert not store._connection.execute(
            "SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",
            (grant.authorization_id,),
        ).fetchone()
        repo.approve_budget_amendment(AssessmentBudgetAmendment.model_validate(prepared['amendment']))
        for ref, raw in prepared['scopes'].items():
            assert repo.put('toolkit_skillsbench_reference_scope', ref, Scope.model_validate(raw)) == ref
            repo.review(ref)
        wrapper = request.plan_id + ':driver'
        repo.reserve(request, wrapper, AssessmentLimits(
            max_operations=1, max_model_turns=0, max_elapsed_seconds=60,
        ), stage='skillsbench_reference_driver_overhead')
        journey = Journey(repo)
        begin = time.perf_counter()
        try:
            image = review['image']
            layout = json.loads(await journey.checked('image-pin', ['image', 'inspect', '--format', '{{json .}}', image['reference']]))
            assert layout['Id'] == image['image_id'] and layout['RootFS']['Layers'] == image['diff_ids']
            assert (layout['Os'], layout['Architecture']) == ('linux', 'amd64') and layout['Config'].get('Volumes') in (None, {})
            await journey.container('solve', work / 'solve', solve=True)
            solved = work / 'solve'
            artifact = solved / 'demographic_analysis.xlsx'
            assert artifact.is_file() and not artifact.is_symlink() and 0 < artifact.stat().st_size <= 4*1024**2
            assert set(p.name for p in solved.iterdir()) == {'population.pdf', 'income.xlsx', artifact.name}
            for name in ('population.pdf', 'income.xlsx'):
                assert digest(solved / name) == review['pins'][str(solved / name)]
            result['artifact'] = {'sha256': digest(artifact), 'bytes': artifact.stat().st_size, 'private': True}
            observations = {}
            for variant, directory in [('reference', solved), ('missing', work/'missing'),
                                       ('wrong-workbook', work/'wrong-workbook')]:
                observation = json.loads(await journey.container(variant, directory))
                observations[variant] = observation
                write(out / (variant + '-verdict.json'), observation)
            reference = observations['reference']
            ids = reference['selected_ids']
            assert len(ids) == len(set(ids)) == 26
            for row in observations.values():
                assert row['selected_ids'] == ids and set(row['native']['statuses']) == set(ids)
            statuses = reference['native']['statuses']
            skipped = [node for node, value in statuses.items() if value == 'SKIPPED']
            assert len(skipped) == 3 and all('::test_pivot_col_field[' in key for key in skipped)
            assert sum(v == 'PASSED' for v in statuses.values()) == 23
            assert reference['pytest_exit_code'] == 0 and reference['upstream_binary_reward'] == 1
            for variant in ('missing', 'wrong-workbook'):
                row = observations[variant]
                assert row['pytest_exit_code'] == 1 and row['upstream_binary_reward'] == 0
                assert any(v in ('FAILED', 'ERROR') for v in row['native']['statuses'].values())
            result.update(passed=True, reference={'passed': 23, 'intended_skips': 3, 'reward': 1},
                          controls={'missing': 0, 'wrong-workbook': 0})
        except Exception as failure:
            result['error_type'] = type(failure).__name__
        finally:
            seconds = max(0.0, time.perf_counter() - begin - journey.nested)
            repo.finish_operation(wrapper, elapsed_seconds=seconds, resources=ResourceVector(latency_ms=seconds*1000))
            result['accounting_uncertain'] = bool(store._connection.execute(
                "SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'", (grant.authorization_id,)
            ).fetchone())
            result['cleanup_uncertain'] = any(
                x['started'] and 'terminal' not in x for x in result['containers'].values()
            )
            result['grant_counters'] = list(store._connection.execute(
                'SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',
                (grant.authorization_id,),
            ).fetchone())
            result['free_bytes_after'] = shutil.disk_usage(ROOT).free
            write(out/'summary.json', result)
            write(out/'operation-ledger.json', repo.operation_ledger(request.plan_id).model_dump(mode='json'))


asyncio.run(execute())
print(json.dumps(result))
raise SystemExit(not result['passed'] or result['accounting_uncertain'] or result['cleanup_uncertain'])
