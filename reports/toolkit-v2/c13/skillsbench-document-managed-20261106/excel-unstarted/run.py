"""Run only the unstarted Excel workflow from the settled document attempt."""

import argparse
import asyncio
import importlib.util
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from aeep.assessment.models import AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.models import utc_now

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / 'managed-engineering'
OVERHEAD_SECONDS = 90

spec = importlib.util.spec_from_file_location('approved_document_run', PARENT / 'run.py')
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
audit = parent.load('document_receipt_reconciliation', HERE / 'audit.py')


def verify(review, digest, original, engine, proxy):
    assert parent.sha(HERE / 'operation-review.json') == digest
    assert not (HERE / 'started.json').exists()
    parent.guard(original, review['parent_review_sha256'])
    assert all(parent.sha(path) == expected for path, expected in review['pins'].items())
    assert review['maximum_model_turns'] == 1 and review['maximum_cash_usd'] == '0'
    assert review['comparisons'] == 'PAUSED' and review['automatic_retries'] is False
    old = parent.read(PARENT / 'result.json')
    assert old['model_turns_reserved'] == 1 and old['proxy_restored_stopped']
    assert old['historical_reservations_preserved'] and not old['new_unresolved_reservations']
    ready = parent.read(PARENT / 'dispatch-ready.json')
    assert ready['zero_turn_workers_verified'] and ready['review_sha256'] == review['parent_review_sha256']
    assert ready['plans']['excel'] == old['plans']['excel'] == review['plan']
    invoice = parent.read(PARENT / 'invoice-reconciliation.json')
    assert invoice['plan_id'] == ready['plans']['invoice']['plan_id'] and invoice['job_state'] == 'complete'
    assert invoice['model_turn_count'] == 1 and invoice['worker_cleanup_confirmed']
    grant_helper = parent.load('read_only_grant_snapshot', parent.AFLOW)
    assert grant_helper.grant_snapshot(original['database']) == review['grant']
    assert list(review['grant']['counters']) == old['grant_after']
    assert engine.proxy_state(proxy) == original['proxy']
    for image in review['image_ids']:
        assert engine.docker('image', 'inspect', '--format', '{{.Id}}', image) == image


