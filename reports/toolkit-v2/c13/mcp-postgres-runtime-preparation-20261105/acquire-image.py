"""Acquire the immutable upstream Postgres MCP server image without executing it."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


parser = argparse.ArgumentParser()
parser.add_argument('--execute-delegated', required=True)
args = parser.parse_args()
review_file = HERE / 'operation-review.json'
identity = sha(review_file)
review = read(review_file)
authority = read(HERE / 'delegated-authority.json')
assert args.execute_delegated == identity == authority['review_sha256'] and authority['first_attempt']
assert datetime.now(UTC) < datetime.fromisoformat(review['expires_at'])
work = Path(review['work'])
assert work.is_dir() and not work.is_symlink()
assert shutil.disk_usage(ROOT).free >= review['minimum_start_free_bytes']
for path, expected in review['assets'].items():
    assert sha(path) == expected, path

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
prepared = read(HERE / 'prepared.json')
grant = AssessmentAuthorization.model_validate(prepared['grant'])
request = RecipeMaterializationRequest.model_validate(prepared['request'])
docker = [review['docker'], '--config', review['docker_config'], '--host',
          'unix://' + review['docker_socket']]
command_env = {'HOME': str(work), 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}
out = HERE / 'acquisition'
out.mkdir(mode=0o700)
write(HERE / 'execution-started.json', {'review_sha256': identity})
result = {'passed': False, 'models': 0, 'containers_created': 0,
          'image_layers_executed': 0, 'comparisons': 'PAUSED', 'images': []}


class Scope(StrictModel):
    role: str
    plan_sha256: str


async def command(repo, name, argv, timeout):
    operation = request.plan_id + ':' + name
    repo.reserve(request, operation, AssessmentLimits(
        max_operations=1, max_model_turns=0, max_elapsed_seconds=timeout+10,
    ), stage='mcp_postgres_artifact_acquisition')
    began, start = time.perf_counter(), utc_now()
    raw = error = evidence_ref = None
    spec = ExecutorSpec(
        id='mcp-postgres.image-acquisition', capability='toolkit.upstream-engineering@1',
        kind='command', side_effect='write', description='Exact public Postgres MCP image acquisition',
        config={'argv': [*docker, *argv], 'argv_literal': True, 'inherit_env': False,
                'env': command_env, 'cwd': str(work), 'timeout_seconds': timeout,
                'max_output_bytes': 65536, 'output': {'type': 'text'}},
    )
    executor = CommandExecutor()

    def authorize():
        assert sha(review_file) == identity
        assert sha(Path(review['docker_config']) / 'config.json') == review['docker_config_sha256']
        assert shutil.disk_usage(ROOT).free >= review['minimum_free_bytes']
        repo.authorize(request)
        return identity

    try:
        with persist_execution_events(lambda key, item: repo.put(
            'execution_event', key + ':' + str(item.sequence), item,
        )):
            handle = await executor.start(ExecutionContext(
                request=ActionRequest(action_id=operation, capability=spec.capability),
                spec=spec, estimate=spec.estimate, attempt=1, attempt_id=operation,
                approved_side_effect=SideEffect.WRITE, invocation_check=authorize,
            ))
            while not handle.task.done():
                await asyncio.wait({handle.task}, timeout=1)
                if shutil.disk_usage(ROOT).free < review['stop_before_reserve_bytes']:
                    await executor.cancel(handle)
                    raise RuntimeError('StorageReserveApproaching')
            raw = await handle.task
        evidence = ExecutionEvidence.model_validate(raw.metadata['execution_evidence'])
        evidence_ref = repo.put('execution_evidence', evidence.digest(), evidence)
        assert raw.exit_code == 0 and evidence.complete
    except BaseException as failure:
        error = type(failure).__name__
    finally:
        await executor.close()
        elapsed = time.perf_counter() - began
        receipt = ExecutionReceipt(
            decision_id=operation, action_id=operation, capability=spec.capability,
            executor_id=spec.id, executor_kind='command', status='success' if error is None else 'failed',
            started_at=start, ended_at=utc_now(), estimated=spec.estimate,
            actual_resources=ResourceVector(latency_ms=elapsed*1000),
            execution_success=error is None, error_type=error or (raw.error_type if raw else None),
            metadata={'review_sha256': identity, 'execution_evidence_ref': evidence_ref,
                      'observed_resource_dimensions': ['latency_ms'], 'other_measurements': 'UNKNOWN',
                      'exit_code': raw.exit_code if raw else None,
                      'command_sha256': content_digest({'argv': argv}),
                      'stderr_sha256': hashlib.sha256((raw.stderr or '').encode()).hexdigest() if raw else None},
        )
        repo.store.save_receipt(receipt)
        repo.finish_operation(operation, elapsed_seconds=elapsed, resources=receipt.actual_resources)
        write(out / (name + '.json'), receipt.model_dump(mode='json'))
    return raw, error, elapsed


async def acquire():
    with ReceiptStore(review['ledger']) as store:
        repo = AssessmentRepository(store)
        assert not store._connection.execute(
            'SELECT 1 FROM assessment_grants WHERE id=?', (grant.authorization_id,)
        ).fetchone()
        for key, value in prepared['scopes'].items():
            scope = Scope.model_validate(value)
            assert repo.put('toolkit_mcp_postgres_artifact_scope', key, scope) == key
            repo.review(key)
        repo.grant(grant)
        wrapper = request.plan_id + ':driver'
        repo.reserve(request, wrapper, AssessmentLimits(
            max_operations=1, max_model_turns=0, max_elapsed_seconds=60,
        ), stage='mcp_postgres_artifact_driver_overhead')
        start = time.perf_counter()
        nested = 0.
        try:
            for image in review['images']:
                record = {'task_id': image['task_id'], 'reference': image['reference'], 'verified': False}
                result['images'].append(record)
                name = image['task_id']
                raw, error, elapsed = await command(repo, name + '-pull', [
                    'image', 'pull', '--platform', 'linux/amd64', '--quiet', image['reference'],
                ], 240)
                nested += elapsed
                record['pull_succeeded'] = error is None
                if raw is None or raw.status.value == 'timeout':
                    result['acquisition_uncertain'] = True
                    break
                if error:
                    continue
                raw, error, elapsed = await command(repo, name + '-inspect', [
                    'image', 'inspect', '--format',
                    '{{json .Id}} {{json .RepoDigests}} {{json .Os}} {{json .Architecture}} {{json .RootFS.Layers}}',
                    image['reference'],
                ], 20)
                nested += elapsed
                if error:
                    continue
                decoder = json.JSONDecoder()
                remaining = raw.stdout.strip()
                fields = []
                while remaining:
                    item, end = decoder.raw_decode(remaining)
                    fields.append(item)
                    remaining = remaining[end:].strip()
                ident, names, operating_system, arch, layers = fields
                record.update(image_id=ident, platform=f'{operating_system}/{arch}',
                              layers=layers, verified=ident in image['allowed_engine_ids']
                              and image['reference'] in names and (operating_system, arch) == ('linux', 'amd64')
                              and layers == image['diff_ids'])
            result['passed'] = len(result['images']) == len(review['images']) and all(
                item['verified'] for item in result['images']
            )
        except Exception as failure:
            result['error_type'] = type(failure).__name__
        finally:
            seconds = max(0., time.perf_counter()-start-nested)
            repo.finish_operation(wrapper, elapsed_seconds=seconds,
                                  resources=ResourceVector(latency_ms=seconds*1000))
            result['accounting_uncertain'] = bool(store._connection.execute(
                "SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",
                (grant.authorization_id,)
            ).fetchone())
            result['grant_counters'] = list(store._connection.execute(
                'SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',
                (grant.authorization_id,)
            ).fetchone())
            result['free_bytes_after'] = shutil.disk_usage(ROOT).free
            write(out/'summary.json', result)
            write(out/'operation-ledger.json', repo.operation_ledger(request.plan_id).model_dump(mode='json'))


asyncio.run(acquire())
print(json.dumps({k: v for k, v in result.items() if k != 'images'}))
raise SystemExit(not result['passed'] or result['accounting_uncertain'])
