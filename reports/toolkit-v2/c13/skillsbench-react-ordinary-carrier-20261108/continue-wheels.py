"""Continue with the five unstarted downloads and retain the verified first wheel."""

import argparse
import email.parser
import hashlib
import importlib.util
import json
import shutil
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener
from zipfile import ZipFile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from aeep.models import utc_now

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('original_react_wheel_acquisition', HERE/'acquire-wheels.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
REVIEW = HERE/'acquisition-continuation-review.json'


def inspect_wheel(file, row):
    assert file.stat().st_size==row['bytes'] and original.sha(file)==row['sha256']
    with ZipFile(file) as archive:
        entries=archive.infolist()
        assert len(entries)==len(set(archive.namelist())) <= 20_000
        assert sum(entry.file_size for entry in entries) <= 256*1024**2
        metadata, = [entry for entry in entries if entry.filename.endswith('.dist-info/METADATA')]
        assert metadata.file_size <= 1024**2
        meta=email.parser.BytesParser().parsebytes(archive.read(metadata))
        assert canonicalize_name(meta['Name'])==canonicalize_name(row['name'])
        assert meta['Version']==row['version']
        actual=Counter(map(Requirement,meta.get_all('Requires-Dist', [])))
        expected=Counter(map(Requirement,row['requires_dist']))
        assert actual==expected
        notices={}
        for entry in entries:
            path=PurePosixPath(entry.filename)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in entry.filename
            assert not entry.filename.endswith('.pth')
            if '.dist-info/' in entry.filename and path.name.casefold().startswith(('license','copying','notice')) and not entry.is_dir():
                assert entry.file_size <= 2*1024**2
                notices[entry.filename]=hashlib.sha256(archive.read(entry)).hexdigest()
        assert notices
    return {'filename':file.name,'bytes':row['bytes'],'sha256':row['sha256'],'notices':notices}


def input_rows():
    return [row for row in original.read(original.LOCK)['wheels'] if row['origin']=='pypi']


def freeze():
    first,*remaining = input_rows()
    previous=original.read(HERE/'acquisition-result.json')
    assert not previous['passed'] and previous['stopped_artifact']==first['filename']
    assert previous['review_sha256']==original.sha(HERE/'acquisition-review.json')
    target=original.WORK/'wheelhouse'
    retained=inspect_wheel(target/first['filename'], first)
    assert len(remaining)==5 and all(not (target/row['filename']).exists() for row in remaining)
    original.write(REVIEW.name,{
        'scope':'Reuse the verified cryptography wheel and acquire the five unstarted Linux counterparts.',
        'parent_review_sha256':previous['review_sha256'],'retained':retained,
        'normalization':'Compare parsed requirement multisets, preserving names, versions, extras and environment markers.',
        'maximum_downloads':5, 'maximum_download_bytes':sum(row['bytes'] for row in remaining),
        'maximum_seconds':150,'automatic_retries':False,
        'expires_at':(utc_now()+timedelta(hours=8)).isoformat(),
        'files':{str(path):original.sha(path) for path in
                 (Path(__file__), original.LOCK, HERE/'acquire-wheels.py',
                  HERE/'acquisition-review.json',HERE/'acquisition-result.json')},
        'destination':str(target),'cash_usd':'0','models':0,'installed_or_executed':False,
    })


def preflight(review, digest):
    assert original.sha(REVIEW)==digest and datetime.fromisoformat(review['expires_at'])>utc_now()
    assert all(original.sha(path)==expected for path,expected in review['files'].items())
    assert shutil.disk_usage(original.ROOT).free>=50*1024**3
    assert not (HERE/'acquisition-continuation-started.json').exists()
    target=Path(review['destination'])
    first,*remaining=input_rows()
    assert inspect_wheel(target/first['filename'],first)==review['retained']
    assert len(remaining)==review['maximum_downloads']==5
    assert sum(row['bytes'] for row in remaining)==review['maximum_download_bytes']
    assert all(not (target/row['filename']).exists() for row in remaining)
    return target,remaining


def execute(review, digest, target, remaining):
    assert original.read(HERE/'acquisition-continuation-approval.json')=={'approved':True,'review_sha256':digest}
    original.write('acquisition-continuation-started.json',{'review_sha256':digest})
    result={'review_sha256':digest,'passed':False,'retained':review['retained'],
            'new_artifacts':[],'models':0,'executed':False}
    start=time.monotonic()
    try:
        for row in remaining:
            filename=row['filename']
            url=urlsplit(row['artifact_url'])
            assert url.scheme=='https' and url.netloc=='files.pythonhosted.org'
            assert not (url.query or url.fragment) and url.path.endswith('/'+filename)
            assert Path(filename).name==filename and filename.endswith('.whl')
            assert time.monotonic()-start < review['maximum_seconds']
            with build_opener(ProxyHandler({})).open(row['artifact_url'], timeout=20) as response:
                assert response.geturl()==row['artifact_url'] and response.status==200
                data=response.read(row['bytes']+1)
            assert time.monotonic()-start < review['maximum_seconds']
            assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
            file=target/filename
            with file.open('xb') as stream:
                stream.write(data)
            file.chmod(0o400)
            result['new_artifacts'].append(inspect_wheel(file,row))
        result['passed']=True
    except Exception as error:
        result.update(error_type=type(error).__name__,stopped_artifact=filename)
        raise
    finally:
        result['elapsed_seconds']=time.monotonic()-start
        original.write('acquisition-continuation-result.json',result)
    print(json.dumps({'passed':result['passed'],'new_artifacts':len(result['new_artifacts']),'models':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    flags=parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--freeze',action='store_true')
    flags.add_argument('--preflight')
    flags.add_argument('--execute-approved')
    args=parser.parse_args()
    if args.freeze:
        freeze()
    digest=original.sha(REVIEW) if args.freeze else args.preflight or args.execute_approved
    review=original.read(REVIEW)
    target,remaining=preflight(review,digest)
    if args.execute_approved:
        execute(review,digest,target,remaining)
    else:
        print(json.dumps({'passed':True,'review_sha256':digest,'remaining_downloads':len(remaining),
                          'maximum_download_bytes':review['maximum_download_bytes'],'models':0}))
