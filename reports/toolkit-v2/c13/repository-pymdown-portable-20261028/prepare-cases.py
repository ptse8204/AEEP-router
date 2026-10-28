"""Add only the exact cached Markdown ZIP-wheel to pending PyMdown payloads."""
import ast
import asyncio
import base64
import copy
import hashlib
import json
from pathlib import Path
import zipfile

from aeep.assessment.repository_suites import RepositorySuiteCase,SuiteAsset,pack_files,grade_suite_output

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'repository-issue-behavior-20261028'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')

async def main():
    assert json.loads((OLD/'remaining-execution-result.json').read_text())['passed']
    assert json.loads((OLD/'provisional-pool.json').read_text())['case_count']==60
    review=json.loads((OLD/'operation-review.json').read_text());cached=HERE.parent/'repository-workload-batch-20261022/runtime-support-review.json'
    pin=next(p for p in json.loads(cached.read_text())['pins'] if p['project']=='Markdown')
    wheel=ROOT/pin['private_cache'];assert sha(wheel)==pin['sha256'] and wheel.stat().st_size==107441
    portable=SuiteAsset(path=str(wheel.resolve()),sha256=pin['sha256'],size_bytes=pin['size_bytes'])
    with zipfile.ZipFile(wheel) as z:module_sha=hashlib.sha256(z.read('markdown/__init__.py')).hexdigest()
    out=ROOT/'.aeep/repository-pymdown-portable-20261028';out.mkdir(exist_ok=False);cases=[];variants=[];metadata=[]
    descriptions={d['id']:d for d in review['case_summary']}
    for original in json.loads((ROOT/review['cases_file']).read_text()):
        if not original['input']['task_id'].startswith('facelessuser'):continue
        before=RepositorySuiteCase.model_validate(original);data=copy.deepcopy(original)
        data['truth']['wheels']=[*data['truth']['wheels'],portable.model_dump(mode='json')]
        data['provenance']+=' Runtime-only correction:ZIP-load exact cached pure Markdown3.9 through existing per-payload wheels. It is not installed in the image or host. Input/source/protected tests/reference/fault bytes,765combined identities and assertions remain unchanged. Earlier failed dependency probe and all charges remain.'
        case=RepositorySuiteCase.model_validate(data);directory=out/case.input.task_id;directory.mkdir()
        outputs={'reference':json.loads(case.reference.read()),'counterexample':case.fault_outputs[0]}
        for label,artifact in outputs.items():
            class Captured(Exception):pass
            async def capture(payload):
                path=directory/('payload-'+label+'.json');path.write_text(json.dumps(payload,separators=(',',':')))
                variants.append({'case':case.input.task_id,'variant':label,'artifact':artifact,'payload':str(path.relative_to(ROOT)),'sha256':sha(path),'bytes':path.stat().st_size});raise Captured()
            try:await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),artifact,capture)
            except Captured:pass
            else:raise AssertionError('Inert preparation returned a grade')
        cases.append(case.model_dump(mode='json'));d=copy.deepcopy(descriptions[case.input.task_id]);d['portable_wheels']=[{'project':'Markdown','version':'3.9','sha256':pin['sha256'],'loading':'Per-payload ZIP on private sys.path;no installer or image mutation.'}];metadata.append(d)
        assert case.input==before.input and case.truth.tests==before.truth.tests and case.reference==before.reference and case.fault_outputs==before.fault_outputs
    assert len(cases)==2 and len(variants)==4 and sum(d['required_tests'] for d in metadata)==765
    save(out/'cases.json',cases);save(out/'variants.json',variants)
    save(HERE/'execution-cases.json',{'prepared_cases':2,'cases_file':str((out/'cases.json').relative_to(ROOT)),'cases_file_sha256':sha(out/'cases.json'),'variants_file':str((out/'variants.json').relative_to(ROOT)),'cases':metadata,'errors':[],'payloads':4,'external_execution_or_models':False})
    parent=json.loads((OLD/'observer-envelope.json').read_text());payload=copy.deepcopy(parent['probes'][0]['payload'])
    assert len(payload['wheels'])==4
    payload['wheels'].append({'filename':wheel.name,'sha256':pin['sha256'],'data':base64.b64encode(wheel.read_bytes()).decode()})
    program='''import hashlib,importlib.metadata,importlib.resources
from pathlib import Path
import markdown,yaml,pygments

def test_private_markdown_zip_runtime():
    assert importlib.metadata.version("Markdown")=="3.9"
    assert str(markdown.__file__).endswith("markdown-3.9-py3-none-any.whl/markdown/__init__.py")
    assert hashlib.sha256(importlib.resources.files(markdown).joinpath("__init__.py").read_bytes()).hexdigest()==MODULE_SHA
    assert markdown.markdown("**AEEP**")=="<p><strong>AEEP</strong></p>"
    assert importlib.metadata.version("PyYAML")=="6.0.2"
    assert importlib.metadata.version("Pygments")=="2.19.2"
    assert yaml.safe_load("key: value")=={"key":"value"}
    for module in (yaml,pygments):
        assert Path(module.__file__).is_relative_to("/usr/local/lib/python3.13/site-packages")
'''.replace('MODULE_SHA',repr(module_sha))
    ast.parse(program);archive=pack_files({'tests/test_portable_markdown.py':program.encode()},large=True)
    payload.update(archive=base64.b64encode(archive).decode(),archive_sha256=hashlib.sha256(archive).hexdigest(),test_paths=['tests/test_portable_markdown.py'])
    parent['probes']=[{'name':'portable_markdown','payload':payload,'payload_sha256':hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest(),'archive_sha256':payload['archive_sha256'],'expected_node':'tests/test_portable_markdown.py::test_private_markdown_zip_runtime'}]
    save(HERE/'observer-envelope.json',parent)
    save(HERE/'portable-wheel-review.json',{'project':'Markdown','version':'3.9','pin':pin,'cached_support_manifest':str(cached.relative_to(ROOT)),'cached_support_manifest_sha256':sha(cached),'loading_mode':'Exact pure wheel ZIP in each private grader payload,not image or host installation.','current_image_installation':'Distribution metadata absent in the actual failed probe;not inferred from a cache.','current_image_and_source_unchanged':True,'active_runtime_dependencies_on_python313':[],'extras_requested':[],'license':'BSD-3-Clause','cached_wheel_bytes':107441,'downloads_builds_installations_models_or_execution':0})
    print(json.dumps({'prepared_cases':2,'variants':4,'required_identities':765,'cached_pure_wheel_bytes':107441,'actual_execution':False}))

if __name__=='__main__':asyncio.run(main())
