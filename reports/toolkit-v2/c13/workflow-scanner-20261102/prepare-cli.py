"""Prepare exact ordinary CLI inputs; no container, upstream import or grant."""
from __future__ import annotations
import contextlib, hashlib, io, json, shutil, sys
from datetime import timedelta
from pathlib import Path
from aeep.assessment.identity import file_digest
from aeep.assessment.models import AssessmentEnvironment, AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import Manifest, StrictModel, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.candidate import inspect
from aeep_toolkit.cli import main
from aeep_toolkit.installation import PreviewPolicy, manifest_digest
from aeep_toolkit.models import ExtensionManifest, ExtensionRegistry
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_security import ScannerRuntimeDefinition, scan_preview

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[3]
SOURCE=verification_source_digest(ROOT)
CACHE=ROOT/'.aeep/workflow-scanner-20261102'; CACHE.mkdir(mode=0o700,exist_ok=True)
FROZEN=ROOT/('.aeep/stack-frozen-source-'+SOURCE[:12])
class Scope(StrictModel):
    role: str
    source: str
    purpose: str='Bounded ordinary CLI scanner engineering; no benchmark or model execution'

def write(name,value):
    path=HERE/name
    if path.exists(): raise ValueError('Preparation output exists: '+str(path))
    data=value.model_dump_json(indent=2) if hasattr(value,'model_dump_json') else json.dumps(value,indent=2)
    path.write_text(data+'\n'); return path

def binding(path): return {'path':str(path),'sha256':file_digest(path)}

