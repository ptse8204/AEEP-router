"""Reopen canonical receipts/attempts and verify terminal owned-resource cleanup."""
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess

from aeep.assessment.containment import container_name
from aeep.assessment.models import RecipeMaterializationRequest, content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.attempts import ExecutionAttempt, ExecutionAttemptState
from aeep.models import ExecutionReceipt
from aeep_toolkit.install_runtime import RuntimeInstallation

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/.aeep/assessments')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    origin = HERE.parent/'repository-suite-integration-20261022'
    bundle = json.loads((origin/'approval-bundle.json').read_text())
    result = json.loads((HERE/'execution-result.json').read_text())
    amended = json.loads((HERE/'operation-review.json').read_text())
    review = {**json.loads((ROOT/amended['parent_review']).read_text()), **amended}
    grader = result
    request = RecipeMaterializationRequest.model_validate(review['request'])
    reopened = []
    for item in grader['receipts']:
        database = BASE/request.plan_id/'recipe-operations'/(item['operation_id']+'.sqlite3')
        with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as connection:
            rows = connection.execute('SELECT payload_json FROM receipts').fetchall()
            assert len(rows)==1
            receipt = ExecutionReceipt.model_validate_json(rows[0][0])
            assert receipt.receipt_id==item['receipt_id'] and content_digest(receipt)==item['receipt_ref']
            attempt_id = receipt.metadata['attempt_id']
            row = connection.execute('SELECT payload_json FROM execution_attempts WHERE attempt_id=?',(attempt_id,)).fetchone()
            assert row is not None
            attempt = ExecutionAttempt.model_validate_json(row[0])
            assert attempt.state is ExecutionAttemptState.COMPLETED
            assert receipt.receipt_id in attempt.terminal_receipt_ids
            assert attempt.executor_id==receipt.executor_id==review['recipe']['extension']['grader']['id']
            assert attempt.executor_fingerprint==receipt.executor_fingerprint
        owned = container_name(attempt_id)
        assert owned==item['container_name']
        current = subprocess.check_output([review['docker'],'--host',review['socket'],'ps','-a',
            '--filter','name=^/'+owned+'$','--format','{{.ID}}'],timeout=20).decode().strip()
        assert not current
        reopened.append({'operation_id':item['operation_id'],'receipt_ref':item['receipt_ref'],
            'attempt_state':attempt.state.value,'container_absent':True})
    ledger = json.loads((HERE/'operation-ledger.json').read_text())
    operations = ledger['operations']
    assert len(operations)==grader['ledger_operations']
    assert all(item['elapsed_seconds'] is not None and math.isfinite(item['elapsed_seconds']) and item['elapsed_seconds']>=0 for item in operations)
    delta = grader['grant_after'][2]-grader['grant_before'][2]
    total = sum(item['elapsed_seconds'] for item in operations)
    assert math.isclose(delta,total,rel_tol=1e-10,abs_tol=1e-8)
    assert grader['grant_after'][0]-grader['grant_before'][0]==len(operations)
    assert grader['grant_after'][1]==grader['grant_before'][1] and grader['grant_after'][3]==grader['grant_before'][3]
    assert not (ROOT/review['host_canary']).exists()
    package = ROOT/'reports/toolkit-v2/integration-completion/package-review-repository-suites-20261022'
    plan = RuntimeInstallation.model_validate_json((package/'installation.json').read_text())
    package_result = json.loads((package/'execution/summary.json').read_text())
    docs = ROOT/'reports/toolkit-v2/integration-completion/lychee-repository-suites-review-20261022'
    docs_result = json.loads((docs/'execution-result.json').read_text())
    assert not Path(plan.destination).exists()
    assert not Path(docs_result['runtime']).exists()
    assert package_result['runtime_removed'] and package_result['private_scratch_removed']
    assert docs_result['runtime_removed'] and docs_result['immutable_runtime_unchanged']
    assert verification_source_digest(ROOT)==bundle['source_digest']
    assert sha(origin/'approval-bundle.json')=='a2787cd8828ebbad3a06169c3df5793e0f43238ad4af57b026cac432a28fc739'
    audit = {'passed':result['passed'] and grader['passed'],'physical_receipt_integrity_passed':True,'bundle_sha256':sha(origin/'approval-bundle.json'),
        'canonical_receipts_reopened':len(reopened),'completed_attempts_reopened':len(reopened),
        'all_owned_containers_absent_from_running_and_stopped':True,'canonical_operations':len(operations),
        'charged_elapsed_delta':delta,'ledger_elapsed_seconds':total,'grant_before':grader['grant_before'],
        'grant_after':grader['grant_after'],'source_unchanged':True,'canary_absent':True,
        'private_installed_runtime_absent':True,'private_docs_runtime_absent':True,'reopened':reopened,
        'new_model_turns':0,'cash_delta':0,'qualification':False,'comparative_usefulness':False,
        'selection_improvement':False,'claim':'Development conformance and installed software checks only; no model task, new value label, official upstream runtime equivalence or release.'}
    with (HERE/'completion-audit.json').open('x') as output:json.dump(audit,output,indent=2);output.write('\n')
    print(json.dumps({key:value for key,value in audit.items() if key!='reopened'}))


if __name__=='__main__':
    main()
