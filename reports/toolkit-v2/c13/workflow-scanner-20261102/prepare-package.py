"""Bind built current wheel and 32 existing dependencies; never install."""
import hashlib,json,platform,shutil,sys,zipfile
from pathlib import Path
from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import RuntimeInstallation,check_closure,digest,file_digest,prepare
from aeep_toolkit.installation import PreviewPolicy,manifest_digest,preview
from aeep_toolkit.models import ExtensionManifest,ExtensionRegistry
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
assert not (HERE/'package-installation.json').exists()
checks=json.loads((HERE/'verification-final/checks.json').read_text())
assert len(checks['checks'])==13 and all(c['exit_code']==0 for c in checks['checks'])
assert checks['source_before']==checks['source_after']==verification_source_digest(ROOT)
old=RuntimeInstallation.model_validate_json((ROOT/'reports/toolkit-v2/integration-completion/package-review-codec-preflight-20261029/installation.json').read_bytes())
assert len(old.wheels)==33
wheel=next((HERE/'verification-final/dist').glob('*.whl'))
assert shutil.disk_usage(ROOT).free>50*1024**3+512*1024**2
wheelhouse=ROOT/'.aeep/workflow-scanner-20261102/package-wheels';wheelhouse.mkdir(mode=0o700,exist_ok=True)
metadata={item.manifest.extension_id:item.manifest for item in old.preview.items}
values=[]
for original in old.wheels:
 source=wheel if original.extension_id=='aeep-agent-router' else Path(old.wheelhouse)/original.filename
 expected=file_digest(source)
 assert original.extension_id=='aeep-agent-router' or expected==original.sha256
 target=wheelhouse/original.filename
 if target.exists():assert file_digest(target)==expected,'preserve changed prepared cache'
 else:shutil.copyfile(source,target)
 values.append(original.model_copy(update={'sha256':expected}))
new=metadata['aeep-agent-router'].model_dump(mode='json')
new['source']['artifact_sha256']=file_digest(wheel);new['source']['revision']=checks['source_before']
groups={'aeep':{},'aeep_toolkit':{},'integrations':{}}
with zipfile.ZipFile(wheel) as archive:
 for file in (ROOT/'src').rglob('*.py'):
  if '__pycache__' not in file.parts and not any(p.endswith('.egg-info') for p in file.parts):
   assert archive.read(file.relative_to(ROOT/'src').as_posix())==file.read_bytes()
 new['disk_bytes']=sum(i.file_size for i in archive.infolist())+wheel.stat().st_size
 for name in archive.namelist():
  if name.endswith('/') or '__pycache__' in name.split('/'):continue
  for label in ('aeep','aeep_toolkit'):
   if name.startswith(label+'/'):groups[label][name.removeprefix(label+'/')]=archive.read(name)
  prefix='aeep_agent_router-0.8.2.data/data/share/aeep/integrations/'
  if name.startswith(prefix):groups['integrations'][name.removeprefix(prefix)]=archive.read(name)
state=hashlib.sha256(b'aeep.installed-source.v1\0')
for label,files in sorted(groups.items()):
 assert files
 for name,raw in sorted(files.items()):
  state.update((label+'/'+name).encode()+b'\0');state.update(hashlib.sha256(raw).digest())
metadata['aeep-agent-router']=ExtensionManifest.model_validate(new)
registry=ExtensionRegistry(extensions=tuple(metadata.values()))
policy=PreviewPolicy.model_validate(old.policy.model_dump(mode='json')|{'free_disk_bytes':shutil.disk_usage(ROOT).free,
 'reviewed_dependency_manifests':tuple(manifest_digest(m) for m in metadata.values())})
proposed=preview(registry,('aeep-agent-router',),policy,profile='essentials')
space_blocked=False
try:
 plan=prepare(proposed,policy,ROOT/'.aeep/workflow-scanner-20261102/installed-runtime',wheelhouse,tuple(values))
except ValueError as error:
 if str(error)!='actual wheel closure would cross the 50 GiB free-space reserve':raise
 space_blocked=True
 # An inert model is a review draft, never permission to bypass apply()'s unchanged
 # pre-effect reserve check. Record the blocker explicitly and defer installation.
 interpreter=Path(sys.executable).resolve(strict=True)
 plan=RuntimeInstallation(preview=proposed,policy=policy,destination=str(ROOT/'.aeep/workflow-scanner-20261102/installed-runtime'),
  wheelhouse=str(wheelhouse),interpreter=str(interpreter),interpreter_sha256=file_digest(interpreter),
  python_version=platform.python_version(),system=sys.platform,machine=platform.machine(),wheels=tuple(values))

for name,value in [('package-installation',plan),('package-registry',registry),('package-policy',policy)]:
 (HERE/(name+'.json')).write_text(value.model_dump_json(indent=2)+'\n')
work=HERE/'package-execution/work';runtime=Path(plan.destination)
profile='(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (literal "/dev/null"))\n'
profile+='(allow file-write* (subpath '+json.dumps(str(work))+'))\n'
profile+='(deny file-read* (subpath '+json.dumps(str(Path.home().resolve()))+'))\n'
for path in (runtime,work):profile+='(allow file-read* (subpath '+json.dumps(str(path))+'))\n'
profile+='(allow file-read-metadata '+' '.join('(literal '+json.dumps(str(p))+')' for p in dict.fromkeys((*runtime.parents,*work.parents)) if p.is_relative_to(Path.home()))+')\n'
(HERE/'package.sb').write_text(profile)
(HERE/'package-preparation.json').write_text(json.dumps({'passed':True,'source':checks['source_before'],'installation_digest':digest(plan),
 'installed_source':state.hexdigest(),'space_blocked':space_blocked,'execution_ready':not space_blocked,'actual_free_bytes':shutil.disk_usage(ROOT).free,'wheels':33,'changed_wheels':1,'unchanged_dependencies':32,
 'reserve_bytes':max(plan.preview.known_disk_bytes,500*1024**2+check_closure(wheelhouse,tuple(values),policy.platform))+16*1024**2,'executed':False},indent=2)+'\n')
print(json.dumps({'prepared':True,'executed':False,'wheels':33}))
