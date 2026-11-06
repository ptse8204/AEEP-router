"""Stage only commit-verified EvoAgentX runtime source for a later offline build."""

import argparse
import hashlib
import io
import json
import shutil
import tarfile
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep' / HERE.name
AUTHORITY = HERE.parent / 'pipeline-standing-authority-20261104.json'
REVISION = 'd77fd6b9a3e76c8dd83bebe3374c53a3f5d16f54'
API = 'https://api.github.com/repos/ANative-Lab/EvoAgentX/git/trees/' + REVISION + '?recursive=1'
SOURCE = 'https://codeload.github.com/ANative-Lab/EvoAgentX/tar.gz/' + REVISION
MAX_ARCHIVE_BYTES = 20 * 1024**2
MAX_EXPANDED_BYTES = 32 * 1024**2


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(name, value):
    with (HERE / name).open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


def fetch(url, limit):
    with urllib.request.urlopen(url, timeout=25) as response:
        assert urlsplit(response.geturl()).netloc == urlsplit(url).netloc
        raw = response.read(limit + 1)
    assert len(raw) <= limit
    return raw


def prepare():
    prior = read(HERE / 'result.json')
    assert not prior['same_reviewed_contract'] and prior['source_revision'] == REVISION
    response = fetch(API, 2 * 1024**2)
    tree = json.loads(response)
    assert tree['sha'] == REVISION and not tree['truncated']
    root_files = {'LICENSE', 'README.md', 'pyproject.toml', 'requirements.txt'}
    files = {entry['path']: {'git_blob': entry['sha'], 'bytes': entry['size']}
             for entry in tree['tree'] if entry['type'] == 'blob' and entry['mode'] == '100644'
             and (entry['path'].startswith('evoagentx/') or entry['path'] in root_files)}
    assert root_files <= files.keys() and len(files) == 262
    assert sum(item['bytes'] for item in files.values()) < 5 * 1024**2
    write('source-operation-review.json', {
        'purpose': 'One static archive read to retain exact EvoAgentX build and runtime source.',
        'revision': REVISION, 'url': SOURCE, 'tree_metadata_sha256': sha(response), 'files': files,
        'maximum_archive_bytes': MAX_ARCHIVE_BYTES, 'maximum_expanded_bytes': MAX_EXPANDED_BYTES,
        'inputs': {str(path): sha(path.read_bytes()) for path in (Path(__file__), HERE/'result.json', AUTHORITY)},
        'maximum_attempts': 1, 'install': False, 'upstream_execution': False, 'models': 0, 'cash_usd': '0',
    })
    identity = sha((HERE / 'source-operation-review.json').read_bytes())
    write('source-delegated-authority.json', {'review_sha256': identity, 'first_attempt': True,
                                             'standing_authority_sha256': sha(AUTHORITY.read_bytes())})
    return {'review_sha256': identity, 'planned_source_files': len(files)}


def acquire(identity):
    path = HERE / 'source-operation-review.json'
    review = read(path)
    authority = read(HERE / 'source-delegated-authority.json')
    assert authority['first_attempt'] and identity == authority['review_sha256'] == sha(path.read_bytes())
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3 and review['url'] == SOURCE
    for path, expected in review['inputs'].items():
        assert sha(Path(path).read_bytes()) == expected
    destination = WORK / 'source'
    destination.mkdir(mode=0o700)
    write('source-started.json', {'review_sha256': identity})
    compressed = fetch(SOURCE, MAX_ARCHIVE_BYTES)
    with tarfile.open(fileobj=io.BytesIO(compressed), mode='r:gz') as archive:
        total, matches = 0, {}
        prefix = 'EvoAgentX-' + REVISION + '/'
        for member in archive:
            total += member.size
            assert total <= MAX_EXPANDED_BYTES
            if not member.name.startswith(prefix):
                continue
            name = member.name.removeprefix(prefix)
            if name not in review['files']:
                continue
            expected = review['files'][name]
            assert member.isfile() and member.size == expected['bytes'] and name not in matches
            data = archive.extractfile(member).read()
            git_blob = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
            assert git_blob == expected['git_blob'], name
            relative = Path(name)
            assert not relative.is_absolute() and '..' not in relative.parts
            out = destination / relative
            out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with out.open('xb') as stream:
                stream.write(data)
            out.chmod(0o400)
            matches[name] = sha(data)
    assert matches.keys() == review['files'].keys()
    result = {'review_sha256': identity, 'revision': REVISION, 'archive_sha256': sha(compressed),
              'archive_bytes': len(compressed), 'files_verified': len(matches), 'source_sha256': matches,
              'source_root': str(destination), 'installed': False, 'upstream_execution': False, 'models': 0}
    write('source-result.json', result)
    return {name: value for name, value in result.items() if name != 'source_sha256'}


parser = argparse.ArgumentParser()
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument('--prepare', action='store_true')
group.add_argument('--acquire')
args = parser.parse_args()
print(json.dumps(prepare() if args.prepare else acquire(args.acquire)))
