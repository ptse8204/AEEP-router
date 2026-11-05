"""Bind the released Postgres MCP image and matching protected grader wheel."""
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT/'.aeep'/HERE.name
INDEX = 'sha256:dbbd346860d29f1543e991f30f3284bf4ab5f096d049ecc3426528f20b1b6e6b'
AMD64 = 'sha256:c04abcb08d7901e28f6f3ee11b6d799f42ae94b64b160175e9905274121294d2'
BASE = 'https://registry-1.docker.io/v2/crystaldba/postgres-mcp'
TAG = 'https://api.github.com/repos/crystaldba/postgres-mcp/git/tags/f9871f614272ea2e8cb1711f91dba7e997190831'
started = time.perf_counter()


def get(url, *, headers=None, limit=512*1024):
    request = urllib.request.Request(url, headers={'User-Agent':'AEEP-upstream-metadata-audit/1', **(headers or {})})
    with urllib.request.urlopen(request, timeout=20) as response:
        assert urllib.parse.urlsplit(response.url).scheme == 'https'
        data = response.read(limit+1)
    assert len(data) <= limit
    return data


def sha(data):
    return hashlib.sha256(data).hexdigest()


def manifest(path, expected, accept):
    data = get(f'{BASE}/{path}', headers={'Authorization':'Bearer '+token,'Accept':accept})
    assert 'sha256:'+sha(data) == expected
    return json.loads(data)


source = get(TAG)
tag = json.loads(source)
assert tag['tag']=='v0.3.0' and tag['object']['type']=='commit'
release_sha = tag['object']['sha']
auth = 'https://auth.docker.io/token?service=registry.docker.io&scope=repository%3Acrystaldba%2Fpostgres-mcp%3Apull'
token = json.loads(get(auth))['token']
index = manifest('manifests/'+INDEX, INDEX, 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json')
child = next(item for item in index['manifests'] if item['platform']=={'architecture':'amd64','os':'linux'})
assert child['digest']==AMD64
m = manifest('manifests/'+AMD64, AMD64, 'application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json')
image_id = m['config']['digest']
config = manifest('blobs/'+image_id, image_id, 'application/octet-stream')
assert (config['os'], config['architecture'])==('linux','amd64')
assert len(config['rootfs']['diff_ids'])==len(m['layers'])
settings = config['config']
labels = {k:v for k,v in (settings.get('Labels') or {}).items() if k in {
    'org.opencontainers.image.source','org.opencontainers.image.version',
    'org.opencontainers.image.revision','org.opencontainers.image.licenses',
}}
assert labels.get('org.opencontainers.image.source','https://github.com/crystaldba/postgres-mcp')=='https://github.com/crystaldba/postgres-mcp'
assert labels.get('org.opencontainers.image.revision',release_sha)==release_sha
size = sum(layer['size'] for layer in m['layers'])
assert size < 110*1024**2
pypi_url = 'https://pypi.org/pypi/psycopg2-binary/2.9.10/json'
package_data = get(pypi_url)
package = json.loads(package_data)
name = 'psycopg2_binary-2.9.10-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl'
artifact = next(item for item in package['urls'] if item['filename']==name)
url = urllib.parse.urlsplit(artifact['url'])
assert (url.scheme,url.hostname)==('https','files.pythonhosted.org')
data = get(artifact['url'],limit=5*1024**2)
assert len(data)==artifact['size'] and sha(data)==artifact['digests']['sha256']
wheel = WORK/name
with wheel.open('xb') as stream:
    stream.write(data)
with ZipFile(wheel) as archive:
    files = archive.namelist()
    licenses = {n:sha(archive.read(n)) for n in files if n.endswith(('/LICENSE','/COPYING'))}
    metadata = archive.read(next(n for n in files if n.endswith('.dist-info/METADATA'))).decode()
    assert 'Version: 2.9.10' in metadata
    assert not any(line.startswith('Requires-Dist:') for line in metadata.splitlines())
evidence = {
    'metadata_kind':'public registry manifest and verifier wheel only',
    'server_release':'v0.3.0','source_release_commit':release_sha,'source_tag_url':TAG,'source_tag_sha256':sha(source),
    'official_image':{'task_id':'postgres-mcp-0.3.0','reference':'docker.io/crystaldba/postgres-mcp@'+AMD64,
                      'tag':'0.3.0','index':INDEX,'config':image_id,'allowed_engine_ids':[image_id,AMD64],
                      'diff_ids':config['rootfs']['diff_ids'],'compressed_layer_bytes':size,
                      'labels':labels,'entrypoint':settings.get('Entrypoint'),'user':settings.get('User'),
                      'declared_volumes':sorted((settings.get('Volumes') or {}).keys())},
    'verifier_wheel':{'name':name,'url':artifact['url'],'sha256':sha(data),'bytes':len(data),
                      'pypi_metadata_sha256':sha(package_data),'license_files':licenses},
    'models':0,'images_pulled':False,'upstream_code_executed':False,
    'elapsed_seconds':time.perf_counter()-started,
}
with (HERE/'upstream-artifacts.json').open('x') as out:
    json.dump(evidence,out,indent=2)
    out.write('\n')
print(json.dumps({'server_release_commit':release_sha,'compressed_bytes':size,
                  'config':image_id,'labels':labels,'entrypoint':settings.get('Entrypoint'),
                  'wheel_bytes':len(data)}))
