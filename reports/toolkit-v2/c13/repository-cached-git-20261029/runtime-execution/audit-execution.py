"""Reopen this batch's canonical evidence and recompute case reproduction outcomes."""
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess

from aeep.assessment.containment import container_name
from aeep.assessment.models import content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.attempts import ExecutionAttempt, ExecutionAttemptState
from aeep.execution import ExecutionEvidence
from aeep.models import ExecutionReceipt
from classify import discrepancies
from operator_output import observation
from aeep.assessment.repository_suites import RepositorySuiteCase, grade_suite_output
from native_scope import expand
import asyncio

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/.aeep/assessments')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    review = json.loads((HERE / 'operation-review.json').read_text())
    result = json.loads((HERE / 'execution-result.json').read_text())
    parent = json.loads((ROOT / review['parent_review']).read_text())
    assert sha(HERE / 'operation-review.json') == result['review_sha256']
    assert result['batch_completed'] and result['source_unchanged'] and result['elapsed_complete']
    assert verification_source_digest(ROOT) == review['source_digest']
    for path, expected in review['assets'].items():
        assert sha(Path(path)) == expected
    reopened = []
    for item in result['receipts']:
        database = BASE / review['request']['plan_id'] / 'recipe-operations' / (item['operation_id'] + '.sqlite3')
        with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as connection:
            rows = connection.execute('SELECT payload_json FROM receipts').fetchall()
            assert len(rows) == 1
            receipt = ExecutionReceipt.model_validate_json(rows[0][0])
            assert receipt.receipt_id == item['receipt_id'] and content_digest(receipt) == item['receipt_ref']
            identity = receipt.metadata['attempt_id']
            row = connection.execute('SELECT payload_json FROM execution_attempts WHERE attempt_id=?', (identity,)).fetchone()
            assert row is not None
            attempt = ExecutionAttempt.model_validate_json(row[0])
            assert attempt.state.value == item['attempt_state']
            assert attempt.state in (ExecutionAttemptState.COMPLETED, ExecutionAttemptState.FAILED)
            assert receipt.receipt_id in attempt.terminal_receipt_ids
            assert receipt.executor_id == attempt.executor_id == parent['recipe']['extension']['reference' if item['profile']=='default' else 'grader']['id']
            assert receipt.executor_fingerprint == attempt.executor_fingerprint
            evidence_ref = receipt.metadata['execution_evidence_digest']
            row = connection.execute("SELECT payload_json FROM assessment_records WHERE kind='execution_evidence' AND digest=?", (evidence_ref,)).fetchone()
            assert row is not None
            evidence = ExecutionEvidence.model_validate_json(row[0])
            assert evidence.complete and evidence.attempt_id == identity and content_digest(evidence) == evidence_ref
        owned = container_name(identity)
        assert owned == item['container_name']
        assert not subprocess.check_output([parent['docker'], '--host', parent['socket'], 'ps', '-a',
            '--filter', 'name=^/' + owned + '$', '--format', '{{.ID}}'], timeout=15).decode().strip()
        reopened.append({'operation_id': item['operation_id'], 'receipt_ref': item['receipt_ref'],
            'attempt_state': attempt.state.value, 'container_absent': True})
    assert len(reopened) == result['contained_calls_started'] == len(result['observations'])
    raw_by_name = {}
    for item in result['observations']:
        path = HERE / item['raw_file']
        assert sha(path) == item['raw_sha256']
        raw = json.loads(path.read_text())
        assert raw['operation_id'] == item['operation_id'] and raw['name'] == item['name']
        raw_by_name[item['name']] = observation(raw['output'],item['profile']) if raw['output'] is not None else None
    assert result['default_observer_probes_passed']
    for profile in ('default','operator'):
        for item in review['probes']:
            raw=raw_by_name[profile+'-probe-'+item['name']]
            assert raw['exit_code']==0 and raw['archive_sha256']==item['archive_sha256'] and raw['statuses'][item['expected_node']]=='PASSED'
        for item in review['native_fixtures']:
            raw=raw_by_name[profile+'-fixture-'+item['name']]
            assert raw['exit_code']==item['exit_code'] and raw['archive_sha256']==item['archive_sha256'] and raw['statuses']==item['statuses']
    assert raw_by_name['runtime-support']['statuses']==result['runtime_support_statuses']
    derived=json.loads((HERE/'derived-review.json').read_text())
    assert sha(HERE/'derived-review.json')==result['derived_review_sha256'] and derived['frozen_before_any_body_trial']
    assert derived['method_sha256']==review['method_sha256']==sha(HERE/'native_scope.py')
    for p,h in derived['assets'].items():assert sha(Path(p))==h
    seeds={c['input']['task_id']:RepositorySuiteCase.model_validate(c) for c in json.loads((ROOT/review['cases_file']).read_text())}
    actual={c['input']['task_id']:RepositorySuiteCase.model_validate(c) for c in json.loads((ROOT/derived['cases_file']).read_text())}
    variants=json.loads((ROOT/derived['variants_file']).read_text())
    for mapping in derived['mappings']:
        identity=mapping['case_id'];seed=seeds[identity];case=actual[identity]
        raw=raw_by_name['collection-'+identity]
        staged=next(c for c in review['collections'] if c['case_id']==identity)
        assert raw['exit_code']==0 and raw['archive_sha256']==staged['archive_sha256']
        f2p,p2p,groups=expand(seed.truth.fail_to_pass,seed.truth.pass_to_pass,raw['native_ids'],seed.truth.test_paths)
        assert groups==mapping['alias_groups'] and case.truth.fail_to_pass==f2p and case.truth.pass_to_pass==p2p
        assert case.input==seed.input and case.reference==seed.reference and case.fault_outputs==seed.fault_outputs
    cases, eligible = [], []
    for item in result['results']:
        accepted = []
        for variant in item['variants']:
            name = item['case_id'] + '-' + variant['variant']
            if 'grade' not in variant:
                assert not variant['passed']
                accepted.append(False)
                continue
            expected = derived['expectations'][item['case_id']][variant['variant']]
            case=actual[item['case_id']]
            staged=next(v for v in variants if v['case']==item['case_id'] and v['variant']==variant['variant'])
            async def replay(payload):
                assert hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()==staged['sha256']
                return raw_by_name[name]
            grade=await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),staged['artifact'],replay)
            assert grade.model_dump(mode='json')==variant['grade']
            failures = discrepancies(raw_by_name[name], variant['grade'], expected)
            assert variant['discrepancies'] == failures and variant['passed'] == (not failures)
            accepted.append(not failures)
        complete = len(accepted) == 2 and all(accepted)
        assert item['reproduction_eligible'] == complete
        if complete:
            eligible.append(item['case_id'])
        cases.append({'case_id': item['case_id'], 'reproduction_eligible': complete,
                      'observed_variants': len(accepted)})
    assert {c['case_id'] for c in cases}==set(review['active_case_ids']) and len(eligible)==result['eligible_cases']
    if actual and 'grade' in result.get('default_reference',{}):
        identity=sorted(actual)[0];case=actual[identity]
        staged=next(v for v in variants if v['case']==identity and v['variant']=='reference')
        raw=raw_by_name['default-reference-'+identity]
        async def default_replay(payload):
            assert hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()==staged['sha256']
            return raw
        grade=await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),staged['artifact'],default_replay)
        errors=discrepancies(raw,grade.model_dump(mode='json'),derived['expectations'][identity]['reference'])
        assert result['default_reference']['grade']==grade.model_dump(mode='json')
        assert result['default_reference']['discrepancies']==errors and result['default_reference']['passed']==(not errors)
    control=json.loads((ROOT/review['shared_default_control_file']).read_text())
    shared_case=RepositorySuiteCase.model_validate(control['case'])
    checks=[]
    for item in control['variants']:
        raw=raw_by_name['shared-default-'+item['variant']]
        async def shared_replay(payload):
            assert hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()==item['sha256']
            return raw
        grade=await grade_suite_output(shared_case.input.model_dump(mode='json'),shared_case.truth.model_dump(mode='json'),item['artifact'],shared_replay)
        errors=discrepancies(raw,grade.model_dump(mode='json'),item['expected'])
        saved=next(v for v in result['shared_default_controls'] if v['variant']==item['variant'])
        assert saved['grade']==grade.model_dump(mode='json') and saved['discrepancies']==errors and saved['passed']==(not errors)
        checks.append(not errors)
    assert len(checks)==2 and result['shared_default_compatibility_passed']==all(checks)
    ledger = json.loads((HERE / 'operation-ledger.json').read_text())
    operations = ledger['operations']
    assert len(operations) == result['ledger_operations'] == len(reopened) + 2
    assert all(item['elapsed_seconds'] is not None and math.isfinite(item['elapsed_seconds']) and
               item['elapsed_seconds'] >= 0 for item in operations)
    assert len(operations) <= review['maximum_operations'] and len(reopened) <= review['maximum_contained_calls']
    before, after = result['grant_before'], result['grant_after']
    delta = after[2] - before[2]
    assert math.isclose(delta, sum(item['elapsed_seconds'] for item in operations), rel_tol=1e-10, abs_tol=1e-8)
    assert after[0] - before[0] == len(operations) and before[1] == after[1] and before[3] == after[3]
    audit = {'batch_completed': True, 'physical_receipt_integrity_passed': True, 'case_results_recomputed': True,'shared_default_compatibility_passed':result['shared_default_compatibility_passed'], 'default_observer_probes_passed':True,'derived_scope_frozen_before_body':True,'derived_review_sha256':result['derived_review_sha256'],
        'review_sha256': result['review_sha256'], 'canonical_receipts_reopened': len(reopened),
        'terminal_attempts_reopened': len(reopened), 'completed_attempts_reopened': sum(x['attempt_state']=='COMPLETED' for x in reopened), 'failed_attempts_reopened': sum(x['attempt_state']=='FAILED' for x in reopened), 'all_owned_containers_absent': True,
        'bounded_raw_observations_retained': len(raw_by_name), 'source_unchanged': True,
        'eligible_cases': eligible, 'case_results': cases, 'canonical_operations': len(operations),
        'charged_elapsed_seconds': delta, 'grant_before': before, 'grant_after': after,
        'model_turns': 0, 'cash_delta': 0, 'cases_adopted': 0, 'stage_assignments_frozen': False,
        'qualification': False, 'comparative_usefulness': False, 'selection_improvement': False,
        'reopened': reopened}
    with (HERE / 'completion-audit.json').open('x') as stream:
        json.dump(audit, stream, indent=2)
        stream.write('\n')
    print(json.dumps({key: value for key, value in audit.items() if key not in ('case_results', 'reopened')}))


if __name__ == '__main__':
    asyncio.run(main())
