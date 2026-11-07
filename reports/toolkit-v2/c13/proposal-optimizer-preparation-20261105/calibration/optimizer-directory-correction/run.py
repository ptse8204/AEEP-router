"""Resume the AFlow capture from the existing protected grade."""

import argparse
import asyncio
import hashlib
import json
import runpy
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.execution import ExecutionEvidence, persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
SUPPORT = runpy.run_path(HERE.parent / 'handoff-continuation/run.py')
read, write, sha = (SUPPORT[name] for name in ('read', 'write', 'sha'))
docker, container_absent = (SUPPORT[name] for name in ('docker', 'container_absent'))


class Scope(StrictModel):
    review_sha256: str


def preflight(review):
    assert datetime.fromisoformat(review['expires_at']) > utc_now()
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    assert verification_source_digest(ROOT) == review['source_sha256']
    assert all(sha(path) == digest for path, digest in review['assets'].items())
    assert not Path(review['work']).exists() and not (HERE / 'started.json').exists()
    assert docker(review, 'version', '--format', '{{.Server.Version}} {{.Server.GitCommit}}').split() == review['engine']
    observed = docker(review, 'image', 'inspect', '--format', '{{.Id}} {{.Architecture}} {{json (index .Config "Volumes")}}', review['image'])
    assert observed.split() == [review['image'], 'arm64', 'null']
    assert container_absent(review)
    prior_operations = [op for path in review['terminal_ledgers'] for op in read(path)['operations']]
    assert len(prior_operations) == review['prior_operations'] == 3
    grade = read(review['grade_receipt'])
    seed = read(review['grade_seed'])
    assert seed == {'grade_sha256': sha(review['grade_receipt']), 'cases': grade['cases'], 'passed': grade['passed']}
    with sqlite3.connect(Path(review['ledger']).as_uri() + '?mode=ro', uri=True) as connection:
        assert connection.execute("SELECT 1 FROM assessment_grants WHERE id=?", (review['authorization_id'],)).fetchone() is None
        for op in prior_operations:
            row = connection.execute(
                "SELECT state FROM assessment_operations WHERE id=?", (op['operation_id'],),
            ).fetchone()
            assert row == ('complete',) and op['elapsed_seconds'] is not None


def register_scope(repo, review, identity):
    scope = Scope(review_sha256=identity)
    ref = content_digest(scope)
    grant = AssessmentAuthorization(
        authorization_id=review['authorization_id'],
        subject_digests=[ref], recipe_digests=[ref], environment_digests=[ref],
        limits=AssessmentLimits(max_operations=1, max_elapsed_seconds=70),
        expires_at=datetime.fromisoformat(review['expires_at']), allowed_destinations=['local'], remote_disclosure=False,
    )
    plan = RecipeMaterializationRequest(
        plan_id=grant.authorization_id, subject_digest=ref, recipe_digest=ref,
        mapping_digest=ref, environment_digest=ref, authorization_id=grant.authorization_id, definition_digests=[ref], seed=0,
    )
    assert repo.put('toolkit_aflow_calibration_scope', ref, scope) == ref
    repo.approve_bundle(grant, {ref: scope.model_dump(mode='json')})
    repo.authorize(plan)
    return plan, grant.limits


def guest_payload(raw):
    if isinstance(raw.output, dict):
        return raw.output
    if isinstance(raw.stdout, str) and len(raw.stdout.encode()) <= 49152:
        try:
            parsed = json.loads(raw.stdout)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


