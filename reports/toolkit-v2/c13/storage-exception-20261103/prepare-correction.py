"""Prepare bounded current-source artifacts; do not approve or execute them."""
from __future__ import annotations
import hashlib,json,shutil,subprocess,sys,zipfile
from datetime import UTC,datetime,timedelta
from pathlib import Path
from aeep.assessment.models import AssessmentAuthorization,AssessmentBudgetAmendment,AssessmentLimits,AssessmentScopeAmendment,RecipeMaterializationRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import StrictModel
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import RuntimeInstallation,check_closure,digest,file_digest,prepare
from aeep_toolkit.installation import PreviewPolicy,manifest_digest,preview
from aeep_toolkit.models import ExtensionManifest,ExtensionRegistry
from aeep_toolkit.storage import StorageReserveException
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_security import ScannerRuntimeDefinition

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
OLD=HERE.parent/'workflow-scanner-20261102'
SOURCE=verification_source_digest(ROOT)

class Scope(StrictModel):
    role:str
    source:str
    purpose:str='Bounded ordinary CLI scanner engineering; no benchmark or model execution'

def write(name,value):
    data=value.model_dump_json(indent=2) if hasattr(value,'model_dump_json') else json.dumps(value,indent=2)
    if (HERE/name).exists():
        assert (HERE/name).read_text()==data+'\n','Preserve different preparation output: '+name
    else:
        with (HERE/name).open('x') as stream:stream.write(data+'\n')
    return HERE/name

def binding(path):return {'path':str(path),'sha256':file_digest(path)}

