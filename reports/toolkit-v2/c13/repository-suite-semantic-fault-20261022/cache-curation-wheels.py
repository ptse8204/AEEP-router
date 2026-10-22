"""Cache two official pure wheels as inert source data, without importing/installing."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import urllib.request
import urllib.parse
import zipfile

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'.aeep/repository-curation-20261022-runtime'
HERE=Path(__file__).parent


def fetch(url,limit):
    request=urllib.request.Request(url,headers={'User-Agent':'AEEP-source-review/2'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=25) as response:
        assert urllib.parse.urlparse(response.geturl()).hostname in ('pypi.org','files.pythonhosted.org')
        data=response.read(limit+1)
    assert len(data)<=limit
    return data


assert shutil.disk_usage(ROOT).free>50*1024**3+2*1024**2
OUT.mkdir(exist_ok=False)
records=[]
for project,version in [('beautifulsoup4','4.12.3'),('soupsieve','2.6')]:
    url='https://pypi.org/pypi/'+project+'/'+version+'/json'
    raw=fetch(url,500_000);metadata=json.loads(raw)
    wheel=next(item for item in metadata['urls'] if item['filename'].endswith('-none-any.whl'))
    payload=fetch(wheel['url'],500_000)
    assert hashlib.sha256(payload).hexdigest()==wheel['digests']['sha256']
    path=OUT/wheel['filename'];path.write_bytes(payload)
    (OUT/(project+'-metadata.json')).write_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names=archive.namelist();assert not any(name.endswith(('.so','.dylib','.pyd','.dll')) for name in names)
        licenses=[name for name in names if '.dist-info/' in name and ('license' in name.casefold() or 'copying' in name.casefold())]
        assert licenses
        license_records=[{'member':name,'sha256':hashlib.sha256(archive.read(name)).hexdigest(),'bytes':len(archive.read(name))} for name in licenses]
        texts='\n'.join(archive.read(name).decode(errors='replace') for name in licenses)
        assert 'Permission is hereby granted' in texts and 'MIT' in texts
    records.append({'project':project,'version':version,'filename':wheel['filename'],'url':wheel['url'],
        'metadata_url':url,'metadata_sha256':hashlib.sha256(raw).hexdigest(),'sha256':wheel['digests']['sha256'],
        'bytes':len(payload),'private_cache':str(path.relative_to(ROOT)),'license':'MIT','license_records':license_records,
        'requires_dist':metadata['info'].get('requires_dist'),'pure_wheel':True,'executed':False,'installed':False})
(HERE/'curation-runtime-wheel-review.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps({'wheels':len(records),'bytes':sum(item['bytes'] for item in records),'installed':False,'executed':False}))
