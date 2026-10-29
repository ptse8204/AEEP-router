"""Correct only canonical wire-digest metadata for six already authorized unstarted calls."""
import ast
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from aeep.assessment.models import RecipeMaterializationRequest, AssessmentScopeAmendment, content_digest
from aeep.assessment.verification import verification_source_digest
from review_bindings import audit, sha

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'repository-cached-audits-20261029'


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    previous_sha = sha(OLD / 'operation-review.json')
    assert previous_sha == 'ca735d78f53c33685af78d487eb83bdc06edf743e0630233eadeb070f76d4518'
    previous = json.loads((OLD / 'operation-review.json').read_text())
    human = json.loads((OLD / 'operator-approval.json').read_text())
    assert human['approved'] and human['review_sha256'] == previous_sha
    terminal = json.loads((OLD / 'runtime-execution/execution-result.json').read_text())
    assert terminal['contained_calls_started'] == 0 and not terminal['receipts'] and not terminal['observations']
    assert terminal['error_type'] == 'StopDispatch' and terminal['source_unchanged']
    assert terminal['elapsed_complete'] and terminal['containers_removed']
    assert json.loads((OLD / 'canary-cleanup.json').read_text())['unchanged_owned_canary_removed']
    ledger = json.loads((OLD / 'runtime-execution/operation-ledger.json').read_text())['operations']
    assert len(ledger) == 2 and all(x['stage'] in ('repository_curated_reproduction_setup', 'repository_curated_reproduction_analysis') for x in ledger)
    initial = human['grant_before']
    with sqlite3.connect('file:/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3?mode=ro', uri=True) as db:
        rows = db.execute('SELECT id,state FROM assessment_operations WHERE id LIKE ?', (previous['request']['plan_id'] + '-%',)).fetchall()
        assert len(rows) == 2 and all(row[1] == 'complete' for row in rows)
        assert {row[0] for row in rows} == {x['operation_id'] for x in ledger}
        current = list(db.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    assert current == terminal['grant_after'] and current[0] - initial[0] == 2
    seconds = sum(x['elapsed_seconds'] for x in ledger)
    assert math.isclose(current[2] - initial[2], seconds, abs_tol=1e-7)
    assert current[1] == initial[1] and current[3] == initial[3]
    assert verification_source_digest(ROOT) == previous['source_digest']
    collections, corrections = [], []
    for item in previous['collections']:
        path = ROOT / item['payload']
        assert sha(path) == previous['assets'][str(path)] == item['sha256']
        data = json.loads(path.read_text())
        wire = hashlib.sha256(json.dumps(data, separators=(',', ':')).encode()).hexdigest()
        assert wire != item['sha256']
        collections.append({**item, 'sha256': wire, 'payload_file_sha256': sha(path)})
        corrections.append({'payload': item['payload'], 'unchanged_file_sha256': sha(path), 'canonical_wire_sha256': wire})
    request_data = {k: v for k, v in previous['request'].items() if k != 'plan_id'}
    request = RecipeMaterializationRequest.model_validate(request_data)
    new_docs = {k: v for k, v in previous['new_documents'].items() if v['kind'] == 'subject'}
    new_docs[content_digest(request)] = {'kind': 'recipe_materialization_request', 'id': request.plan_id, 'document': request.model_dump(mode='json')}
    parent = json.loads((ROOT / previous['parent_review']).read_text())
    parent['request'] = request.model_dump(mode='json')
    parent_path = HERE / 'observer-envelope.json'
    save(parent_path, parent)
    documents = {**parent['documents'], **new_docs}
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=previous['authorization_digest'],
        subject_digests=[request.subject_digest], recipe_digests=[request.recipe_digest],
        environment_digests=[request.environment_digest], reviewed_digests=list(documents))
    authority = {'recorded_at': datetime.now(timezone.utc).isoformat(),
        'actual_human_source_approval': str((OLD / 'operator-approval.json').relative_to(ROOT)),
        'actual_human_review_sha256': previous_sha,
        'definition_authority': 'AGENTS.md and docs/ASSESSMENT_TESTING.md Standing operator authority: coordinating agent may review/apply routine definition/scope revisions and finite budget amendments;do not ask again for routine revisions. User pasted continuation expressly retains this delegation.',
        'why_no_new_untrusted_execution_authority_needed': 'Exactly the same six software calls remain unstarted. Source,tests,references,negative artifacts,collector programs,environment,permissions and actual payload files are byte-identical. Only expected canonical wire digest is corrected. This resumes unstarted authorized calls after reconciliation;no source invocation is retried.',
        'finite_control_budget_amendment': {'original_operations': 8, 'cumulative_operations': 10,
            'original_reserved_seconds': 360, 'cumulative_reserved_seconds': 362,
            'reason': 'Preserve two completed bookkeeping operations/under1second and reserve the same eight-operation source phase. Absolute grant ceilings,cash/model/disclosure/credential scope unchanged.'},
        'original_phase_operations': ledger, 'original_phase_seconds': seconds,
        'source_calls_previously_started': 0, 'source_calls_authorized_total': 6,
        'cumulative_grant_anchor': initial, 'current_grant': current,
        'payload_corrections': corrections, 'new_human_reply_claimed': False,
        'no_automatic_trial_retry_refund_reset_or_software_change': True}
    save(HERE / 'operator-definition-budget-amendment.json', authority)
    assets = dict(previous['assets'])
    for file in [*HERE.glob('*.py'), *sorted((HERE / 'runtime-execution').glob('*.py')),
        parent_path, HERE / 'operator-definition-budget-amendment.json', OLD / 'operation-review.json',
        OLD / 'operator-approval.json', OLD / 'runtime-execution/execution-result.json',
        OLD / 'runtime-execution/operation-ledger.json', OLD / 'canary-cleanup.json']:
        if file.suffix == '.py':
            ast.parse(file.read_text())
        assets[str(file.resolve())] = sha(file)
    review = {**previous, 'assets': assets, 'collections': collections,
        'parent_review': str(parent_path.relative_to(ROOT)), 'parent_review_sha256': sha(parent_path),
        'request': request.model_dump(mode='json'), 'new_documents': new_docs,
        'reviewed_document_digests': list(documents), 'amendment': amendment.model_dump(mode='json'),
        'derived_directory': '.aeep/repository-cached-audit-execution-20261029/canonical-continuation-derived',
        'maximum_operations': 10, 'maximum_reserved_seconds': 362,
        'cumulative_grant_anchor': initial, 'controller_phase_operations_already_charged': 2,
        'driver_files': {name: sha(HERE / 'runtime-execution' / name) for name in previous['driver_files']},
        'actual_human_source_authority_sha256': previous_sha,
        'control_amendment_sha256': sha(HERE / 'operator-definition-budget-amendment.json'),
        'failure_policy': 'One finite reconciled controller continuation. Six unstarted approved source calls only;no source retry. Known cleaned-up case failures stay excluded;common uncertainty stops dispatch. Preserve all charges;no refunds/resets.',
        'prepared_only': True}
    for field in ('cases_file', 'records_file', 'required_count_bounds', 'active_case_ids',
        'parent_image', 'maximum_contained_calls', 'maximum_model_turns', 'cash_usd', 'maximum_builds', 'maximum_downloads', 'reused_conformance'):
        assert review[field] == previous[field]
    assert review['maximum_contained_calls'] == 6
    save(HERE / 'operation-review.json', review)
    check = audit([HERE / 'operation-review.json'], ROOT)
    assert check['passed'], check['errors']
    save(HERE / 'preparation-audit.json', {**check, 'unchanged_source_authority_retained': True,
        'six_source_calls_unstarted': True, 'new_source_execution_or_charge': False})
    print(json.dumps({'prepared': True, 'review_sha256': sha(HERE / 'operation-review.json'),
        'source_calls_remain': 6, 'cumulative_operations': 10, 'cumulative_seconds': 362}))


if __name__ == '__main__':
    main()
