"""Select new repository groups from pinned metadata, then reuse bounded data reads."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    previous_path = BASE / 'repository-supported-suites-20261027/source-review.json'
    previous = json.loads(previous_path.read_text())
    known_repositories = {r['repository'].casefold() for r in previous['sources']}
    inv_path = BASE / 'repository-suite-integration-20261022/cohort-inventory.json'
    inventory = json.loads(inv_path.read_text())
    eligible = {r['instance_id']: r for r in inventory['rows'] if not r['metadata_blockers']}
    metadata_path = BASE / 'repository-cohort-20261022/union-candidate-metadata.json'
    metadata = json.loads(metadata_path.read_text())
    meta = {r['instance_id']: r for r in metadata['candidate_metadata']}
    candidates = {}
    for source in metadata['sources']:
        path = ROOT / source['private_cache']; assert digest(path) == source['sha256']
        for wrapper in json.loads(path.read_text())['rows']:
            row = wrapper['row']; identity = row['instance_id']
            if (identity in eligible and row['repo'].casefold() not in known_repositories
                    and all(n.startswith('tests/') for n in row['FAIL_TO_PASS'] + row['PASS_TO_PASS'])):
                candidates[identity] = row
    # Prefer modest declared runtime scope, then a fixed identity hash. Neither
    # model outcomes nor reproduced-reference outcomes are available or used.
    def rank(identity):
        m = meta[identity]
        return (m['has_pre_install'], m['has_environment_file'], len(m['declared_pip_packages']),
                hashlib.sha256(('aeep-diversity-20261027:' + identity).encode()).hexdigest())
    selected, used = [], set()
    for family, count, audit in [('single-file-repair', 8, True), ('multi-file-repair', 6, False), ('single-file-repair', 6, False)]:
        added = 0
        for identity in sorted(candidates, key=rank):
            row = candidates[identity]
            if row['repo'].casefold() in used or eligible[identity]['family_hint'] != family:
                continue
            used.add(row['repo'].casefold())
            selected.append({'identity': identity, 'repository': row['repo'], 'metadata_family_hint': family,
                             'proposed_audit': audit, 'runtime_metadata': meta[identity]})
            added += 1
            if added == count:
                break
        assert added == count
    assert len(selected) == len(used) == 20
    (HERE / 'selection.json').write_text(json.dumps({'selection': selected, 'candidate_rows': len(candidates),
        'prior_source_manifest': str(previous_path.relative_to(ROOT)), 'prior_source_manifest_sha256': digest(previous_path),
        'metadata_manifest_sha256': digest(metadata_path), 'inventory_sha256': digest(inv_path),
        'proposed_counts': {'contract-audit': 8, 'multi-file-repair': 6, 'single-file-repair': 6},
        'stage_assignments_frozen': False, 'outcome_based_selection': False}, indent=2) + '\n')
    spec = importlib.util.spec_from_file_location('existing_inert_source_collector', BASE / 'repository-workload-batch-20261022/collect-sources.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.HERE = HERE
    module.CACHE = ROOT / '.aeep/repository-diverse-sources-20261027'
    module.EXPLICIT_SQLGLOT = {r['identity'] for r in selected}
    module.REPOSITORIES = ()
    module.main()
    new_path = HERE / 'source-review.json'
    new = json.loads(new_path.read_text())
    assert len(new['sources']) == 20 and new['downloaded_bytes'] <= 20 * 650_001
    assert not known_repositories & {r['repository'].casefold() for r in new['sources']}
    (HERE / 'new-source-review.json').write_text(json.dumps(new, indent=2) + '\n')
    combined = {**new, 'sources': [*previous['sources'], *new['sources']],
                'new_rows': 20, 'new_repository_groups': 20, 'prior_source_review': str(previous_path.relative_to(ROOT)),
                'prior_source_review_sha256': digest(previous_path), 'rows': len(previous['sources']) + 20,
                'read_only_source_curation': True, 'cases_adopted': 0, 'stage_frozen': False}
    assert len({r['instance_id'] for r in combined['sources']}) == len(combined['sources'])
    new_path.write_text(json.dumps(combined, indent=2) + '\n')
    print(json.dumps({'new_sources': 20, 'new_repository_groups': 20, 'combined_sources': combined['rows'],
                      'new_bytes': new['downloaded_bytes'], 'subject_execution': False, 'models': 0}))


if __name__ == '__main__':
    main()
