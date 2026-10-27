"""Consolidate only independently reproduced audits; preserve earlier bindings."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess

from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.router import Router

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    old_path = HERE.parent / 'repository-supported-suites-20261027/provisional-pool.json'
    old = json.loads(old_path.read_text()); old_cases = ROOT / old['cases_file']
    assert sha(old_cases) == old['cases_file_sha256']
    review = json.loads((HERE / 'runtime-execution/operation-review.json').read_text())
    result = json.loads((HERE / 'runtime-execution/execution-result.json').read_text())
    audit_path = HERE / 'runtime-execution/completion-audit.json'; audit = json.loads(audit_path.read_text())
    parent = json.loads((ROOT / review['parent_review']).read_text())
    prepared = json.loads((HERE / 'prepared-cases.json').read_text())
    assert result['batch_completed'] and audit['physical_receipt_integrity_passed'] and audit['all_owned_containers_absent']
    assert audit['canonical_receipts_reopened'] == 4 and len(audit['eligible_cases']) == 2
    assert verification_source_digest(ROOT) == review['source_digest']
    for path, expected in review['assets'].items():
        assert sha(Path(path)) == expected
    base = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
    router = Router.from_manifest(base / 'aeep.json')
    try:
        repo = AssessmentService(router, base / '.aeep/assessments').repository
        operations = repo.operation_ledger(review['request']['plan_id']).operations
        assert len(operations) == 6
        for operation in operations:
            assert router.store._connection.execute('SELECT state FROM assessment_operations WHERE id=?', (operation.operation_id,)).fetchone()[0] == 'complete'
            assert operation.elapsed_seconds is not None and math.isfinite(operation.elapsed_seconds) and operation.elapsed_seconds >= 0
        before, after = result['grant_before'], result['grant_after']
        charged = sum(o.elapsed_seconds for o in operations)
        assert after[0] - before[0] == len(operations) and before[1] == after[1] and before[3] == after[3]
        assert math.isclose(charged, after[2] - before[2], abs_tol=1e-6)
        assert list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone()) == after
    finally:
        router.store.close()
    assert subprocess.check_output([parent['docker'], '--host', parent['socket'], 'image', 'inspect', parent['image'], '--format', '{{.Id}}'], text=True, timeout=20).strip() == parent['image']
    source = ROOT / prepared['cases_file']; assert sha(source) == prepared['cases_file_sha256']
    cases = json.loads(old_cases.read_text()); bindings = dict(old['source_runtime_bindings'])
    for case in json.loads(source.read_text()):
        identity = case['input']['task_id']
        assert identity in audit['eligible_cases'] and identity not in bindings
        cases.append(case)
        bindings[identity] = {'evidence_manifest': str(audit_path.relative_to(ROOT)), 'source_digest': review['source_digest'],
                              'image_id': parent['image'], 'image_tag': 'aeep-toolkit-v2/repository-grader:py313-cached-suites-20261027'}
    assert len(cases) == len({(c['source_repository'].casefold(), c['source_revision']) for c in cases}) == len({c['input']['source_sha256'] for c in cases}) == 44
    counts = dict(Counter(c['input']['family'] for c in cases))
    assert counts == {'single-file-repair': 16, 'contract-audit': 10, 'multi-file-repair': 18}
    out = ROOT / '.aeep/repository-provisional-pool-library-20261027'; out.mkdir(exist_ok=False)
    target = out / 'cases.json'; target.write_text(json.dumps(cases, indent=2) + '\n')
    output = {**old, 'cases_file': str(target.relative_to(ROOT)), 'cases_file_sha256': sha(target),
        'case_count': 44, 'repository_count': len({c['source_repository'].casefold() for c in cases}),
        'family_counts': counts, 'required_reference_identities': sum(len(c['truth']['fail_to_pass']) + len(c['truth']['pass_to_pass']) for c in cases),
        'source_runtime_bindings': bindings, 'inputs': [
            {'manifest': str(old_path.relative_to(ROOT)), 'manifest_sha256': sha(old_path), 'cases_sha256': sha(old_cases)},
            {'manifest': str(audit_path.relative_to(ROOT)), 'manifest_sha256': sha(audit_path), 'cases_sha256': sha(source)}],
        'missing_family_counts': {k: 47 - n for k, n in counts.items()}, 'latest_grant': after,
        'batch_operations_including_build': 6, 'builds_in_this_batch': 0, 'batch_charged_operation_seconds': charged,
        'image_retained': parent['image'], 'new_external_calls_for_consolidation': 0,
        'cases_adopted': 0, 'stages_frozen': False, 'qualification': False, 'comparative_usefulness': False, 'selection': False}
    assert output['repository_count'] == 29 and output['required_reference_identities'] == 2686
    with (HERE / 'provisional-pool.json').open('x') as stream:
        json.dump(output, stream, indent=2); stream.write('\n')
    print(json.dumps({k: output[k] for k in ('case_count', 'repository_count', 'family_counts', 'required_reference_identities', 'missing_family_counts', 'batch_charged_operation_seconds', 'latest_grant')}))


if __name__ == '__main__':
    main()
