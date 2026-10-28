"""Freeze native identity mappings from source literals before any collection run."""
import ast
import asyncio
import base64
import copy
import hashlib
import json
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase,SuiteAsset,SuiteAssetV5,archive_files,pack_files,_decode_suite_patch,compressed_patch_artifact,grade_suite_output
from aeep.assessment.repository_tasks import RepositoryPatch

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'repository-pymdown-portable-20261028'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def asset(p,large=False):return (SuiteAssetV5 if large else SuiteAsset)(path=str(p.resolve()),sha256=sha(p),size_bytes=p.stat().st_size)

async def payload(case,artifact,path):
    class Captured(Exception):pass
    captured=[]
    async def capture(value):
        captured.append(value);path.write_text(json.dumps(value,separators=(',',':')));raise Captured()
    try:await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),artifact,capture)
    except Captured:pass
    else:raise AssertionError('Inert preparation returned a grade')
    assert len(captured)==1
    return captured[0]

async def main():
    assert json.loads((BASE/'provisional-pool.json').read_text())['case_count']==62
    oldmeta=HERE.parent/'repository-test-roots-20261027/prepared-cases.json';meta=json.loads(oldmeta.read_text())
    original=RepositorySuiteCase.model_validate(next(c for c in json.loads((ROOT/meta['cases_file']).read_text()) if 'icalendar-880' in c['input']['task_id']))
    source=archive_files(original.truth.source.read(),large=True);test_path='src/icalendar/tests/test_issue_662_component_properties.py'
    tree=ast.parse(source[test_path]);function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='test_invalid_event')
    decorators={str(ast.literal_eval(d.args[0])):d for d in function.decorator_list if isinstance(d,ast.Call)}
    pairs=decorators[str(('invalid_component','message'))].args[1];attrs=ast.literal_eval(decorators['attr'].args[1])
    assert isinstance(pairs,ast.List) and len(pairs.elts)==8 and attrs==['start','end']
    required=original.truth.fail_to_pass+original.truth.pass_to_pass;mapping={n:n for n in required};repairs=[]
    stem=test_path+'::test_invalid_event'
    for attr in attrs:
        for index,row in enumerate(pairs.elts):
            assert isinstance(row,ast.Tuple) and isinstance(row.elts[0],ast.Name)
            message=ast.literal_eval(row.elts[1]);assert isinstance(message,str) and ' ' in message
            alias=stem+'['+attr+'-invalid_component'+str(index)+'-'+message.split()[0]
            native=stem+'['+attr+'-invalid_component'+str(index)+'-'+message+']'
            assert alias in mapping and not alias.endswith(']')
            mapping[alias]=native;repairs.append({'published_alias':alias,'native_id':native,'source_message_literal':message,'source_parameter_index':index,'attr':attr})
    assert len(required)==len(mapping)==len(set(mapping.values()))==915 and len(repairs)==16
    assert {n for n in required if '[' in n and not n.endswith(']')}=={r['published_alias'] for r in repairs}
    out=ROOT/'.aeep/repository-native-identity-20261028-v6';out.mkdir(exist_ok=False)
    overlay=archive_files(original.truth.tests.read(),large=True);selectors=[n for n,b in overlay.items() if b'_AEEP_REQUIRED_NODES' in b];assert len(selectors)==1
    name=selectors[0];before=overlay[name].decode();selector_tree=ast.parse(before)
    assignment=next(n for n in selector_tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_AEEP_REQUIRED_NODES' for t in n.targets))
    assert isinstance(assignment.value,ast.Call) and ast.literal_eval(assignment.value.args[0])==required and assignment.lineno==assignment.end_lineno
    lines=before.splitlines(keepends=True);lines[assignment.lineno-1]='_AEEP_REQUIRED_NODES = frozenset('+repr([mapping[n] for n in required])+')\n';overlay[name]=''.join(lines).encode()
    tests=out/'native-tests.tar.gz';tests.write_bytes(pack_files(overlay,large=True))
    data=original.model_dump(mode='json');data['schema_version']='assessment.repository-suite-case.v6';data['input']['task_id']='collective__icalendar-880-native-identity-audit'
    binding=content_digest(data['input']);data['truth'].update(identity_format='pytest-native-v1',input_sha256=binding,archive_profile='repository-v1',source=SuiteAssetV5.model_validate(data['truth']['source']).model_dump(mode='json'),tests=asset(tests,True).model_dump(mode='json'),fail_to_pass=[mapping[n] for n in original.truth.fail_to_pass],pass_to_pass=[mapping[n] for n in original.truth.pass_to_pass])
    reference=_decode_suite_patch(original.truth,json.loads(original.reference.read()));assert len(reference.files)==2
    ref=out/'native-reference-artifact.json';ref.write_text(json.dumps(compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files=reference.files)),separators=(',',':')))
    data['reference']=asset(ref).model_dump(mode='json');data['fault_outputs']=[compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files=_decode_suite_patch(original.truth,o).files)) for o in original.fault_outputs]
    data['independent_case_id']=data['input']['task_id'];data['origin_kind']='authored_control';data['provenance']+=' New authored native-identity audit:16 published truncated aliases are expanded from unchanged source message literals before execution;899 names unchanged. All915 assertions/F2P/P2P roles retained;only the existing first-party selector literal changes. The old899/915 result remains excluded. Native collection must confirm this frozen mapping before any body trial;no outcome-based remapping or dropped tests.'
    native=RepositorySuiteCase.model_validate(data)
    pool=json.loads((BASE/'provisional-pool.json').read_text());all_cases=json.loads((ROOT/pool['cases_file']).read_text())
    controls=[RepositorySuiteCase.model_validate(next(c for c in all_cases if c['input']['task_id']==identity)) for identity in ['facelessuser__pymdown-extensions-2576-single-source-scope','tefra__xsdata-1126-issue-behavior-audit']]
    control_reviews={
        controls[0].input.task_id:json.loads((BASE/'operation-review.json').read_text()),
        controls[1].input.task_id:json.loads((HERE.parent/'repository-issue-behavior-20261028/control-continuation/operation-review.json').read_text())}
    variants=[];expected={};labels={}
    for case in [*controls,native]:
        identity=case.input.task_id;expected[identity]={};required_now=case.truth.fail_to_pass+case.truth.pass_to_pass
        if case is native:
            outputs={'reference':json.loads(ref.read_text()),'counterexample':compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files={n:source[n].decode() for n in reference.files}))}
            for i,path in enumerate(sorted(reference.files),1):
                files=dict(reference.files);files[path]=source[path].decode();outputs['partial-'+str(i)]=compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files=files))
        else:
            old=control_reviews[identity];outputs={v['variant']:v['artifact'] for v in json.loads((ROOT/old['variants_file']).read_text()) if v['case']==identity and v['variant'] in ('reference','counterexample')}
        labels[identity]=list(outputs)
        for label,artifact in outputs.items():
            path=out/(identity+'-payload-'+label+'.json');await payload(case,artifact,path)
            variants.append({'case':identity,'variant':label,'artifact':artifact,'payload':str(path.relative_to(ROOT)),'sha256':sha(path),'bytes':path.stat().st_size})
            if case is not native:
                expected[identity][label]=control_reviews[identity]['expectations'][identity][label]
            elif label=='reference':expected[identity][label]={'exit_code':0,'valid':True,'detail':'','statuses':{n:'PASSED' for n in required_now},'required_identities':required_now}
            elif label=='counterexample':expected[identity][label]={'exit_code':1,'valid':False,'detail':'test_failure','statuses':{**{n:'PASSED' for n in case.truth.pass_to_pass},**{n:'FAILED' for n in case.truth.fail_to_pass}},'required_identities':required_now}
            else:expected[identity][label]={'exit_code':1,'valid':False,'detail':'test_failure','statuses':{n:'PASSED' for n in case.truth.pass_to_pass},'at_least_one_failed':case.truth.fail_to_pass,'required_identities':required_now}
    collection_path=out/'collection-payload.json';collection=await payload(original,json.loads(original.reference.read()),collection_path)
    collection['collect_only']=True;collection_path.write_text(json.dumps(collection,separators=(',',':')))
    save(out/'cases.json',[c.model_dump(mode='json') for c in [*controls,native]]);save(out/'variants.json',variants)
    save(HERE/'identity-map.json',{'frozen_before_native_collection':True,'source_asset_sha256':original.truth.source.sha256,'source_test_path':test_path,'source_test_sha256':hashlib.sha256(source[test_path]).hexdigest(),'original_case':original.model_dump(mode='json'),'new_case_id':native.input.task_id,'required_count':915,'unchanged_names':899,'expanded_names':16,'repairs':repairs,'mapping':mapping,'selector_path':name,'all_assertions_preserved':True,'old_failure_unchanged':True,'actual_native_collection_executed':False})
    save(HERE/'execution-cases.json',{'cases_file':str((out/'cases.json').relative_to(ROOT)),'cases_file_sha256':sha(out/'cases.json'),'variants_file':str((out/'variants.json').relative_to(ROOT)),'case_ids':[c.input.task_id for c in [*controls,native]],'compatibility_case_ids':[c.input.task_id for c in controls],'new_case_id':native.input.task_id,'required_identities':993,'variants':8,'expectations':expected,'variant_labels':labels,'collection':{'name':'native-collection','payload':str(collection_path.relative_to(ROOT)),'payload_sha256':sha(collection_path),'archive_sha256':collection['archive_sha256'],'expected_native_required':list(mapping.values()),'expected_selected_ids':[n for n in required if mapping[n]==n]},'no_execution':True})
    print(json.dumps({'prepared_only':True,'required_native_ids':915,'source_literal_expansions':16,'unchanged_ids':899,'compatibility_controls':2,'body_variants':8,'collection_calls':1,'actual_execution':False}))

if __name__=='__main__':asyncio.run(main())
