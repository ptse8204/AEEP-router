"""Add only the actually reproduced task to the provisional, unassigned pool."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    prior = HERE.parent / 'repository-native-identity-20261028/provisional-pool.json'
    old = json.loads(prior.read_text())
    assert sha(ROOT / old['cases_file']) == old['cases_file_sha256']
    audit = json.loads((HERE / 'completion-audit.json').read_text())
    result = json.loads((HERE / 'execution-result.json').read_text())
    review = json.loads((HERE / 'operation-review.json').read_text())
    derived = json.loads((HERE / 'derived-review.json').read_text())
    assert audit['physical_receipt_integrity_passed'] and audit['all_owned_containers_absent']
    assert audit['derived_scope_frozen_before_body'] and result['default_reference']['passed']
    assert audit['canonical_receipts_reopened'] == audit['completed_attempts_reopened'] == 17
    assert audit['failed_attempts_reopened'] == 0 and audit['canonical_operations'] == 19
    assert result['source_unchanged'] and len(audit['eligible_cases']) == 1
    assert sha(HERE / 'derived-review.json') == audit['derived_review_sha256']
    for path, digest in derived['assets'].items():
        assert sha(Path(path)) == digest
    operations = json.loads((HERE / 'operation-ledger.json').read_text())['operations']
    assert len(operations) == 19
    with sqlite3.connect('file:/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3?mode=ro', uri=True) as db:
        for op in operations:
            assert db.execute('SELECT state FROM assessment_operations WHERE id=?', (op['operation_id'],)).fetchone()[0] == 'complete'
            assert op['elapsed_seconds'] is not None and math.isfinite(op['elapsed_seconds']) and op['elapsed_seconds'] >= 0
        after = list(db.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    assert after == audit['grant_after']
    before = audit['grant_before']
    seconds = sum(op['elapsed_seconds'] for op in operations)
    assert after[0] - before[0] == 19 and after[1] == before[1] and after[3] == before[3]
    assert math.isclose(after[2] - before[2], seconds, abs_tol=1e-7)
    assert json.loads((HERE / 'canary-cleanup.json').read_text())['unchanged_owned_canary_removed']
    added = json.loads((ROOT / derived['cases_file']).read_text())
    assert len(added) == 1
    new = added[0]
    identity = new['input']['task_id']
    assert identity in audit['eligible_cases']
    assert len(new['truth']['fail_to_pass']) + len(new['truth']['pass_to_pass']) == 171
    cases = json.loads((ROOT / old['cases_file']).read_text())
    bindings = dict(old['source_runtime_bindings'])
    assert identity not in bindings
    cases.append(new)
    bindings[identity] = {'evidence_manifest': str((HERE / 'completion-audit.json').relative_to(ROOT)),
        'source_digest': review['source_digest'], 'image_id': review['parent_image'],
        'observer_profile': 'Explicit contained stable-workspace profile; all171native obligations passed in diagnostic/raw references; original rejected. Not packaged-default or corpus-wide qualification.',
        'operator_program_sha256': sha(HERE / 'observer-operator.py'),
        'default_program_sha256': sha(HERE / 'observer-default.py'),
        'recipe_digest': review['request']['recipe_digest'],
        'derived_review_sha256': sha(HERE / 'derived-review.json'),
        'upstream_assertions_unchanged': True, 'earlier168of171_failure_preserved': True}
    assert len(cases) == len({(c['source_repository'].casefold(), c['source_revision']) for c in cases}) == len({c['input']['source_sha256'] for c in cases}) == 64
    counts = dict(Counter(c['input']['family'] for c in cases))
    assert counts == {'single-file-repair': 26, 'contract-audit': 15, 'multi-file-repair': 23}
    cache = ROOT / '.aeep/repository-provisional-pool-stable-20261028'
    cache.mkdir(exist_ok=False)
    target = cache / 'cases.json'
    save(target, cases)
    pool = {**old, 'cases_file': str(target.relative_to(ROOT)), 'cases_file_sha256': sha(target),
        'case_count': len(cases), 'repository_count': len({c['source_repository'].casefold() for c in cases}),
        'family_counts': counts,
        'required_reference_identities': sum(len(c['truth']['fail_to_pass']) + len(c['truth']['pass_to_pass']) for c in cases),
        'source_runtime_bindings': bindings,
        'inputs': [{'manifest': str(prior.relative_to(ROOT)), 'manifest_sha256': sha(prior), 'cases_sha256': old['cases_file_sha256']},
                   {'manifest': str((HERE / 'completion-audit.json').relative_to(ROOT)), 'manifest_sha256': sha(HERE / 'completion-audit.json'), 'cases_sha256': sha(ROOT / derived['cases_file'])}],
        'missing_family_counts': {k: 47 - n for k, n in counts.items()}, 'latest_grant': after,
        'batch_operations_including_build': 19, 'builds_in_this_batch': 0,
        'batch_charged_operation_seconds': seconds, 'new_external_calls_for_consolidation': 0,
        'cases_adopted': 0, 'stages_frozen': False, 'qualification': False,
        'comparative_usefulness': False, 'selection': False,
        'native_observer_scope': 'Fresh current-source/image containment/event checks in both profiles and this171-testsubject only. All63older bindings remain; no automatic corpus-wide or model qualification.',
        'initial_docs_result': 'No docs execution in this review; completed aacf34a8 evidence retained separately.'}
    assert pool['required_reference_identities'] == 5037
    save(HERE / 'provisional-pool.json', pool)
    save(HERE / 'final-accounting-audit.json', {'passed': True,
        'canonical_operations_reopened': 19, 'physical_completed_receipts_reopened': 17,
        'grant_before': before, 'grant_after': after, 'charged_operation_seconds': seconds,
        'all_operations_complete': True, 'all_owned_containers_and_canary_absent': True,
        'all_images_retained': True, 'new_calls_for_consolidation': 0,
        'pool_additions': 1, 'controls_duplicated': 0, 'models_cash_builds_installs_downloads': 0})
    print(json.dumps({k: pool[k] for k in ('case_count', 'repository_count', 'family_counts',
        'required_reference_identities', 'missing_family_counts', 'latest_grant', 'batch_charged_operation_seconds')}))


if __name__ == '__main__':
    main()
