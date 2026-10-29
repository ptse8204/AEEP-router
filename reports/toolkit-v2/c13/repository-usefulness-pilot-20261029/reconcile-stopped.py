"""Reconcile a stopped controller without replaying any source or model call."""
import asyncio
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess

from pydantic import model_serializer
from aeep.assessment.containment import container_name
from aeep.assessment.models import content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.recovery import recover
from aeep.models import ExecutionReceipt, StrictModel
from aeep.router import Router

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']


class Document(StrictModel):
    value: dict

    @model_serializer(mode='plain')
    def document(self):
        return self.value


async def main():
    model = json.loads((HERE / 'model-result.json').read_text())
    start = json.loads((HERE / 'execution-started.json').read_text())
    proposal = json.loads((HERE / 'collector-definitions.json').read_text())
    review = json.loads((HERE / 'operation-review.json').read_text())
    assert not model['completed'] and model['error_type'] == 'RuntimeError'
    assert model['error_message'] == 'Incomplete execution/grading/prompt/cleanup evidence; stop dispatch'
    assert model['proxy_restored_stopped'] and model['source_unchanged']
    assert len(model['records']) == 3
    names = set(subprocess.check_output([*DOCKER, 'ps', '-a', '--format', '{{.Names}}'], text=True).splitlines())
    for image in review['model_worker_images']:
        assert not subprocess.check_output([*DOCKER, 'ps', '-a', '--filter', 'ancestor=' + image, '--format', '{{.Names}}'], text=True).strip()
    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    repo = service.repository
    try:
        recovery = await recover(service, model['assessment_id'])
        assert recovery.retained_attempt_ids == [] and recovery.containers_removed == 0
        plans = {request['plan_id'] for request in proposal['requests']} | {model['plan_id']}
        grader_count = 0
        for plan in plans:
            for path in (service.directory / plan / 'recipe-operations').glob('*.sqlite3'):
                with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
                    for raw, in connection.execute('SELECT payload_json FROM receipts'):
                        receipt = ExecutionReceipt.model_validate_json(raw)
                        attempt = receipt.metadata['attempt_id']
                        assert connection.execute('SELECT state FROM execution_attempts WHERE attempt_id=?', (attempt,)).fetchone()[0] == 'COMPLETED'
                        assert container_name(attempt) not in names
                        assert content_digest(repo.get('recipe_receipt', receipt.receipt_id)) == content_digest(receipt)
                        grader_count += 1
        campaign = service.directory / model['plan_id'] / 'campaign.sqlite3'
        censored = set()
        with sqlite3.connect(campaign.as_uri() + '?mode=ro', uri=True) as connection:
            for trial_id, raw in connection.execute('SELECT trial_id,payload_json FROM trial_receipts'):
                receipt = ExecutionReceipt.model_validate_json(raw)
                saved = model['records'][trial_id]
                assert saved['receipt_ref'] == content_digest(receipt)
                assert saved['worker_cleanup_confirmed'] and saved['token_capture']['status'] == 'verified'
                path = Path(connection.execute('SELECT database_path FROM trial_stores WHERE trial_id=?', (trial_id,)).fetchone()[0])
                with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as original:
                    assert original.execute('SELECT state FROM execution_attempts WHERE attempt_id=?', (receipt.metadata['attempt_id'],)).fetchone()[0] == 'COMPLETED'
                trial = json.loads(connection.execute('SELECT payload_json FROM trials WHERE trial_id=?', (trial_id,)).fetchone()[0])
                censored.add(trial['case_id'].removeprefix('development-'))
        operation = model['assessment_id'] + ':report'
        pending = [item for plan in plans for item in repo.operation_ledger(plan).operations if item.elapsed_seconds is None]
        assert len(pending) == 1 and pending[0].operation_id == operation and pending[0].stage == 'report_generation'
        assert service.status(model['assessment_id'])['report_id'] is None
        # This exact gate exception propagates from trial execution before the report body's clock starts.
        service_source = (ROOT / 'src/aeep/assessment/service.py').read_text()
        assert service_source.index('except BaseException:', service_source.index('campaign = await runner.run(plan.suite)')) < service_source.index('report = fit_report(plan, recipe, campaign, ledger=ledger)')
        proof = {'basis': 'Known unstarted report body,not missing telemetry. The exact per-trial gate RuntimeError propagated through the source-bound BaseException branch before report-generation code or its clock began.',
            'operation_id': operation, 'report_body_started': False, 'elapsed_body_work_seconds': 0,
            'operation_allowance_retained': True, 'model_turn_allowances_retained': 3,
            'actual_report_not_created': True, 'source_digest': review['source_digest'],
            'gate_sha256': hashlib.sha256((HERE / 'trial-evidence.py').read_bytes()).hexdigest(),
            'recovery_record_digest': content_digest(recovery)}
        repo.put('operator_reconciliation', operation, Document(value=proof))
        repo.finish_operation(operation, elapsed_seconds=0)
        operations = [item for plan in plans for item in repo.operation_ledger(plan).operations]
        assert all(item.elapsed_seconds is not None for item in operations)
        after = list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        charged = sum(item.elapsed_seconds for item in operations)
        assert len(operations) == after[0] - start['grant_before'][0]
        assert math.isclose(charged, after[2] - start['grant_before'][2], abs_tol=1e-6)
        result = {'passed': True, 'source_unchanged': True, 'recovery': recovery.model_dump(mode='json'),
            'completed_canonical_grader_chains': grader_count, 'completed_canonical_task_chains': 3,
            'engineering_censored_cases': sorted(censored), 'task_value_observations': 0,
            'cumulative_operations': len(operations), 'model_turns_charged': 3,
            'charged_operation_seconds': charged, 'all_operations_complete': True,
            'unused_report_reservation_settled_from_verified_unstarted_body': proof,
            'all_owned_workers_graders_absent': True, 'proxy_stopped': True,
            'grant_before': start['grant_before'], 'grant_after': after,
            'no_invocation_retried_or_model_allowance_refunded': True}
        with (HERE / 'stopped-accounting-audit.json').open('x') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
        print(json.dumps({key: value for key, value in result.items() if key not in ('recovery', 'unused_report_reservation_settled_from_verified_unstarted_body')}))
    finally:
        await router.close()


if __name__ == '__main__':
    asyncio.run(main())