def prepare():
    assert shutil.disk_usage(ROOT).free > 50*1024**3+256*1024**2
    # Capture only the established source digest's inputs, preserving previous snapshots.
    FROZEN.mkdir(mode=0o700)
    sources=[ROOT/'pyproject.toml']
    for folder in ('src','tests','integrations/aeep','integrations/assessment-runtime','integrations/managed-worker','scripts'):
        sources.extend((ROOT/folder).rglob('*'))
    files={}
    for original in sources:
        if not original.is_file() or any(p=='__pycache__' or p.endswith('.egg-info') for p in original.parts):continue
        assert not original.is_symlink()
        relative=original.relative_to(ROOT); target=FROZEN/relative
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(original,target)
        files[str(relative)]=file_digest(target)
    assert verification_source_digest(FROZEN)==SOURCE
    write('source-snapshot.json',{'path':str(FROZEN),'source':SOURCE,'files':files})
    manifest=write('cli-manifest.json',Manifest(database=str(CACHE/'canonical.sqlite3'),executors=[]))
    with contextlib.redirect_stdout(io.StringIO()) as output:
        main(['candidate',str(ROOT/'examples/toolkit_offline/format-json'),'--stage',str(CACHE/'candidate'),'--manifest',str(manifest)])
    captured=json.loads(output.getvalue()); write('candidate-inspection.json',captured)
    payload=inspect(CACHE/'candidate')
    runtime=str(Path('/usr/local/bin/docker').resolve())
    worker=FROZEN/'src/aeep_toolkit/scanner_worker.py'
    environment=AssessmentEnvironment(environment_id='reviewed-cisco-cli-20261102',kind='container',
        identity={'scanner_version':'2.2.1','scanner_wheel':'e5e6a3d7f956afccae73c7326e3a1a2d43203a431b7cbd598333f6098b3190e6'},
        container_image='sha256:1cf3c4405db2f9b4721a35e10534f72a6b428fda49b3ee1114ef27d4f8a17eb4',
        container_runtime=runtime,container_socket='/Users/edwintse/.docker/run/docker.sock',network=False)
    grants=[]; requests={}; definitions={}
    with ReceiptStore(CACHE/'canonical.sqlite3') as store:
        repo=AssessmentRepository(store)
        for role in ('scanner','wrapper'):
            recipe=Scope(role=role+'-recipe',source=SOURCE);mapping=Scope(role=role+'-mapping',source=SOURCE)
            env=environment if role=='scanner' else AssessmentEnvironment(environment_id='ordinary-cli-wrapper-20261102',kind='codex_sandbox',identity={})
            refs=[captured['subject_ref'],repo.put('toolkit_engineering_scope',role+'-recipe',recipe),
                  repo.put('environment',env.environment_id,env),repo.put('toolkit_engineering_scope',role+'-mapping',mapping)]
            definitions[role]=refs
            grant=AssessmentAuthorization(authorization_id='workflow-scanner-'+role+'-'+SOURCE[:12],
                subject_digests=[refs[0]],recipe_digests=[refs[1]],environment_digests=[refs[2]],
                limits=AssessmentLimits(max_operations=3 if role=='wrapper' else 1,max_model_turns=0,max_elapsed_seconds=100 if role=='wrapper' else 165),
                allowed_destinations=['local'],expires_at=utc_now()+timedelta(days=7))
            grants.append(grant.model_dump(mode='json'))
            request=RecipeMaterializationRequest(subject_digest=refs[0],recipe_digest=refs[1],environment_digest=refs[2],mapping_digest=refs[3],
                authorization_id=grant.authorization_id,definition_digests=refs,seed=0)
            repo.put('recipe_materialization_request',request.plan_id,request);requests[role]=request
        scan=ScannerRuntimeDefinition(environment=environment,request=requests['scanner'],candidate_sha256=payload.sha256,
            worker_sha256=file_digest(worker),executable_dependencies={runtime:file_digest(Path(runtime)),str(worker):file_digest(worker)})
        write('scanner-runtime.json',scan)
        repo.put('toolkit_scanner_runtime',content_digest(scan),scan)
    # Complete installed dependency inventory; none of these components is installed here.
    artifacts=json.loads((ROOT/'reports/toolkit-v2/c13/workflow-accounting-20261101/scanner-preparation/cached-artifacts.json').read_bytes())['artifacts']
    manifests=[]; scanner=None
    rights='Private offline scan only; preserve exact artifact license notices. No redistribution reviewed.'
    for item in artifacts:
        is_scanner=item['name']=='cisco-ai-skill-scanner'
        expression=item['license_expression'] or item['license'] or 'UNRESOLVED_DECLARATION'
        # Labels are existing package declarations; full notice hashes stay in the original review.
        expression=expression[:200]
        value=ExtensionManifest(extension_id='skill-scanner' if is_scanner else 'scanner-dep.'+item['name'],
            purpose='Retained reviewed offline scanner artifact '+item['name']+' '+item['version'],role='scanner' if is_scanner else 'support',
            source={'repository':item['url'],'revision':item['sha256'] if not is_scanner else scan.source_revision,
                    'artifact_sha256':item['sha256'],'license_expression':expression,'data_rights':rights},
            hosts=('codex',),platforms=('darwin-arm64',),dependencies=(),
            permissions={'network_destinations':[],'filesystem_scope':'workspace','authentication':'none','financial_exposure':'none'},
            disk_bytes=0,memory_bytes=None,install_effects=('Use exact retained image; no install or image change.',),
            rollback='Stop only a verified owned disposable container; preserve all images and volumes.',status='experimental')
        if is_scanner:scanner=value
        else:manifests.append(value)
    assert scanner and len(manifests)==91
    scanner.dependencies=tuple({'extension_id':m.extension_id,'manifest_sha256':manifest_digest(m)} for m in manifests)
    scanner=ExtensionManifest.model_validate(scanner.model_dump(mode='json'));manifests.append(scanner)
    registry=ExtensionRegistry(extensions=tuple(manifests));write('cli-registry.json',registry)
    policy=PreviewPolicy(host='codex',platform='darwin-arm64',allowed_licenses=tuple(sorted({m.source.license_expression for m in manifests})),
        allowed_data_rights=(rights,),allowed_filesystem_scopes=('workspace',),allowed_authentication=('none',),allowed_financial_exposure=('none',),
        free_disk_bytes=shutil.disk_usage(ROOT).free,allow_unknown_memory=True,
        reviewed_dependency_manifests=tuple(manifest_digest(m) for m in manifests));write('cli-policy.json',policy)
    pack=ROOT/'reports/toolkit-v2/c13/full-stack-20261030/skillsbench-pack.json'
    configs={}
    for domain,tasks in [('document-data',['financial-modeling-qa','pdf-excel-diff','sales-pivot-analysis']),
                         ('software-engineering',['spring-boot-jakarta-migration','react-performance-debugging','software-dependency-audit'])]:
        configs[domain]={'evaluator':'managed','candidate':{'path':str(CACHE/'candidate'),'sha256':payload.sha256},
            'benchmark':binding(pack),'asset_root':str(ROOT/'.aeep/skillsbench-stack-9a1f4dd5'),'task_ids':tasks,
            'components':['skill-scanner'],'scanner':binding(HERE/'scanner-runtime.json')}
    workflow=write('cli-workflow.json',{'schema_version':'aeep.toolkit.workflow.v2','registry':binding(HERE/'cli-registry.json'),
        'policy':binding(HERE/'cli-policy.json'),'configurations':configs})
    scope=WorkflowAccountingDefinition(schema_version='aeep.toolkit.workflow-accounting.v3',workflow_sha256=file_digest(workflow),
        configurations=('document-data','software-engineering'),operations=('scan',),source_digest=SOURCE,
        manifest_path=str(manifest),manifest_sha256=file_digest(manifest),request=requests['wrapper'],maximum_overhead_seconds=30)
    write('cli-accounting.json',scope)
    with ReceiptStore(CACHE/'canonical.sqlite3') as store:
        repo=AssessmentRepository(store);repo.put('toolkit_workflow_accounting',content_digest(scope),scope)
    write('cli-authority.json',{'grants':grants,'review_refs':list(dict.fromkeys([r for refs in definitions.values() for r in refs]+[content_digest(scan),content_digest(scope)])),
        'purpose':'Inert pending exact grouped execution approval. No grant or review applied during preparation.'})
    # The frozen CLI will emit a different path-bound digest; use it now for exact review.
    sys.path.insert(0,str(FROZEN/'src'))
    import subprocess
    command=[sys.executable,'-m','aeep_toolkit','workflow','scan','--workflow',str(workflow),'--configuration','document-data']
    env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(FROZEN/'src'),'PYTHONDONTWRITEBYTECODE':'1','LC_ALL':'C'}
    preview=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=30,check=True)
    value=json.loads(preview.stdout);write('cli-preview.json',value)
    assert len(value['installation']['items'])==92
    write('cli-preparation.json',{'passed':True,'source':SOURCE,'frozen':str(FROZEN),'candidate':payload.sha256,
        'preview_sha256':value['review_sha256'],'dependency_artifacts':92,'grants_created':False,'upstream_executed':False,
        'task_execution':False,'stack_completion':False})
    print(json.dumps({'prepared':True,'upstream_executed':False,'source':SOURCE}))

if __name__=='__main__':prepare()
