"""Read pinned cached wheels and prepare an inert composed-runtime review."""
import hashlib
import json
import shutil
import zipfile
from email.parser import BytesParser
from graphlib import TopologicalSorter
from pathlib import Path

from packaging.requirements import Requirement
from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import Wheel,check_closure,digest,file_digest,prepare
from aeep_toolkit.installation import PreviewPolicy,manifest_digest,preview
from aeep_toolkit.models import ExtensionManifest,ExtensionRegistry

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
cache=ROOT/'.aeep/upstream-stack-runtimes-20261101';cache.mkdir(exist_ok=True)
wheelhouse=cache/'composed-wheels';wheelhouse.mkdir(exist_ok=True)
previous=json.loads((ROOT/'reports/toolkit-v2/c13/full-stack-20261030/composed-sdk-runtime/installation.json').read_text())
values=[Wheel.model_validate(x) for x in previous['wheels'] if x['name']!='aeep-agent-router']
for w in values:
    assert file_digest(wheelhouse/w.filename)==w.sha256
extra=json.loads((ROOT/'reports/toolkit-v2/c13/workflow-engine-20261101/ase-additional-artifacts.json').read_text())['artifacts']
for item in extra:
    assert file_digest(wheelhouse/item['filename'])==item['sha256']
    values.append(Wheel(extension_id=item['name'],filename=item['filename'],name=item['name'],version=item['version'],sha256=item['sha256']))
wheel=next((ROOT/'reports/toolkit-v2/c13/workflow-accounting-20261101/verification/dist').glob('*.whl'));target=wheelhouse/wheel.name
if target.exists():
    assert file_digest(target)==file_digest(wheel), 'Do not overwrite a historical wheel'
else:shutil.copyfile(wheel,target)
values.append(Wheel(extension_id='aeep-agent-router',filename=wheel.name,name='aeep-agent-router',version='0.8.2',sha256=file_digest(target)))
old_sources={}
previous_packages=json.loads((ROOT/'reports/toolkit-v2/c13/full-stack-20261030/composed-sdk-runtime/packages.json').read_text())
for filename in ['reports/toolkit-v2/integration-completion/package-review-codec-preflight-20261029/installation.json','reports/toolkit-v2/integration-completion/langgraph-review-v2/installation.json']:
    for item in json.loads((ROOT/filename).read_text())['preview']['items']:
        source=item['manifest']['source'];old_sources[source['artifact_sha256']]=source
packages={}
for w in values:
    with zipfile.ZipFile(wheelhouse/w.filename) as bundle:
        meta=BytesParser().parsebytes(bundle.read(next(n for n in bundle.namelist() if n.endswith('.dist-info/METADATA'))))
        deps=[]
        for req in meta.get_all('Requires-Dist',[]):
            parsed=Requirement(req)
            if parsed.marker is None or parsed.marker.evaluate({'extra':''}):deps.append(parsed.name.lower().replace('_','-'))
        old=old_sources.get(w.sha256)
        previous_package=previous_packages.get(w.extension_id)
        license_name=old['license_expression'] if old else meta.get('License-Expression') or meta.get('License')
        if previous_package and previous_package['sha256']==w.sha256:license_name=previous_package['license']
        if w.name=='agent-framework-core':license_name='MIT'
        packages[w.extension_id]={'name':w.name,'version':w.version,
            'url':old['repository'] if old else previous_package['url'] if previous_package and previous_package['sha256']==w.sha256 else next((i['url'] for i in extra if i['name']==w.name),'https://github.com/ptse8204/AEEP-router'),
            'sha256':w.sha256,'license':license_name,
            'license_records':{n:hashlib.sha256(bundle.read(n)).hexdigest() for n in bundle.namelist() if not n.endswith('/') and ('license' in n.lower() or 'notice' in n.lower())},
            'archive_bytes':(wheelhouse/w.filename).stat().st_size,'expanded_bytes':sum(i.file_size for i in bundle.infolist()),
            'dependencies':list(dict.fromkeys(deps)),'requires_dist':meta.get_all('Requires-Dist',[])}
        assert license_name and len(license_name)<200,(w.name,'missing bounded reviewed license')
