"""One first-party canary for the contained worker carrier, with no upstream test execution."""

import argparse
import asyncio
import json
import re
import runpy
import time
from datetime import datetime, timedelta
from pathlib import Path

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
original = runpy.run_path(str(HERE / 'run-calibration.py'))
read, sha, save = (original[key] for key in ('read', 'sha', 'save'))
DELEGATION = original['DELEGATION']
OUT = HERE / 'bootstrap'
REVIEW = OUT / 'operation-review.json'
GRANT = 'skillsbench-prefix-cache-bootstrap-canary-20261109'
MARKERS = {
    'aeep_import': r'no module named [\'"]?aeep',
    'pydantic_import': r'no module named [\'"]?pydantic',
    'psutil_import': r'no module named [\'"]?psutil',
    'python_import': r'\b(?:ImportError|ModuleNotFoundError)\b',
    'python_permission': r'\bPermissionError\b|permission denied',
    'python_validation': r'\bValidationError\b',
    'python_configuration': r'\bConfigurationError\b',
    'python_missing_file': r'\bFileNotFoundError\b|no such file or directory',
    'python_json_decode': r'\bJSONDecodeError\b',
    'python_process_limit': r'\bBlockingIOError\b|resource temporarily unavailable',
    'unsupported_exec': r'exec format error|unsupported platform',
    'rosetta': r'\bros(etta)?\b',
    'read_only': r'read-only file system',
    'python_assertion': r'\bAssertionError\b',
}


def markers(stream):
    return sorted(key for key, pattern in MARKERS.items()
                  if isinstance(stream, str) and re.search(pattern, stream[:16384], re.IGNORECASE))


def definition():
    prior = read(HERE / 'calibration-review.json')
    original['preflight'](prior | {'expires_at': (utc_now() + timedelta(minutes=1)).isoformat()})
    evidence = read(HERE / 'continuation/result.json')
    assert evidence['accounting_settled'] and evidence['operations'] == 1 and not evidence['cases']
    env = original['checked_environment']()
    context = original['context']('reference')
    guest = context.spec.model_copy(update={'config': context.spec.config | {
        'argv': ['/usr/bin/python3', '-I', '-B', '-c', 'print("{}")'],
        'timeout_seconds': 15,
    }})
    context.spec = guest
    context.attempt_id = GRANT
    context.request = ActionRequest(action_id=GRANT, capability=guest.capability)
    argv, name = ContainerExecutor(env).command(context)
    assert argv[argv.index('--network') + 1] == 'none' and '--pull=never' in argv
    assert '--read-only' in argv and all(item.endswith(',readonly') for item in argv if item.startswith('type=bind,'))
    assert original['container_absent'](env, name)
    assert '--entrypoint' in argv and argv[-2:] == ['-m', 'aeep.assessment.container_worker']
    host = ExecutorSpec(id='skillsbench.prefix-cache.bootstrap', capability='assessment.skillsbench.prefix-cache@1',
        kind='command', description='Fixed first-party carrier bootstrap canary', side_effect='write',
        config={'argv': argv, 'argv_literal': True, 'stdin_json': True, 'inherit_env': False,
                'timeout_seconds': 20, 'max_output_bytes': 16384, 'output': {'type': 'json'}})
    payload = {'request': context.request.model_dump(mode='json'), 'spec': guest.model_dump(mode='json'),
               'attempt': 1, 'attempt_id': GRANT, 'approved_side_effect': guest.side_effect.value}
    return env, host, payload, name


def freeze():
    OUT.mkdir()
    env, host, payload, name = definition()
    pins = [Path(__file__).resolve(), HERE / 'run-calibration.py', HERE / 'calibration-review.json',
            HERE / 'continuation/result.json', DELEGATION, Path(env.container_runtime)]
    assert markers("ModuleNotFoundError: No module named 'pydantic'\nother data") == ['pydantic_import', 'python_import']
    save(REVIEW, {'purpose': 'One first-party canary for the ordinary protected carrier bootstrap.',
        'pins': {str(p): sha(p) for p in pins}, 'container': name, 'image': env.container_image,
        'carrier_sha256': content_digest(host), 'payload_sha256': content_digest(payload),
        'maximum_operations': 1, 'maximum_reserved_seconds': 40,
        'network': False, 'upstream_task_execution': False, 'models': 0, 'cash_usd': '0',
        'automatic_retries': False, 'expires_at': (utc_now() + timedelta(hours=12)).isoformat()})
    save(OUT / 'authority.json', {'review_sha256': sha(REVIEW), 'first_canary': True, 'authority_sha256': sha(DELEGATION)})
    print(sha(REVIEW))


