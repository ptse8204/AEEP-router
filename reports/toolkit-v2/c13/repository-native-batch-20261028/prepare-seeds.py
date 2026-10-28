"""Prepare three cached native-scope subjects; no downloads or subject execution."""
import ast
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteAsset, SuiteAssetV5, SuiteInput, SuiteTruthV6, _decode_suite_patch, archive_files, compressed_patch_artifact, grade_suite_output, pack_files
from aeep.assessment.repository_tasks import RepositoryPatch

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
OUT=ROOT/'.aeep/repository-native-batch-20261028-v2'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def asset(p,large=False):return (SuiteAssetV5 if large else SuiteAsset)(path=str(p.resolve()),sha256=sha(p),size_bytes=p.stat().st_size)
def save(p,v):
    with p.open('x') as stream:json.dump(v,stream,indent=2);stream.write('\n')

async def payload(case,artifact):
    captured=[]
    class Captured(Exception):pass
    async def probe(v):captured.append(v);raise Captured()
    try:await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),artifact,probe)
    except Captured:pass
    else:raise AssertionError('Inert preparation returned a grade')
    assert len(captured)==1;return captured[0]

async def main():
    assert shutil.disk_usage(ROOT).free>51*1024**3;OUT.mkdir(exist_ok=False)
    helper=load('aeep_existing_inert_patch_helper',HERE.parent/'repository-suite-integration-20261022/prepare-development-assets.py')
    rooted=load('aeep_existing_selector_helper',HERE.parent/'repository-test-roots-20261027/prepare-rooted-cases.py')
    base=json.loads((HERE.parent/'repository-replacement-runtime-20261022/runtime-wheel-review.json').read_text())['pins']
    core=[asset(ROOT/p['private_cache']) for p in base if p['project'] in {'pytest','iniconfig','packaging','pluggy'}];assert len(core)==4
    identify_review=json.loads((HERE.parent/'repository-workload-batch-20261022/runtime-support-review.json').read_text())
    identify=next(p for p in identify_review['pins'] if p['project']=='identify')
    assert identify['version']=='2.6.15' and sha(ROOT/identify['private_cache'])==identify['sha256']
    descriptions=[];cases=[];records=[]
    entries=[('asottile__dead-204',ROOT/'.aeep/repository-workload-batch-20261022-sources/asottile__dead-204',False),
             ('nhairs__python-json-logger-39',ROOT/'.aeep/repository-corpus-expansion-20261022-sources/nhairs__python-json-logger-39',False)]
    for identity,directory,audit in entries:
        row=json.loads((directory/'row.json').read_text());raw=(directory/'source.tar.gz').read_bytes()
        scope=None
        if identity=='nhairs__python-json-logger-39':
            scope=next(x for x in json.loads((HERE.parent/'repository-corpus-expansion-20261022/source-scope-review.json').read_text())['sources'] if x['instance_id']==identity)
            p=ROOT/scope['private_cache']/'source-only.tar.gz';assert sha(p)==scope['normalized_archive_sha256'] and hashlib.sha256(raw).hexdigest()==scope['full_archive_sha256'];files=archive_files(p.read_bytes())
        else:files,_=helper.normalize(raw)
        licenses={n:b for n,b in files.items() if '/' not in n and n.upper().startswith(('LICENSE','COPYING','NOTICE'))};assert licenses
        license_records=[]
        for n,b in licenses.items():
            p=HERE/'licenses'/identity/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b);license_records.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':len(b)})
        with tempfile.TemporaryDirectory(prefix='aeep-INERT-native-seed-',dir='/private/tmp') as temporary:
            work=Path(temporary).resolve()
            for n,b in files.items():p=work/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
            helper.apply(work,row['test_patch'],work.parent)
            tested={p.relative_to(work).as_posix():p.read_bytes() for p in work.rglob('*') if p.is_file()}
            assert set(files)<=tested.keys();overlay={n:b for n,b in tested.items() if files.get(n)!=b}
            required=row['FAIL_TO_PASS']+row['PASS_TO_PASS'];assert len(required)==len(set(required))
            roots={n.split('::')[0].split('/')[0] for n in required};assert roots=={'tests'}
            assert overlay and all(n.startswith('tests/') for n in overlay)
            selected=[];omitted=[]
            for section in row['patch'].split('diff --git ')[1:]:
                n=section.splitlines()[0].split()[0].removeprefix('a/')
                if n.endswith('.py') and n in tested and not set(Path(n).parts)&{'test','tests','testing'} and Path(n).name not in {'setup.py','conftest.py'}:selected.append('diff --git '+section)
                else:assert n.endswith(('.md','.rst','.txt')),n;omitted.append(n)
            helper.apply(work,''.join(selected),work.parent)
            fixed={p.relative_to(work).as_posix():p.read_bytes() for p in work.rglob('*') if p.is_file()};assert fixed.keys()==tested.keys()
        changed=sorted(n for n,b in fixed.items() if tested[n]!=b);bodies=[n for n in changed if rooted.executable(tested[n])!=rooted.executable(fixed[n])]
        assert len(changed)==len(bodies)==1
        source=pack_files(files,large=True);case_id=identity+'-native-expanded-scope';folder=OUT/case_id;folder.mkdir()
        src=folder/(hashlib.sha256(source).hexdigest()+'.tar.gz');src.write_bytes(source)
        top=Path(changed[0]).parts[0]
        editable=sorted(n for n in files if n==changed[0] or n.startswith(top+'/') and n.endswith('.py') and not set(Path(n).parts)&{'test','tests','testing'} and Path(n).name!='conftest.py')
        contract=row['problem_statement']+('\n\n'+row['interface'] if row.get('interface') else '')
        contract+='\n\nScope:listed existing Python source only. Preserve unrelated behavior. Packaging,new/deleted files and external services are outside this task.'
        task=SuiteInput(task_id=case_id,task=contract,family='single-file-repair',source_sha256=sha(src),editable_paths=editable);binding=content_digest(task)
        changes={n:fixed[n].decode() for n in changed};reference=compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files=changes));negative=compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files={}))
        faults=[compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files={n:files[n].decode() for n in changed}))]
        overlay['tests/conftest.py']=rooted.select_nodes(overlay.get('tests/conftest.py',files.get('tests/conftest.py',b'')).decode(),required)
        tests=folder/'tests.tar.gz';tests.write_bytes(pack_files(overlay,large=True));ref=folder/'reference-artifact.json';ref.write_text(json.dumps(reference,separators=(',',':')))
        wheels=[*core,*([asset(ROOT/identify['private_cache'])] if identity.startswith('asottile') else [])]
        truth=SuiteTruthV6(input_sha256=binding,source=asset(src,True),tests=asset(tests,True),wheels=wheels,python='3.13',pytest='8.3.5',test_paths=sorted({n.split('::')[0] for n in required}),fail_to_pass=row['FAIL_TO_PASS'],pass_to_pass=row['PASS_TO_PASS'],pytest_plugins=[],patch_encoding='gzip-json',test_roots=['tests'],archive_profile='repository-v1',identity_format='pytest-native-v1')
        case=RepositorySuiteCase(schema_version='assessment.repository-suite-case.v6',input=task,truth=truth,reference=asset(ref),fault_outputs=faults,source_repository='https://github.com/'+row['repo'],source_revision=row['base_commit'],independent_case_id=case_id,license='Retained upstream license texts;dataset metadata CC-BY-4.0.',provenance='New authored exhaustive native-name scope over a pinned public upstream repair. Original aliases remain seed metadata until collection-derived full names are frozen before body trials. All original upstream assertions retained;no official benchmark/runtime-equivalence or model-value claim.',origin_kind='authored_control',split='qualification',used_for_development=False)
        cases.append(case);records.append({'case_id':case_id,'original_issue_id':identity,'audit':False,'source_cache':str(directory.relative_to(ROOT)),'archive_sha256':hashlib.sha256(raw).hexdigest(),'row_sha256':sha(directory/'row.json'),'source_body_files':bodies,'omitted_reference_documentation':omitted,'source_scope':scope,'license_records':license_records,'upstream_bug_aliases':row['FAIL_TO_PASS'],'upstream_preservation_aliases':row['PASS_TO_PASS'],'reference':reference,'counterexample':negative})
        descriptions.append({'case_id':case_id,'required_aliases':len(required),'family':task.family,'source_bytes':len(source),'source_revision':row['base_commit'],'pure_private_wheels':len(wheels),'actual_collection_or_body_trials':False})
    # Reuse the complete existing Sopel audit seed without changing its assertions.
    old_meta=json.loads((HERE.parent/'repository-test-roots-20261027/prepared-cases.json').read_text())
    old=RepositorySuiteCase.model_validate(next(c for c in json.loads((ROOT/old_meta['cases_file']).read_text()) if 'sopel-irc__sopel-2653' in c['input']['task_id']))
    data=old.model_dump(mode='json');data['schema_version']='assessment.repository-suite-case.v6';data['input']['task_id']='sopel-irc__sopel-2653-native-expanded-audit';binding=content_digest(data['input']);case_id=data['input']['task_id'];folder=OUT/case_id;folder.mkdir()
    data['truth'].update(identity_format='pytest-native-v1',archive_profile='repository-v1',input_sha256=binding)
    reference=compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files=_decode_suite_patch(old.truth,json.loads(old.reference.read())).files));ref=folder/'reference-artifact.json';ref.write_text(json.dumps(reference,separators=(',',':')));data['reference']=asset(ref).model_dump(mode='json')
    data['fault_outputs']=[compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files=_decode_suite_patch(old.truth,v).files)) for v in old.fault_outputs]
    data.update(independent_case_id=case_id,origin_kind='authored_control');data['provenance']+=' New exhaustive native-name scope;original aliases and old record retained;all assertions/source/repair bytes stay.'
    case=RepositorySuiteCase.model_validate(data);cases.append(case)
    original_dir=ROOT/'.aeep/repository-test-root-sources-20261027/sopel-irc__sopel-2653';row=json.loads((original_dir/'row.json').read_text())
    variants=json.loads((ROOT/old_meta['variants_file']).read_text());negative_old=next(v['artifact'] for v in variants if v['case']==old.input.task_id and v['variant']=='counterexample')
    negative=compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files=_decode_suite_patch(old.truth,negative_old).files))
    records.append({'case_id':case_id,'original_issue_id':row['instance_id'],'audit':True,'source_cache':str(original_dir.relative_to(ROOT)),'archive_sha256':sha(original_dir/'source.tar.gz'),'row_sha256':sha(original_dir/'row.json'),'source_body_files':['sopel/bot.py'],'upstream_bug_aliases':row['FAIL_TO_PASS'],'upstream_preservation_aliases':row['PASS_TO_PASS'],'snapshot_guard':'test/test_aeep_preservation.py::test_snapshot_preserved','reference':reference,'counterexample':negative,'parent_case':old.model_dump(mode='json')})
    descriptions.append({'case_id':case_id,'required_aliases':len(case.truth.fail_to_pass+case.truth.pass_to_pass),'family':case.input.family,'source_bytes':case.truth.source.size_bytes,'source_revision':row['base_commit'],'pure_private_wheels':len(case.truth.wheels),'actual_collection_or_body_trials':False})
    collections=[]
    for case,record in zip(cases,records,strict=True):
        value=await payload(case,record['reference']);value['collect_only']=True;p=OUT/(case.input.task_id+'-collection.json');p.write_text(json.dumps(value,separators=(',',':')))
        collections.append({'case_id':case.input.task_id,'payload':str(p.relative_to(ROOT)),'sha256':sha(p),'archive_sha256':value['archive_sha256']})
    save(OUT/'seeds.json',[c.model_dump(mode='json') for c in cases]);save(OUT/'records.json',records)
    save(HERE/'prepared-seeds.json',{'cases_file':str((OUT/'seeds.json').relative_to(ROOT)),'cases_file_sha256':sha(OUT/'seeds.json'),'records_file':str((OUT/'records.json').relative_to(ROOT)),'records_sha256':sha(OUT/'records.json'),'collections':collections,'cases':descriptions,'portable_identify':identify,'derived_scope_policy':'Exhaustive exact/first-token parameter aliases;disjoint complete groups only;all matched tests required. Freeze full data and payloads before any body call.','actual_external_execution_models_downloads_or_installs':0,'adopted_cases':0})
    print(json.dumps({'prepared_subjects':len(cases),'source_caches_only':True,'collections':len(collections),'actual_execution':False,'cases':descriptions}))

if __name__=='__main__':asyncio.run(main())
