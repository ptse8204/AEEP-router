"""Small authored controls plus the actual failed nested-review regression."""
import json
from pathlib import Path
import tempfile

from review_bindings import audit, sha

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='aeep-review-binding-') as temporary:
        root = Path(temporary)
        asset = root / 'asset.txt'
        asset.write_text('authored fixture')
        child = root / 'runtime-review.json'
        parent = root / 'approval-bundle.json'

        def write(expected):
            child.write_text(json.dumps({'assets': {str(asset): expected}}))
            parent.write_text(json.dumps({'assets': {str(asset): sha(asset)},
                'components': {'runtime': {'directory': str(root),
                    'review_file': child.name, 'review_sha256': sha(child)}}}))

        write(sha(asset))
        assert audit([parent], root)['passed']
        checks.append('matching_parent_child_bindings_pass')
        write('0' * 64)
        result = audit([parent], root)
        assert not result['passed']
        assert {e['kind'] for e in result['errors']} == {'conflicting_pin', 'file_binding'}
        checks.append('outer_current_hash_cannot_shadow_nested_stale_hash')
        write(sha(asset))
        child.write_text(child.read_text() + '\n')
        assert not audit([parent], root)['passed']
        checks.append('child_review_bytes_checked')
        write(sha(asset))
        alias = root / 'alias'
        alias.symlink_to(asset)
        child.write_text(json.dumps({'assets': {str(alias): sha(asset)}}))
        assert not audit([child], root)['passed']
        checks.append('symlink_binding_rejected')
        child.write_text(json.dumps({'assets': {str(root / 'missing'): sha(asset)}}))
        assert not audit([child], root)['passed']
        checks.append('missing_binding_rejected')
        child.write_text(json.dumps({'build_documents': {'authored': {'document': {
            'dependency_digests': {str(asset): '0' * 64}}}}}))
        assert not audit([child], root)['passed']
        checks.append('embedded_subject_dependencies_checked')
    assert not Path(temporary).exists()
    old = HERE.parent / 'repository-shared-native-20261028'
    failed = audit([old / 'approval-bundle.json'], ROOT)
    stale = [e for e in failed['errors'] if e['kind'] == 'file_binding']
    assert len(stale) == 3 and {Path(e['path']).name for e in stale} == {
        'run-integration-bundle.py', 'prepare-integration-bundle.py', 'check-integration-dispatch.py'}
    checks.append('actual_17defe159_graph_rejects_exact_three_stale_pins')
    result = {'passed': True, 'checks': checks, 'actual_failed_review_audit': failed,
        'owned_fixtures_removed': True, 'new_external_execution_or_grant_charges': 0,
        'fixture_is_not_authority_or_benchmark': True}
    with (HERE / 'binding-check.json').open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(json.dumps({'passed': True, 'checks': len(checks), 'stale_pins_detected': len(stale)}))


if __name__ == '__main__':
    main()
