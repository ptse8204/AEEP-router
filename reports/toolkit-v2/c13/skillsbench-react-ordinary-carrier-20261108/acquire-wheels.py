"""Acquire six exact Linux wheels under the first-attempt delegation."""

import argparse
import email.parser
import hashlib
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener
from zipfile import ZipFile

from packaging.utils import canonicalize_name

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep' / HERE.name
AUTHORITY = HERE.parent / 'pipeline-standing-authority-20261104.json'
LOCK = HERE / 'wheel-lock.json'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


def freeze():
    lock = read(LOCK)
    rows = [row for row in lock['wheels'] if row['origin'] == 'pypi']
    assert len(rows) == 6 and sum(row['bytes'] for row in rows) == lock['download_bytes']
    assert lock['metadata_closure_verified'] and lock['download_bytes'] <= 12*1024**2
    write('acquisition-review.json', {
        'scope':'First acquisition of the six pinned platform counterparts. Download and static inspection only.',
        'assets':{str(path):sha(path) for path in (Path(__file__), LOCK, AUTHORITY)},
        'maximum_downloads':6, 'maximum_download_bytes':lock['download_bytes'], 'automatic_retries':False,
        'cash_usd':'0', 'model_turns':0, 'provider_disclosure':False,
        'wheels_installed_or_executed':False, 'destination':str(WORK/'wheelhouse'),
    })
    review_sha = sha(HERE/'acquisition-review.json')
    write('acquisition-authority.json', {'review_sha256':review_sha, 'first_attempt':True,
                                        'standing_authority_sha256':sha(AUTHORITY)})
    print(review_sha)


def execute(identity):
    review_file = HERE/'acquisition-review.json'
    review = read(review_file)
    authority = read(HERE/'acquisition-authority.json')
    assert authority == {'review_sha256':identity,'first_attempt':True,'standing_authority_sha256':sha(AUTHORITY)}
    assert sha(review_file) == identity and all(sha(path)==digest for path,digest in review['assets'].items())
    assert not (HERE/'acquisition-started.json').exists()
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    target = Path(review['destination'])
    target.mkdir(mode=0o700, parents=True)
    write('acquisition-started.json', {'review_sha256':identity})
    rows = [row for row in read(LOCK)['wheels'] if row['origin']=='pypi']
    assert len(rows)==review['maximum_downloads'] and sum(row['bytes'] for row in rows)==review['maximum_download_bytes']
    result = {'review_sha256':identity,'passed':False,'artifacts':[],'models':0,'executed':False}
    try:
        for row in rows:
            name = row['filename']
            url = urlsplit(row['artifact_url'])
            assert url.netloc=='files.pythonhosted.org' and url.scheme=='https'
            assert Path(name).name==name and url.path.endswith('/'+name) and name.endswith('.whl')
            file = target/name
            with build_opener(ProxyHandler({})).open(row['artifact_url'],timeout=20) as response:
                assert response.geturl()==row['artifact_url'] and response.status==200
                data=response.read(row['bytes']+1)
            assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
            with file.open('xb') as stream:
                stream.write(data)
            file.chmod(0o400)
            with ZipFile(file) as archive:
                entries=archive.infolist()
                assert len(entries)==len(set(archive.namelist())) <= 20_000
                assert sum(entry.file_size for entry in entries) <= 256*1024**2
                metadata, = [entry for entry in entries if entry.filename.endswith('.dist-info/METADATA')]
                assert metadata.file_size <= 1024**2
                meta=email.parser.BytesParser().parsebytes(archive.read(metadata))
                assert canonicalize_name(meta['Name'])==canonicalize_name(row['name'])
                assert meta['Version']==row['version']
                assert sorted(meta.get_all('Requires-Dist', []))==sorted(row['requires_dist'])
                notices={}
                for entry in entries:
                    path=Path(entry.filename)
                    assert not path.is_absolute() and '..' not in path.parts and not entry.filename.endswith('.pth')
                    if '.dist-info/' in entry.filename and path.name.casefold().startswith(('license','copying','notice')) and not entry.is_dir():
                        assert entry.file_size <= 2*1024**2
                        notices[entry.filename]=hashlib.sha256(archive.read(entry)).hexdigest()
                assert notices
            result['artifacts'].append({'filename':name,'bytes':len(data),'sha256':row['sha256'],'notices':notices})
        result['passed']=True
    except Exception as error:
        result['error_type']=type(error).__name__
        result['stopped_artifact']=name
        raise
    finally:
        write('acquisition-result.json', result)
    print(json.dumps({'passed':result['passed'],'artifacts':len(result['artifacts']),'models':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    flags=parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--freeze',action='store_true')
    flags.add_argument('--execute-delegated')
    args=parser.parse_args()
    if args.freeze:
        freeze()
    else:
        execute(args.execute_delegated)
