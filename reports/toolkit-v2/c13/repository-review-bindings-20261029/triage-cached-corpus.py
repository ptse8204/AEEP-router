"""Inventory unused cached public snapshots as inert metadata, never task evidence."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repository(value):
    return value.removeprefix('https://github.com/').removesuffix('.git').strip('/').casefold()


def source_paths(patch):
    paths = re.findall(r'^\+\+\+ b/(.+)$', patch, re.MULTILINE)
    return sorted({name for name in paths if name.endswith('.py')
        and not any(part.casefold() in ('tests', 'test', 'docs', 'documentation')
                    for part in Path(name).parts)
        and not Path(name).name.startswith('test_')
        and not Path(name).name.endswith('_test.py')
        and Path(name).name not in ('setup.py', 'conftest.py')})


def main():
    assert repository('https://github.com/Owner/Project.git') == repository('owner/project')
    assert source_paths('+++ b/library/a.py\n+++ b/tests/test_a.py\n+++ b/setup.py\n') == ['library/a.py']
    pool_path = HERE.parent / 'repository-stable-workspace-20261028/provisional-pool.json'
    pool = json.loads(pool_path.read_text())
    cases_file = ROOT / pool['cases_file']
    assert sha(cases_file) == pool['cases_file_sha256']
    cases = json.loads(cases_file.read_text())
    used = {(repository(c['source_repository']), c['source_revision']) for c in cases}
    queues, rows, origins, divergent = {}, {}, {}, set()
    for path in sorted((ROOT / '.aeep').glob('*/queue.json')):
        queues[str(path.relative_to(ROOT))] = sha(path)
        for row in json.loads(path.read_text()):
            identity = row['instance_id']
            canonical = {k: row[k] for k in ('repo', 'base_commit', 'patch', 'test_patch', 'FAIL_TO_PASS', 'PASS_TO_PASS')}
            fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
            if identity in rows and rows[identity][0] != fingerprint:
                divergent.add(identity)
            rows.setdefault(identity, (fingerprint, row))
            origins.setdefault(identity, []).append(str(path.relative_to(ROOT)))
    unused = []
    for identity, (fingerprint, row) in sorted(rows.items()):
        if (repository(row['repo']), row['base_commit']) in used:
            continue
        paths = source_paths(row['patch'])
        archives = sorted((ROOT / '.aeep').glob('*/' + identity + '/source.tar.gz'))
        unused.append({'instance_id': identity, 'repository': row['repo'],
            'base_commit': row['base_commit'], 'metadata_semantic_sha256': fingerprint,
            'queue_files': origins[identity], 'conflicting_cached_metadata': identity in divergent,
            'source_patch_paths': paths,
            'preliminary_path_shape': 'one-Python-body-path' if len(paths) == 1 else
                'multiple-Python-body-paths' if len(paths) > 1 else 'requires-manual-scope-audit',
            'published_fail_to_pass_count': len(row['FAIL_TO_PASS']),
            'published_pass_to_pass_count': len(row['PASS_TO_PASS']),
            'cached_archives_not_yet_verified': [str(p.relative_to(ROOT)) for p in archives],
            'qualified': False, 'stage_assigned': False,
            'remaining_checks': ['review rights and exact source/cache pins',
                'distinguish behavioral changes from docstrings and metadata',
                'resolve genuine runtime and installed-metadata requirements',
                'preserve every declared obligation; reproduce reference and counterexamples under exact authority']})
    counts = Counter(x['preliminary_path_shape'] for x in unused)
    assert len(cases) == 64 and len(rows) == 184 and len(unused) == 133
    result = {'metadata_only': True, 'queue_sha256': queues,
        'prior_pool_file': str(pool_path.relative_to(ROOT)), 'prior_pool_sha256': sha(pool_path),
        'unique_cached_rows': len(rows), 'unused_rows': len(unused),
        'unused_repositories': len({repository(x['repository']) for x in unused}),
        'preliminary_path_shapes_not_verified_families': dict(counts),
        'rows_with_cached_archive': sum(bool(x['cached_archives_not_yet_verified']) for x in unused),
        'divergent_cached_ids': sorted(divergent), 'rows': unused,
        'pool_unchanged': 64, 'remaining_verified_cases_needed': 77,
        'remaining_family_counts': pool['missing_family_counts'],
        'new_software_execution_or_download_or_model_or_grant_charge': False,
        'qualification_or_usefulness_or_selection_evidence': False}
    with (HERE / 'cached-corpus-triage.json').open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(json.dumps({k: result[k] for k in ('unused_rows', 'unused_repositories',
        'preliminary_path_shapes_not_verified_families', 'rows_with_cached_archive', 'divergent_cached_ids')}))


if __name__ == '__main__':
    main()
