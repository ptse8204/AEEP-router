"""Acquire the exact portable interpreter and verify the pinned AFlow source tree."""

import argparse
import hashlib
import json
import shutil
import tarfile
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep' / HERE.name


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def fetch(url, destination, limit, hosts):
    assert urllib.parse.urlsplit(url).scheme == 'https'
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'AEEP exact source artifact'}), timeout=30) as response:
        assert urllib.parse.urlsplit(response.geturl()).hostname in hosts
        with destination.open('xb') as output:
            left = limit
            while chunk := response.read(min(left + 1, 262144)):
                left -= len(chunk)
                assert left >= 0
                output.write(chunk)
    destination.chmod(0o444)
    return limit - left


parser = argparse.ArgumentParser()
parser.add_argument('--execute-delegated', required=True)
args = parser.parse_args()
scope = HERE / 'aflow-runtime-inputs-review.json'
identity = sha(scope)
authority = read(HERE / 'aflow-runtime-inputs-authority.json')
assert args.execute_delegated == identity == authority['review_sha256'] and authority['first_attempt']
review = read(scope)
assert datetime.now(UTC) < datetime.fromisoformat(review['expires_at'])
assert shutil.disk_usage(ROOT).free >= 51 * 1024**3
for path, digest in review['assets'].items():
    assert sha(Path(path)) == digest
target = WORK / 'aflow-runtime-inputs'
target.mkdir(mode=0o700)
write(HERE / 'aflow-runtime-inputs-started.json', {'review_sha256':identity})
result = {'passed':False,'installed':False,'guest_code_executed':False,'models':0}
try:
    py = review['portable_python']
    binary = target / py['artifact']
    count = fetch(py['url'],binary,py['bytes'],{'github.com','release-assets.githubusercontent.com'})
    assert count == py['bytes'] and sha(binary) == py['sha256']
    result['portable_python'] = {'sha256':py['sha256'],'bytes':count,'artifact':str(binary)}
    archive = target / 'source.tar.gz'
    count = fetch(review['source_archive_url'],archive,review['maximum_source_archive_bytes'],{'codeload.github.com'})
    result['source_archive'] = {'sha256':sha(archive),'bytes':count,'path':str(archive)}
    entries = review['source_files']
    assert sum(row['size'] for row in entries.values()) <= 8*1024**2
    found = {}
    with tarfile.open(archive,'r:gz') as source:
        for member in source:
            path = PurePosixPath(member.name)
            assert not path.is_absolute() and '..' not in path.parts
            relative = '/'.join(path.parts[1:])
            if relative not in entries:
                continue
            row = entries[relative]
            assert relative not in found and member.isfile() and member.size == row['size']
            handle = source.extractfile(member)
            assert handle is not None
            data = handle.read(member.size + 1)
            assert hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest() == row['sha']
            output = target / 'source' / relative
            output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            with output.open('xb') as stream:stream.write(data)
            output.chmod(0o444)
            found[relative] = hashlib.sha256(data).hexdigest()
    assert set(found) == set(entries)
    result.update(passed=True, verified_source_files=found, source_revision=review['source_revision'])
finally:
    write(HERE / 'aflow-runtime-inputs-result.json',result)
print({'passed':result['passed'],'verified_source_files':len(result['verified_source_files']),
       'portable_python_bytes':result['portable_python']['bytes'],'source_archive_bytes':result['source_archive']['bytes']})
