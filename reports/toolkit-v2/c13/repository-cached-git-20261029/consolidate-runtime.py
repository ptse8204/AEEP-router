"""Add only the actually reproduced Dead snapshot; controls add no cases."""
from collections import Counter
import json
import math
from pathlib import Path
import sqlite3

from review_bindings import sha

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = HERE / 'runtime-execution'


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    prior_path = HERE.parent / 'repository-stable-workspace-20261028/provisional-pool.json'
    prior = json.loads(prior_path.read_text())
    assert sha(ROOT / prior['cases_file']) == prior['cases_file_sha256']
    review = json.loads((HERE / 'runtime-review.json').read_text())
    result = json.loads((HERE / 'execution-result.json').read_text())
    audit = json.loads((OUT / 'completion-audit.json').read_text())
    derived = json.loads((OUT / 'derived-review.json').read_text())
    assert result['batch_completed'] and result['build_passed'] and result['source_unchanged']
    assert audit['physical_receipt_integrity_passed'] and audit['all_owned_containers_absent']
    assert audit['canonical_receipts_reopened'] == audit['completed_attempts_reopened'] == 19
    assert audit['failed_attempts_reopened'] == 0 and audit['canonical_operations'] == 21
    assert audit['derived_scope_frozen_before_body'] and audit['shared_default_compatibility_passed']
    assert sha(OUT / 'derived-review.json') == audit['derived_review_sha256']
    for name, digest in derived['assets'].items():
        assert sha(name) == digest
    assert json.loads((HERE / 'canary-cleanup.json').read_text())['unchanged_owned_canary_removed']
    assert not (ROOT / review['host_canary']).exists()
    build_operations = json.loads((HERE / 'build-operation-ledger.json').read_text())['operations']
    worker_operations = json.loads((OUT / 'operation-ledger.json').read_text())['operations']
    operations = build_operations + worker_operations
    assert len(operations) == len({x['operation_id'] for x in operations}) == 22
    with sqlite3.connect('file:/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3?mode=ro', uri=True) as db:
        for operation in operations:
            assert db.execute('SELECT state FROM assessment_operations WHERE id=?', (operation['operation_id'],)).fetchone()[0] == 'complete'
            assert math.isfinite(operation['elapsed_seconds']) and operation['elapsed_seconds'] >= 0
        current = list(db.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    assert current == result['grant_after'] == audit['grant_after']
    before = result['grant_before']
    seconds = sum(x['elapsed_seconds'] for x in operations)
    assert current[0] - before[0] == 22 and current[1] == before[1] and current[3] == before[3]
    assert math.isclose(current[2] - before[2], seconds, abs_tol=1e-7)
    added = json.loads((ROOT / derived['cases_file']).read_text())
    assert len(added) == len(audit['eligible_cases']) == 1
    case = added[0]
    identity = case['input']['task_id']
    assert identity in audit['eligible_cases'] and case['input']['family'] == 'single-file-repair'
    assert len(case['truth']['fail_to_pass']) == 1 and len(case['truth']['pass_to_pass']) == 37
    cases = json.loads((ROOT / prior['cases_file']).read_text())
    bindings = dict(prior['source_runtime_bindings'])
    assert identity not in bindings
    cases.append(case)
    bindings[identity] = {'evidence_manifest': str((OUT / 'completion-audit.json').relative_to(ROOT)),
        'source_digest': review['source_digest'], 'image_id': result['image_id'],
        'observer_profile': 'Fresh diagnostic/raw shared-v6 conformance on this image;38-test reference and original counterexample reproduced. Two frozen171-test controls passed. No corpus-wide,model or scientific qualification transfer.',
        'operator_program_sha256': sha(HERE / 'observer-operator.py'),
        'default_program_sha256': sha(HERE / 'observer-default.py'),
        'recipe_digest': review['build_request']['recipe_digest'],
        'derived_review_sha256': sha(OUT / 'derived-review.json'), 'upstream_assertions_unchanged': True,
        'earlier_missing_Git_reference_failure_preserved': True}
    assert len(cases) == len({(c['source_repository'].casefold(), c['source_revision']) for c in cases}) == len({c['input']['source_sha256'] for c in cases}) == 65
    counts = dict(Counter(c['input']['family'] for c in cases))
    assert counts == {'single-file-repair': 27, 'contract-audit': 15, 'multi-file-repair': 23}
    cache = ROOT / '.aeep/repository-provisional-pool-cached-git-20261029'
    cache.mkdir(exist_ok=False)
    path = cache / 'cases.json'
    save(path, cases)
    pool = {**prior, 'cases_file': str(path.relative_to(ROOT)), 'cases_file_sha256': sha(path),
        'case_count': len(cases), 'repository_count': len({c['source_repository'].casefold() for c in cases}),
        'family_counts': counts, 'required_reference_identities': sum(len(c['truth']['fail_to_pass']) + len(c['truth']['pass_to_pass']) for c in cases),
        'source_runtime_bindings': bindings, 'missing_family_counts': {k: 47 - n for k, n in counts.items()},
        'inputs': [{'manifest': str(prior_path.relative_to(ROOT)), 'manifest_sha256': sha(prior_path), 'cases_sha256': prior['cases_file_sha256']},
            {'manifest': str((OUT / 'completion-audit.json').relative_to(ROOT)), 'manifest_sha256': sha(OUT / 'completion-audit.json'), 'cases_sha256': sha(ROOT / derived['cases_file'])}],
        'latest_grant': current, 'batch_operations_including_build': 22, 'builds_in_this_batch': 1,
        'batch_charged_operation_seconds': seconds, 'new_external_calls_for_consolidation': 0,
        'cases_adopted': 0, 'stages_frozen': False, 'qualification': False, 'comparative_usefulness': False,
        'selection': False, 'native_observer_scope': bindings[identity]['observer_profile'],
        'initial_docs_result': 'Completed69document/package20checks retained separately;no repeat in this runtime.'}
    assert pool['repository_count'] == 41 and pool['required_reference_identities'] == 5075
    save(HERE / 'provisional-pool.json', pool)
    save(HERE / 'final-accounting-audit.json', {'passed': True, 'canonical_operations_reopened': 22,
        'physical_completed_receipts_reopened': 19, 'grant_before': before, 'grant_after': current,
        'charged_operation_seconds': seconds, 'all_operations_complete': True,
        'all_owned_containers_and_canary_absent': True, 'all_images_retained': True,
        'pool_additions': 1, 'controls_duplicated': 0, 'models_cash_downloads_installs': 0})
    print(json.dumps({k: pool[k] for k in ('case_count', 'repository_count', 'family_counts',
        'required_reference_identities', 'missing_family_counts', 'latest_grant', 'batch_charged_operation_seconds')}))


if __name__ == '__main__':
    main()
