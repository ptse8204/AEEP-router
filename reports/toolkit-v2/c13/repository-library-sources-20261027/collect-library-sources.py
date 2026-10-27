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
    previous_path = BASE / 'repository-diverse-sources-20261027/source-review.json'
    previous = json.loads(previous_path.read_text())
    known_repositories = {r['repository'].casefold() for r in previous['sources']}
    screening = json.loads((BASE / 'repository-declared-tests-20261022/composed-screening-reproduction.json').read_text())
    known_repositories.update(r['repository'].removeprefix('https://github.com/').casefold() for r in screening['cases'])
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
    # A named domain sample of libraries and CLIs, chosen before any new source
    # or outcome is observed. Sparse package metadata is unknown, not low cost.
    wanted = ['marshmallow-code/marshmallow-sqlalchemy',
        'luolingchun/flask-openapi3', 'opsmill/infrahub-sdk-python',
        'Ljzd-PRO/KToolBox', 'Spenhouet/confluence-markdown-exporter', 'CrossGL/crosstl',
        'googleapis/python-api-core', 'tox-dev/sphinx-autodoc-typehints', 'qBraid/pyqasm',
        'DARMA-tasking/LB-analysis-framework']
    selected, used = [], set()
    for repository in wanted:
        options = [i for i, row in candidates.items() if row['repo'].casefold() == repository.casefold()]
        assert options, repository
        identity = min(options, key=lambda i: (eligible[i]['family_hint'] != 'multi-file-repair', hashlib.sha256(('library-20261027:' + i).encode()).hexdigest()))
        row = candidates[identity]; used.add(row['repo'].casefold())
        selected.append({'identity': identity, 'repository': row['repo'],
            'metadata_family_hint': eligible[identity]['family_hint'], 'proposed_audit': False, 'runtime_metadata': meta[identity]})
    single = sorted((r for r in selected if r['metadata_family_hint'] == 'single-file-repair'), key=lambda r: hashlib.sha256(('audit-20261027:' + r['identity']).encode()).hexdigest())
    assert len(single) >= 6
    for r in single[:6]:r['proposed_audit'] = True
    assert len(selected) == len(used) == 10
    (HERE / 'selection.json').write_text(json.dumps({'selection': selected, 'candidate_rows': len(candidates),
        'prior_source_manifest': str(previous_path.relative_to(ROOT)), 'prior_source_manifest_sha256': digest(previous_path),
        'metadata_manifest_sha256': digest(metadata_path), 'inventory_sha256': digest(inv_path),
        'selection_basis': 'Named metadata-only domain sample of libraries/CLIs; prefer available multi-file metadata. Six single-file snapshots preassigned as authored audits. Missing dependency metadata is unknown.',
        'stage_assignments_frozen': False, 'outcome_based_selection': False}, indent=2) + '\n')
    spec = importlib.util.spec_from_file_location('existing_inert_source_collector', BASE / 'repository-workload-batch-20261022/collect-sources.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.HERE = HERE
    module.CACHE = ROOT / '.aeep/repository-library-sources-20261027-v2'
    module.EXPLICIT_SQLGLOT = {r['identity'] for r in selected}
    module.REPOSITORIES = ()
    module.main()
    new_path = HERE / 'source-review.json'
    new = json.loads(new_path.read_text())
    assert len(new['sources']) == 10 and new['downloaded_bytes'] <= 10 * 650_001
    assert not known_repositories & {r['repository'].casefold() for r in new['sources']}
    (HERE / 'new-source-review.json').write_text(json.dumps(new, indent=2) + '\n')
    combined = {**new, 'sources': [*previous['sources'], *new['sources']],
                'new_rows': 10, 'new_repository_groups': 10, 'prior_source_review': str(previous_path.relative_to(ROOT)),
                'prior_source_review_sha256': digest(previous_path), 'rows': len(previous['sources']) + 10,
                'read_only_source_curation': True, 'cases_adopted': 0, 'stage_frozen': False}
    assert len({r['instance_id'] for r in combined['sources']}) == len(combined['sources'])
    new_path.write_text(json.dumps(combined, indent=2) + '\n')
    print(json.dumps({'new_sources': 10, 'new_repository_groups': 10, 'combined_sources': combined['rows'],
                      'new_bytes': new['downloaded_bytes'], 'subject_execution': False, 'models': 0}))


if __name__ == '__main__':
    main()
