"""Compare the official wheel with the reviewed EvoAgentX commit without importing it."""

import argparse
import hashlib
import json
import shutil
import urllib.request
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREVIOUS = HERE.parent / 'proposal-optimizer-preparation-20261105'
SOURCE = PREVIOUS / 'source-contracts.json'
REQUIREMENTS = PREVIOUS / 'evoagentx-base-requirements.json'
AUTHORITY = HERE.parent / 'pipeline-standing-authority-20261104.json'
METADATA = 'https://pypi.org/pypi/evoagentx/0.1.4/json'
WORK = ROOT / '.aeep' / HERE.name


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(name, value):
    with (HERE / name).open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


def fetch(url, limit, host):
    assert urlsplit(url).scheme == 'https' and urlsplit(url).hostname == host
    with urllib.request.urlopen(url, timeout=20) as response:
        assert urlsplit(response.geturl()).hostname == host
        raw = response.read(limit + 1)
    assert len(raw) <= limit
    return raw


def prepare():
    package = read(REQUIREMENTS)
    raw = fetch(METADATA, 512 * 1024, 'pypi.org')
    metadata = json.loads(raw)
    name = 'evoagentx-' + package['package_version'] + '-py3-none-any.whl'
    wheel, = [entry for entry in metadata['urls'] if entry['filename'] == name]
    assert not wheel['yanked'] and wheel['size'] <= 2 * 1024**2
    assert urlsplit(wheel['url']).hostname == 'files.pythonhosted.org'
    observed = [requirement for requirement in metadata['info']['requires_dist'] if ';' not in requirement]
    declared = [entry['runtime_requirement'] for entry in package['base_requirements']]
    assert observed == declared
    review = {'purpose': 'Acquire the official wheel once for private, static source comparison.',
              'metadata_url': METADATA, 'metadata_sha256': sha(raw),
              'version': package['package_version'], 'source_revision': package['source_revision'],
              'wheel': {key: wheel[key] for key in ('filename', 'url', 'size')},
              'base_requirements': declared, 'requires_python': metadata['info']['requires_python'],
              'inputs': {str(path): sha(path.read_bytes()) for path in (
                  SOURCE, REQUIREMENTS, AUTHORITY, Path(__file__),
              )},
              'operations': 1, 'maximum_artifact_bytes': wheel['size'], 'models': 0,
              'cash_usd': '0', 'install': False, 'automatic_retries': False}
    review['wheel']['sha256'] = wheel['digests']['sha256']
    write('operation-review.json', review)
    identity = sha((HERE / 'operation-review.json').read_bytes())
    write('delegated-authority.json', {'review_sha256': identity, 'first_attempt': True,
                                      'standing_authority_sha256': sha(AUTHORITY.read_bytes())})
    return {'review_sha256': identity}


def audit(identity):
    path = HERE / 'operation-review.json'
    review = read(path)
    authority = read(HERE / 'delegated-authority.json')
    assert identity == sha(path.read_bytes()) == authority['review_sha256']
    assert authority['first_attempt'] is True and shutil.disk_usage(ROOT).free >= 50 * 1024**3
    for path, expected in review['inputs'].items():
        assert sha(Path(path).read_bytes()) == expected
    contract = read(SOURCE)['components']['evoagentx']
    assert contract['revision'] == review['source_revision']
    WORK.mkdir(mode=0o700)
    write('started.json', {'review_sha256': identity})
    wheel = review['wheel']
    raw = fetch(wheel['url'], wheel['size'], 'files.pythonhosted.org')
    assert len(raw) == wheel['size'] and sha(raw) == wheel['sha256']
    path = WORK / wheel['filename']
    with path.open('xb') as stream:
        stream.write(raw)
    path.chmod(0o400)
    with ZipFile(path) as archive:
        entries = archive.infolist()
        assert len(entries) <= 2000 and sum(entry.file_size for entry in entries) < 32 * 1024**2
        names = set(archive.namelist())
        assert len(entries) == len(names)
        distinfo = f"evoagentx-{review['version']}.dist-info/"
        meta = BytesParser().parsebytes(archive.read(distinfo + 'METADATA'))
        assert meta['Name'].lower() == 'evoagentx' and meta['Version'] == review['version']
        assert [req for req in meta.get_all('Requires-Dist') if ';' not in req] == review['base_requirements']
        license_path = next(name for name in names if name in (distinfo + 'LICENSE', distinfo + 'licenses/LICENSE'))
        checks = {}
        for source, pinned in contract['files'].items():
            file = license_path if source == 'LICENSE' else source
            if source != 'LICENSE' and not source.startswith('evoagentx/'):
                continue
            data = archive.read(file)
            checks[source] = {'published_sha256': sha(data), 'pinned_sha256': pinned['sha256'],
                              'same': len(data) == pinned['bytes'] and sha(data) == pinned['sha256']}
    matches = sum(check['same'] for check in checks.values())
    result = {'review_sha256': identity, 'wheel_sha256': wheel['sha256'], 'source_revision': contract['revision'],
              'checked_contract_files': checks, 'matching_files': matches, 'checked_files': len(checks),
              'same_reviewed_contract': matches == len(checks), 'wheel_installed': False,
              'upstream_imports': 0, 'model_turns': 0}
    write('result.json', result)
    return {key: value for key, value in result.items() if key != 'checked_contract_files'}


parser = argparse.ArgumentParser()
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument('--prepare', action='store_true')
group.add_argument('--audit')
args = parser.parse_args()
print(json.dumps(prepare() if args.prepare else audit(args.audit)))
