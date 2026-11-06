"""Stage the proven Invoice Fraud task through the existing SkillsBench transport."""

import base64
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

from aeep.assessment.models import content_digest
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.workflow_preparation import TaskRightsReview

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'source-inventory.json'
ASSET_USE = HERE / 'asset-use.json'
RESULT = HERE / 'continuation/reference-execution/result.json'


def read(path):
    return json.loads(path.read_bytes())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(name, value):
    with (HERE / name).open('x') as out:
        out.write(json.dumps(value, indent=2) + '\n')


source = read(SOURCE)
use, reference = read(ASSET_USE), read(RESULT)
assert use['local_engineering_use'] == 'CLEARED_FOR_PINNED_CONTRIBUTION_FILES'
assert use['provider_disclosure'] == 'SEPARATE_AUTHORITY_REQUIRED'
assert reference['passed'] and reference['unsettled_operations'] == 0 and reference['models'] == 0
assert reference['phases']['reference']['status'] == 'passed'
assert [reference['phases'][key]['status'] for key in ('missing','empty','infrastructure')] == [
    'rejected', 'rejected', 'infrastructure_error',
]
private = Path(source['private_root'])
root = private / 'task-pack'
root.mkdir(mode=0o700)
task = source['task_id']
roles = {'notice': 'license', 'review': 'environment', 'oracle': 'oracle', 'verifier': 'verifier'}
assets = []
for name, asset in source['files'].items():
    original = private / asset['role'] / Path(name).name
    raw = original.read_bytes()
    assert len(raw) == asset['bytes'] and sha(raw) == asset['sha256']
    role = ('instruction' if name.endswith('/task.md') else 'input') if asset['role'] == 'public' else roles[asset['role']]
    target = root / name
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with target.open('xb') as out:
        out.write(raw)
    target.chmod(0o400)
    assets.append({'path': name, 'sha256': asset['sha256'], 'bytes': asset['bytes'], 'role': role})

assert len(assets) == 10 and all(row['role'] != 'candidate_skill' for row in assets)
rights = TaskRightsReview(
    source_revision=source['revision'], task_id=task,
    assets={row['path']: row['sha256'] for row in assets},
    local_execution_allowed=True, provider_disclosure_allowed=False,
    basis=[use['contribution'], use['repository_notice'], 'asset-use.json sha256:' + sha(ASSET_USE.read_bytes())],
)
pack = BenchmarkPack.model_validate({
    'pack_id': 'skillsbench',
    'source': {'repository': 'https://github.com/benchflow-ai/skillsbench', 'revision': source['revision'],
               'artifact_sha256': sha(SOURCE.read_bytes()), 'license_expression': 'Apache-2.0',
               'data_rights': 'Private engineering use of the pinned contribution. Provider disclosure requires separate authority.'},
    'tasks': [{
        'task_id': task, 'domain': 'document-data', 'difficulty': 'hard', 'assets': assets,
        'output_paths': ['fraud_report.json'], 'upstream_score': 'binary',
        'rights_review_ref': None,
        'adaptations': [
            'Only the original public instruction and inputs are included in agent transport.',
            'Offline reference run mounts an isolated tmpfs at the original /root path and uses pinned pytest wheels.',
            'Protected verifier and answers stay outside the agent archive. Binary reward follows the original test assertions.',
        ],
    }],
})
transient = task_input(pack, root, task)
raw = base64.b64decode(transient['task_archive_b64'], validate=True)
assert sha(raw) == transient['task_archive_sha256']
public = {item['path']: item['sha256'] for item in assets if item['role'] in ('instruction', 'input')}
with ZipFile(io.BytesIO(raw)) as archive:
    assert len(archive.namelist()) == len(public) == 4
    assert set(archive.namelist()) == public.keys()
    assert all(sha(archive.read(path)) == digest for path, digest in public.items())
write('task-pack.json', pack.model_dump(mode='json'))
write('local-rights-draft.json', rights.model_dump(mode='json'))
report = {
    'pack_root': str(root), 'pack_sha256': content_digest(pack.model_dump(mode='json')),
    'local_rights_draft_sha256': content_digest(rights), 'rights_registered_for_workflow': False,
    'public_archive_sha256': sha(raw), 'public_archive_bytes': len(raw), 'public_files': public,
    'protected_assets_excluded_from_archive': True,
    'reference_result_sha256': sha(RESULT.read_bytes()), 'provider_disclosure': False, 'models': 0,
}
write('task-pack-transport.json', report)
print(json.dumps(report))
