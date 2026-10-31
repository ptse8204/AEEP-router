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
cache=ROOT/'.aeep/upstream-stack-runtimes-20261030';wheelhouse=cache/'composed-wheels'
values=[Wheel.model_validate(x) for x in json.loads((cache/'dependencies.json').read_text())]
wheel=next((cache/'build').glob('*.whl'));target=wheelhouse/wheel.name
if not target.exists():shutil.copyfile(wheel,target)
assert file_digest(target)==file_digest(wheel)
values.append(Wheel(extension_id='aeep-agent-router',filename=wheel.name,name='aeep-agent-router',version='0.8.2',sha256=file_digest(target)))
old_sources={}
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
        license_name=old['license_expression'] if old else meta.get('License-Expression') or meta.get('License')
        packages[w.extension_id]={'name':w.name,'version':w.version,
            'url':old['repository'] if old else 'https://github.com/ptse8204/AEEP-router',
            'sha256':w.sha256,'license':license_name,
            'license_records':{n:hashlib.sha256(bundle.read(n)).hexdigest() for n in bundle.namelist() if not n.endswith('/') and ('license' in n.lower() or 'notice' in n.lower())},
            'archive_bytes':(wheelhouse/w.filename).stat().st_size,'expanded_bytes':sum(i.file_size for i in bundle.infolist()),
            'dependencies':list(dict.fromkeys(deps)),'requires_dist':meta.get_all('Requires-Dist',[])}
        assert license_name and len(license_name)<200,(w.name,'missing bounded reviewed license')
manifest={};rights='Private retained runtime for engineering only; preserve bundled notices. No redistribution or provider authority.'
for name in TopologicalSorter({name:p['dependencies'] for name,p in packages.items()}).static_order():
    p=packages[name]
    manifest[name]=ExtensionManifest(extension_id=name,purpose='Retained AEEP/LangGraph runtime: '+name,
        role='orchestrator' if name=='langgraph' else 'evaluator' if name=='aeep-agent-router' else 'support',
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
install=prepare(preview(registry,('aeep-agent-router','langgraph'),policy,profile='full'),policy,cache/'composed-runtime',wheelhouse,tuple(values))
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
review={
    'purpose':'Install the exact local AEEP/LangGraph wheel closure once in a retained private runtime, then check real SDK composition over existing approved command executors and installed package metadata. Engineering only.',
    'checkout_source':verification_source_digest(ROOT),'installed_source':installed_source,'installation_digest':digest(install),
    'wheel_count':len(values),'wheel_sha256':file_digest(target),'driver_sha256':file_digest(HERE/'run-review.py'),'worker_sha256':file_digest(HERE/'functional-check.py'),
    'disk_reservation_bytes':500*1024**2+check_closure(wheelhouse,tuple(values),policy.platform),'minimum_host_reserve_bytes':50*1024**3,
    'maximum_install_processes':3,'maximum_install_process_seconds_each':300,
    'maximum_sdk_processes':1,'maximum_sdk_seconds':90,'maximum_owned_executor_calls':6,'maximum_owned_executor_seconds_each':5,
    'maximum_private_grant_operations':8,'maximum_private_grant_reserved_seconds':120,
    'maximum_package_processes':1,'maximum_package_seconds':30,'maximum_boundary_processes':1,'maximum_boundary_seconds':20,
    'maximum_model_turns':0,'cash_usd':0,'downloads':False,'docker_changes':False,'credentials':False,'services':False,'activation':False,'release':False,
    'runtime_retained':str(install.destination),'automatic_retry':False,'candidate_usefulness':'NOT_ASSESSED','selection_usefulness':'NOT_ASSESSED',
    'source_wheel_equivalence':'LangGraph1.2.14 wheel is exact and independently reviewed. Inspected source40a2e6d8 has different dependency metadata; no source equivalence claim.',
    'dependency_compatibility':'AEEP pins packaging24.2; preserve it and otherwise prefer already-reviewed LangGraph dependency pins. All selected wheel requirements pass static closure validation.',
    'accounting_scope':'Canonical owned-step grant/attempt receipts and outer SDK receipts. New isolated engineering grant only; no existing assessment grant changes or model/value-study charges. Outer and nested resource intervals overlap and are not summed.',
    'recovery_scope':'Conditional execution, bounded loops, same-runtime interruption/resumption, lost-checkpoint refusal, denied dispatch. Cross-process checkpoint continuation remains unverified.',
    'stop_rules':'One component attempt only. Preserve failures, runtime and receipts. No automatic retry, cleanup, image removal or source repair execution. Installed metadata check proceeds independently after SDK failure. Refuse execution until all13 current-source checks pass.',
}
for name,value in [('installation',install.model_dump(mode='json')),('registry',registry.model_dump(mode='json')),('policy',policy.model_dump(mode='json')),('packages',packages),('operation-review',review)]:
    (HERE/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps({'review_sha256':file_digest(HERE/'operation-review.json'),'wheels':len(values),'reserve_bytes':review['disk_reservation_bytes'],'installed':False,'executed':False,'source':review['checkout_source']}))
