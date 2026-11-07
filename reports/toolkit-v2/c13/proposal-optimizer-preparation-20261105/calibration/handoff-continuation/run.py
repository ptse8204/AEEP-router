"""Charge and record the first offline AFlow calibration handoff."""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.execution import ExecutionEvidence, persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, StrictModel, ValidationSpec, utc_now
from aeep.store import ReceiptStore
from aeep.validators import ValidationContext, run_validators

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'handoff'))
from baseline import Workflow

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]


class Scope(StrictModel):
    review_sha256: str


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value, mode=0o644):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode), 'w') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


async def grade(review):
    baseline = Workflow()
    data = read(review['protected_reference'])
    assert data['case_sha256'] == sha(review['public_cases'])
    public = read(review['public_cases'])['cases']
    assert len(public) == len(data['definitions']) == 3
    results = []
    for case, definition in zip(public, data['definitions'], strict=True):
        assert case['id'] == definition['case_id']
        assert content_digest(case['input']) == definition['input_sha256']
        value = await baseline(**case['input'])
        spec = ValidationSpec.model_validate(definition['validator'])
        validated, = await run_validators([spec], ValidationContext(case['input'], value), {}, raise_errors=True)
        results.append({'case_id': case['id'], 'passed': validated.valid})
    assert [row['passed'] for row in results] == [True, True, False]
    return {'observations': results, 'passed': sum(row['passed'] for row in results), 'cases': len(results),
            'recipe_sha256': data['recipe_sha256'], 'reference_sha256': sha(review['protected_reference'])}


def docker(review, *args):
    return subprocess.check_output([*review['docker'], *args], text=True,
                                   env=review['environment'], timeout=15).strip()


def container_absent(review):
    return not docker(review, 'ps', '-aq', '--filter', 'name=^/' + review['container_name'] + '$')


def preflight(review, identity):
    assert datetime.fromisoformat(review['expires_at']) > utc_now()
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    assert verification_source_digest(ROOT) == review['source_sha256']
    assert all(sha(path) == digest for path, digest in review['assets'].items())
    assert not Path(review['work']).exists() and not (HERE / 'started.json').exists()
    assert docker(review, 'version', '--format', '{{.Server.Version}} {{.Server.GitCommit}}').split() == review['engine']
    observed = docker(review, 'image', 'inspect', '--format', '{{.Id}} {{.Architecture}} {{json (index .Config "Volumes")}}', review['image'])
    assert observed.split() == [review['image'], 'arm64', 'null']
    assert container_absent(review)
    assert sha(review['terminal_review']) == review['terminal_review_sha256']
    assert Path(review['terminal_work']).is_dir() and not any(Path(review['terminal_work']).iterdir())
    with sqlite3.connect(Path(review['ledger']).as_uri() + '?mode=ro', uri=True) as connection:
        assert connection.execute("SELECT 1 FROM assessment_grants WHERE id=?", (review['authorization_id'],)).fetchone() is None
        assert connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=?", (review['authorization_id'],)).fetchone() is None
    assert sha(HERE / 'operation-review.json') == identity


def register_scope(repo, review, identity):
    scope = Scope(review_sha256=identity)
    ref = content_digest(scope)
    grant = AssessmentAuthorization(
        authorization_id=review['authorization_id'],
        subject_digests=[ref], recipe_digests=[ref], environment_digests=[ref],
        limits=AssessmentLimits(max_operations=2, max_elapsed_seconds=80),
        expires_at=datetime.fromisoformat(review['expires_at']), allowed_destinations=['local'], remote_disclosure=False,
    )
    plan = RecipeMaterializationRequest(
        plan_id=grant.authorization_id, subject_digest=ref, recipe_digest=ref, mapping_digest=ref,
        environment_digest=ref, authorization_id=grant.authorization_id, definition_digests=[ref], seed=0,
    )
    assert repo.put('toolkit_aflow_calibration_scope', ref, scope) == ref
    repo.approve_bundle(grant, {ref: scope.model_dump(mode='json')})
    repo.authorize(plan)
    return plan