async def run(digest, *, execute):
    review = parent.read(HERE / 'operation-review.json')
    original = parent.read(PARENT / 'operation-review.json')
    engine = parent.load('document_managed_helpers', parent.PRIOR / 'run-engineering.py')
    proxy = parent.read(engine.PREVIOUS / 'operation-review.json')
    parent.configure(engine, original, {})
    engine.emit = lambda name, value: parent.write(HERE / name, value)
    verify(review, digest, original, engine, proxy)

    plan = engine.AssessmentPlan.model_validate_json((engine.WORK / 'excel-prepared/plan.json').read_bytes())
    expected = review['plan']
    ref = expected['execution_review_ref']
    source = original['source_sha256']
    case = next(item for item in original['cases'] if item['role'] == 'excel')
    assert plan.plan_id == expected['plan_id'] and content_digest(plan) == expected['plan_digest']
    assert [item.case_id for item in plan.suite.cases] == [case['task_id']]
    target = engine.WORK / 'excel-result'
    assert not target.exists() and not (engine.CAMPAIGNS / plan.plan_id).exists()
    with closing(sqlite3.connect(Path(original['database']).as_uri() + '?mode=ro', uri=True)) as connection:
        assert connection.execute('SELECT 1 FROM assessment_jobs WHERE plan_id=?', (plan.plan_id,)).fetchone() is None
    workflow = engine.WORK / 'excel-prepared/workflow.json'
    preview = engine.cli('plan', '--workflow', workflow, '--configuration', case['configuration'])
    assert not preview['blockers'] and preview['review_sha256'] == expected['workflow_review_sha256']
    assert preview['assessment']['backend_review']['plan_sha256'] == expected['plan_digest']
    router = engine.Router.from_manifest(engine.MANIFEST)
    service = engine.AssessmentService(router, engine.CAMPAIGNS)
    repo = service.repository
    try:
        initial = engine.previous.counters(repo)
        assert list(initial) == review['grant']['counters']
        assert not repo.operation_ledger(plan.plan_id).operations
        historical = engine.reserved(repo)
        engine.require_engineering_run(repo, ref, plan=plan, source_digest=source)
        service._verify_dependencies(plan)
        environment = engine.AssessmentEnvironment.model_validate(repo.get('environment', plan.environment_digest))
        pair = parent.WorkerPairInspection.model_validate(parent.read(case['pair']))
        boundaries = parent.read(engine.WORK / 'excel-readiness.json')['boundaries']
        assert set(boundaries) == {'control', 'treatment'}
        for role, result in boundaries.items():
            assert environment.conformance_digests[getattr(pair, role).id] == result['conformance_digest']
            assert result['observed_probe_count'] == 11
            record = engine.require_conformance(repo, result['conformance_digest'],
                source_digest=source, worker_digest=result['worker_digest'], identity_digest=result['identity_digest'])
            engine.require_candidate_access(repo, record, pair.differential, available=role == 'treatment')
        allowance = service.budget_preview(plan.plan_id)
        operations, turns, seconds = engine.measure_allowance(allowance)
        assert turns == 1 and allowance['campaign_allowance']['fits_remaining']
        needed = AssessmentLimits(max_operations=operations + 1, max_model_turns=1,
                                  max_elapsed_seconds=seconds + OVERHEAD_SECONDS)
        engine.budget.require_room(initial, initial, needed, review)
        engine.budget.require_room(initial, original['grant']['counters'], needed, original)
        bootstrap = RecipeMaterializationRequest.model_validate(repo.get(
            'recipe_materialization_request', 'skillsbench-document-overhead-20261106'))
        operation = bootstrap.plan_id + ':unstarted-excel-proxy-overhead'
        assert engine.proxy_state(proxy) == original['proxy']
        if not execute:
            print(json.dumps({'passed': True, 'review_sha256': digest, 'plan_id': plan.plan_id,
                              'unstarted': True, 'proxy_stopped': True, 'models': 0,
                              'remaining_budget_checked': True, 'worker_proofs_reused': True}))
            return True
        parent.write(HERE / 'started.json', {'review_sha256': digest, 'plan_id': plan.plan_id,
                                             'grant_before': list(initial), 'invoice_replayed': False})
        start = time.perf_counter()
        repo.reserve(bootstrap, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=OVERHEAD_SECONDS),
                     stage='owned_workflow_proxy_overhead')
        result = {'passed': False, 'review_sha256': digest, 'comparisons': 'PAUSED',
                  'candidate_usefulness': 'NOT_ASSESSED', 'selection_usefulness': 'NOT_ASSESSED'}
        attempted = False
        nested = 0.
        phase = 'proxy start'
        try:
            attempted = True
            engine.docker('start', proxy['proxy_name'])
            active = engine.proxy_state(proxy)
            assert active['Running'] and active['Id'] == original['proxy']['Id']
            assert active['Image'] == original['proxy']['Image']
            assert active['Networks']['aeep-reviewed-model-private']['IPAddress'] == '172.18.0.2'
            parent.guard(original, review['parent_review_sha256'])
            phase = 'ordinary CLI run'
            began = time.perf_counter()
            try:
                engine.cli('run', '--workflow', workflow, '--configuration', case['configuration'],
                           '--manifest', engine.MANIFEST, '--directory', engine.CAMPAIGNS,
                           '--reviewed-digest', preview['review_sha256'], '--accounting', engine.WORK / 'excel-accounting.json',
                           '--operation-id', 'execute', '--output', target, '--engineering-review', ref,
                           output='excel-run-cli.json', timeout=2100)
            finally:
                nested += time.perf_counter() - began
            phase = 'canonical receipt reconciliation'
            result['trial'] = audit.audit_document(parent, engine, original, 'excel')
            result['passed'] = result['trial']['model_turn_count'] == 1
        except (Exception, asyncio.CancelledError, KeyboardInterrupt) as error:
            result.update(stopped_phase=phase, error_type=type(error).__name__)
        finally:
            try:
                if attempted and engine.proxy_state(proxy)['Running']:
                    engine.docker('stop', '--time', '5', proxy['proxy_name'])
                result['proxy_restored_stopped'] = engine.proxy_state(proxy) == original['proxy']
                if result['proxy_restored_stopped']:
                    repo.finish_operation(operation, elapsed_seconds=max(0., time.perf_counter() - start - nested))
            except Exception as error:
                result['settlement_error_type'] = type(error).__name__
            now = engine.reserved(repo)
            after = engine.previous.counters(repo)
            result['grant_after'] = list(after)
            result['charged'] = [after[index] - initial[index] for index in range(3)]
            result['historical_reservations_preserved'] = all(now.get(key) == value for key, value in historical.items())
            result['new_unresolved_reservations'] = sorted(set(now) - set(historical))
            result['passed'] &= (result.get('proxy_restored_stopped', False) and not result['new_unresolved_reservations']
                                 and 'settlement_error_type' not in result and result['historical_reservations_preserved']
                                 and after[3] == initial[3] and result['charged'][1] == 1)
            parent.write(HERE / 'result.json', result)
        print(json.dumps(result))
        return result['passed']
    finally:
        await router.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--preflight')
    flags.add_argument('--execute-approved')
    args = parser.parse_args()
    if args.execute_approved:
        assert parent.read(HERE / 'operator-approval.json') == {
            'approved': True, 'review_sha256': args.execute_approved}
    raise SystemExit(not asyncio.run(run(args.preflight or args.execute_approved, execute=bool(args.execute_approved))))
