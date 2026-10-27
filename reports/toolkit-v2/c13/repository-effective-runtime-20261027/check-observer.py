"""First-party parser and whole-observer fixtures; no test child is dispatched."""
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'repository-test-roots-20261027';ROOT=HERE.parents[3]


def main():
    old=(OLD/'operator-observer.py').read_text();new=(HERE/'operator-observer.py').read_text()
    raw=json.loads((OLD/'runtime-execution/raw-observation-8.json').read_text())['output']['evaluation']
    required={k:v for k,v in raw['statuses'].items() if v=='PASSED'};assert len(required)==11
    # This deliberately models the ambiguity. It is NOT the original full log,
    # which the successful-exit retention policy did not retain.
    noise=b'ERROR:Parser:Not supported query\nERROR Parser:parser.py:129 unsupported query\n'
    positive=''.join('PASSED '+n+'\n' for n in required).encode()
    cases=[('pass',0,b'PASSED tests/test_fake.py::test_ok\n',None),('failure',1,b'FAILED tests/test_fake.py::test_ok - failure\n',None),('module_error',2,b'ERROR tests/test_fake.py - import failure\n',None),('all_statuses',1,b'PASSED tests/test_fake.py::one\nFAILED tests/test_fake.py::two\nERROR tests/test_fake.py::three\nSKIPPED tests/test_fake.py::four\nXFAIL tests/test_fake.py::five\n',None),('unexpected_test_preserved',0,b'PASSED other/test_outside.py::test_extra\n',None),('logging_collision',0,noise+positive,required),('logging_without_result',0,noise,{})]
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w:gz') as out:
        body=b'raise AssertionError("Synthetic subject must never execute")\n';item=tarfile.TarInfo('tests/test_fake.py');item.size=len(body);out.addfile(item,io.BytesIO(body))
    payload={'archive':base64.b64encode(archive.getvalue()).decode(),'archive_sha256':hashlib.sha256(archive.getvalue()).hexdigest(),'python':'3.13','pytest':'8.3.5','wheels':[],'pytest_plugins':[],'source_modules':[],'test_paths':['tests/test_fake.py']}
    checked=[];stdin=sys.stdin
    try:
        for name,exit_code,log,expected in cases:
            outputs=[]
            for program in (old,new):
                namespace={'__name__':'first_party_synthetic_observer_only'};exec(compile(program,'reviewed-operator-fixture','exec'),namespace)
                def fake(argv,**kwargs):
                    assert argv[:3]==[sys.executable,'-B','-c'] and kwargs['env']['PYTEST_DISABLE_PLUGIN_AUTOLOAD']=='1'
                    kwargs['stdout'].write(log);return SimpleNamespace(returncode=exit_code)
                namespace['subprocess']=SimpleNamespace(run=fake,STDOUT=subprocess.STDOUT);sys.stdin=io.StringIO(json.dumps(payload));outputs.append(namespace['main']())
            if expected is None:assert outputs[0]==outputs[1]
            else:
                assert outputs[1]['evaluation']['statuses']==expected
                if name=='logging_collision':assert outputs[0]['evaluation']['statuses']==raw['statuses']
            assert outputs[1]['evaluation']['exit_code']==exit_code
            assert base64.b64decode(outputs[1]['failure_log_tail_b64'])==(log[-8192:] if exit_code else b'')
            checked.append({'name':name,'passed':True})
    finally:sys.stdin=stdin
    parser=(ROOT/'integrations/assessment-runtime/swe_rebench_pytest_parser.py').read_text();assert old.startswith(parser+'\n') and new.startswith(parser+'\n')
    result={'passed':True,'whole_observer_synthetic_cases':checked,'upstream_parser_body_unchanged':True,'nonzero_exit_and_test_rows_preserved':True,'unexpected_test_ids_preserved':True,'missing_results_not_invented':True,'current_raw_malformed_status_map_reproduced_by_synthetic_log':True,'original_success_log_recovered':False,'test_children_or_upstream_subjects_executed':False,'fixture_is_not_benchmark_evidence':True}
    (HERE/'operator-observer-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
