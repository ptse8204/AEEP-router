"""Capture the bounded public contribution and protected verifier at the selected revision."""

import hashlib
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PRIVATE = ROOT / '.aeep' / HERE.name
REVISION = '9a1f4dd5f7659f75707435da3ce854b6e48321d1'
TASK = 'invoice-fraud-detection'
REPO = 'benchflow-ai/skillsbench'
PREFIX = f'tasks/{TASK}/'
FILES = {
    'LICENSE': 'notice',
    PREFIX + 'task.md': 'public',
    PREFIX + 'environment/Dockerfile': 'review',
    PREFIX + 'environment/invoices.pdf': 'public',
    PREFIX + 'environment/vendors.xlsx': 'public',
    PREFIX + 'environment/purchase_orders.csv': 'public',
    PREFIX + 'oracle/solve.sh': 'oracle',
    PREFIX + 'verifier/test.sh': 'verifier',
    PREFIX + 'verifier/test_outputs.py': 'verifier',
    PREFIX + 'verifier/ground_truth.json': 'verifier',
}


def fetch(url, limit):
    with urllib.request.urlopen(url, timeout=20) as response:
        data = response.read(limit + 1)
    assert len(data) <= limit
    return data


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()


tree_url = f'https://api.github.com/repos/{REPO}/git/trees/{REVISION}?recursive=1'
tree = json.loads(fetch(tree_url, 8 * 1024**2))
assert tree['sha'] == REVISION and not tree['truncated']
entries = {item['path']: item for item in tree['tree'] if item['path'] in FILES}
assert set(entries) == FILES.keys()
assert all(item['type'] == 'blob' and item['mode'] == '100644' for item in entries.values())
assert sum(item['size'] for item in entries.values()) <= 150_000
PRIVATE.mkdir(mode=0o700)
facts = {}
for name, role in FILES.items():
    url = f'https://raw.githubusercontent.com/{REPO}/{REVISION}/{name}'
    expected = entries[name]
    data = fetch(url, expected['size'])
    assert len(data) == expected['size'] and git_blob(data) == expected['sha']
    directory = PRIVATE / role
    directory.mkdir(mode=0o700, exist_ok=True)
    destination = directory / Path(name).name
    with destination.open('xb') as output:
        output.write(data)
    destination.chmod(0o400)
    facts[name] = {'role': role, 'git_blob': expected['sha'], 'sha256': sha(data),
                   'bytes': len(data), 'source_url': url}

report = {'repository': REPO, 'revision': REVISION, 'task_id': TASK,
          'private_root': str(PRIVATE), 'files': facts, 'models': 0,
          'upstream_code_executed': False}
with (HERE / 'source-inventory.json').open('x') as output:
    json.dump(report, output, indent=2)
    output.write('\n')
print(f'Captured {len(facts)} pinned source blobs')
