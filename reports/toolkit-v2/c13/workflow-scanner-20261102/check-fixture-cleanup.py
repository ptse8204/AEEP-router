"""Check cleanup keeps failures/skips and cannot turn an assertion failure into success."""
import json,os,subprocess,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
with tempfile.TemporaryDirectory(prefix='aeep-cleanup-hook-fixture-') as temp:
 work=Path(temp).resolve();test=work/'test_owned_cleanup.py';record=work/'cleanup.json'
 test.write_text('''import os,pytest
from pathlib import Path

def test_pass(tmp_path,monkeypatch):
    (tmp_path/'fixture.txt').write_text('owned')
    monkeypatch.setattr(os,'open',lambda *args,**kwargs:pytest.fail('denied open before hook restoration'))

def test_fail(tmp_path):
    (tmp_path/'retain.txt').write_text('owned failed fixture')
    assert False, 'intentional first-party failure'

def test_skip(tmp_path):
    (tmp_path/'retain.txt').write_text('owned skipped fixture')
    pytest.skip('intentional first-party skip')
''')
 env=dict(os.environ,PYTHONPATH=str(HERE)+':'+str(ROOT/'src'),AEEP_FIXTURE_CLEANUP_RECORD=str(record))
 result=subprocess.run([sys.executable,'-m','pytest','-q','-p','aeep_fixture_cleanup','-o','tmp_path_retention_policy=all',str(test)],
  cwd=work,env=env,capture_output=True,text=True,timeout=30)
 data=json.loads(record.read_text())
 assert result.returncode==1 and 'intentional first-party failure' in result.stdout
 assert len(data['removed'])==1 and len(data['kept'])==2
 assert all(not Path(p).exists() for p in data['removed'])
 assert all((Path(p)/'retain.txt').is_file() for p in data['kept'])
 (HERE/'fixture-cleanup-check.json').write_text(json.dumps({'passed':True,'evidence_kind':'first_party_controls',
  'expected_subprocess_exit_code':1,'intentional_failed_assertion_preserved':True,'passing_denial_hook_restored_before_cleanup':True,
  'failed_and_skipped_fixture_retained':True,'upstream_executed':False},indent=2)+'\n')
print('Cleanup control passed: expected assertion failure stays failed; skip/failure data retained.')
