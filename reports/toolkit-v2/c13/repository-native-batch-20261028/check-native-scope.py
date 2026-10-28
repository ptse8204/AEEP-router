"""Authored data-only checks for exhaustive alias expansion and immutable scope."""
import hashlib
import json
from pathlib import Path
import tempfile

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteAsset, SuiteAssetV5, SuiteInput, SuiteTruthV6, archive_files, compressed_patch_artifact, pack_files
from aeep.assessment.repository_tasks import RepositoryPatch
from native_scope import derive, expand

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent

def main():
    module='tests/test_core.py';a=module+'::test_repair[x';b=module+'::test_keep'
    native=[a+' two]',b,a+' one]']
    f,p,g=expand([a],[b],native,[module]);assert f==[a+' one]',a+' two]'] and p==[b] and len(g)==2
    checks=1
    bad=[([a,a],[b],native),([a],[b],native+[native[0]]),([a],[b],[b]),
         ([a],[b],['bad\nnode',b]),([a],[b],[' ',b]),([a],[b],[{},b]),
         ([a],[a+' one]'],native),([a],[b],[a+' one]',b+' another']),
         ([a],[b],[a+' '+str(i)+']' for i in range(5001)]+[b]),
         ([a],[b],[a+' '+str(i)+'z'*8000+']' for i in range(50)]+[b])]
    for args in bad:
        try:expand(*args,[module])
        except ValueError:checks+=1
        else:raise AssertionError('Unsafe/incomplete or overlapping scope accepted')
    try:expand([a],[b],native,['tests/other.py'])
    except ValueError:checks+=1
    else:raise AssertionError('Undeclared module accepted')
    with tempfile.TemporaryDirectory(prefix='aeep-FIRST-PARTY-native-scope-',dir=ROOT/'.aeep') as temporary:
        root=Path(temporary).resolve()
        def asset(path,large=False):
            data=path.read_bytes();return (SuiteAssetV5 if large else SuiteAsset)(path=str(path),sha256=hashlib.sha256(data).hexdigest(),size_bytes=len(data))
        source=pack_files({'library/core.py':b'def value():\n    return 0\n'},large=True)
        digest=hashlib.sha256(source).hexdigest();src=root/(digest+'.tar.gz');src.write_bytes(source)
        task=SuiteInput(task_id='FIRST-PARTY-data-only',task='Fixture only,never executed.',family='fixture',source_sha256=digest,editable_paths=['library/core.py']);binding=content_digest(task)
        code='_AEEP_REQUIRED_NODES = frozenset('+repr([a,b])+')\n\ndef pytest_collection_modifyitems(config,items):\n    items[:]=[i for i in items if i.nodeid in _AEEP_REQUIRED_NODES]\n'
        tests=root/'tests.tar.gz';tests.write_bytes(pack_files({'tests/conftest.py':code.encode(),module:b'def test_keep():\n    assert True\n'},large=True))
        wheel=root/'fixture-0-py3-none-any.whl';wheel.write_bytes(b'NOT EXECUTED:inert fake wheel')
        repair=compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files={'library/core.py':'def value():\n    return 1\n'}));ref=root/'ref.json';ref.write_text(json.dumps(repair))
        truth=SuiteTruthV6(input_sha256=binding,source=asset(src,True),tests=asset(tests,True),wheels=[asset(wheel)],python='3.13',pytest='8.3.5',test_paths=[module],fail_to_pass=[a],pass_to_pass=[b],pytest_plugins=[],patch_encoding='gzip-json',test_roots=['tests'],archive_profile='repository-v1',identity_format='pytest-native-v1')
        seed=RepositorySuiteCase(schema_version='assessment.repository-suite-case.v6',input=task,truth=truth,reference=asset(ref),fault_outputs=[repair],source_repository='https://example.invalid/FIRST-PARTY',source_revision='a'*40,independent_case_id='FIRST-PARTY',license='Authored fixture',provenance='Data-only first-party fixture;not benchmark evidence.')
        case,proof=derive(seed,{'exit_code':0,'python':'3.13','pytest':'8.3.5','native_ids':native},root/'derived.tar.gz')
        assert case.truth.fail_to_pass==f and case.truth.pass_to_pass==p and proof['only_selector_literal_changed']
        original=archive_files(seed.truth.tests.read(),large=True);derived=archive_files(case.truth.tests.read(),large=True)
        assert original[module]==derived[module] and set(original)==set(derived)
        assert case.input==seed.input and case.fault_outputs==seed.fault_outputs and case.reference==seed.reference
        assert case.truth.source.read()==seed.truth.source.read();checks+=1
        for changes in [{'exit_code':1},{'python':'3.9'},{'pytest':'9.0.3'}]:
            try:derive(seed,{'exit_code':0,'python':'3.13','pytest':'8.3.5','native_ids':native,**changes},root/'never-created.tar.gz')
            except ValueError:checks+=1
            else:raise AssertionError('Unknown/changed collection accepted')
        assert not(root/'never-created.tar.gz').exists()
    assert not root.exists()
    result={'passed':True,'first_party_data_checks':checks,'no_subject_or_fake_wheel_execution':True,'owned_scratch_removed':True,'no_containers_models_installs_downloads_or_grant_debits':True,'fixture_is_not_benchmark_evidence':True,'method_sha256':hashlib.sha256((HERE/'native_scope.py').read_bytes()).hexdigest()}
    with(HERE/'native-scope-check.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result))

if __name__=='__main__':main()
