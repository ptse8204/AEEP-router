"""Cache the exact projected wheels for static inspection; never install/import."""
import hashlib
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.parser import BytesParser
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
projection=json.loads((HERE/'dependency-projection.json').read_text())
cache=ROOT/'.aeep/upstream-stack-source-20261101/scanner-wheels'
assert shutil.disk_usage(ROOT).free>50*1024**3+512*1024**2
cache.mkdir(parents=True,exist_ok=True)
items=[item['artifact']|{'name':item['name'],'version':item['version']} for item in projection['packages']]
items+=[projection['root_artifacts'][0]|{'name':'cisco-ai-skill-scanner','version':'2.2.1'}]
existing={}
for folder in ('upstream-stack-runtimes-20261101/composed-wheels','upstream-stack-source-20261101/scanner-artifact'):
 for file in (ROOT/'.aeep'/folder).glob('*.whl'):existing[file.name]=file

def inspect(item):
 started=time.monotonic();target=cache/item['filename'];downloaded=False;copied=False
 if not target.exists():
  source=existing.get(item['filename'])
  if source and hashlib.sha256(source.read_bytes()).hexdigest()==item['sha256']:
   shutil.copyfile(source,target);copied=True
  else:
   assert shutil.disk_usage(ROOT).free>50*1024**3+512*1024**2
   with urlopen(item['url'],timeout=60) as response:raw=response.read(item['bytes']+1)
   assert len(raw)==item['bytes'] and hashlib.sha256(raw).hexdigest()==item['sha256']
   with target.open('xb') as handle:handle.write(raw)
   downloaded=True
 assert target.stat().st_size==item['bytes']
 assert hashlib.sha256(target.read_bytes()).hexdigest()==item['sha256']
 with ZipFile(target) as bundle:
  metadata_name=next(n for n in bundle.namelist() if n.endswith('.dist-info/METADATA'))
  assert bundle.getinfo(metadata_name).file_size<1024**2
  metadata=BytesParser().parsebytes(bundle.read(metadata_name))
  assert metadata['Name'].lower().replace('_','-')==item['name'] and metadata['Version']==item['version']
  notices={n:hashlib.sha256(bundle.read(n)).hexdigest() for n in bundle.namelist()
           if not n.endswith('/') and ('license' in n.lower() or 'notice' in n.lower()) and bundle.getinfo(n).file_size<1024**2}
  return item|{'retained_path':str(target),'downloaded':downloaded,'copied_from_verified_cache':copied,
    'elapsed_seconds':time.monotonic()-started,'expanded_bytes':sum(n.file_size for n in bundle.infolist()),
    'requires_python':metadata.get('Requires-Python'),'requires_dist':metadata.get_all('Requires-Dist',[]),
    'license_expression':metadata.get('License-Expression'),'license':metadata.get('License'),
    'license_classifiers':[n for n in metadata.get_all('Classifier',[]) if n.startswith('License ::')],
    'notice_hashes':notices,'installed':False,'executed':False}

results=[];errors=[]
with ThreadPoolExecutor(max_workers=4) as pool:
 pending={pool.submit(inspect,item):item for item in items}
 for future in as_completed(pending):
  try:results.append(future.result())
  except Exception as error:errors.append({'name':pending[future]['name'],'error_type':type(error).__name__})
record={'purpose':'Hash-bound static archive/cache preparation only',
 'artifacts':sorted(results,key=lambda item:item['name']),'errors':errors,
 'installed':False,'executed':False,'models':0,'docker_mutations':False,
 'historical_accounting':'Preparation has no canonical workflow scope; observed transfer bytes/elapsed are retained here, not invented into older grants or benchmark measurements.'}
(HERE/'cached-artifacts.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'artifacts':len(results),'errors':errors,
 'downloaded_bytes':sum(item['bytes'] for item in results if item['downloaded']),
 'copied_bytes':sum(item['bytes'] for item in results if item['copied_from_verified_cache']),
 'expanded_bytes':sum(item['expanded_bytes'] for item in results),'installed':False,'executed':False}))