manifest={};rights='Private retained runtime for engineering only; preserve bundled notices. No redistribution or provider authority.'
for name in TopologicalSorter({name:p['dependencies'] for name,p in packages.items()}).static_order():
    p=packages[name]
    manifest[name]=ExtensionManifest(extension_id=name,purpose='Retained AEEP/composed SDK runtime: '+name,
        role='orchestrator' if name in ('langgraph','agent-framework-core') else 'evaluator' if name in ('aeep-agent-router','agent-skill-eval') else 'support',
        source={'repository':p['url'],'revision':p['sha256'],'artifact_sha256':p['sha256'],'license_expression':p['license'],'data_rights':rights},
        hosts=('local-python',),platforms=('darwin-arm64',),dependencies=tuple({'extension_id':dep,'manifest_sha256':manifest_digest(manifest[dep])} for dep in p['dependencies']),
        permissions={'network_destinations':[],'filesystem_scope':'workspace','authentication':'none','financial_exposure':'none'},
        disk_bytes=p['archive_bytes']+p['expanded_bytes'],memory_bytes=None,
        install_effects=('Private reusable runtime only; no activation, credentials, provider calls or service.',),
        rollback='Keep reusable runtime. Selective removal needs applicable review and existing installer ownership/conflict checks.',status='not_installed')
registry=ExtensionRegistry(extensions=tuple(manifest.values()))
policy=PreviewPolicy(host='local-python',platform='darwin-arm64',allowed_licenses=tuple(sorted({p['license'] for p in packages.values()})),
    allowed_data_rights=(rights,),allowed_filesystem_scopes=('workspace',),free_disk_bytes=shutil.disk_usage(ROOT).free,
    allow_unknown_memory=True,reviewed_dependency_manifests=tuple(manifest_digest(m) for m in manifest.values()))
install=prepare(preview(registry,('aeep-agent-router','langgraph','agent-framework-core','agent-skill-eval'),policy,profile='full'),policy,cache/'composed-runtime',wheelhouse,tuple(values))
with zipfile.ZipFile(target) as bundle:
    groups={'aeep':{},'aeep_toolkit':{},'integrations':{}}
    for name in bundle.namelist():
        if name.endswith('/') or '__pycache__' in name.split('/'):continue
        for label in ('aeep','aeep_toolkit'):
            if name.startswith(label+'/'):groups[label][name.removeprefix(label+'/')]=bundle.read(name)
        prefix='aeep_agent_router-0.8.2.data/data/share/aeep/integrations/'
        if name.startswith(prefix):groups['integrations'][name.removeprefix(prefix)]=bundle.read(name)
    state=hashlib.sha256(b'aeep.installed-source.v1'+bytes([0]))
    for label,files in sorted(groups.items()):
        assert files
        for name,raw in sorted(files.items()):
            state.update((label+'/'+name).encode()+bytes([0]));state.update(hashlib.sha256(raw).digest())
    installed_source=state.hexdigest()
checks=json.loads((ROOT/'reports/toolkit-v2/c13/workflow-accounting-20261101/verification/checks.json').read_text())
source=verification_source_digest(ROOT)
assert checks['source_before']==checks['source_after']==source
assert len(checks['checks'])==13 and all(x['exit_code']==0 for x in checks['checks'])
snapshot_root=ROOT/'.aeep/stack-frozen-source-443b90a7'
snapshot_root.mkdir(exist_ok=True)
source_files=[ROOT/'pyproject.toml']
for label in ('src','tests','integrations/aeep','integrations/assessment-runtime','integrations/managed-worker','scripts'):
    source_files.extend((ROOT/label).rglob('*'))
files={}
for source_file in source_files:
    rel=source_file.relative_to(ROOT)
    if not source_file.is_file() or any(part=='__pycache__' or part.endswith('.egg-info') for part in rel.parts):continue
    assert not source_file.is_symlink()
    destination=snapshot_root/rel;destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists():shutil.copyfile(source_file,destination)
    assert file_digest(destination)==file_digest(source_file)
    files[str(rel)]=file_digest(destination)