async def execute(review, identity):
    preflight(review)
    assert read(HERE / 'operator-approval.json') == {'approved': True, 'review_sha256': identity}
    work = Path(review['work'])
    work.mkdir(mode=0o700)
    write(HERE / 'started.json', {'review_sha256': identity, 'automatic_retries': False})
    result = {'review_sha256': identity, 'passed': False, 'models': 0, 'provider_disclosure': False,
              'initial_grade_sha256': sha(review['grade_receipt']), 'initial_grade_replayed': False}
    with ReceiptStore(review['ledger']) as store:
        repo = AssessmentRepository(store)
        plan, limits = register_scope(repo, review, identity)
        operation = plan.plan_id + ':capture'
        repo.reserve(plan, operation, limits, stage='aflow_optimizer_formatted_request_capture')
        spec = ExecutorSpec(id='aflow.calibration.capture', capability='toolkit.upstream-engineering@1',
            kind='command', description='Capture the AFlow formatted optimizer request once', side_effect='write',
            config={'argv': review['argv'], 'argv_literal': True, 'inherit_env': False,
                    'env': review['environment'], 'timeout_seconds': 60,
                    'max_output_bytes': 49152, 'output': {'type': 'json'}})
        executor = CommandExecutor()
        started, began = utc_now(), time.perf_counter()
        evidence_ref = error_type = None
        try:
            with persist_execution_events(lambda key, event: repo.put('execution_event', key + ':' + str(event.sequence), event)):
                handle = await executor.start(ExecutionContext(
                    request=ActionRequest(action_id=operation, capability=spec.capability), spec=spec,
                    estimate=spec.estimate, attempt=1, attempt_id=operation,
                    approved_side_effect=spec.side_effect, invocation_check=lambda: (repo.authorize(plan), identity)[1],
                ))
                raw = await handle.task
            evidence = ExecutionEvidence.model_validate(raw.metadata['execution_evidence'])
            evidence_ref = repo.put('execution_evidence', evidence.digest(), evidence)
            observed = guest_payload(raw)
            if raw.exit_code != 0:
                result['guest_exit'] = raw.exit_code
                result['stderr_sha256'] = hashlib.sha256((raw.stderr or '').encode()).hexdigest()
                if observed.get('status') == 'failed':
                    result['guest_diagnostic'] = {key: observed[key] for key in ('stage', 'error_type', 'locations')}
            assert raw.exit_code == 0 and evidence.complete and observed['status'] == 'request_ready'
            prompt = observed['request']
            assert len(prompt.encode()) <= 32768 and 'class Workflow:' in prompt
            digest = hashlib.sha256(prompt.encode()).hexdigest()
            assert digest == observed['request_sha256'] and observed['initial_grade_sha256'] == result['initial_grade_sha256']
            assert observed['upstream_optimizer_executed'] and observed['proposal_requests'] == 1
            assert observed['models'] == 0 and not observed['generated_code_executed']
            assert observed['boundary']['inherited_sockets'] == 0 and observed['boundary']['local_unix_pair_verified']
            assert container_absent(review)
            write(work / 'request.json', {'request': prompt, 'sha256': digest}, mode=0o600)
            result.update(passed=True, request_sha256=digest, request_bytes=len(prompt.encode()),
                          proposal_requests=1, boundary=observed['boundary'], generated_code_executed=False)
        except Exception as error:
            error_type = type(error).__name__
            result['error_type'] = error_type
        finally:
            await executor.close()
            elapsed = time.perf_counter() - began
            result['cleanup_verified'] = container_absent(review)
            result['passed'] = result['passed'] and result['cleanup_verified']
            receipt = ExecutionReceipt(decision_id=operation, action_id=operation, capability=spec.capability,
                executor_id=spec.id, executor_kind=spec.kind, status='success' if result['passed'] else 'failed',
                started_at=started, ended_at=utc_now(), estimated=spec.estimate, execution_success=result['passed'],
                error_type=error_type, actual_resources=ResourceVector(latency_ms=elapsed * 1000),
                metadata={'execution_evidence_ref': evidence_ref, 'review_sha256': identity})
            store.save_receipt(receipt)
            repo.finish_operation(operation, elapsed_seconds=elapsed, resources=receipt.actual_resources)
            write(HERE / 'receipt.json', receipt.model_dump(mode='json'))
            write(HERE / 'ledger.json', repo.operation_ledger(plan.plan_id).model_dump(mode='json'))
            write(HERE / 'result.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--preflight')
    flags.add_argument('--execute-approved')
    args = parser.parse_args()
    path = HERE / 'operation-review.json'
    identity = sha(path)
    assert identity == (args.preflight or args.execute_approved)
    review = read(path)
    if args.preflight:
        preflight(review)
        print(json.dumps({'review_sha256': identity, 'passed': True, 'models': 0, 'containers_started': 0}))
    else:
        result = asyncio.run(execute(review, identity))
        print(json.dumps(result))
        raise SystemExit(not result['passed'])
