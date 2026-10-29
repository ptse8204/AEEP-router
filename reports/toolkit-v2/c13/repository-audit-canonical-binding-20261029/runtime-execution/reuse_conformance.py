"""Reuse only canonical evidence for the exact unchanged container backend."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from aeep.assessment.models import content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.attempts import ExecutionAttempt, ExecutionAttemptState
from aeep.execution import ExecutionEvidence
from aeep.models import ExecutionReceipt

BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/.aeep/assessments')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_reuse(review, root):
    binding = review['reused_conformance']
    for name, expected in binding['files'].items():
        assert sha(root / name) == expected, name
    old_dir = root / binding['directory']
    previous = json.loads((old_dir / 'operation-review.json').read_text())
    old = json.loads((old_dir / 'execution-result.json').read_text())
    audit = json.loads((old_dir / 'completion-audit.json').read_text())
    old_parent = json.loads((root / previous['parent_review']).read_text())
    parent = json.loads((root / review['parent_review']).read_text())
    assert verification_source_digest(root) == review['source_digest'] == previous['source_digest']
    assert audit['batch_completed'] and audit['physical_receipt_integrity_passed']
    assert audit['canonical_receipts_reopened'] == audit['completed_attempts_reopened'] == 19
    assert audit['failed_attempts_reopened'] == 0 and audit['all_owned_containers_absent']
    assert old['default_observer_probes_passed'] and old['shared_default_compatibility_passed']
    assert old['batch_completed'] and old['source_unchanged']
    assert parent['image'] == old_parent['image'] == binding['image_id']
    assert parent['docker'] == old_parent['docker'] and parent['socket'] == old_parent['socket']
    for role in ('reference', 'grader'):
        assert parent['recipe']['extension'][role] == old_parent['recipe']['extension'][role]
    env = next(v['document'] for v in parent['documents'].values() if v['kind'] == 'environment')
    old_env = next(v['document'] for v in old_parent['documents'].values() if v['kind'] == 'environment')
    assert env == old_env
    image = json.loads(subprocess.check_output([parent['docker'], '--host', parent['socket'],
        'image', 'inspect', binding['image_id']], timeout=20))[0]
    assert image['Id'] == binding['image_id'] and image['Config']['User'] == '65534:65534'
    active_names = set(subprocess.check_output([parent['docker'], '--host', parent['socket'],
        'ps', '-a', '--format', '{{.Names}}'], text=True, timeout=20).splitlines())
    count = 0
    for item in old['receipts']:
        database = BASE / previous['request']['plan_id'] / 'recipe-operations' / (item['operation_id'] + '.sqlite3')
        with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as db:
            rows = db.execute('SELECT payload_json FROM receipts').fetchall()
            assert len(rows) == 1
            receipt = ExecutionReceipt.model_validate_json(rows[0][0])
            assert receipt.receipt_id == item['receipt_id'] and content_digest(receipt) == item['receipt_ref']
            identity = receipt.metadata['attempt_id']
            row = db.execute('SELECT payload_json FROM execution_attempts WHERE attempt_id=?', (identity,)).fetchone()
            assert row is not None
            attempt = ExecutionAttempt.model_validate_json(row[0])
            assert attempt.state == ExecutionAttemptState.COMPLETED
            assert receipt.receipt_id in attempt.terminal_receipt_ids
            assert receipt.executor_id == attempt.executor_id
            assert receipt.executor_fingerprint == attempt.executor_fingerprint
            ref = receipt.metadata['execution_evidence_digest']
            row = db.execute("SELECT payload_json FROM assessment_records WHERE kind='execution_evidence' AND digest=?", (ref,)).fetchone()
            assert row is not None
            evidence = ExecutionEvidence.model_validate_json(row[0])
            assert evidence.complete and evidence.attempt_id == identity and content_digest(evidence) == ref
        assert item['container_name'] not in active_names
        count += 1
    assert count == 19
    return {'source_digest': review['source_digest'], 'image_id': binding['image_id'],
        'evidence_review_sha256': sha(old_dir / 'operation-review.json'),
        'evidence_audit_sha256': sha(old_dir / 'completion-audit.json'),
        'canonical_completed_receipt_chains_reopened': count,
        'executor_definitions_and_environment_identical': True,
        'shared_default_compatibility_passed': True, 'new_runtime_probes': 0,
        'new_subjects_not_qualified_by_reuse': True}
