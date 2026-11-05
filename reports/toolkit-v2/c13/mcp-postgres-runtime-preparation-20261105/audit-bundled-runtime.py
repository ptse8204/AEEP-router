"""Read exact package metadata from a Docker export without running the image."""
import hashlib
import json
import shutil
import subprocess
import tarfile
import time
import tomllib
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from urllib.request import ProxyHandler, build_opener

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
review = json.loads((HERE/'operation-review.json').read_bytes())
artifact = json.loads((HERE/'upstream-artifacts.json').read_bytes())
identity = json.loads((HERE/'retained-image-identity.json').read_bytes())
image = artifact['official_image']
assert identity['verified_image_identity'] and identity['image_id'] in image['allowed_engine_ids']
work = Path(review['work'])
assert shutil.disk_usage(ROOT).free >= 54 * 1024**3
scope = HERE/'bundled-runtime-review.json'
assert not scope.exists() and not (work/'image.tar').exists()
source_url = f"https://raw.githubusercontent.com/crystaldba/postgres-mcp/{artifact['source_release_commit']}/uv.lock"
with build_opener(ProxyHandler({})).open(source_url, timeout=20) as response:
    assert response.url == source_url
    lock_bytes = response.read(512*1024+1)
lock_sha = hashlib.sha256(lock_bytes).hexdigest()
assert lock_sha == '2be9dda9c88443dede61ada6bfed457d403a7b76e47447b75c93f3fed37009e9'
packages = {p['name']:p['version'] for p in tomllib.loads(lock_bytes.decode())['package']
            if p['name'] in ('postgres-mcp','pglast','mcp','psycopg','instructor')}
assert packages == {'postgres-mcp':'0.3.0','pglast':'7.2','mcp':'1.6.0','psycopg':'3.2.6','instructor':'1.7.9'}
path = work/'image.tar'
env = {'HOME':str(work),'PATH':'/usr/bin:/bin','LC_ALL':'C'}
cli = [review['docker'],'--config',review['docker_config'],'--host','unix://'+review['docker_socket']]
usage = subprocess.check_output([*cli,'system','df'],env=env,text=True).strip().splitlines()

def write(target, data):
    with target.open('x') as f:
        json.dump(data,f,indent=2)
        f.write('\n')

write(scope, {'image_ref':image['reference'],'image_id':identity['image_id'],'packages':packages,
              'lock_url':source_url,'lock_sha256':lock_sha,'docker_usage_before':usage,
              'free_bytes_before':shutil.disk_usage(ROOT).free,'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope':'One read-only export and selective local metadata inspection. No image pull, container creation, guest execution, installation, credentials, deletion or release.',
              'automatic_retries':False,'models':0})
clock = time.perf_counter()
with path.open('xb') as target:
    run = subprocess.run([*cli,'image','save',image['reference']],env=env,cwd=work,
                         stdout=target,stderr=subprocess.PIPE,timeout=75,check=True)
assert 0<path.stat().st_size<256*1024**2
assert shutil.disk_usage(ROOT).free >= 50*1024**3
lib = 'app/.venv/lib/python3.12/site-packages'
paths = {f"{lib}/{name.replace('-','_')}-{version}.dist-info/METADATA":name for name,version in packages.items()}
entrypoint = 'app/docker-entrypoint.sh'
seen = {}
with tarfile.open(path, mode='r:*') as outer:
    manifest = json.load(outer.extractfile('manifest.json'))
    assert len(manifest)==1
    item = manifest[0]
    config_bytes = outer.extractfile(item['Config']).read(512*1024+1)
    assert 'sha256:'+hashlib.sha256(config_bytes).hexdigest()==image['config']
    assert len(item['Layers'])==len(image['diff_ids'])
    for filename in item['Layers']:
        with tarfile.open(fileobj=outer.extractfile(filename),mode='r|*') as layer:
            for record in layer:
                name=PurePosixPath(record.name).as_posix().lstrip('/')
                if PurePosixPath(name).name.startswith('.wh.') and (name.startswith('app/') or name=='.wh.app'):
                    raise ValueError('whiteout in inspected layer paths')
                if name not in paths and name!=entrypoint:
                    continue
                assert record.isfile() and 0<record.size<=128*1024
                data=layer.extractfile(record).read()
                seen[name]=data
assert set(seen)==set(paths)|{entrypoint}
versions={}
for name, package in paths.items():
    metadata=BytesParser().parsebytes(seen[name],headersonly=True)
    assert metadata['Name'].lower().replace('_','-')==package and metadata['Version']==packages[package]
    versions[package]={'version':metadata['Version'],'metadata_sha256':hashlib.sha256(seen[name]).hexdigest(),
                       'license_expression':metadata['License-Expression']}
result={'passed':True,'image_id':identity['image_id'],'lock_sha256':lock_sha,
        'observed_packages':versions,'entrypoint_sha256':hashlib.sha256(seen[entrypoint]).hexdigest(),
        'image_export_bytes':path.stat().st_size,'guest_executions':0,'containers_created':0,
        'elapsed_seconds':time.perf_counter()-clock,'models':0,'comparison_eligible':False}
write(HERE/'bundled-runtime-audit.json',result)
print(json.dumps(result))
