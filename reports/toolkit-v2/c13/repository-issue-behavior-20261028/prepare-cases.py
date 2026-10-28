"""Prepare authored issue guards and cached single-file tasks as inert data."""
import ast
import asyncio
import base64
import copy
import hashlib
import json
from pathlib import Path
import zipfile

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteAsset, SuiteAssetV5, archive_files, pack_files, _decode_suite_patch, compressed_patch_artifact, grade_suite_output
from aeep.assessment.repository_tasks import RepositoryPatch

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'repository-contract-scope-20261028';MULTI=HERE.parent/'repository-multifile-sources-20261027'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def asset(p,large=False):return (SuiteAssetV5 if large else SuiteAsset)(path=str(p.resolve()),sha256=sha(p),size_bytes=p.stat().st_size)

def extend_selector(data,old,new):
    text=data.decode();tree=ast.parse(text)
    node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_AEEP_REQUIRED_NODES' for t in n.targets))
    assert isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='frozenset'
    assert ast.literal_eval(node.value.args[0])==old
    lines=text.splitlines(keepends=True);assert node.lineno==node.end_lineno
    lines[node.lineno-1]='_AEEP_REQUIRED_NODES = frozenset('+repr(new)+')\n'
    # Only the existing first-party selector literal changes, never an assertion.
    return ''.join(lines).encode()

