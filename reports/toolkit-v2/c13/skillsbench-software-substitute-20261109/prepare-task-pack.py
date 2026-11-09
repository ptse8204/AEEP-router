"""Verify selected source files and stage a private SkillsBench task pack."""

import base64
import hashlib
import io
import json
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

from aeep.assessment.models import content_digest
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.workflow_preparation import TaskRightsReview

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PACK_ROOT = ROOT / '.aeep' / HERE.name / 'pack'
REVIEW = HERE / 'candidate-review.json'
SELECTION = HERE / 'selection.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    assert not any(part.is_symlink() for part in (path, *path.parents))
    if path.exists():
        assert path.read_bytes() == data
    else:
        with path.open('xb') as stream:
            stream.write(data)
        path.chmod(0o400)


def write(path, value):
    save(path, (json.dumps(value, indent=2) + '\n').encode())


def fetch_exact(url, size, digest):
    with urlopen(url, timeout=15) as stream:
        data = stream.read(size + 1)
    assert len(data) == size and sha(data) == digest
    return data


def prepare():
    review_bytes = REVIEW.read_bytes()
    review = json.loads(review_bytes)
    task = review['candidate']
    revision = review['revision']
    selection = json.loads(SELECTION.read_bytes())
    assert selection == {'approved_selection': task, 'replaces': review['replaces_if_selected'],
                         'candidate_review_sha256': sha(review_bytes), 'runtime_authorized_by_selection': False,
                         'provider_disclosure': False, 'models': 0}
    prefix = f'tasks/{task}/'
    roles = {'LICENSE': 'license', 'task.md': 'instruction', 'environment/trace.jsonl': 'input',
             'environment/config.json': 'input', 'environment/Dockerfile': 'environment',
             'verifier/test.sh': 'verifier', 'verifier/test_outputs.py': 'verifier',
             'verifier/oracle_helpers.py': 'verifier', 'oracle/solve.sh': 'oracle'}
    assert {name.removeprefix(prefix) for name in review['assets']} == roles.keys()
    assets = []
    for name, entry in review['assets'].items():
        url = f'https://raw.githubusercontent.com/benchflow-ai/skillsbench/{revision}/{name}'
        data = fetch_exact(url, entry['bytes'], entry['sha256'])
        git_blob = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
        assert git_blob == entry['git_blob']
        save(PACK_ROOT / name, data)
        assets.append({'path': name, 'sha256': entry['sha256'], 'bytes': entry['bytes'],
                       'role': roles[name.removeprefix(prefix)]})
    origin = review['input_origin']
    notice = origin['license_notice']
    url = f"https://raw.githubusercontent.com/kvcache-ai/Mooncake/{origin['revision']}/LICENSE-APACHE"
    data = fetch_exact(url, notice['bytes'], notice['sha256'])
    name = 'notices/mooncake-LICENSE-APACHE'
    save(PACK_ROOT / name, data)
    assets.append({'path': name, **notice, 'role': 'license'})
    pack = BenchmarkPack.model_validate({
        'pack_id': 'skillsbench',
        'source': {'repository': 'https://github.com/benchflow-ai/skillsbench', 'revision': revision,
                   'artifact_sha256': sha(review_bytes), 'license_expression': 'Apache-2.0',
                   'data_rights': 'Private integration with retained SkillsBench and Mooncake notices. Provider disclosure needs separate authority.'},
        'tasks': [{'task_id': task, 'domain': 'software-engineering', 'difficulty': review['difficulty'],
                   'assets': assets, 'output_paths': ['report.json'], 'upstream_score': 'binary',
                   'adaptations': ['Original task instructions, config and trace are kept byte-identical.',
                                   'The review will map upstream /root paths to isolated nonroot scratch paths.',
                                   'Bundled skills, original solver and verifier stay outside the agent archive.']}],
    })
    rights = TaskRightsReview(source_revision=revision, task_id=task,
        assets={asset['path']: asset['sha256'] for asset in assets},
        local_execution_allowed=True, provider_disclosure_allowed=False,
        basis=[review['task_source'], origin['trace'], origin['license'], 'Candidate review SHA-256 ' + sha(review_bytes)])
    archive = task_input(pack, PACK_ROOT, task)
    raw = base64.b64decode(archive['task_archive_b64'], validate=True)
    public = {asset['path']: asset['sha256'] for asset in assets if asset['role'] in ('instruction', 'input')}
    assert len(public) == 3 and sha(raw) == archive['task_archive_sha256']
    with ZipFile(io.BytesIO(raw)) as package:
        assert set(package.namelist()) == public.keys()
        assert all(sha(package.read(path)) == digest for path, digest in public.items())
    write(HERE / 'task-pack.json', pack.model_dump(mode='json'))
    write(HERE / 'local-rights-draft.json', rights.model_dump(mode='json'))
    write(HERE / 'task-pack-transport.json', {'pack_root': str(PACK_ROOT), 'pack_sha256': content_digest(pack.model_dump(mode="json")),
        'task_id': task, 'public_archive_sha256': sha(raw), 'public_archive_bytes': len(raw), 'public_files': public,
        'protected_assets_excluded_from_archive': True, 'rights_registered_for_workflow': False,
        'runtime_executed': False, 'provider_disclosure': False, 'models': 0})


if __name__ == '__main__':
    prepare()
