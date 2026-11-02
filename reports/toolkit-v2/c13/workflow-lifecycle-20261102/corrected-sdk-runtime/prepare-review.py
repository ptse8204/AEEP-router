"""Static preparation only: retain selected pins, capture current source and review."""
import hashlib,json,shutil,zipfile
from pathlib import Path
from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import RuntimeInstallation,Wheel,check_closure,digest,file_digest,prepare
from aeep_toolkit.installation import PreviewPolicy,manifest_digest,preview
from aeep_toolkit.models import ExtensionManifest,ExtensionRegistry

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
old=ROOT/'reports/toolkit-v2/c13/workflow-accounting-20261101/composed-sdk-runtime'
prior=RuntimeInstallation.model_validate_json((old/'installation.json').read_bytes())
source=verification_source_digest(ROOT)
assert source=='e363cfa5ada2201e355b1e4528ff36cb2d05a08fff7423912c6d5e163ea43dfb'
cache=ROOT/'.aeep/upstream-stack-runtimes-20261102'
cache.mkdir(exist_ok=True)
wheelhouse=cache/'wheels';wheelhouse.mkdir(exist_ok=True)
wheel=HERE/'artifacts/aeep_agent_router-0.8.2-py3-none-any.whl'
assert shutil.disk_usage(ROOT).free>50*1024**3+1024**3
values=[]
for original in prior.wheels:
 source_file=wheel if original.extension_id=='aeep-agent-router' else Path(prior.wheelhouse)/original.filename
 expected=file_digest(source_file)
 target=wheelhouse/original.filename
 if target.exists():assert file_digest(target)==expected,'do not overwrite retained bytes'
 else:shutil.copyfile(source_file,target)
 values.append(original.model_copy(update={'sha256':expected}))
metadata={item.manifest.extension_id:item.manifest for item in prior.preview.items}
a=metadata['aeep-agent-router'].model_dump(mode='json')
a['source']['artifact_sha256']=values[next(i for i,w in enumerate(values) if w.extension_id=='aeep-agent-router')].sha256
a['source']['revision']=a['source']['artifact_sha256']
with zipfile.ZipFile(wheel) as archive:
 a['disk_bytes']=wheel.stat().st_size+sum(item.file_size for item in archive.infolist())
 for file in (ROOT/'src').rglob('*.py'):
  relative=file.relative_to(ROOT/'src').as_posix()
  if '__pycache__' not in file.parts and '.egg-info' not in str(file):
   assert archive.read(relative)==file.read_bytes(),relative
 groups={'aeep':{},'aeep_toolkit':{},'integrations':{}}
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
 installed_source=state.hexdigest()
metadata['aeep-agent-router']=ExtensionManifest.model_validate(a)
registry=ExtensionRegistry(extensions=tuple(metadata.values()))
policy=PreviewPolicy.model_validate(prior.policy.model_dump(mode='json')|{
 'free_disk_bytes':shutil.disk_usage(ROOT).free,
 'reviewed_dependency_manifests':tuple(manifest_digest(value) for value in metadata.values())})
plan=prepare(preview(registry,prior.preview.selected,policy,profile='full'),policy,
             cache/'corrected-composed-runtime',wheelhouse,tuple(values))
for name,value in (('installation',plan),('registry',registry),('policy',policy)):
 (HERE/(name+'.json')).write_text(value.model_dump_json(indent=2)+'\n')
frozen=ROOT/'.aeep/stack-frozen-source-e363cfa5';frozen.mkdir(exist_ok=True)
files={}
for folder in ('src','tests','integrations/aeep','integrations/assessment-runtime','integrations/managed-worker','scripts'):
 for original in (ROOT/folder).rglob('*'):
  if not original.is_file() or any(p=='__pycache__' or p.endswith('.egg-info') for p in original.parts):continue
  relative=original.relative_to(ROOT);target=frozen/relative;target.parent.mkdir(parents=True,exist_ok=True)
  if target.exists():assert file_digest(target)==file_digest(original)
  else:shutil.copyfile(original,target)
  files[str(relative)]=file_digest(target)
