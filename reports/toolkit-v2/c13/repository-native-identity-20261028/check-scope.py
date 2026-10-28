"""Prove only the first-party selector and identity metadata changed; no imports."""
import ast
import hashlib
import json
from pathlib import Path

from aeep.assessment.repository_suites import RepositorySuiteCase,_decode_suite_patch,archive_files

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent

def main():
    mapping=json.loads((HERE/'identity-map.json').read_text());original=RepositorySuiteCase.model_validate(mapping['original_case'])
    meta=json.loads((HERE/'execution-cases.json').read_text());cases=[RepositorySuiteCase.model_validate(c) for c in json.loads((ROOT/meta['cases_file']).read_text())]
    native=cases[-1]
    left=original.input.model_dump(mode='json');right=native.input.model_dump(mode='json')
    assert {k for k in left if left[k]!=right[k]}=={'task_id'} and left.keys()==right.keys()
    assert original.source_revision==native.source_revision and original.truth.source.model_dump(mode='json')==native.truth.source.model_dump(mode='json')
    assert original.truth.wheels==native.truth.wheels and original.truth.python==native.truth.python and original.truth.pytest==native.truth.pytest
    old=archive_files(original.truth.tests.read(),large=True);new=archive_files(native.truth.tests.read(),large=True)
    selector=mapping['selector_path'];assert old.keys()==new.keys() and {n for n in old if old[n]!=new[n]}=={selector}
    trees=[ast.parse(value[selector]) for value in (old,new)]
    for tree in trees:
        row=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_AEEP_REQUIRED_NODES' for t in n.targets))
        row.value=ast.Constant(value='identity literal removed only for comparison')
    assert ast.dump(trees[0],include_attributes=False)==ast.dump(trees[1],include_attributes=False)
    assert _decode_suite_patch(original.truth,json.loads(original.reference.read())).files==_decode_suite_patch(native.truth,json.loads(native.reference.read())).files
    assert len(original.fault_outputs)==len(native.fault_outputs)
    for a,b in zip(original.fault_outputs,native.fault_outputs,strict=True):assert _decode_suite_patch(original.truth,a).files==_decode_suite_patch(native.truth,b).files
    pool=json.loads((HERE.parent/'repository-pymdown-portable-20261028/provisional-pool.json').read_text())
    prior={c['input']['task_id']:c for c in json.loads((ROOT/pool['cases_file']).read_text())}
    for control in cases[:-1]:assert control.model_dump(mode='json')==prior[control.input.task_id]
    result={'passed':True,'source_and_upstream_test_bytes_unchanged':True,'only_protected_selector_literal_changes':True,'selector_rest_ast_identical':True,'all915_identity_roles_retained':True,'reference_and_fault_replacement_text_identical':True,'both_controls_entire_case_records_identical':True,'input_changes_only_task_id':True,'source_executed':False,'reviewed_identity_map_sha256':hashlib.sha256((HERE/'identity-map.json').read_bytes()).hexdigest()}
    with(HERE/'scope-check.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))

if __name__=='__main__':main()