def main():
    checks=json.loads((HERE/'preparation/checks.json').read_bytes())
    assert checks['source_before']==checks['source_after']==SOURCE
    assert len(checks['checks'])==6 and all(c['exit_code']==0 for c in checks['checks'])
    assert shutil.disk_usage(ROOT).free>42*1024**3+1024**3
    frozen=ROOT/('.aeep/stack-frozen-source-'+SOURCE[:12]);frozen.mkdir(mode=0o700,exist_ok=True)
    originals=[ROOT/'pyproject.toml']
    for folder in ('src','tests','integrations/aeep','integrations/assessment-runtime','integrations/managed-worker','scripts'):
        originals.extend((ROOT/folder).rglob('*'))
    files={}
    for path in sorted(originals):
        if not path.is_file() or any(p=='__pycache__' or p.endswith('.egg-info') for p in path.parts):continue
        assert not path.is_symlink()
        relative=path.relative_to(ROOT);target=frozen/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert file_digest(target)==file_digest(path)
        else:shutil.copyfile(path,target)
        files[str(relative)]=file_digest(target)
    assert verification_source_digest(frozen)==SOURCE
    write('source-snapshot.json',{'source':SOURCE,'path':str(frozen),'files':files})
    old=RuntimeInstallation.model_validate_json((OLD/'package-installation.json').read_bytes())
    wheel=next((HERE/'preparation/dist').glob('*.whl'))
    cache=ROOT/'.aeep/storage-exception-20261103';cache.mkdir(mode=0o700,exist_ok=True)
    wheelhouse=cache/'package-wheels';wheelhouse.mkdir(mode=0o700,exist_ok=True)
    metadata={i.manifest.extension_id:i.manifest for i in old.preview.items};wheels=[]
    groups={'aeep':{},'aeep_toolkit':{},'integrations':{}}
    with zipfile.ZipFile(wheel) as archive:
        for path in (ROOT/'src').rglob('*.py'):
            if '__pycache__' not in path.parts and not any(p.endswith('.egg-info') for p in path.parts):
                assert archive.read(path.relative_to(ROOT/'src').as_posix())==path.read_bytes()
        for name in archive.namelist():
            if name.endswith('/') or '__pycache__' in name.split('/'):continue
            for label in ('aeep','aeep_toolkit'):
                if name.startswith(label+'/'):groups[label][name.removeprefix(label+'/')]=archive.read(name)
            prefix='aeep_agent_router-0.8.2.data/data/share/aeep/integrations/'
            if name.startswith(prefix):groups['integrations'][name.removeprefix(prefix)]=archive.read(name)
        expanded=sum(i.file_size for i in archive.infolist())+wheel.stat().st_size
    installed=hashlib.sha256(b'aeep.installed-source.v1\0')
    for label,entries in sorted(groups.items()):
        assert entries
        for name,data in sorted(entries.items()):
            installed.update((label+'/'+name).encode()+b'\0');installed.update(hashlib.sha256(data).digest())
    for original in old.wheels:
        source=wheel if original.extension_id=='aeep-agent-router' else Path(old.wheelhouse)/original.filename
        expected=file_digest(source)
        assert original.extension_id=='aeep-agent-router' or expected==original.sha256
        target=wheelhouse/original.filename
        if target.exists():assert file_digest(target)==expected
        else:shutil.copyfile(source,target)
        wheels.append(original.model_copy(update={'sha256':expected}))
    item=metadata['aeep-agent-router'].model_dump(mode='json')
    item['source']['artifact_sha256']=file_digest(wheel);item['source']['revision']=SOURCE;item['disk_bytes']=expanded
    metadata['aeep-agent-router']=ExtensionManifest.model_validate(item)
    registry=ExtensionRegistry(extensions=tuple(metadata.values()))
    if (HERE/'package-installation.json').exists():
        plan=RuntimeInstallation.model_validate_json((HERE/'package-installation.json').read_bytes())
        assert plan.wheels==tuple(wheels) and plan.storage_exception is not None
    else:
        policy=PreviewPolicy.model_validate(old.policy.model_dump(mode='json')|{
            'free_disk_bytes':shutil.disk_usage(ROOT).free,
            'reviewed_dependency_manifests':tuple(manifest_digest(m) for m in metadata.values())})
        destination=cache/'installed-runtime';issued=datetime.now(UTC)
        exception=StorageReserveException(exception_id='scanner-correction-20261103',destination=str(destination),
            filesystem_device=cache.stat().st_dev,wheel_set_sha256=digest([w.model_dump(mode='json') for w in wheels]),
            minimum_free_bytes=42*1024**3,maximum_additional_bytes=1024**3,
            issued_at=issued,expires_at=issued+timedelta(hours=24))
        proposed=preview(registry,('aeep-agent-router',),policy,profile='essentials')
        plan=prepare(proposed,policy,destination,wheelhouse,tuple(wheels),storage_exception=exception)
        write('package-installation.json',plan);write('storage-exception.json',exception)
        write('package-preparation.json',{'source':SOURCE,'installed_source':installed.hexdigest(),
            'installation_digest':digest(plan),'wheels':33,'unchanged_dependencies':32,
            'required_bytes':max(plan.preview.known_disk_bytes,500*1024**2+check_closure(wheelhouse,plan.wheels,policy.platform)),
            'actual_free_bytes':shutil.disk_usage(ROOT).free,'executed':False})
    work=HERE/'package-execution/work';runtime=Path(plan.destination)
    profile='(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (literal "/dev/null"))\n'
    profile+='(allow file-write* (subpath '+json.dumps(str(work))+'))\n'
    profile+='(deny file-read* (subpath '+json.dumps(str(Path.home().resolve()))+'))\n'
    for path in (runtime,work):profile+='(allow file-read* (subpath '+json.dumps(str(path))+'))\n'
    profile+='(allow file-read-metadata '+' '.join('(literal '+json.dumps(str(p))+')' for p in dict.fromkeys((*runtime.parents,*work.parents)) if p.is_relative_to(Path.home()))+')\n'
    if (HERE/'package.sb').exists():assert (HERE/'package.sb').read_text()==profile
    else:
        with (HERE/'package.sb').open('x') as stream:stream.write(profile)
    authority=json.loads((OLD/'cli-authority.json').read_bytes())
    database=Path(json.loads((OLD/'cli-manifest.json').read_bytes())['database'])
    manifest=write('cli-manifest.json',{'database':str(database),'executors':[]})
    definitions={};requests={};amendments=[];baseline={};role_refs={}
    with ReceiptStore(database) as store:
        repo=AssessmentRepository(store)
        for root_grant,role in zip(authority['grants'],('scanner','wrapper'),strict=True):
            grant=repo.effective_grant(root_grant['authorization_id'])
            assert content_digest(repo.get('authorization',grant.authorization_id))==content_digest(AssessmentAuthorization.model_validate(root_grant))
            row=store._connection.execute('SELECT revoked,operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone()
            assert row and row[0]==0
            baseline[grant.authorization_id]={'revoked':row[0],'operations':row[1],'model_turns':row[2],'elapsed_seconds':row[3],'cash_usd':row[4]}
            if role=='scanner':assert row[1]==1
            else:assert row[1]==0
            unresolved=store._connection.execute("SELECT count(*) FROM assessment_operations WHERE grant_id=? AND state='reserved'",(grant.authorization_id,)).fetchone()[0]
            assert unresolved==0
            env=repo.get('environment',grant.environment_digests[0]);subject=repo.get('subject',grant.subject_digests[0])
            recipe=Scope(role=role+'-recipe',source=SOURCE);mapping=Scope(role=role+'-mapping',source=SOURCE)
            refs=[content_digest(subject),repo.put('toolkit_engineering_scope',SOURCE[:12]+'-'+role+'-recipe',recipe),
                  content_digest(env),repo.put('toolkit_engineering_scope',SOURCE[:12]+'-'+role+'-mapping',mapping)]
            for value in (subject,recipe,env,mapping):definitions[content_digest(value)]=value.model_dump(mode='json') if hasattr(value,'model_dump') else value
            request=RecipeMaterializationRequest(subject_digest=refs[0],recipe_digest=refs[1],environment_digest=refs[2],
                mapping_digest=refs[3],authorization_id=grant.authorization_id,definition_digests=refs,seed=0)
            repo.put('recipe_materialization_request',request.plan_id,request)
            definitions[content_digest(request)]=request.model_dump(mode='json');requests[role]=request;role_refs[role]=refs
        old_runtime=ScannerRuntimeDefinition.model_validate_json((OLD/'scanner-runtime.json').read_bytes())
        worker=frozen/'src/aeep_toolkit/scanner_worker.py'
        scan=ScannerRuntimeDefinition.model_validate(old_runtime.model_dump(mode='json')|{
            'request':requests['scanner'].model_dump(mode='json'),
            'executable_dependencies':{str(old_runtime.environment.container_runtime):old_runtime.executable_dependencies[str(old_runtime.environment.container_runtime)],str(worker):file_digest(worker)}})
        repo.put('toolkit_scanner_runtime',content_digest(scan),scan);definitions[content_digest(scan)]=scan.model_dump(mode='json')
        write('scanner-runtime.json',scan)
        workflow=json.loads((OLD/'cli-workflow.json').read_bytes())
        for config in workflow['configurations'].values():config['scanner']=binding(HERE/'scanner-runtime.json')
        workflow_file=write('cli-workflow.json',workflow)
        accounting=WorkflowAccountingDefinition(schema_version='aeep.toolkit.workflow-accounting.v3',workflow_sha256=file_digest(workflow_file),
            configurations=('document-data','software-engineering'),operations=('scan',),source_digest=SOURCE,
            manifest_path=str(manifest),manifest_sha256=file_digest(manifest),request=requests['wrapper'],maximum_overhead_seconds=30)
        repo.put('toolkit_workflow_accounting',content_digest(accounting),accounting);definitions[content_digest(accounting)]=accounting.model_dump(mode='json')
        write('cli-accounting.json',accounting)
        for original,role in zip(authority['grants'],('scanner','wrapper'),strict=True):
            refs=role_refs[role]
            amendments.append(AssessmentScopeAmendment(authorization_id=original['authorization_id'],authorization_digest=content_digest(AssessmentAuthorization.model_validate(original)),
                subject_digests=[refs[0]],recipe_digests=[refs[1]],environment_digests=[refs[2]],reviewed_digests=list(definitions)))
        original=authority['grants'][0]
        latest=store._connection.execute("SELECT digest FROM assessment_records WHERE kind='budget_amendment' AND json_extract(payload_json,'$.authorization_id')=? ORDER BY rowid DESC LIMIT 1",(original['authorization_id'],)).fetchone()
        budget=AssessmentBudgetAmendment(authorization_id=original['authorization_id'],authorization_digest=content_digest(AssessmentAuthorization.model_validate(original)),
            previous_amendment_digest=latest[0] if latest else None,limits=AssessmentLimits(max_operations=3,max_model_turns=0,max_elapsed_seconds=240),expires_at=original['expires_at'])
    write('cli-authority.json',{'definitions':definitions,'scope_amendments':[a.model_dump(mode='json') for a in amendments],
        'budget_amendment':budget.model_dump(mode='json'),'baseline':baseline,'original_grants':authority['grants'],
        'previous_scanner_plan_id':old_runtime.request.plan_id,'authority_applied':False,'existing_counters_reset':False})
    env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(frozen/'src'),'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','LC_ALL':'C'}
    result=subprocess.run([sys.executable,'-m','aeep_toolkit','workflow','scan','--workflow',str(workflow_file),'--configuration','document-data'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=30,check=True)
    write('cli-preview.json',json.loads(result.stdout))
    protocol=frozen/'src/aeep/assessment/container_worker.py'
    write('bootstrap-input.json',{'protocol_file':str(protocol),'protocol_sha256':file_digest(protocol)})
    print(json.dumps({'prepared':True,'source':SOURCE,'authority_applied':False,'runtime_executed':False,'baseline':baseline}))

if __name__=='__main__':main()