assert verification_source_digest(snapshot_root)==source
snapshot_manifest={'snapshot_path':str(snapshot_root),'source_digest':source,'files':files}
(HERE/'source-snapshot.json').write_text(json.dumps(snapshot_manifest,indent=2)+'\n')
working=HERE/'execution/owned-work'
runtime=Path(install.destination)
profile='(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (literal "/dev/null"))\n'
profile+='(allow file-write* (subpath '+json.dumps(str(working))+'))\n'
profile+='(deny file-read* (subpath '+json.dumps(str(Path.home().resolve()))+'))\n'
profile+='(allow file-read* (subpath '+json.dumps(str(runtime))+'))\n'
profile+='(allow file-read* (subpath '+json.dumps(str(working))+'))\n'
profile+='(allow file-read-metadata '+' '.join('(literal '+json.dumps(str(p))+')' for p in dict.fromkeys((*runtime.parents,*working.parents)) if p.is_relative_to(Path.home()))+')\n'
(HERE/'reviewed-boundary.sb').write_text(profile)
review={
    'purpose':'Retain current AEEP and 63 dependency wheels for the composed SDK/ASE runtime. Execute the existing real LangGraph/Agent Framework reference-only checks; verify installed ASE source bytes without invoking it. Engineering only.',
    'checkout_source':source,'installed_source':installed_source,'installation_digest':digest(install),
    'source_snapshot_manifest_sha256':file_digest(HERE/'source-snapshot.json'),
    'verification_checks_sha256':file_digest(ROOT/'reports/toolkit-v2/c13/workflow-accounting-20261101/verification/checks.json'),
    'ase_functional_execution':False,'ase_installed_source_files':16,'wheel_count':len(values),'wheel_sha256':file_digest(target),'driver_sha256':file_digest(HERE/'run-review.py'),
    'worker_sha256':file_digest(HERE/'functional-check.py'),'langgraph_worker_sha256':file_digest(HERE/'langgraph-check.py'),'profile_sha256':file_digest(HERE/'reviewed-boundary.sb'),
    'first_party_program_fixture_sha256':file_digest(HERE/'first-party-functional-program-check.json'),
    'first_party_boundary_sha256':file_digest(HERE/'first-party-boundary-check.json'),
    'disk_reservation_bytes':500*1024**2+check_closure(wheelhouse,tuple(values),policy.platform),
    'minimum_host_reserve_bytes':50*1024**3,
    'maximum_install_processes':3,'maximum_install_process_seconds_each':300,
    'maximum_sdk_processes':2,'maximum_sdk_seconds':90,'maximum_owned_executor_calls':11,
    'maximum_owned_executor_seconds_each':5,'maximum_private_grant_operations':16,
    'maximum_private_grant_reserved_seconds':240,'maximum_package_processes':1,
    'maximum_package_seconds':30,'maximum_boundary_processes':1,'maximum_boundary_seconds':20,
    'maximum_model_turns':0,'cash_usd':0,'downloads':False,'docker_changes':False,'credentials':False,
    'services':False,'activation':False,'release':False,'runtime_retained':str(install.destination),
    'automatic_retry':False,'candidate_usefulness':'NOT_ASSESSED','selection_usefulness':'NOT_ASSESSED',
    'artifact_provenance':'Existing 60 common dependency pins retained. Adds ASE0.7.0, OpenAI3.26.1 and Jiter0.17.0 from the selected original stack pins. Their mandatory imports confer no provider access. ASE installed source check is not its scheduler/grader/controlled-worker functional journey. Framework builder source identity retains its original narrower scope.',
    'accounting_scope':'Canonical engineering-only grant, operation reservations and actual receipts. Outer SDK receipt retained separately; nested intervals overlap and are not summed. No existing assessment grant changes.',
    'langgraph_recovery_scope':'Conditional flow, bounded loops, same-runtime checkpoint interruption/resumption and lost-state/denied-dispatch refusal. Cross-process continuation unverified.',
    'recovery_scope':'Agent Framework SDK interruption keeps actual completed command receipt; same object cannot restart. One distinct pre-reviewed continuation consumes the retained public result without replay. SDK checkpoint restoration and cross-process recovery unsupported.',
    'stop_rules':'One attempt per component. Failed installation blocks SDK/package checks; after successful installation, A terminal SDK failure does not block the other SDK or installed-package verification. Common boundary/accounting uncertainty stops dispatch. Preserve all failures/runtime. No source/permission correction, reinstall, retry or cleanup. Refuse execution if frozen verification or any bound artifact differs.',
}
for name,value in [('installation',install.model_dump(mode='json')),('registry',registry.model_dump(mode='json')),('policy',policy.model_dump(mode='json')),('packages',packages),('operation-review',review)]:
    (HERE/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps({'review_sha256':file_digest(HERE/'operation-review.json'),'wheels':len(values),'reserve_bytes':review['disk_reservation_bytes'],'installed':False,'executed':False,'source':review['checkout_source']}))
