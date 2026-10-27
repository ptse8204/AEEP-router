"""Reopen terminal diagnostic receipts and ledger; never rerun an observation."""
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess

from aeep.assessment.models import RecipeMaterializationRequest, content_digest
from aeep.assessment.service import AssessmentService
from aeep.attempts import ExecutionAttempt, ExecutionAttemptState
from aeep.models import ExecutionReceipt
from aeep.router import Router
from sanitize import validate_reply
from run import BASE, DOCKER, HERE, ROOT, validate_review


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    review = json.loads((HERE / 'operation-review.json').read_text())
    recipe = validate_review(review)
    result = json.loads((HERE / 'execution-result.json').read_text())
    assert result['completed'] and result['source_unchanged'] and not result['grade_or_qualification']
    assert result['review_sha256'] == sha(HERE / 'operation-review.json')
    assert len(result['receipts']) == len(result['observations']) == result['contained_calls'] == 4
    assert result['new_host_canaries_created'] == 0
    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    repo = service.repository
    reopened, diagnostics, operations = [], [], []
    try:
        index = 0
        for group in review['groups']:
            request = RecipeMaterializationRequest.model_validate(group['request'])
            for call in [*group['probes'], *group['diagnostics']]:
                item = result['receipts'][index]; raw_ref = result['observations'][index]; index += 1
                assert item['operation_id'] == request.plan_id + '-call-' + str(index)
                database = service.directory / request.plan_id / 'recipe-operations' / (item['operation_id'] + '.sqlite3')
                with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
                    rows = connection.execute('SELECT payload_json FROM receipts').fetchall()
                    assert len(rows) == 1
                    receipt = ExecutionReceipt.model_validate_json(rows[0][0])
                    attempt = ExecutionAttempt.model_validate_json(connection.execute('SELECT payload_json FROM execution_attempts WHERE attempt_id=?', (receipt.metadata['attempt_id'],)).fetchone()[0])
                    assert attempt.state is ExecutionAttemptState.COMPLETED
                    assert receipt.receipt_id in attempt.terminal_receipt_ids
                    spec = recipe.extension.reference if call['kind'] == 'probe' else recipe.extension.grader
                    assert receipt.executor_id == attempt.executor_id == spec.id
                    assert receipt.executor_fingerprint == attempt.executor_fingerprint
                    assert receipt.receipt_id == item['receipt_id'] and content_digest(receipt) == item['receipt_ref']
                assert content_digest(repo.get('recipe_receipt', receipt.receipt_id)) == item['receipt_ref']
                assert not subprocess.check_output([*DOCKER, 'ps', '-a', '--filter', 'name=^/' + item['container_name'] + '$', '--format', '{{.ID}}'], text=True, timeout=20).strip()
                assert sha(HERE / raw_ref['file']) == raw_ref['sha256'] and raw_ref['name'] == call['name']
                raw = json.loads((HERE / raw_ref['file']).read_text())
                assert raw['name'] == call['name'] and raw['kind'] == call['kind'] and raw['image_id'] == group['image_id']
                payload = json.loads((ROOT / call['payload_file']).read_text())
                if call['kind'] == 'diagnostic':
                    validate_reply(raw['output'], payload)
                    diagnostics.append({'name': call['name'], 'image_id': group['image_id'], 'facts': raw['output'],
                                        'trusted_task_grade': False, 'prior_result_unchanged': True})
                else:
                    assert raw['output']['exit_code'] == 0 and raw['output']['archive_sha256'] == payload['archive_sha256']
                    assert raw['output']['statuses'].get(call['expected_node']) == 'PASSED'
                reopened.append(item)
            for operation in repo.operation_ledger(request.plan_id).operations:
                state = router.store._connection.execute('SELECT state FROM assessment_operations WHERE id=?', (operation.operation_id,)).fetchone()[0]
                assert state == 'complete' and operation.elapsed_seconds is not None
                assert math.isfinite(operation.elapsed_seconds) and operation.elapsed_seconds >= 0
                operations.append(operation)
            assert subprocess.check_output([*DOCKER, 'image', 'inspect', '--format', '{{.Id}}', group['image_tag']], text=True, timeout=20).strip() == group['image_id']
        before, after = result['grant_before'], result['grant_after']
        charged = sum(o.elapsed_seconds for o in operations)
        assert len(operations) == after[0] - before[0] == 6
        assert math.isclose(charged, after[2] - before[2], abs_tol=1e-6)
        assert before[1] == after[1] and before[3] == after[3]
        assert charged <= review['maximum_reserved_seconds']
        assert sum(o.reserved.max_elapsed_seconds for o in operations) == review['maximum_reserved_seconds']
        retained = json.loads((HERE / 'operation-ledgers.json').read_text())
        assert sum(len(l['operations']) for l in retained) == len(operations)
        assert list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone()) == after
    finally:
        router.store.close()
    audit = {'passed': True, 'canonical_receipts_reopened': len(reopened), 'completed_attempts_reopened': len(reopened),
             'canonical_operations': len(operations), 'charged_operation_seconds': charged,
             'all_owned_containers_absent': True, 'new_host_canaries_created': 0, 'images_retained': True,
             'source_unchanged': True, 'prior_failures_unchanged': True, 'diagnostics': diagnostics,
             'new_eligible_cases': 0, 'qualification': False, 'comparative_usefulness': False, 'selection': False,
             'grant_before': before, 'grant_after': after}
    with (HERE / 'completion-audit.json').open('x') as stream:
        json.dump(audit, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({k: v for k, v in audit.items() if k != 'diagnostics'}))


if __name__ == '__main__':
    main()