async def main():
    assert json.loads((OLD/'bundle-execution-result.json').read_text())['all_components_passed']
    assert json.loads((OLD/'provisional-pool.json').read_text())['case_count']==58
    old_review=json.loads((OLD/'operation-review.json').read_text());multi=json.loads((MULTI/'prepared-cases.json').read_text())
    entries=[*(v for v in json.loads((ROOT/old_review['cases_file']).read_text()) if v['input']['task_id'].startswith('tefra')),*(v for v in json.loads((ROOT/multi['cases_file']).read_text()) if v['input']['task_id'].startswith('facelessuser'))]
    descriptions={d['id']:d for d in [*old_review['case_summary'],*multi['cases']]}
    out=ROOT/'.aeep/repository-issue-behavior-20261028-v5';out.mkdir(exist_ok=False)
    result=[];variants=[];metadata=[];origins=[]
    for original in entries:
        data=copy.deepcopy(original);value=RepositorySuiteCase.model_validate(original)
        old_id=value.input.task_id;description=copy.deepcopy(descriptions[old_id]);directory=out/old_id;directory.mkdir()
        published=_decode_suite_patch(value.truth,json.loads(value.reference.read()))
        old_required=value.truth.fail_to_pass+value.truth.pass_to_pass
        if old_id.startswith('tefra'):
            issue='1126' if '1126' in old_id else '1132'
            guard=HERE/'authored-guards'/('test_issue'+issue+'.py');body=guard.read_bytes();tree=ast.parse(body)
            method=next(n.name for n in tree.body if isinstance(n,ast.FunctionDef))
            protected='tests/test_aeep_issue_contract.py';node=protected+'::'+method
            overlay=archive_files(value.truth.tests.read(),large=True);assert protected not in overlay
            overlay['tests/conftest.py']=extend_selector(overlay['tests/conftest.py'],old_required,[*value.truth.fail_to_pass,node,*value.truth.pass_to_pass])
            overlay[protected]=body;tests=directory/'tests.tar.gz';tests.write_bytes(pack_files(overlay,large=True))
            data['input']['task_id']=old_id.replace('-declared-tests','-issue-behavior-audit')
            data['input']['task']+='\n\nPreserve the published issue behavior across the existing source modules: '+('same-named nested enum types must remain distinct after promotion and lookup.' if issue=='1126' else 'a parent-qualified decorator applies only to matching parent paths, not other same-named classes.')
            data['truth'].update(tests=asset(tests,True).model_dump(mode='json'),fail_to_pass=[*value.truth.fail_to_pass,node],test_paths=[*value.truth.test_paths,protected])
            data['origin_kind']='authored_control'
            data['provenance']+=' Authored issue-derived behavior guard,not an unmodified upstream benchmark: '+('two same-named nested enums through existing promotion/lookup APIs' if issue=='1126' else 'matching and nonmatching parent paths for decorators')+'. All original assertions/identities retained;only the existing first-party selector literal extended. No golden source-text,private new method or exact implementation assertion.'
            description.update(id=data['input']['task_id'],origin_kind='authored_control',authored_preservation_guard=False,authored_issue_behavior_guard=True,required_tests=len(old_required)+1,upstream_required_identities=old_required,authored_required_identities=[node],guard_path=str(guard.relative_to(ROOT)),guard_sha256=sha(guard),scope_adaptation='Explicit issue-derived behavior check;every original assertion and required identity retained')
            origins.append({'case':data['input']['task_id'],'upstream_issue':description['original_issue_id'],'original_required_count':len(old_required),'added_authored_guard':node,'reason':'Observed reference/original differentiation but a passing first partial in the predecessor. No model result informed the check.','old_definition_remains_excluded':True})
            reference_files=published.files
        else:
            target='pymdownx/fancylists.py' if '2576' in old_id else 'pymdownx/arithmatex.py'
            assert set(published.files)=={'pymdownx/__meta__.py',target}
            data['input'].update(task_id=old_id.replace('-declared-tests','-single-source-scope'),family='single-file-repair',editable_paths=[target],task=value.input.task+'\n\nScope: repair the described Markdown behavior in '+target+';preserve unrelated code and package-version metadata.')
            data['provenance']+=' New single-functional-file scope:exclude only the unrelated package-version bump and changelog. All original protected test bytes/assertions and'+str(len(old_required))+'identities unchanged. Previous multi-file curation exclusion remains;no execution is replayed.'
            description.update(id=data['input']['task_id'],family='single-file-repair',reference_changed_files=[target],executable_changed_files=[target],omitted_non_source_reference_changes=['pymdownx/__meta__.py (version bookkeeping)','docs/src/markdown/about/changelog.md'],scope_adaptation='One functional repair file;preserve original version metadata and all protected assertions/identities')
            reference_files={target:published.files[target]}
        binding=content_digest(data['input']);data['truth']['input_sha256']=binding
        ref=directory/'reference-artifact.json';ref.write_text(json.dumps(compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files=reference_files)),separators=(',',':')))
        data['reference']=asset(ref).model_dump(mode='json');data['fault_outputs']=[compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files={p:archive_files(value.truth.source.read(),large=True)[p].decode() for p in reference_files}))];data['independent_case_id']=data['input']['task_id']
        case=RepositorySuiteCase.model_validate(data)
        outputs={'reference':json.loads(ref.read_text()),'counterexample':data['fault_outputs'][0]}
        if old_id.startswith('tefra'):
            source=archive_files(case.truth.source.read(),large=True)
            for index,path in enumerate(sorted(reference_files),1):
                partial=dict(reference_files);partial[path]=source[path].decode()
                outputs['partial-'+str(index)]=compressed_patch_artifact(RepositoryPatch(base_sha256=binding,files=partial))
        for label,artifact in outputs.items():
            class Captured(Exception):pass
            async def capture(payload):
                path=directory/('payload-'+label+'.json');path.write_text(json.dumps(payload,separators=(',',':')))
                variants.append({'case':case.input.task_id,'variant':label,'artifact':artifact,'payload':str(path.relative_to(ROOT)),'sha256':sha(path),'bytes':path.stat().st_size});raise Captured()
            try:await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),artifact,capture)
            except Captured:pass
            else:raise AssertionError('Inert preparation returned a grade')
        result.append(case.model_dump(mode='json'));metadata.append(description)
    assert len(result)==4 and len(variants)==12 and sum(d['required_tests'] for d in metadata)==873
    save(out/'cases.json',result);save(out/'variants.json',variants)
    save(HERE/'execution-cases.json',{'prepared_cases':4,'cases_file':str((out/'cases.json').relative_to(ROOT)),'cases_file_sha256':sha(out/'cases.json'),'variants_file':str((out/'variants.json').relative_to(ROOT)),'cases':metadata,'errors':[],'payloads':12,'old_outcomes_retained':True,'new_external_execution_or_models':False})
    save(HERE/'authored-guard-provenance.json',origins)
    parent=json.loads((OLD/'observer-envelope.json').read_text())
    # Current source/image/boundary and benchmark-plugin observations are retained.
    # One fresh Markdown/YAML/Pygments identity probe checks the cached new subjects.
    payload=copy.deepcopy(parent['probes'][0]['payload']);versions={};modules={};pins=[]
    for folder,project,module in [('repository-workload-batch-20261022','Markdown','markdown'),('repository-replacement-runtime-20261022','PyYAML','yaml'),('repository-supported-suites-20261027','Pygments','pygments')]:
        manifest=HERE.parent/folder/('runtime-wheel-review.json' if project=='PyYAML' else 'runtime-support-review.json')
        pin=next(p for p in json.loads(manifest.read_text())['pins'] if p['project']==project)
        wheel=ROOT/pin['private_cache'];assert sha(wheel)==pin['sha256']
        with zipfile.ZipFile(wheel) as z:module_sha=hashlib.sha256(z.read(module+'/__init__.py')).hexdigest()
        versions[project]=pin['version'];modules[module]=module_sha;pins.append({'project':project,'version':pin['version'],'manifest':str(manifest.relative_to(ROOT)),'cached_wheel':str(wheel.relative_to(ROOT)),'sha256':pin['sha256']})
    program='import hashlib,importlib.metadata,importlib\nfrom pathlib import Path\n\ndef test_cached_markup_runtime():\n    expected='+repr(versions)+'\n    for name,version in expected.items():\n        assert importlib.metadata.version(name)==version\n        assert str(importlib.metadata.distribution(name).locate_file(""))=="/usr/local/lib/python3.13/site-packages"\n    for name,digest in '+repr(modules)+'.items():\n        path=Path(importlib.import_module(name).__file__)\n        assert path.is_relative_to("/usr/local/lib/python3.13/site-packages")\n        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest\n'
    ast.parse(program);encoded=pack_files({'tests/test_markup_runtime.py':program.encode()},large=True)
    payload.update(archive=base64.b64encode(encoded).decode(),archive_sha256=hashlib.sha256(encoded).hexdigest(),test_paths=['tests/test_markup_runtime.py'])
    parent['probes']=[{'name':'markup_runtime','payload':payload,'payload_sha256':hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest(),'archive_sha256':payload['archive_sha256'],'expected_node':'tests/test_markup_runtime.py::test_cached_markup_runtime'}]
    parent['benchmark_plugin_reuse']={'manifest':str((OLD/'completion-audit.json').relative_to(ROOT)),'manifest_sha256':sha(OLD/'completion-audit.json'),'receipt':json.loads((OLD/'completion-audit.json').read_text())['reopened'][0]}
    save(HERE/'existing-runtime-pins.json',pins);save(HERE/'observer-envelope.json',parent)
    print(json.dumps({'cases':4,'variants':12,'required_identities':873,'authored_guards':2,'fresh_probe':1,'builds_installs_downloads_models':0,'executed':False}))

if __name__=='__main__':asyncio.run(main())
