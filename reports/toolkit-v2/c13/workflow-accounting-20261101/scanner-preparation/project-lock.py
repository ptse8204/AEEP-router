"""Project the selected upstream lock without executing or installing its code."""
import hashlib
import json
import tomllib
from collections import defaultdict, deque
from pathlib import Path
from urllib.request import urlopen

from packaging.markers import Marker, default_environment
from packaging.requirements import Requirement
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import parse_wheel_filename

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
SOURCE=ROOT/'.aeep/upstream-stack-source-20261031/cisco-ai-defense__skill-scanner'
lock_bytes=(SOURCE/'uv.lock').read_bytes()
assert hashlib.sha256(lock_bytes).hexdigest()=='788df6effe50e74ac3ba01d3116b42b5fc3e2a9cf8886e77d53a407ccf48c50c'
lock=tomllib.loads(lock_bytes.decode())
project=tomllib.loads((SOURCE/'pyproject.toml').read_text())['project']
env=default_environment()|{'python_version':'3.13','python_full_version':'3.13.15',
 'sys_platform':'linux','os_name':'posix','platform_system':'Linux',
 'platform_machine':'aarch64','platform_python_implementation':'CPython','extra':''}
platforms=[f'manylinux_2_{minor}_aarch64' for minor in range(41,16,-1)]+['manylinux2014_aarch64','linux_aarch64']
tags=list(cpython_tags((3,13),abis=['cp313'],platforms=platforms))+list(compatible_tags((3,13),interpreter='cp313',platforms=platforms))
rank={tag:i for i,tag in enumerate(tags)}
index=defaultdict(list)
for package in lock['package']:index[package['name']].append(package)
selected={};extras=defaultdict(set);queue=deque([{'name':project['name']}]);edges=[];skipped=[]
while queue:
 edge=queue.popleft()
 if edge.get('marker') and not Marker(edge['marker']).evaluate(env):
  skipped.append(edge);continue
 name=edge['name']
 candidates=[p for p in index[name] if ('version' not in edge or p.get('version')==edge['version'])]
 if len(candidates)!=1:raise ValueError(('ambiguous lock package',name,[p.get('version') for p in candidates]))
 package=candidates[0]
 new_extras=set(edge.get('extra',[]))-extras[name]
 if name not in selected:
  selected[name]=package
  queue.extend(package.get('dependencies',[]))
  edges.extend({'parent':name,**item} for item in package.get('dependencies',[]))
 for extra in new_extras:
  added=package.get('optional-dependencies',{}).get(extra)
  if added is None:raise ValueError(('missing declared extra',name,extra))
  queue.extend(added);edges.extend({'parent':name,'enabled_extra':extra,**item} for item in added)
 extras[name].update(new_extras)
packages=[];missing=[]
for name,p in sorted(selected.items()):
 if name==project['name']:continue
 wheels=[]
 for artifact in p.get('wheels',[]):
  filename=artifact['url'].rsplit('/',1)[-1]
  _,_,_,wheel_tags=parse_wheel_filename(filename)
  positions=[rank[tag] for tag in wheel_tags if tag in rank]
  if positions:wheels.append((min(positions),artifact))
 item={'name':name,'version':p['version'],'extras':sorted(extras[name])}
 if wheels:
  artifact=min(wheels,key=lambda value:value[0])[1]
  item['artifact']={'url':artifact['url'],'sha256':artifact['hash'].removeprefix('sha256:'),
    'bytes':artifact['size'],'filename':artifact['url'].rsplit('/',1)[-1]}
 else:
  item['sdist_metadata_only']=p.get('sdist');missing.append(name)
 packages.append(item)
checks=[]
for declaration in project['dependencies']:
 req=Requirement(declaration);p=selected[req.name.lower().replace('_','-')]
 assert req.specifier.contains(p['version']),declaration
 checks.append({'requirement':declaration,'version':p['version'],'compatible':True})
url='https://pypi.org/pypi/cisco-ai-skill-scanner/2.2.1/json'
with urlopen(url,timeout=30) as response:
 raw=response.read(4*1024*1024+1)
assert len(raw)<=4*1024*1024
metadata=json.loads(raw)
root_artifacts=[]
for artifact in metadata['urls']:
 if artifact['packagetype']=='bdist_wheel':
  _,_,_,wheel_tags=parse_wheel_filename(artifact['filename'])
  if any(tag in rank for tag in wheel_tags):
   root_artifacts.append({'filename':artifact['filename'],'url':artifact['url'],
    'bytes':artifact['size'],'sha256':artifact['digests']['sha256'],'yanked':artifact['yanked']})
result={'purpose':'Static mandatory dependency projection; not an installation or execution review',
 'source_revision':'c3d7fd9fee50cf2ea45f0b381eb61f857360f825','source_lock_sha256':hashlib.sha256(lock_bytes).hexdigest(),
 'target':env,'retained_image':'sha256:35dc1bcb7e8162c2a0cef6cbd30bc4bf276c082b11b6e5fc259b6800e8c5ca04',
 'python_version_basis':'Read-only selected image PYTHON_VERSION metadata; no container execution',
 'dependency_count':len(packages),'packages':packages,'dependency_edges':edges,'marker_exclusions':skipped,
 'root_requirements':checks,'packages_without_compatible_wheel':missing,
 'dependency_archive_bytes':sum(p.get('artifact',{}).get('bytes',0) for p in packages),
 'root_metadata_url':url,'root_metadata_sha256':hashlib.sha256(raw).hexdigest(),
 'root_requires_dist':metadata['info'].get('requires_dist',[]),'root_artifacts':root_artifacts,
 'root_license':metadata['info'].get('license_expression') or metadata['info'].get('license'),
 'compatibility_blockers':['The selected source requires openai<3 and rich<15; the composed SDK runtime pins OpenAI3.26.1 and Rich15.0.0. Keep the scanner in its own component runtime with upstream lock pins.',
 'Package wheel identity/source equivalence, remaining sdist-only artifacts, licenses/notices and actual static analyzer dependencies still require review.',
 'No dependency graph/version projection by itself establishes a functional scanner.'],
 'downloaded_dependency_wheels':False,'installed':False,'executed':False,'models':0}
(HERE/'dependency-projection.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('dependency_count','dependency_archive_bytes','packages_without_compatible_wheel','root_artifacts')}))
