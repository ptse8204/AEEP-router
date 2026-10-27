"""Retain only reproduced cases, preserving earlier source/runtime bindings."""
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
    old_path = HERE.parent / 'repository-independent-sources-20261024/provisional-pool.json'
    old = json.loads(old_path.read_text())
    old_cases = ROOT / old['cases_file']
    assert sha(old_cases) == old['cases_file_sha256']
    result = json.loads((HERE / 'execution-result.json').read_text())
    audit = json.loads((HERE / 'runtime-execution/completion-audit.json').read_text())
    review = json.loads((HERE / 'approval-bundle.json').read_text())
    build = json.loads((HERE / 'build-result.json').read_text())
    prepared = json.loads((HERE / 'prepared-cases.json').read_text())
    assert result['batch_completed'] and result['receipt_integrity_passed']
    assert audit['physical_receipt_integrity_passed'] and audit['all_owned_containers_absent']
    assert audit['canonical_receipts_reopened'] == 12 and len(audit['eligible_cases']) == 3
    assert json.loads((HERE / 'canary-cleanup.json').read_text())['unchanged_owned_canary_removed']
    assert verification_source_digest(ROOT) == review['source_digest']
    for name, expected in review['assets'].items():
        assert sha(Path(name)) == expected
    base = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
    router = Router.from_manifest(base / 'aeep.json')
    try:
        repo = AssessmentService(router, base / '.aeep/assessments').repository
        child = json.loads((HERE / 'runtime-execution/operation-review.json').read_text())
        operations = []
        for plan_id in [review['build_request']['plan_id'], child['request']['plan_id']]:
            for operation in repo.operation_ledger(plan_id).operations:
                state = router.store._connection.execute('SELECT state FROM assessment_operations WHERE id=?', (operation.operation_id,)).fetchone()[0]
                assert state == 'complete' and math.isfinite(operation.elapsed_seconds) and operation.elapsed_seconds >= 0
                operations.append(operation)
        before, after = result['grant_before'], result['grant_after']
        assert len(operations) == result['canonical_operations'] == after[0] - before[0] == 15
        charged = sum(o.elapsed_seconds for o in operations)
        assert math.isclose(charged, after[2] - before[2], abs_tol=1e-6)
        assert before[1] == after[1] and before[3] == after[3]
        assert len(operations) <= review['maximum_operations'] and charged <= review['maximum_reserved_seconds']
        current = list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        assert current == after
    finally:
        router.store.close()
    docker = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']
    assert subprocess.check_output([*docker, 'image', 'inspect', '--format', '{{.Id}}', build['target_tag']], text=True, timeout=20).strip() == build['image_id']
    assert subprocess.check_output([*docker, 'image', 'inspect', '--format', '{{.Id}}', review['parent_reference']], text=True, timeout=20).strip() == review['parent_image']
    cases = json.loads(old_cases.read_text())
    bindings = dict(old['source_runtime_bindings'])
    new_cases = ROOT / prepared['cases_file']
    assert sha(new_cases) == prepared['cases_file_sha256']
    for case in json.loads(new_cases.read_text()):
        identity = case['input']['task_id']
        if identity not in audit['eligible_cases']:
            continue
        assert identity not in bindings
        cases.append(case)
        bindings[identity] = {'evidence_manifest': str((HERE / 'runtime-execution/completion-audit.json').relative_to(ROOT)), 'source_digest': review['source_digest'], 'image_id': build['image_id'], 'image_tag': build['target_tag']}
    assert len(cases) == 42
    assert len({(c['source_repository'].casefold(), c['source_revision']) for c in cases}) == 42
    assert len({c['input']['source_sha256'] for c in cases}) == 42
    counts = dict(Counter(c['input']['family'] for c in cases))
    assert counts == {'single-file-repair': 16, 'contract-audit': 8, 'multi-file-repair': 18}
    out = ROOT / '.aeep/repository-provisional-pool-supported-20261027'
    out.mkdir(exist_ok=False)
    target = out / 'cases.json'
    target.write_text(json.dumps(cases, indent=2) + '\n')
    output = {'cases_file': str(target.relative_to(ROOT)), 'cases_file_sha256': sha(target), 'case_count': len(cases), 'repository_count': len({c['source_repository'].casefold() for c in cases}), 'family_counts': counts, 'required_reference_identities': sum(len(c['truth']['fail_to_pass']) + len(c['truth']['pass_to_pass']) for c in cases), 'source_runtime_bindings': bindings, 'inputs': [{'manifest': str(old_path.relative_to(ROOT)), 'manifest_sha256': sha(old_path), 'cases_sha256': sha(old_cases)}, {'manifest': str((HERE / 'runtime-execution/completion-audit.json').relative_to(ROOT)), 'manifest_sha256': sha(HERE / 'runtime-execution/completion-audit.json'), 'cases_sha256': sha(new_cases)}], 'target_family_totals': {k: 47 for k in counts}, 'missing_family_counts': {k: 47 - n for k, n in counts.items()}, 'cases_adopted': 0, 'stages_frozen': False, 'qualification': False, 'comparative_usefulness': False, 'selection': False, 'historical_results_unchanged': True, 'new_external_calls_for_consolidation': 0, 'latest_grant': after, 'batch_operations_including_build': 15, 'batch_charged_operation_seconds': charged, 'image_retained': build['image_id'], 'old_image_retained': review['parent_image'], 'excluded': [{'case': identity, 'observed': 'Reference collection ERROR, exit2; required identities absent. Other variants unstarted.', 'cause': 'Exact exception/traceback not retained; static imports do not establish the runtime cause.'} for identity in ['modelcontextprotocol__python-sdk-222-declared-tests', 'modelcontextprotocol__python-sdk-384-aeep-contract-audit', 'elementsinteractive__twyn-317-declared-tests']] + old['excluded']}
    assert output['repository_count'] == 27 and output['required_reference_identities'] == 2613
    with (HERE / 'provisional-pool.json').open('x') as stream:
        json.dump(output, stream, indent=2); stream.write('\n')
    print(json.dumps({k: output[k] for k in ('case_count', 'repository_count', 'family_counts', 'required_reference_identities', 'missing_family_counts', 'batch_charged_operation_seconds', 'latest_grant')}))


if __name__ == '__main__':
    main()