async def execute(digest):
    review = read(REVIEW)
    assert sha(REVIEW) == digest
    assert read(OUT / 'authority.json') == {'review_sha256': digest, 'first_canary': True, 'authority_sha256': sha(DELEGATION)}
    assert not (OUT / 'started.json').exists()

    def check():
        assert utc_now() < datetime.fromisoformat(review['expires_at'])
        assert all(sha(path) == h for path, h in review['pins'].items())
        env, host, payload, name = definition()
        assert content_digest(host) == review['carrier_sha256'] and content_digest(payload) == review['payload_sha256']
        assert env.container_image == review['image'] and name == review['container']
        return env, host, payload, name

    env, host, payload, name = check()
    path = original['PRIVATE'] / 'bootstrap.sqlite3'
    assert not path.exists()
    scope = original['Scope'](review_sha256=digest)
    ref = content_digest(scope)
    limits = AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=40)
    request = RecipeMaterializationRequest(plan_id=GRANT, subject_digest=ref, recipe_digest=ref,
        environment_digest=ref, mapping_digest=ref, authorization_id=GRANT, definition_digests=[ref], seed=0)
    save(OUT / 'started.json', {'review_sha256': digest, 'models': 0})
    result = {'review_sha256': digest, 'models': 0, 'upstream_task_executed': False}
    with ReceiptStore(str(path)) as store:
        repo = AssessmentRepository(store)
        assert repo.put('toolkit_skillsbench_prefix_bootstrap_scope', ref, scope) == ref
        repo.approve_bundle(AssessmentAuthorization(authorization_id=GRANT, subject_digests=[ref],
            recipe_digests=[ref], environment_digests=[ref], allowed_destinations=['local'],
            remote_disclosure=False, expires_at=datetime.fromisoformat(review['expires_at']), limits=limits),
            {ref: scope.model_dump(mode='json')})
        repo.reserve(request, GRANT, limits, stage='carrier_bootstrap')
        started, clock = utc_now(), time.monotonic()
        runner = CommandExecutor()

        def authorize():
            repo.authorize(request)
            check()
            return digest

        try:
            raw = await runner.execute(ExecutionContext(
                request=ActionRequest(action_id=GRANT, capability=host.capability, input=payload), spec=host,
                estimate=host.estimate, attempt=1, attempt_id=GRANT, approved_side_effect=host.side_effect,
                invocation_check=authorize))
            result.update(exit_code=raw.exit_code, error_type=raw.error_type, stderr_categories=markers(raw.stderr))
            result['canary_passed'] = (raw.status.value == 'success' and isinstance(raw.output, dict)
                                       and raw.output.get('status') == 'success' and raw.output.get('output') == {})
            if isinstance(raw.output, dict):
                result['inner_error_type'] = raw.output.get('error_type')
        except Exception as error:
            result.update(canary_passed=False, error_type=type(error).__name__)
        finally:
            await runner.close()
            if not original['container_absent'](env, name):
                await ContainerExecutor(env).cleanup(GRANT)
            result['cleanup_confirmed'] = original['container_absent'](env, name)
            elapsed = time.monotonic() - clock
            result['elapsed_seconds'] = elapsed
            receipt = ExecutionReceipt(decision_id=GRANT, action_id=GRANT, capability=host.capability,
                executor_id=host.id, executor_kind=host.kind, status='success' if result['canary_passed'] else 'failed',
                started_at=started, ended_at=utc_now(), estimated=host.estimate,
                actual_resources=ResourceVector(latency_ms=elapsed*1000), execution_success=result['canary_passed'],
                error_type=result.get('error_type'), metadata={'observation': result,
                    'review_sha256': digest, 'observed_resource_dimensions': ['latency_ms']})
            store.save_receipt(receipt)
            repo.finish_operation(GRANT, elapsed_seconds=elapsed, resources=receipt.actual_resources)
            save(OUT / 'receipt.json', receipt.model_dump(mode='json'))
            save(OUT / 'result.json', result | {'accounting_settled': True})
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--freeze', action='store_true')
    group.add_argument('--execute-delegated')
    options = parser.parse_args()
    if options.freeze:
        freeze()
    else:
        asyncio.run(execute(options.execute_delegated))
