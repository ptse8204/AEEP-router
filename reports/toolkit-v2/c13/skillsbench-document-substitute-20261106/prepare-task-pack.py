"""Package the verified document/data substitute without its restricted oracle."""

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
ROOT = HERE.parents[3]
PRIVATE = ROOT / '.aeep' / HERE.name


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def bind(path, data):
    assert not path.is_symlink()
    if path.exists():
        assert path.read_bytes() == data
        return
    with path.open('xb') as stream:
        stream.write(data)


def write(path, value):
    bind(path, (json.dumps(value, indent=2) + '\n').encode())


review = read(HERE / 'candidate-review.json')
selection = read(HERE / 'selection-and-oracle-rights.json')
reference = read(HERE / 'result.json')
task = review['candidate']
assert selection['approved_selection'] == task and not selection['oracle_execution_allowed']
assert reference['passed'] and reference['models'] == 0 and reference['cleanup_verified']
assert reference['observed']['protected_grader']['reference']['upstream_binary_reward'] == 1
root = PRIVATE / 'task-pack-v1'
root.mkdir(mode=0o700, exist_ok=True)
assert not root.is_symlink()
files = [review['candidate_license_notice'], *[a for a in review['assets'] if '/oracle/' not in a['path']]]
roles = {'LICENSE': 'license', 'task.md': 'instruction', 'environment/input.pptx': 'input',
         'environment/Dockerfile': 'environment', 'verifier/test_outputs.py': 'verifier',
         'verifier/test.sh': 'verifier'}
assets = []
for item in files:
    name = item['path']
    relative = name.removeprefix(f'tasks/{task}/')
    source = PRIVATE / relative if name != 'LICENSE' else ROOT / '.aeep/skillsbench-stack-9a1f4dd5/LICENSE'
    data = source.read_bytes()
    assert sha(data) == item['sha256'] and len(data) == item['bytes']
    target = root / name
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    bind(target, data)
    target.chmod(0o400)
    assets.append({'path': name, 'sha256': item['sha256'], 'bytes': item['bytes'], 'role': roles[relative]})
assert len(assets) == len(roles) == 6
reference_source = (HERE / 'reference.py').read_bytes()
assert sha(reference_source) == read(HERE / 'reference-static-result.json')['reference_source_sha256']
oracle = root / 'aeep-protected/independent-reference.py'
oracle.parent.mkdir(mode=0o700, exist_ok=True)
assert not oracle.parent.is_symlink()
bind(oracle, reference_source)
oracle.chmod(0o400)
assets.append({'path': str(oracle.relative_to(root)), 'sha256': sha(reference_source),
               'bytes': len(reference_source), 'role': 'oracle'})
pack = BenchmarkPack.model_validate({
    'pack_id': 'skillsbench',
    'source': {'repository': 'https://github.com/benchflow-ai/skillsbench', 'revision': review['revision'],
               'artifact_sha256': sha((HERE / 'candidate-review.json').read_bytes()), 'license_expression': 'Apache-2.0',
               'data_rights': 'Private integration; provider disclosure requires separate authority.'},
    'tasks': [{'task_id': task, 'domain': 'document-data', 'difficulty': review['difficulty'],
               'assets': assets, 'output_paths': ['results.pptx'], 'upstream_score': 'binary',
               'rights_review_ref': None,
               'adaptations': [
                   'Original instructions and deck enter the worker archive.',
                   'The independent OOXML reference replaces the uncleared upstream oracle for calibration.',
                   'The original verifier uses isolated scratch paths and exact cached dependencies.',
               ]}],
})
rights = TaskRightsReview(
    source_revision=review['revision'], task_id=task,
    assets={asset['path']: asset['sha256'] for asset in assets},
    local_execution_allowed=True, provider_disclosure_allowed=False,
    basis=[review['task_source'], 'Candidate review sha256 ' + sha((HERE / 'candidate-review.json').read_bytes()),
           'Selection and oracle rights sha256 ' + sha((HERE / 'selection-and-oracle-rights.json').read_bytes())],
)
task_archive = task_input(pack, root, task)
raw = base64.b64decode(task_archive['task_archive_b64'], validate=True)
assert sha(raw) == task_archive['task_archive_sha256']
public = {asset['path']: asset['sha256'] for asset in assets if asset['role'] in ('instruction', 'input')}
with ZipFile(io.BytesIO(raw)) as archive:
    assert set(archive.namelist()) == public.keys() and len(public) == 2
    assert all(sha(archive.read(path)) == digest for path, digest in public.items())
write(HERE / 'task-pack.json', pack.model_dump(mode='json'))
write(HERE / 'local-rights-draft.json', rights.model_dump(mode='json'))
transport = {'pack_root': str(root), 'pack_sha256': content_digest(pack.model_dump(mode='json')), 'task_id': task,
             'public_archive_sha256': sha(raw), 'public_archive_bytes': len(raw), 'public_files': public,
             'protected_assets_excluded_from_archive': True, 'rights_registered_for_workflow': False,
             'provider_disclosure': False, 'models': 0}
write(HERE / 'task-pack-transport.json', transport)
print(json.dumps(transport))
