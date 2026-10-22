"""Classify cached task metadata; no repository or test execution, no holdout freeze."""
import collections
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


meta_path = ROOT / 'reports/toolkit-v2/c13/repository-cohort-20261022/union-candidate-metadata.json'
meta = json.loads(meta_path.read_text())
rows = []
for source in meta['sources']:
    path = ROOT / source['private_cache']
    assert sha(path) == source['sha256']
    rows += [item['row'] for item in json.loads(path.read_text())['rows']]
assert len(rows) == len({row['instance_id'] for row in rows}) == 860
excluded = {'delgan/loguru', 'pallets/click', 'marshmallow-code/marshmallow', 'pgmpy/pgmpy'}
all_origins = collections.Counter((row['repo'].casefold(), row['base_commit']) for row in rows)
records = []
for row in rows:
    blockers = []
    repository = row['repo'].casefold()
    if repository in excluded:
        blockers.append('development_repository_excluded')
    if not row['PASS_TO_PASS']:
        blockers.append('no_preservation_identities')
    if all_origins[(repository, row['base_commit'])] > 1:
        blockers.append('shared_source_origin_requires_group_resolution')
    task = row['problem_statement'] + ('\n\n' + row['interface'] if row.get('interface') else '')
    if len(task) > 3750:
        blockers.append('public_task_requires_scope_review_before_4000_character_contract')
    source_names = re.findall(r'^diff --git a/(\S+) b/\S+', row['patch'], re.M)
    python_files = [name for name in source_names if name.endswith('.py') and not name.startswith(('tests/', 'test/'))]
    if not python_files:
        blockers.append('no_scoped_python_repair')
    if len(python_files) > 32:
        blockers.append('patch_file_bound')
    config = row['install_config']
    records.append({'instance_id':row['instance_id'],'repo':row['repo'],'base_commit':row['base_commit'],
        'family_hint':'multi-file-repair' if len(python_files)>1 else 'single-file-repair',
        'published_source_file_count':len(python_files),'fail_to_pass_count':len(row['FAIL_TO_PASS']),
        'pass_to_pass_count':len(row['PASS_TO_PASS']),'declared_python':config['python'],
        'installer_record_present':bool(config.get('install') or config.get('pre_install')),
        'metadata_blockers':blockers,'adopted':False,'stage':None,
        'unverified':['repository_license','source_archive_size_and_safety','exact_runtime_closure',
            'baseline_reproduction','reference_success','regression_rejection','public_worker_exposure','origin_independence']})
eligible = [row for row in records if not row['metadata_blockers']]
result = {'schema_version':'aeep.repository-cohort-inventory.v1','source_revision':meta['revision_before_and_after'],
    'metadata_sha256':sha(meta_path),'development_excluded_repositories':sorted(excluded),
    'count':len(records),'metadata_only_candidates':len(eligible),
    'candidate_repositories':len({row['repo'].casefold() for row in eligible}),
    'family_hints':dict(collections.Counter(row['family_hint'] for row in eligible)),
    'declared_python_counts':dict(collections.Counter(row['declared_python'] for row in eligible)),
    'blocker_counts':dict(collections.Counter(item for row in records for item in row['metadata_blockers'])),
    'cases_adopted':0,'frozen_holdouts':0,'authored_no_change_controls':0,'executed_external_code':False,
    'warning':'Metadata filtering supplies no runtime, rights, preservation or validity evidence. Repair tasks cannot be relabelled as no-change controls.',
    'rows':records}
with (HERE/'cohort-inventory.json').open('x') as output:
    json.dump(result,output,indent=2);output.write('\n')
print(json.dumps({key:value for key,value in result.items() if key!='rows'}))
