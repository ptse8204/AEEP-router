"""Count source-pool prerequisites without adopting cases or running repository code."""
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
POOL = HERE.parent / 'repository-cohort-20261022/union-candidate-metadata.json'
INVENTORY = HERE.parent / 'repository-suite-integration-20261022/cohort-inventory.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    pool, inventory = json.loads(POOL.read_text()), json.loads(INVENTORY.read_text())
    raw = {}
    for item in pool['sources']:
        path = ROOT / item['private_cache']
        assert sha(path) == item['sha256']
        for row in json.loads(path.read_text())['rows']:
            raw[row['row']['instance_id']] = row['row']
    eligible, excluded = [], Counter()
    for record in inventory['rows']:
        if record['metadata_blockers']:
            excluded['existing_metadata_blocker'] += 1
            continue
        row = raw[record['instance_id']]
        required = row['FAIL_TO_PASS'] + row['PASS_TO_PASS']
        if not required or not all(name.split('::')[0].startswith('tests/') for name in required):
            excluded['required_test_outside_current_tests_directory_contract'] += 1
            continue
        eligible.append(record)
    repositories = {item['repo'].casefold() for item in eligible}
    by_family = {family: {item['repo'].casefold() for item in eligible if item['family_hint'] == family}
                 for family in ('single-file-repair', 'multi-file-repair')}
    targets = {'qualification': {'single-file-repair': 3, 'multi-file-repair': 3, 'contract-audit': 2},
               'training': {'single-file-repair': 9, 'multi-file-repair': 9, 'contract-audit': 10},
               'holdout': {'single-file-repair': 35, 'multi-file-repair': 35, 'contract-audit': 35}}
    assert [sum(counts.values()) for counts in targets.values()] == [8, 28, 105]
    assert all(max(counts.values()) - min(counts.values()) <= 1 for counts in targets.values())
    assert all(sum(stage[family] for stage in targets.values()) == 47 for family in targets['holdout'])
    review = {'schema_version': 'aeep.repository-cohort-capacity.v1', 'metadata_only': True,
        'dataset_revision': inventory['source_revision'], 'pool_sha256': sha(POOL), 'inventory_sha256': sha(INVENTORY),
        'candidate_issues': len(eligible), 'candidate_repositories': len(repositories), 'excluded_counts': dict(excluded),
        'family_issue_counts': dict(Counter(item['family_hint'] for item in eligible)),
        'family_repository_counts': {family: len(items) for family, items in by_family.items()},
        'balanced_planning_counts': targets, 'planning_counts_are_not_frozen_stages': True,
        'necessary_repository_capacity_checks': {'at_least_141_total': len(repositories) >= 141,
            'at_least_47_single_file': len(by_family['single-file-repair']) >= 47,
            'at_least_47_multi_file': len(by_family['multi-file-repair']) >= 47},
        'caveat': 'These are necessary counts, not proof of a jointly assignable licensed/reproducible cohort. Audits must be authored from distinct corrected snapshots and separately verified, never relabeled buggy issues.',
        'unresolved_per_case': ['source archive/license/edit-scope review', 'runtime closure and adapted version applicability',
            'published reference and original/counterexample reproduction', 'authored audit contract where applicable',
            'repository-grouped stage independence and final balanced freeze'],
        'next_execution_review': 'operation-review.json', 'cases_adopted': 0, 'stage_assignments_frozen': 0,
        'model_trials': 0, 'external_code_executed': False,
        'critical_path': ['Verify new workload references and counterexamples', 'Finish reproducible independent balanced8/28/105 cohorts',
            'Freeze exact worker/candidate/model/metric definitions', 'Run required-use capability qualification',
            'Run optional-use paired comparisons including stronger baseline and candidate-use capture',
            'Evaluate actual AEEP selection against independent value evidence and equal-inventory alternatives'],
        'separate_gates': ['human control comprehension/use', 'workload-derived infrastructure resource acceptance', 'release authorization']}
    (HERE / 'cohort-capacity.json').write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps({key: review[key] for key in ('candidate_issues', 'candidate_repositories', 'family_repository_counts',
        'necessary_repository_capacity_checks', 'cases_adopted', 'external_code_executed')}))


if __name__ == '__main__':
    main()
