"""Acquire the exact upstream RapidFuzz wheel once after approval."""

import argparse
import hashlib
import io
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with path.open('x') as out:
        json.dump(value, out, indent=2)
        out.write('\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify(review, identity):
    assert identity == sha((HERE/'rapidfuzz-continuation-review.json').read_bytes())
    assert shutil.disk_usage(HERE).free >= 50 * 1024**3
    assert all(sha(Path(p).read_bytes()) == expected for p, expected in review['pins'].items())
    target = Path(review['target'])
    assert not target.exists() and not target.is_symlink() and target.parent.is_dir()
    assert not (HERE/'rapidfuzz-continuation-started.json').exists()
    assert urlsplit(review['url']).scheme == 'https' and urlsplit(review['url']).hostname == 'files.pythonhosted.org'
    assert 0 < review['bytes'] <= review['maximum_download_bytes'] <= 2*1024**2
    return target


def check_license(data):
    with ZipFile(io.BytesIO(data)) as archive:
        license_file, = [n for n in archive.namelist() if n.endswith('.dist-info/licenses/LICENSE')]
        assert archive.getinfo(license_file).file_size <= 64 * 1024
        text = ' '.join(archive.read(license_file).decode('utf-8').split()).casefold()
        assert 'permission is hereby granted, free of charge' in text
        assert 'the software is provided "as is"' in text
        return sha(archive.read(license_file))


def apply(review, identity):
    target = verify(review, identity)
    assert read(HERE/'rapidfuzz-continuation-approval.json') == {'approved': True, 'review_sha256': identity}
    write(HERE/'rapidfuzz-continuation-started.json', {'review_sha256': identity})
    result = {'review_sha256': identity, 'models': 0, 'package_executed': False, 'passed': False}
    try:
        with urlopen(review['url'], timeout=25) as response:
            assert response.geturl() == review['url']
            data = response.read(review['bytes'] + 1)
        result['downloaded_bytes'] = len(data)
        assert len(data) == review['bytes'] and sha(data) == review['sha256']
        result['license_sha256'] = check_license(data)
        with target.open('xb') as output:
            output.write(data)
        target.chmod(0o400)
        result.update(passed=True, sha256=sha(data), license='MIT')
    except Exception as error:
        result['error_type'] = type(error).__name__
        raise
    finally:
        write(HERE/'rapidfuzz-continuation-result.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight')
    mode.add_argument('--execute-approved')
    args = p.parse_args()
    review = read(HERE/'rapidfuzz-continuation-review.json')
    if args.preflight:
        verify(review, args.preflight)
        print(json.dumps({'review_sha256': args.preflight, 'preflight': True, 'network': False}))
    else:
        apply(review, args.execute_approved)