target=frozen/'pyproject.toml'
if not target.exists():shutil.copyfile(ROOT/'pyproject.toml',target)
files['pyproject.toml']=file_digest(target)
assert verification_source_digest(frozen)==source
(HERE/'source-snapshot.json').write_text(json.dumps({'snapshot_path':str(frozen),'source_digest':source,'files':files},indent=2)+'\n')
for component in ('framework','package'):
 work=HERE/'execution/owned-work'/component
 runtime=Path(plan.destination)
 profile='(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (literal "/dev/null"))\n'
 profile+='(allow file-write* (subpath '+json.dumps(str(work))+'))\n'
 profile+='(deny file-read* (subpath '+json.dumps(str(Path.home().resolve()))+'))\n'
 for path in (runtime,work):profile+='(allow file-read* (subpath '+json.dumps(str(path))+'))\n'
 profile+='(allow file-read-metadata '+' '.join('(literal '+json.dumps(str(p))+')' for p in dict.fromkeys((*runtime.parents,*work.parents)) if p.is_relative_to(Path.home()))+')\n'
 (HERE/(component+'.sb')).write_text(profile)
review={'purpose':'Verify corrected current AEEP wheel and actual Agent Framework1.21.0 context contract in one reusable private runtime; keep previous runtimes and evidence.',
 'checkout_source':source,'installed_source':installed_source,'installation_digest':digest(plan),'runtime':plan.destination,
 'verification_checks':str((HERE.parent/'verification-correction/checks.json').relative_to(ROOT)),
 'execution_gate':'All13 original gate names must pass on the exact frozen source before any installation. Pending check records grant no execution authority.',
 'wheel_count':64,'changed_wheels':1,'unchanged_dependency_wheels':63,
 'wheel_sha256':file_digest(wheel),'disk_reservation_bytes':500*1024**2+check_closure(wheelhouse,tuple(values),policy.platform),
 'minimum_host_reserve_bytes':50*1024**3,'maximum_install_attempts':1,'maximum_install_processes':3,'maximum_install_seconds_each':300,
 'maximum_framework_attempts':1,'maximum_framework_process_seconds':90,'maximum_owned_executor_calls':5,
 'maximum_new_isolated_engineering_operations':8,'maximum_new_reserved_engineering_seconds':120,
 'maximum_boundary_processes':2,'maximum_boundary_seconds_each':20,'maximum_package_processes':1,'maximum_package_seconds':30,
 'maximum_model_turns':0,'cash_usd':0,'downloads':False,'docker_changes':False,'services':False,'credentials':False,
 'activation':False,'publication':False,'release':False,'cleanup':False,'retain_runtimes':True,
 'langgraph_execution':False,'ase_execution':False,
 'scope':'One current wheel plus unchanged63 dependencies. Framework uses the concrete optional SDK WorkflowContext annotation; program remains identical. Package check validates source,16 ASE files and lifecycle CLI/schema. Earlier Graph success is preserved, not replayed.',
 'failure_policy':'One attempt per component. Installation/boundary/runtime drift or uncertain SDK reservations stops dispatch. A settled Framework failure may leave independent package check eligible. No retry, repair, source/profile change, cleanup or counter reset under this review.',
 'accounting':'Owned numeric engineering grant and actual receipts only. Outer receipts overlap nested operations and are not summed. No existing assessment grant changes; missing measurements remain unknown.',
 'evidence_scope':'Component/installed-package engineering only. Full stack, both SkillsBench domain journeys, candidate usefulness, selection usefulness, resource acceptance and release remain separate/open.'}
# Complete the preparation/fixture checks before binding this review.
(HERE/'review-draft.json').write_text(json.dumps(review,indent=2)+'\n')
print(json.dumps({'prepared':True,'installed':False,'executed':False,'source':source,'wheels':64,'reserve_bytes':review['disk_reservation_bytes']}))
