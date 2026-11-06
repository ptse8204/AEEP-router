"""Pin original upstream bytes and narrow offline role mounts for the first reference journey."""

import hashlib
import json
import shutil
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
C13 = HERE.parent
PRIVATE = ROOT / '.aeep' / HERE.name
WHEELS = ROOT / '.aeep/skillsbench-spring-reference-20261105/wheels'
SPRING = C13 / 'skillsbench-spring-reference-20261105/toolchain.json'
AUTHORITY = C13 / 'pipeline-standing-authority-20261104.json'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def publish(path, content, mode):
    with path.open('xb') as stream:
        stream.write(content)
    path.chmod(mode)


def copy(source, target, expected):
    assert sha(source) == expected
    publish(target, source.read_bytes(), 0o444)


assert shutil.disk_usage(ROOT).free >= 52 * 1024**3
source = read(HERE / 'source-inventory.json')
asset_use = read(HERE / 'asset-use.json')
assert source['revision'] == asset_use['revision']
assert asset_use['local_engineering_use'] == 'CLEARED_FOR_PINNED_CONTRIBUTION_FILES'
acquisition = read(HERE / 'acquisition/summary.json')
assert acquisition['passed'] and not acquisition['accounting_uncertain']
image, = acquisition['images']
old = read(HERE / 'acquisition-operation-review.json')
work = PRIVATE / 'reference'
work.mkdir(mode=0o700)
inputs, tools, grade, oracle = [work / name for name in ('inputs', 'tools', 'grade', 'oracle')]
for folder in (inputs, tools, grade, oracle):
    folder.mkdir(mode=0o755)
paths = {Path(name).name: info for name, info in source['files'].items()}
for name in ('invoices.pdf', 'vendors.xlsx', 'purchase_orders.csv'):
    copy(PRIVATE / 'public' / name, inputs / name, paths[name]['sha256'])
copy(PRIVATE / 'oracle/solve.sh', oracle / 'solve.sh', paths['solve.sh']['sha256'])
for name in ('test_outputs.py', 'ground_truth.json'):
    copy(PRIVATE / 'verifier' / name, grade / name, paths[name]['sha256'])
for folder in (oracle, grade):
    source_file = HERE / 'reference-boundary.py'
    copy(source_file, folder / 'boundary.py', sha(source_file))
copy(HERE / 'reference-oracle.sh', oracle / 'entry.sh', sha(HERE / 'reference-oracle.sh'))
copy(HERE / 'reference-grader.py', grade / 'entry.py', sha(HERE / 'reference-grader.py'))
capture = ROOT / '.aeep/skillsbench-contained-graders-20261105/sales/runtime/repository_suite_native_capture.py'
assert sha(capture) == read(C13 / 'skillsbench-financial-audit-assets-20261105/dependency-audit-protected-preparation.json')['context_file_sha256'][capture.name]
copy(capture, grade / capture.name, sha(capture))

wheel_paths = []
for wheel in read(SPRING)['toolchain']:
    path = WHEELS / wheel['filename']
    assert sha(path) == wheel['sha256']
    wheel_paths.append(path)
    with ZipFile(path) as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            relative = Path(entry.filename)
            assert not relative.is_absolute() and '..' not in relative.parts
            assert stat.S_IFMT(entry.external_attr >> 16) in (0, stat.S_IFREG)
            target = tools / relative
            target.parent.mkdir(mode=0o755, exist_ok=True, parents=True)
            publish(target, archive.read(entry), 0o444)

shared_grader = {str(grade / name): '/aeep/' + name for name in (
    'entry.py', 'boundary.py', 'test_outputs.py', capture.name,
)}
shared_grader[str(tools)] = '/aeep/tools'
protected = {**shared_grader, str(grade / 'ground_truth.json'): '/aeep/ground_truth.json'}
mounts = {
    'oracle': {str(inputs): '/inputs', str(oracle): '/aeep'},
    'reference': protected, 'missing': protected, 'empty': protected,
    'infrastructure': shared_grader,
}
assets = [Path(__file__).resolve(), HERE / 'run-reference.py', HERE / 'source-inventory.json',
          HERE / 'asset-use.json', HERE / 'acquisition/summary.json', AUTHORITY, SPRING,
          Path(old['docker']), Path(old['docker_config']) / 'config.json', *wheel_paths]
assets.extend(p for directory in (inputs, tools, grade, oracle) for p in directory.rglob('*') if p.is_file())
review = {
    'purpose': 'First offline Invoice Fraud reference journey with original oracle and protected verifier.',
    'work': str(work), 'task_id': source['task_id'], 'revision': source['revision'],
    'source_snapshot': old['coordinator_source_snapshot'], 'source_sha256': old['source'],
    'docker': [old['docker'], '--config', old['docker_config'], '--host', 'unix://' + old['docker_socket']],
    'ledger': old['ledger'], 'image': image['image_id'], 'layers': image['layers'],
    'platform': image['platform'], 'mounts': mounts,
    'phases': list(mounts), 'files': {str(p): sha(p) for p in assets},
    'expires_at': (datetime.now(UTC) + timedelta(hours=3)).isoformat(),
    'max_operations': 24, 'max_seconds': 1100, 'max_models': 0, 'max_cash_usd': '0',
    'minimum_free_gib': 50, 'automatic_retries': False,
    'retention': 'Retain the image and prior resources. Retain all newly owned containers stopped for audit.',
    'adaptation': 'Read-only public mount plus private tmpfs at the original /root paths. '
                  'Load the cached pinned pytest toolchain offline and capture native test identities. '
                  'Do not execute the upstream pip installer. Original oracle, tests and answers remain byte-for-byte.',
}
path = HERE / 'reference-operation-review.json'
publish(path, (json.dumps(review, indent=2) + '\n').encode(), 0o444)
approval = {'review_sha256': sha(path), 'first_attempt': True, 'standing_authority_sha256': sha(AUTHORITY)}
publish(HERE / 'reference-delegated-authority.json', (json.dumps(approval, indent=2) + '\n').encode(), 0o444)
print(sha(path))
