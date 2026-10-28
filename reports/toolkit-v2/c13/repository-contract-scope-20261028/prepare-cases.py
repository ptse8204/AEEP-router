"""Prepare issue-aligned oracle/config corrections as inert data;no subject execution."""
import ast
import asyncio
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase,SuiteAssetV5,SuiteAsset,archive_files,pack_files,_decode_suite_patch,compressed_patch_artifact,grade_suite_output
from aeep.assessment.repository_tasks import RepositoryPatch

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'repository-multifile-sources-20261027'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def asset(path,large=False):return (SuiteAssetV5 if large else SuiteAsset)(path=str(path),sha256=sha(path),size_bytes=path.stat().st_size)

async def main():
    assert json.loads((OLD/'bundle-execution-result.json').read_text())['all_components_passed']
    pool=json.loads((OLD/'provisional-pool.json').read_text());assert pool['case_count']==57
    review=json.loads((OLD/'runtime-review.json').read_text());cases=json.loads((ROOT/review['cases_file']).read_text())
    out=ROOT/'.aeep/repository-contract-scope-20261028-v2';out.mkdir(exist_ok=False)
    result=[];descriptions=[];variants=[]
    old_metadata={c['id']:c for c in review['case_summary']}
    for data in cases:
        if data['input']['task_id'].startswith('canopen'):continue
        value=RepositorySuiteCase.model_validate(data);identity=value.input.task_id;description=dict(old_metadata[identity])
        if identity.startswith('duo-labs'):
            source=archive_files(value.truth.source.read(),large=True);overlay=archive_files(value.truth.tests.read(),large=True)
            auth='webauthn/authentication/verify_authentication_response.py';target='webauthn/registration/formats/android_safetynet.py';test='tests/test_verify_authentication_response.py'
            assert 'user_verified: bool' in source[auth].decode() and 'user_verified=auth_data.flags.uv' in source[auth].decode()
            assert source[test].count(b'assert not verification.user_verified')==1 and source[test].count(b'assert verification.user_verified')==1
            # Restore all original authentication assertions. The issue asks only
            # about SafetyNet;the publisher's unrelated API cleanup is excluded.
            before_overlay=dict(overlay);overlay[test]=source[test]
            assert all(overlay[n]==b for n,b in before_overlay.items() if n!=test)
            data['input'].update(task_id='duo-labs__py_webauthn-241-safetynet-scope',family='single-file-repair',editable_paths=[target],task=value.input.task+'\n\nScope: change SafetyNet verification only. Preserve the authentication-response API and all unrelated behavior.')
            binding=content_digest(data['input']);published=_decode_suite_patch(value.truth,json.loads(value.reference.read()));gold=published.files[target]
            assert set(published.files)=={auth,target} and 'if not payload.basic_integrity:' in gold
            target_dir=out/'webauthn';target_dir.mkdir();tests=target_dir/'tests.tar.gz';tests.write_bytes(pack_files(overlay,large=True))
            ref=target_dir/'reference.json';ref.write_text(json.dumps(compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files={target:gold})),separators=(',',':')))
            fault=compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files={target:gold.replace('if not payload.basic_integrity:','if False:')}))
            data['truth'].update(input_sha256=binding,tests=asset(tests,large=True).model_dump(mode='json'))
            data['reference']=asset(ref).model_dump(mode='json');data['fault_outputs']=[fault];data['independent_case_id']=data['input']['task_id']
            data['provenance']+=' New bounded SafetyNet issue scope:exclude the unrelated authentication API removal,restore both original user_verified test assertions,restrict edits to the SafetyNet module. Retain all11 required identities. The old multi-file attempt remains ineligible;its accepted partial was legitimate for the published issue. No historical result is rewritten.'
            description.update(id=data['input']['task_id'],family='single-file-repair',reference_changed_files=[target],executable_changed_files=[target],omitted_non_source_reference_changes=[auth+' (unrelated API cleanup)'],scope_adaptation='SafetyNet-only issue contract;two original authentication assertions restored;all11 identities unchanged',authored_preservation_guard=False)
            outputs={'reference':json.loads(ref.read_text()),'counterexample':compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files={})),'preservation-fault':fault}
        else:
            assert identity.startswith('tefra')
            data['truth']['pytest_plugins']=[*value.truth.pytest_plugins,'pytest_benchmark.plugin']
            data['provenance']+=' Explicit operator pytest-benchmark plugin for the source pyproject --benchmark-skip option. Source/reference/protected test bytes,required identities and all assertions unchanged. Earlier collection failures remain failed.'
            description.update(explicit_plugins=data['truth']['pytest_plugins'],scope_adaptation='Enable already-installed pytest_benchmark.plugin;no source/oracle/reference byte changes')
            original=[v for v in json.loads((ROOT/review['variants_file']).read_text()) if v['case']==identity];outputs={v['variant']:v['artifact'] for v in original}
        case=RepositorySuiteCase.model_validate(data)
        for label,artifact in outputs.items():
            class Captured(Exception):pass
            async def capture(payload):
                path=out/(case.input.task_id+'-'+label+'.json');path.write_text(json.dumps(payload,separators=(',',':')))
                variants.append({'case':case.input.task_id,'variant':label,'artifact':artifact,'payload':str(path.relative_to(ROOT)),'sha256':sha(path),'bytes':path.stat().st_size});raise Captured()
            try:await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),artifact,capture)
            except Captured:pass
            else:raise AssertionError('Inert preparation returned a grade')
        result.append(case.model_dump(mode='json'));descriptions.append(description)
    assert len(result)==3 and len(variants)==11
    cases_file=out/'cases.json';save(cases_file,result);save(out/'variants.json',variants)
    save(HERE/'execution-cases.json',{'prepared_cases':3,'cases_file':str(cases_file.relative_to(ROOT)),'cases_file_sha256':sha(cases_file),'variants_file':str((out/'variants.json').relative_to(ROOT)),'cases':descriptions,'errors':[],'payloads':11,'old_failures_preserved':True,'new_external_execution_or_models':False})
    # One fresh plugin/config probe supplements the applicable completed4 probes
    # on the identical source/image/observer/permissions. No benchmark is measured.
    parent=json.loads((OLD/'runtime-execution/parent-runtime-review.json').read_text());parent['external_execution']=False
    payload=dict(parent['probes'][0]['payload']);payload['pytest_plugins']=['pytest_mock','_hypothesis_pytestplugin','pytest_benchmark.plugin']
    support=json.loads((HERE.parent/'repository-supported-suites-20261027/runtime-support-review.json').read_text());pin=next(x for x in support['pins'] if x['project']=='pytest-benchmark');wheel=ROOT/pin['private_cache'];assert sha(wheel)==pin['sha256']
    with zipfile.ZipFile(wheel) as z:plugin_sha=hashlib.sha256(z.read('pytest_benchmark/plugin.py')).hexdigest()
    program='import hashlib,importlib.metadata\nfrom pathlib import Path\nimport pytest_benchmark.plugin\n\ndef test_explicit_benchmark_option(pytestconfig):\n    assert pytestconfig.getoption("benchmark_skip") is True\n    assert importlib.metadata.version("pytest-benchmark")=="5.1.0"\n    path=Path(pytest_benchmark.plugin.__file__)\n    assert path.is_relative_to("/usr/local/lib/python3.13/site-packages")\n    assert hashlib.sha256(path.read_bytes()).hexdigest()=='+repr(plugin_sha)+'\n'
    ast.parse(program);encoded=pack_files({'pytest.ini':b'[pytest]\naddopts = --benchmark-skip\n','tests/test_plugin_scope.py':program.encode()},large=True)
    payload.update(archive=base64.b64encode(encoded).decode(),archive_sha256=hashlib.sha256(encoded).hexdigest(),test_paths=['tests/test_plugin_scope.py'])
    parent['probes']=[{'name':'benchmark_plugin','payload':payload,'payload_sha256':hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest(),'archive_sha256':payload['archive_sha256'],'expected_node':'tests/test_plugin_scope.py::test_explicit_benchmark_option'}]
    parent['current_containment_reuse']={'manifest':str((OLD/'runtime-execution/completion-audit.json').relative_to(ROOT)),'manifest_sha256':sha(OLD/'runtime-execution/completion-audit.json'),'source_digest':review['source_digest'],'image':parent['image'],'observer_program_sha256':parent['recipe']['dependencies']['program'],'reason':'Same exact host source374579f1,image9f473,observer,core private bootstrap wheels and permission boundary;all four probes completed. Only explicit plugin/oracle/task definitions change;one new plugin/config probe is mandatory.','completed_probe_receipts':json.loads((OLD/'runtime-execution/completion-audit.json').read_text())['reopened'][:4]}
    save(HERE/'observer-envelope.json',parent)
    save(HERE/'scope-review.json',{'issue_text_source':'.aeep/repository-multifile-source-review-20261027/duo-labs__py_webauthn-241/row.json','issue_contract':'SafetyNet basicIntegrity check;does not request unrelated authentication API removal.','old_multifile_result':'Reference/counterexample verified;partial retaining the old authentication field also passed. Do not force unrelated changes to make the reference look necessary.','new_scope':'One editable SafetyNet file;both original authentication assertions restored;all11 identities retained. Three variants include an integrity-bypass preservation fault.','xsdata_change':'Explicit existing pytest_benchmark.plugin for project --benchmark-skip. No flag removal,assertion deletion or source/reference/test byte change.','new_plugin_probe':'Honor the existing project option with pinned installed plugin bytes;no performance benchmark or model use.','source_and_image_unchanged':True,'cases_unadopted':True,'old_attempts_and_charges_retained':True,'actual_tests_or_models_run':False})
    print(json.dumps({'cases':len(result),'variants':len(variants),'new_plugin_probes':1,'required_identities':sum(c['required_tests'] for c in descriptions),'external_execution':False}))

if __name__=='__main__':asyncio.run(main())