async def execute(review, identity):
    preflight(review, identity)
    assert read(HERE / 'operator-approval.json') == {'approved': True, 'review_sha256': identity}
    work = Path(review['work'])
    work.mkdir(mode=0o700)
    write(HERE / 'started.json', {'review_sha256': identity, 'automatic_retries': False})
    result = {'review_sha256': identity, 'passed': False, 'models': 0, 'provider_disclosure': False}
    with ReceiptStore(review['ledger']) as store:
        repo = AssessmentRepository(store)
        plan = register_scope(repo, review, identity)
        try:
            result['stage'] = 'protected initial grade'
            operation = plan.plan_id + ':initial-grade'
            repo.reserve(plan, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=10),
                         stage='aflow_protected_initial_grade')
            began = time.perf_counter()
            try:
                observation = await grade(review)
                write(HERE / 'initial-grade.json', observation)
                seed = {'grade_sha256': sha(HERE / 'initial-grade.json'),
                        'cases': observation['cases'], 'passed': observation['passed']}
                write(work / 'grade.json', seed, mode=0o444)
                result['initial_grade'] = seed
            finally:
                repo.finish_operation(operation, elapsed_seconds=time.perf_counter() - began)
            result['stage'] = 'actual optimizer proposal capture'
            operation = plan.plan_id + ':capture'
            repo.reserve(plan, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=70),
                         stage='aflow_optimizer_proposal_capture')
            spec = ExecutorSpec(id='aflow.calibration.capture', capability='toolkit.upstream-engineering@1',
                kind='command', description='Capture the bounded AFlow proposal request locally', side_effect='write',
                config={'argv': review['argv'], 'argv_literal': True, 'inherit_env': False,
                        'env': review['environment'], 'timeout_seconds': 60,
                        'max_output_bytes': 49152, 'output': {'type': 'json'}})
            executor = CommandExecutor()
            started, began = utc_now(), time.perf_counter()
            evidence_ref = error_type = None
            try:
                with persist_execution_events(lambda key, event: repo.put('execution_event', key + ':' + str(event.sequence), event)):
                    handle = await executor.start(ExecutionContext(
                        request=ActionRequest(action_id=operation, capability=spec.capability),
                        spec=spec, estimate=spec.estimate, attempt=1, attempt_id=operation,
                        approved_side_effect=spec.side_effect,
                        invocation_check=lambda: (repo.authorize(plan), identity)[1],
                    ))
                    raw = await handle.task
                evidence = ExecutionEvidence.model_validate(raw.metadata['execution_evidence'])
                evidence_ref = repo.put('execution_evidence', evidence.digest(), evidence)
                if raw.exit_code != 0:
                    result['guest_exit'] = raw.exit_code
                    result['stderr_sha256'] = hashlib.sha256((raw.stderr or '').encode()).hexdigest()
                    result['diagnostic_categories'] = [
                        name for name in ('AssertionError', 'ModuleNotFoundError', 'PermissionError',
                                          'KeyError', 'IndexError', 'ValueError', 'RuntimeError')
                        if name in (raw.stderr or '')
                    ]
                assert raw.exit_code == 0 and evidence.complete
                observed = raw.output
                prompt = observed['request']
                assert len(prompt.encode()) <= 32768 and 'class Workflow:' in prompt
                digest = hashlib.sha256(prompt.encode()).hexdigest()
                assert digest == observed['request_sha256']
                assert observed['initial_grade_sha256'] == seed['grade_sha256']
                assert observed['upstream_optimizer_executed'] and observed['proposal_requests'] == 1
                assert observed['models'] == 0 and not observed['generated_code_executed']
                assert observed['boundary']['inherited_sockets'] == 0 and observed['boundary']['local_unix_pair_verified']
                assert container_absent(review)
                write(work / 'request.json', {'request': prompt, 'sha256': digest}, mode=0o600)
                result.update(passed=True, stage='complete', request_sha256=digest, request_bytes=len(prompt.encode()),
                              proposal_requests=1, boundary=observed['boundary'], generated_code_executed=False)
            except Exception as error:
                error_type = type(error).__name__
                raise
            finally:
                await executor.close()
                elapsed = time.perf_counter() - began
                receipt = ExecutionReceipt(decision_id=operation, action_id=operation, capability=spec.capability,
                    executor_id=spec.id, executor_kind=spec.kind, status='success' if result['passed'] else 'failed',
                    started_at=started, ended_at=utc_now(), estimated=spec.estimate, execution_success=result['passed'],
                    error_type=error_type, actual_resources=ResourceVector(latency_ms=elapsed * 1000),
                    metadata={'execution_evidence_ref': evidence_ref, 'review_sha256': identity})
                store.save_receipt(receipt)
                repo.finish_operation(operation, elapsed_seconds=elapsed, resources=receipt.actual_resources)
                write(HERE / 'capture-receipt.json', receipt.model_dump(mode='json'))
        except Exception as error:
            result.update(passed=False, error_type=type(error).__name__)
        finally:
            result['cleanup_verified'] = container_absent(review)
            result['passed'] = result['passed'] and result['cleanup_verified']
            write(HERE / 'ledger.json', repo.operation_ledger(plan.plan_id).model_dump(mode='json'))
            write(HERE / 'result.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--preflight')
    flags.add_argument('--execute-approved')
    args = parser.parse_args()
    review_path = HERE / 'operation-review.json'
    digest = sha(review_path)
    assert digest == (args.preflight or args.execute_approved)
    review = read(review_path)
    if args.preflight:
        preflight(review, digest)
        print(json.dumps({'review_sha256': digest, 'passed': True, 'models': 0, 'containers_started': 0}))
    else:
        result = asyncio.run(execute(review, digest))
        print(json.dumps(result))
        raise SystemExit(not result['passed'])
