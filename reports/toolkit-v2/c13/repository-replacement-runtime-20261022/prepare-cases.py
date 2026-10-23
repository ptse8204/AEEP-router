"""Prepare eight source-grounded screening candidates as inert, unadopted data."""
import ast
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import (RepositorySuiteCase,SuiteAsset,SuiteInput,SuiteTruth,
    grade_suite_output,pack_files,patch_artifact)
from aeep.assessment.repository_tasks import RepositoryPatch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PRIOR=HERE.parent/'repository-suite-semantic-fault-20261022'
PRIVATE=ROOT/'.aeep/repository-replacement-runtime-20261022-cases'


def sha(data):return hashlib.sha256(data).hexdigest()


def asset(path):return SuiteAsset(path=str(path.resolve()),sha256=sha(path.read_bytes()),size_bytes=path.stat().st_size)


async def main():
    assert shutil.disk_usage(ROOT).free>50*1024**3+20*1024**2
    PRIVATE.mkdir(exist_ok=False);public=PRIVATE/'public';public.mkdir();protected=PRIVATE/'protected';protected.mkdir()
    spec=importlib.util.spec_from_file_location('reviewed_data_preparation',HERE.parent/'repository-suite-integration-20261022/prepare-development-assets.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    source_records=[]
    for filename in ('source-review.json','audit-source-review.json'):
        source_records+=json.loads((HERE/filename).read_text())['sources']
    sources={item['instance_id']:item for item in source_records}
    pins=json.loads((HERE.parent/'repository-cohort-20261022/wheel-source-review.json').read_text())['pins']
    core_wheels=[asset(ROOT/'.aeep/repository-cohort-20261022/wheels'/item['filename']) for item in pins if item['project'] in ('pytest','iniconfig','packaging','pluggy')]
    assert len(core_wheels)==4
    extras={}
    for filename in ('runtime-wheel-review.json',):
        extras.update({item['project']:asset(ROOT/item['private_cache']) for item in json.loads((HERE.parent/'repository-suite-integration-20261022'/filename).read_text())})
    for item in pins:
        if item['project'] not in ('pytest','iniconfig','packaging','pluggy'):
            extras[item['project']]=asset(ROOT/'.aeep/repository-cohort-20261022/wheels'/item['filename'])
    entries=[
      ('AbsaOSS__generate-release-notes-207','release_notes_generator/','Apache-2.0',[],False),
      ('iluvcapra__pycmx-12','pycmx/','MIT',[],True),
    ]
    cases=[];summary=[];staged=[];errors=[]
    for identity,prefix,license_name,extra_names,audit_control in entries:
      try:
        review=sources[identity];assert review['status']=='STATIC_REVIEW_REQUIRED'
        directory=ROOT/review['private_cache'];row=json.loads((directory/'row.json').read_text())
        raw=(directory/'source.tar.gz').read_bytes();assert sha(raw)==review['archive_sha256']
        files,_=helper.normalize(raw)
        licenses=[files[item['file']].decode(errors='replace') for item in review['licenses']]
        joined='\n'.join(licenses)
        if license_name=='MIT':assert 'Permission is hereby granted' in joined and 'AS IS' in joined
        elif license_name=='BSD-3-Clause':assert 'Redistribution and use' in joined and ('endorse' in joined or 'contributors' in joined)
        else:assert 'Apache License' in joined and 'Version 2.0' in joined
        editable=sorted(name for name in files if name.startswith(prefix) and name.endswith('.py') and 'tests' not in Path(name).parts)
        assert editable and len(editable)<=256
        with tempfile.TemporaryDirectory(prefix='aeep-curation-data-',dir='/private/tmp') as temporary:
            work=Path(temporary).resolve()
            for name,data in files.items():
                path=work/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            helper.apply(work,row['test_patch'],work.parent)
            after_test={path.relative_to(work).as_posix():path.read_bytes() for path in work.rglob('*') if path.is_file()}
            assert files.keys()<=after_test.keys()
            overlay={name:data for name,data in after_test.items() if files.get(name)!=data}
            assert overlay and all(name.startswith('tests/') for name in overlay)
            helper.apply(work,row['patch'],work.parent)
            fixed={path.relative_to(work).as_posix():path.read_bytes() for path in work.rglob('*') if path.is_file()}
            assert after_test.keys()==fixed.keys()
            all_changes={name for name,data in fixed.items() if after_test[name]!=data}
            omitted=sorted(all_changes-set(editable))
            reviewed_omissions={'spulec__freezegun-582':{'CHANGELOG'},'jsonpickle__jsonpickle-587':{'.gitignore','.pre-commit-config.yaml','CHANGES.rst','README.rst','pyproject.toml'}}
            assert all(name.endswith(('.md','.rst','.txt')) or name in reviewed_omissions.get(identity,set()) for name in omitted), 'Unreviewed non-source gold changes'
            if identity=='jsonpickle__jsonpickle-587':
                import tomllib
                before_config=tomllib.loads(after_test['pyproject.toml'].decode());after_config=tomllib.loads(fixed['pyproject.toml'].decode())
                before_config.get('tool',{}).pop('ruff',None);after_config.get('tool',{}).pop('ruff',None)
                assert before_config==after_config, 'Gold config changes exceed reviewed Ruff-only omission'
            changes={name:fixed[name].decode('utf-8') for name in all_changes if name in editable};assert changes
        public_files=dict(files)
        if audit_control:public_files.update({name:text.encode() for name,text in changes.items()})
        source=pack_files(public_files)
        source_path=public/(sha(source)+'.tar.gz');source_path.write_bytes(source)
        contract=row['problem_statement']+('\n\n'+row['interface'] if row.get('interface') else '')
        family='multi-file-repair' if len(changes)>1 else 'single-file-repair'
        if audit_control:
            family='contract-audit'
            contract=('Audit the provided current source against the behavior contract described by the issue report below. Change source only if that contract is violated. If it already holds, return an empty patch and preserve the source bytes.\n\n'+contract)
        contract+='\n\nAEEP scope: listed Python source only. Preserve public behavior; documentation, packaging and new/deleted files are outside this adaptation.'
        case_id=identity+('-aeep-contract-audit' if audit_control else '')
        value=SuiteInput(task_id=case_id,task=contract,family=family,source_sha256=sha(source),editable_paths=editable)
        binding=content_digest(value)
        reference=patch_artifact(RepositoryPatch(base_sha256=binding,files={} if audit_control else changes))
        negative=patch_artifact(RepositoryPatch(base_sha256=binding,files={name:files[name].decode() for name in changes} if audit_control else {}))
        counterexample=negative if audit_control else patch_artifact(RepositoryPatch(base_sha256=binding,files={sorted(changes)[0]:files[sorted(changes)[0]].decode()}))
        f2p=[] if audit_control else row['FAIL_TO_PASS']
        p2p=row['FAIL_TO_PASS']+row['PASS_TO_PASS'] if audit_control else row['PASS_TO_PASS']
        test_paths=sorted({name.split('::')[0] for name in row['FAIL_TO_PASS']+row['PASS_TO_PASS']})
        if audit_control:
            hashes={name:sha(public_files[name]) for name in editable}
            guard=('import hashlib\nfrom pathlib import Path\n\ndef test_snapshot_preserved():\n'
                +'    root=Path(__file__).resolve().parents[1]\n'
                +'    expected='+repr(hashes)+'\n'
                +'    assert all(hashlib.sha256((root/name).read_bytes()).hexdigest()==value for name,value in expected.items())\n')
            ast.parse(guard)
            guard_path='tests/test_aeep_preservation.py';assert guard_path not in files and guard_path not in overlay
            overlay[guard_path]=guard.encode();test_paths.append(guard_path);p2p=[*p2p,guard_path+'::test_snapshot_preserved']
        tests_path=protected/(case_id+'-tests.tar.gz');tests_path.write_bytes(pack_files(overlay))
        ref_path=protected/(case_id+'-reference.json');ref_path.write_text(json.dumps(reference,separators=(',',':')))
        truth=SuiteTruth(input_sha256=binding,source=asset(source_path),tests=asset(tests_path),wheels=[*core_wheels,*(extras[n] for n in extra_names)],python='3.13',pytest='8.3.5',test_paths=test_paths,fail_to_pass=f2p,pass_to_pass=p2p)
        case=RepositorySuiteCase(input=value,truth=truth,reference=asset(ref_path),fault_outputs=[counterexample],source_repository='https://github.com/'+row['repo'],source_revision=row['base_commit'],independent_case_id=case_id,license='Source: '+license_name+'; issue data: CC-BY-4.0',origin_kind='authored_control' if audit_control else 'upstream_issue',split='qualification',used_for_development=False,
            provenance='Provisional screening curation only; not adopted or frozen. Base '+row['base_commit']+'; Codeload SHA256 '+sha(raw)+'. Source prefix '+prefix+'. '+('Starting snapshot includes the published Python repair (patch SHA256 '+sha(row['patch'].encode())+'); this is an authored audit, not the unmodified upstream issue. Empty patch is correct under a byte-preservation contract; original bug source is its negative. Original test assertions remain, plus an explicitly authored snapshot-preservation test. ' if audit_control else 'Published Python repair is the reference; original source is the negative. A nonempty original-source counterexample maps to the same tested filesystem as the empty baseline and is not a separate observation. ')+
                'No source/test/installer executed during preparation. Declared Python'+row['install_config']['python']+' adapted to3.13 /pytest8.3.5; explicit pure wheels, no project install or optional plugin autoload. Non-source published edits omitted: '+repr(omitted)+'. Licensing and source bounds reviewed; runtime reproduction remains required. These sources have not been used to change the grader.')
        cases.append(case)
        summary.append({'id':case_id,'original_issue_id':identity,'repository':row['repo'],'source_revision':row['base_commit'],'origin_kind':case.origin_kind,'family':family,'declared_python':row['install_config']['python'],'adapted_python':'3.13','source_sha256':value.source_sha256,'source_bytes':len(source),'editable_paths':len(editable),'reference_changes':sorted(changes),'omitted_non_source_edits':omitted,'required_bug_tests':len(f2p),'preservation_tests':len(p2p),'wheels':len(truth.wheels),'license':license_name,'license_records':review['licenses'],'adopted':False,'stage_assignment_frozen':False})
        class Captured(Exception):pass
        for label,output in [('reference',reference),('counterexample',negative)]:
            async def capture(payload):
                path=protected/(case_id+'-'+label+'-payload.json');path.write_text(json.dumps(payload,separators=(',',':')))
                staged.append({'case':case_id,'variant':label,'payload':str(path.relative_to(ROOT)),'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size,'artifact':output})
                raise Captured()
            try:await grade_suite_output(value.model_dump(mode='json'),truth.model_dump(mode='json'),output,capture)
            except Captured:pass
            else:raise AssertionError('Preparation returned a grade')
      except Exception as exc:
        errors.append({'id':identity,'error_type':type(exc).__name__,'error':str(exc)[:250],'phase':'Inert source/test/license/scope preparation; no external execution'})
    cases_path=protected/'cases.json';cases_path.write_text(json.dumps([case.model_dump(mode='json') for case in cases],indent=2)+'\n')
    (protected/'variants.json').write_text(json.dumps(staged,indent=2)+'\n')
    result={'prepared_cases':len(cases),'cases':summary,'errors':errors,'payloads':[{k:v for k,v in item.items() if k!='artifact'} for item in staged],'cases_file':str(cases_path.relative_to(ROOT)),'cases_file_sha256':sha(cases_path.read_bytes()),'variants_file':str((protected/'variants.json').relative_to(ROOT)),'cases_adopted':0,'frozen_holdouts':0,'external_code_executed':False,'model_turns':0,'containers_started':0,'candidate_grades_returned':0,'independence':'Two replacement candidates from different repositories. All four earlier development repositories and all eight earlier screening repositories excluded. No final stage freeze or model outcome selection.'}
    (HERE/'prepared-cases.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'prepared_cases':len(cases),'payloads':len(staged),'errors':errors,'external_code_executed':False}))


if __name__=='__main__':asyncio.run(main())
