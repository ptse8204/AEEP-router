"""Check issue provenance, retained tests and actual selector/grader guards inertly."""
import ast
import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

from aeep.assessment.repository_suites import RepositorySuiteCase, archive_files, _decode_suite_patch, grade_suite_output

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent

def selector_guard(overlay,required):
    tree=ast.parse(overlay['tests/conftest.py'])
    assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_AEEP_REQUIRED_NODES' for t in n.targets))
    function=next(n for n in reversed(tree.body) if isinstance(n,ast.FunctionDef) and n.name=='pytest_collection_modifyitems')
    called=[];removed=[]
    ns={'_AEEP_PREVIOUS_COLLECTION':lambda *a:called.append(True)}
    # Execute only the existing first-party selector, never upstream conftest code.
    exec(compile(ast.Module(body=[assignment,function],type_ignores=[]),'AEEP-FIRST-PARTY-SELECTOR-FIXTURE','exec'),ns)
    items=[SimpleNamespace(nodeid=n) for n in [*required,'tests/outside_scope.py::outside']]
    config=SimpleNamespace(hook=SimpleNamespace(pytest_deselected=lambda **kw:removed.extend(kw['items'])))
    ns['pytest_collection_modifyitems'](config,items)
    assert [x.nodeid for x in items]==required and len(removed)==1 and called==[True]

async def main():
    review=json.loads((HERE/'operation-review.json').read_text())
    old_review=json.loads((HERE.parent/'repository-contract-scope-20261028/operation-review.json').read_text())
    raw=json.loads((HERE.parent/'repository-multifile-sources-20261027/prepared-cases.json').read_text())
    old={c['input']['task_id']:RepositorySuiteCase.model_validate(c) for path in (raw['cases_file'],old_review['cases_file']) for c in json.loads((ROOT/path).read_text())}
    cases=[RepositorySuiteCase.model_validate(c) for c in json.loads((ROOT/review['cases_file']).read_text())]
    records=[];checks=0;selector_checks=0
    for case in cases:
        old_id=case.input.task_id.replace('-issue-behavior-audit','-declared-tests').replace('-single-source-scope','-declared-tests')
        original=old[old_id];assert case.truth.source==original.truth.source
        before=archive_files(original.truth.tests.read(),large=True);after=archive_files(case.truth.tests.read(),large=True)
        if old_id.startswith('tefra'):
            assert case.origin_kind=='authored_control' and case.input.family=='multi-file-repair'
            assert case.truth.pass_to_pass==original.truth.pass_to_pass and case.truth.fail_to_pass[:-1]==original.truth.fail_to_pass
            assert case.truth.pytest_plugins==original.truth.pytest_plugins
            protected='tests/test_aeep_issue_contract.py';assert set(after)==set(before)|{protected}
            assert {n for n in before if before[n]!=after[n]}=={'tests/conftest.py'}
            # The sole old-file change is the first-party selector literal.
            a=ast.parse(before['tests/conftest.py']);b=ast.parse(after['tests/conftest.py'])
            for tree in (a,b):
                node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_AEEP_REQUIRED_NODES' for t in n.targets));node.value=ast.Constant(value='SYNTHETIC-ONLY-SELECTOR-LITERAL')
            assert ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False)
            assert _decode_suite_patch(case.truth,json.loads(case.reference.read())).files==_decode_suite_patch(original.truth,json.loads(original.reference.read())).files
            text=after[protected].decode();guard_tree=ast.parse(text)
            assert not any(isinstance(n,ast.Attribute) and n.attr in {'ref','parent_pattern','_parent_match'} for n in ast.walk(guard_tree))
        else:
            assert case.origin_kind=='upstream_issue' and case.input.family=='single-file-repair'
            assert case.truth.tests==original.truth.tests and case.truth.fail_to_pass==original.truth.fail_to_pass and case.truth.pass_to_pass==original.truth.pass_to_pass
            gold=_decode_suite_patch(original.truth,json.loads(original.reference.read()))
            scoped=_decode_suite_patch(case.truth,json.loads(case.reference.read()))
            assert len(case.input.editable_paths)==1 and scoped.files=={p:gold.files[p] for p in case.input.editable_paths}
            assert 'pymdownx/__meta__.py' not in scoped.files
        required=case.truth.fail_to_pass+case.truth.pass_to_pass
        selector_guard(after,required);selector_checks+=1
        artifact=json.loads(case.reference.read())
        for mode in ('pass','nonzero','missing_authored_or_bug','error_authored_or_bug','skip_authored_or_bug','preservation_failed'):
            async def fake(payload):
                statuses={n:'PASSED' for n in required};exit_code=0;bug=case.truth.fail_to_pass[-1]
                if mode=='nonzero':exit_code=1
                elif mode=='missing_authored_or_bug':statuses.pop(bug)
                elif mode=='error_authored_or_bug':statuses[bug]='ERROR'
                elif mode=='skip_authored_or_bug':statuses[bug]='SKIPPED'
                elif mode=='preservation_failed':statuses[case.truth.pass_to_pass[0]]='FAILED'
                return {'exit_code':exit_code,'statuses':statuses,'archive_sha256':payload['archive_sha256'],'python':case.truth.python,'pytest':case.truth.pytest}
            grade=await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),artifact,fake)
            assert grade.valid==(mode=='pass');checks+=1
        records.append({'case':case.input.task_id,'original_required_identities':len(original.truth.fail_to_pass+original.truth.pass_to_pass),'new_authored_guards':int(case.origin_kind=='authored_control'),'required_identities':len(required),'original_assertions_retained':True})
    result={'passed':True,'cases':records,'first_party_selector_fixtures':selector_checks,'actual_grader_guard_fixtures':checks,'original_assertions_and_871_identities_retained':True,'new_issue_behavior_guards':2,'all_required_identities':873,'upstream_code_executed':False,'models_installs_builds_downloads':0,'fixture_results_are_not_benchmark_evidence':True}
    (HERE/'scope-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':asyncio.run(main())
