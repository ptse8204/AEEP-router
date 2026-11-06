"""Run one no-network Sales carrier diagnostic and retain canonical accounting."""

import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from aeep.assessment.models import (
    AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.hosts.workers import ARTIFACT_PROGRAM
from aeep.models import ActionRequest, ExecutionReceipt, ResourceVector, SideEffect, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREVIOUS = HERE.parent / 'skillsbench-managed-worker-preparation-20261105'
IDENTITY = HERE.name


class Definition(StrictModel):
    review_sha256: str
    purpose: str


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with (HERE / path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def review():
    previous = read(PREVIOUS / 'engineering-dispatch-review.json')
    tool = read(PREVIOUS / 'build-review.json')
    name = 'aeep-' + hashlib.sha256(IDENTITY.encode()).hexdigest()[:32]
    return {'purpose': 'First synthetic artifact carrier check in the exact retained Sales image.',
            'authority_sha256': sha(HERE.parent / 'pipeline-standing-authority-20261104.json'),
            'worker_image': previous['worker_image_ids']['sales-candidate'], 'container_name': name,
            'source_sha256': previous['source_sha256'], 'ledger': tool['ledger'],
            'docker': tool['docker'], 'docker_socket': tool['docker_socket'], 'docker_config': tool['docker_config'],
            'expires_at': tool['expires_at'], 'maximum_operations': 1, 'maximum_reserved_seconds': 35,
            'models': 0, 'cash_usd': '0', 'network': 'none',
            'only_temporary_owned_container_is_disposable': True,
            'artifact_program_sha256': hashlib.sha256(ARTIFACT_PROGRAM.encode()).hexdigest(),
            'pins': {str(path): sha(path) for path in (
                HERE / 'probe.py', HERE / 'run.py', PREVIOUS / 'engineering-dispatch-review.json',
                PREVIOUS / 'engineering-sales-trial-audit.json', Path(tool['docker']),
                Path(tool['docker_config']) / 'config.json',
            )}}


async def execute(pinned, identity):
    assert pinned == review() and verification_source_digest(ROOT) == pinned['source_sha256']
    assert datetime.now(UTC) < datetime.fromisoformat(pinned['expires_at'])
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    authority = read(HERE.parent / 'pipeline-standing-authority-20261104.json')
    assert authority['first_attempts'].startswith('Concrete finite') and pinned['models'] == 0
    docker = [pinned['docker'], '--config', pinned['docker_config'], '--host', 'unix://' + pinned['docker_socket']]
    image, name = pinned['worker_image'], pinned['container_name']
    env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}

    def metadata(*args):
        return subprocess.check_output([*docker, *args], timeout=10, text=True, env=env).strip()

    assert metadata('image', 'inspect', '--format', '{{.Id}}', image) == image
    assert not metadata('ps', '-aq', '--filter', 'name=^/'+name+'$')
    argv = [*docker, 'run', '--pull=never', '--rm', '--name', name,
            '--label', 'com.aeep.engineering.owner='+IDENTITY,
            '--network=none', '--user=65534:65534', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--cpus=1', '--memory=256m',
            '--memory-swap=256m', '--pids-limit=32',
            '--tmpfs', '/workspace:rw,noexec,nosuid,nodev,size=4m,mode=1777',
            '--entrypoint', 'python3', image, '-I', '-B', '-c', (HERE/'probe.py').read_text(), ARTIFACT_PROGRAM]
    from aeep.models import ExecutorSpec

    spec = ExecutorSpec(id='skillsbench.sales.artifact-diagnostic', capability='toolkit.upstream-engineering@1',
        description='Transfer synthetic bytes with the exact existing worker protocol', kind='command',
        config={'argv': argv, 'argv_literal': True, 'inherit_env': False, 'env': env,
                'timeout_seconds': 25, 'max_output_bytes': 4096, 'output': {'type': 'json'}})
    scope = Definition(review_sha256=identity, purpose=pinned['purpose'])
    reference = content_digest(scope)
    limit = AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=35)
    grant = AssessmentAuthorization(authorization_id=IDENTITY, subject_digests=[reference],
        recipe_digests=[reference], environment_digests=[reference], limits=limit,
        remote_disclosure=False, allowed_destinations=['local'], expires_at=datetime.fromisoformat(pinned['expires_at']))
    request = RecipeMaterializationRequest(plan_id=IDENTITY, subject_digest=reference, recipe_digest=reference,
        mapping_digest=reference, environment_digest=reference, authorization_id=IDENTITY,
        definition_digests=[reference], seed=0)
    write('started.json', {'review_sha256': identity, 'actual_model_authority': 0})
    with ReceiptStore(pinned['ledger']) as store:
        repo = AssessmentRepository(store)
        assert repo.put('toolkit_skillsbench_artifact_diagnostic', reference, scope) == reference
        repo.approve_bundle(grant, {reference: scope.model_dump(mode='json')})
        operation = IDENTITY + ':offline-artifact'
        repo.reserve(request, operation, limit, stage='skillsbench_offline_artifact_diagnostic')
        started = utc_now()
        clock = time.perf_counter()
        engine = CommandExecutor()
        raw = None
        error = None
        cleaned = False
        try:
            raw = await engine.execute(ExecutionContext(
                request=ActionRequest(action_id=operation, capability=spec.capability), spec=spec,
                estimate=spec.estimate, attempt=1, attempt_id=operation, approved_side_effect=SideEffect.READ))
        except Exception as exc:
            error = type(exc).__name__
        finally:
            await engine.close()
            leftover = metadata('ps', '-aq', '--filter', 'name=^/'+name+'$')
            if leftover:
                actual = metadata('inspect', '--format',
                    '{{.Image}} {{index .Config.Labels "com.aeep.engineering.owner"}}', name)
                if actual == image+' '+IDENTITY:
                    metadata('stop', '--time', '2', name)
            cleaned = not metadata('ps', '-aq', '--filter', 'name=^/'+name+'$')
            resources = ResourceVector(latency_ms=(time.perf_counter() - clock)*1000)
            passed = bool(raw and raw.status.value == 'success' and cleaned)
            receipt = ExecutionReceipt(decision_id=operation, action_id=operation, capability=spec.capability,
                executor_id=spec.id, executor_kind='command', status='success' if passed else 'failed',
                started_at=started, ended_at=utc_now(), estimated={}, actual_resources=resources,
                execution_success=passed, error_type=error or (raw.error_type if raw else None),
                metadata={'review_sha256': identity, 'image': image, 'owned_container_cleaned': cleaned})
            store.save_receipt(receipt)
            if cleaned:
                repo.finish_operation(operation, elapsed_seconds=resources.latency_ms/1000, resources=resources)
            result = {'passed': passed, 'observed': raw.output if passed else None, 'model_turns': 0,
                      'original_failure_cause_known': False, 'receipt_id': receipt.receipt_id,
                      'elapsed_seconds': resources.latency_ms/1000, 'owned_container_cleaned': cleaned}
            write('result.json', result)
            print(json.dumps(result))
    return not passed


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--execute')
    args = parser.parse_args()
    path = HERE / 'operation-review.json'
    if args.prepare:
        write(path.name, review())
        print(sha(path))
    elif args.execute == sha(path) and not (HERE / 'started.json').exists():
        raise SystemExit(asyncio.run(execute(read(path), args.execute)))
    else:
        raise SystemExit('Exact unstarted review required.')
