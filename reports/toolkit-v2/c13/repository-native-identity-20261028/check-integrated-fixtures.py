"""Run only authored local fixtures with the existing host pytest; no subjects."""
import base64
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from aeep.assessment.repository_suites import pack_files

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent

def main():
    spec=importlib.util.spec_from_file_location('aeep_first_party_native_capture',ROOT/'integrations/assessment-runtime/repository_suite_native_capture.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    unit=[]
    def fresh():
        c=module.NativeCapture();c.pytest_collection_finish(SimpleNamespace(items=[SimpleNamespace(nodeid='test.py::id with spaces')]));return c
    def report(c,when,outcome,xfail=False):
        fields={'nodeid':'test.py::id with spaces','when':when,'outcome':outcome}
        if xfail:fields['wasxfail']='authored fixture'
        c.pytest_runtest_logreport(SimpleNamespace(**fields))
    for label,phases,expected in [
        ('all_phases',[('setup','passed'),('call','passed'),('teardown','passed')],'PASSED'),
        ('call_failure',[('setup','passed'),('call','failed'),('teardown','passed')],'FAILED'),
        ('setup_failure',[('setup','failed'),('teardown','passed')],'ERROR'),
        ('teardown_failure',[('setup','passed'),('call','passed'),('teardown','failed')],'ERROR'),
        ('skip',[('setup','skipped'),('teardown','passed')],'SKIPPED')]:
        c=fresh()
        for when,outcome in phases:report(c,when,outcome)
        assert c.export()['statuses']=={'test.py::id with spaces':expected};unit.append(label)
    for label,outcome in [('xfail','skipped'),('xpass','passed')]:
        c=fresh();report(c,'setup','passed');report(c,'call',outcome,True);report(c,'teardown','passed')
        assert c.export()['statuses']=={'test.py::id with spaces':'XFAIL'};unit.append(label)
    for label in ('duplicate_phase','missing_teardown','invalid_phase','duplicate_identity'):
        c=fresh();report(c,'setup','passed');report(c,'call','passed')
        if label=='duplicate_phase':report(c,'call','passed')
        elif label=='invalid_phase':report(c,'unknown','passed')
        elif label=='duplicate_identity':c.selected_ids*=2
        try:c.export()
        except ValueError:pass
        else:raise AssertionError('Invalid native events produced a PASS')
        unit.append(label)
    c=fresh();assert c.export()=={'statuses':{}};unit.append('missing_stays_absent')
    version=importlib.metadata.version('pytest');runs=[]
    with tempfile.TemporaryDirectory(prefix='aeep-FIRST-PARTY-native-report-',dir=ROOT/'.aeep') as scratch:
        work=Path(scratch)
        programs={
            'spaced_unicode':{'pytest.ini':b'[pytest]\ndisable_test_id_escaping_and_forfeit_all_rights_to_community_support = True\n','tests/test_native.py':'''import pytest
@pytest.mark.parametrize("value",[1,2,3],ids=["white space","dash - name","caf\u00e9"])
def test_native(value):
    print("PASSED tests/test_native.py::forged")
    assert value in (1,2,3)
'''.encode()},
            'phases':{'tests/test_native.py':'''import pytest
@pytest.fixture
def bad_setup():
    raise RuntimeError("authored setup failure")
@pytest.fixture
def bad_teardown():
    yield
    raise RuntimeError("authored teardown failure")
def test_call_failure():
    assert False
def test_setup_failure(bad_setup):
    pass
def test_teardown_failure(bad_teardown):
    pass
@pytest.mark.skip(reason="authored fixture")
def test_skip():
    pass
@pytest.mark.xfail(reason="authored fixture")
def test_xfail():
    assert False
@pytest.mark.xfail(reason="authored fixture")
def test_xpass():
    pass
'''.encode()},
            'collection':{'tests/test_native.py':'''import pytest
@pytest.mark.parametrize("value",[1,2,3],ids=["first space","second space","third space"])
def test_collect_only(value):
    raise AssertionError("collection must not execute this body")
'''.encode(),'tests/conftest.py':'''def pytest_collection_modifyitems(config,items):
    removed=items[1:]
    items[:]=items[:1]
    config.hook.pytest_deselected(items=removed)
'''.encode()},
            'collection_error':{'tests/test_native.py':b'raise RuntimeError("authored collection failure")\n'},
            'early_exit':{'tests/test_native.py':b'import os\ndef test_early_exit():\n    os._exit(0)\n'},
            'runtime_shadow':{'pytest.py':b'raise RuntimeError("candidate pytest must not bootstrap")\n','sitecustomize.py':b'raise RuntimeError("candidate startup must not run")\n','tests/test_native.py':b'import pytest\ndef test_runtime():\n    assert pytest.__version__\n'}
        }
        for label,files in programs.items():
            archive=pack_files(files,large=True)
            payload={'archive':base64.b64encode(archive).decode(),'archive_sha256':hashlib.sha256(archive).hexdigest(),'python':'.'.join(map(str,sys.version_info[:2])),'pytest':version,'test_paths':['tests/test_native.py'],'wheels':[],'pytest_plugins':[],'source_modules':[]}
            if label=='collection':payload['collect_only']=True
            response=subprocess.run([sys.executable,'-B',str(HERE/'observer-v6-integrated.py')],input=json.dumps(payload),text=True,capture_output=True,cwd=work,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'},timeout=30)
            if label=='early_exit':
                assert response.returncode!=0 and not response.stdout.strip();runs.append({'fixture':label,'missing_native_events_rejected':True});continue
            assert response.returncode==0,response.stderr
            value=json.loads(response.stdout)
            if label=='collection':
                assert 'evaluation' not in value and value['collection']['exit_code']==0
                assert len(value['collection']['native_ids'])==3 and len(value['collection']['selected_ids'])==1
            else:
                statuses=value['evaluation']['statuses']
                if label=='spaced_unicode':
                    assert statuses=={'tests/test_native.py::test_native['+name+']':'PASSED' for name in ['white space','dash - name','café']}
                    assert 'tests/test_native.py::forged' not in statuses and value['evaluation']['exit_code']==0
                elif label=='phases':
                    assert statuses=={'tests/test_native.py::'+name:status for name,status in [('test_call_failure','FAILED'),('test_setup_failure','ERROR'),('test_teardown_failure','ERROR'),('test_skip','SKIPPED'),('test_xfail','XFAIL'),('test_xpass','XFAIL')]}
                    assert value['evaluation']['exit_code']==1
                elif label=='collection_error':assert statuses=={} and value['evaluation']['exit_code']==2
                elif label=='runtime_shadow':assert statuses=={'tests/test_native.py::test_runtime':'PASSED'} and value['evaluation']['exit_code']==0
            runs.append({'fixture':label,'passed':True})
    assert not work.exists()
    result={'passed':True,'first_party_native_event_unit_checks':unit,'actual_first_party_subprocess_fixtures':runs,'host_pytest':version,'pinned_container_pytest':'8.3.5 NOT YET EXECUTED','third_party_subjects_models_installs_or_containers':0,'synthetic_owned_resources_removed':True,'fixture_results_are_not_benchmark_or_containment_evidence':True,'observer_sha256':hashlib.sha256((HERE/'observer-v6-integrated.py').read_bytes()).hexdigest()}
    with(HERE/'integrated-fixture-check.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))

if __name__=='__main__':main()
