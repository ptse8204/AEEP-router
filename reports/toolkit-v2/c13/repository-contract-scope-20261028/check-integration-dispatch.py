"""Exercise actual bundle dispatch/stop logic with child execution fully replaced."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if (HERE/'approval-bundle.json').exists():original=json.loads((HERE/'approval-bundle.json').read_text())
    else:
        components={}
        for name,folder,review_file,driver,result,passed,timeout in [
            ('runtime',HERE,'operation-review.json','run-runtime.py','completion-audit.json','batch_completed',1000),
            ('docs',ROOT/'reports/toolkit-v2/integration-completion/lychee-contract-scope-review-20261028','operation-review.json','run-review.py','execution-result.json','passed',600)]:
            components[name]={'directory':str(folder),'review_file':review_file,'review_sha256':sha(folder/review_file),'argv':[str(folder/driver)],'maximum_driver_seconds':timeout,'result_file':result,'passed_field':passed}
        from aeep.assessment.verification import verification_source_digest
        original={'source_digest':verification_source_digest(ROOT),'assets':{},'components':components,'host_canary':json.loads((HERE/'operation-review.json').read_text())['host_canary'],'SYNTHETIC_FIXTURE_ONLY':True}
    checks=[]
    for mode in ('pass','runtime_uncertain','docs_failure','timeout'):
        with tempfile.TemporaryDirectory(prefix='aeep-SYNTHETIC-dispatch-only-',dir=ROOT/'.aeep') as temp:
            fixture=Path(temp);bundle=copy.deepcopy(original)
            for name,component in bundle['components'].items():
                directory=fixture if name=='runtime' else fixture/name;directory.mkdir(exist_ok=True)
                source=Path(component['directory'])/component['review_file']
                (directory/component['review_file']).write_bytes(source.read_bytes())
                component['directory']=str(directory)
            path=fixture/'approval-bundle.json';path.write_text(json.dumps(bundle))
            (fixture/'bundle-operator-approval.json').write_text(json.dumps({'approved':True,'review_sha256':sha(path),'operator_text':'SYNTHETIC FIXTURE ONLY; no user approval or execution authority'}))
            spec=importlib.util.spec_from_file_location('synthetic_dispatch_'+mode,HERE/'run-integration-bundle.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            module.HERE=fixture
            calls=[]
            def fake(argv,**kwargs):
                name=('runtime','docs')[len(calls)];calls.append(name)
                component=bundle['components'][name]
                assert argv[:2]==[sys.executable,component['argv'][0]]
                assert kwargs['cwd']==ROOT and kwargs['stdin']==subprocess.DEVNULL
                assert kwargs['timeout']==component['maximum_driver_seconds']
                assert sha(Path(component['directory'])/component['review_file'])==component['review_sha256']
                if name=='package':assert argv[-2]=='--execute-reviewed-digest'
                else:assert argv[-1]==component['review_sha256']
                if mode=='timeout':raise subprocess.TimeoutExpired(argv,1)
                target=Path(component['directory'])/component['result_file'];target.parent.mkdir(parents=True,exist_ok=True)
                passed=not (mode=='runtime_uncertain' and name=='runtime' or mode=='docs_failure' and name=='docs')
                target.write_text(json.dumps({component['passed_field']:passed}))
                if name=='runtime' and passed:
                    (fixture/'completion-audit.json').write_text(json.dumps({'batch_completed':True,'all_owned_containers_absent':True,'physical_receipt_integrity_passed':True}))
                    (fixture/'canary-cleanup.json').write_text(json.dumps({'unchanged_owned_canary_removed':True}))
                return SimpleNamespace(returncode=0 if passed else 1)
            module.subprocess=SimpleNamespace(run=fake,DEVNULL=subprocess.DEVNULL,STDOUT=subprocess.STDOUT)
            previous=sys.argv;sys.argv=['SYNTHETIC-no-authority',sha(path)]
            try:
                try:module.main()
                except (AssertionError,subprocess.TimeoutExpired):
                    assert mode in ('runtime_uncertain','timeout')
                else:assert mode in ('pass','docs_failure')
            finally:sys.argv=previous
            result=json.loads((fixture/'bundle-execution-result.json').read_text())
            assert calls==(['runtime'] if mode in ('runtime_uncertain','timeout') else ['runtime','docs'])
            assert result['all_components_passed']==(mode=='pass')
            assert result['source_unchanged'] and result['models']==0 and result['automatic_retry'] is False
            checks.append({'mode':mode,'observed_dispatch':calls,'passed':True})
        assert not fixture.exists()
    value={'passed':True,'actual_driver_fixture_checks':checks,'subprocess_dispatch_replaced_before_main':True,'new_containers_installs_or_third_party_execution':0,'synthetic_resources_removed':True,'fixture_is_not_authority_or_benchmark':True}
    (HERE/'integration-dispatch-check.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))


if __name__=='__main__':main()
