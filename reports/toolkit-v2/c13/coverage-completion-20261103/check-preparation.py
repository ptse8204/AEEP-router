"""First-party in-memory guard and gate checks; never run a component."""
from __future__ import annotations
import ast,importlib.util,json,shutil,tempfile
from datetime import UTC,datetime,timedelta
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
spec=importlib.util.spec_from_file_location('coverage_completion',HERE/'run-completion.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
review,plan=m.verify()
assert review['hard_minimum_free_bytes']==50*1024**3
assert review['source_capacity_stop_bytes'] is None
assert review['package']['installation_digest']==m.digest(plan)
assert not (HERE/'coverage-started.json').exists()
old=Path(review['scanner_context']);parent=Path(review['parent_directory'])
assert not (old/'cli-started.json').exists() and not (parent/'package-started.json').exists()
assert not Path(plan.destination).exists()
checks=[]
for gib,expected in [(41.5,False),(49.99,False),(50.01,False),(50.02,True),(61.88,True)]:
 with patch.object(m.shutil,'disk_usage',return_value=shutil._ntuple_diskusage(100*1024**3,0,int(gib*1024**3))):
  try:m.storage_guard(review)
  except AssertionError:assert not expected
  else:assert expected
 checks.append({'guard_free_gib':gib,'accepted':expected,'actual_measurement':False})
# A >1.25GiB prior net change must not defeat the real reserve; no baseline read.
with patch.object(m.shutil,'disk_usage',return_value=shutil._ntuple_diskusage(100*1024**3,0,61*1024**3)):
 assert m.storage_guard(review)==61*1024**3
checks.append({'large_net_change_is_not_a_stop':True,'actual_measurement':False})
class Expired:
 @classmethod
 def now(cls,_tz):return datetime(2026,11,5,tzinfo=UTC)
 @classmethod
 def fromisoformat(cls,value):return datetime.fromisoformat(value)
with patch.object(m,'datetime',Expired):
 try:m.storage_guard(review)
 except AssertionError:pass
 else:raise AssertionError('Expired review accepted')
checks.append({'expired_review_rejected':True})
with tempfile.TemporaryDirectory(prefix='aeep-completion-guard-fixture-') as name:
 tmp=Path(name);(tmp/'verification').mkdir()
 record={'source_before':review['source'],'source_after':review['source'],'checks':[{'name':n,'exit_code':0} for n in m.GATES]}
 p=tmp/'verification/checks.json'
 with patch.object(m,'HERE',tmp):
  assert m.passed(review) is False
  p.write_text(json.dumps(record));assert m.passed(review) is True
  record['checks'][6]['exit_code']=125;p.write_text(json.dumps(record));assert m.passed(review) is False
  record['checks'][6]['exit_code']=0;record['source_after']='drift';p.write_text(json.dumps(record));assert m.passed(review) is False
checks.append({'missing_interrupted_and_drifted_gates_rejected':True})
node=ast.parse((HERE/'verify-remaining.py').read_text())
assignment=next(n for n in ast.walk(node) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='checks' for t in n.targets))
commands=ast.unparse(assignment.value)
assert "('pytest'," not in commands and "('coverage-tests'," in commands
assert len(assignment.value.elts)==6
assert review['source_checks_to_execute']==[n.elts[0].value for n in assignment.value.elts]
checks.append({'only_six_remaining_checks_full_pytest_not_repeated':True})
for path in [HERE/'run-completion.py',HERE/'verify-remaining.py',HERE/'prepare-review.py',HERE/'check-preparation.py']:
 compile(path.read_text(),str(path),'exec')
print(json.dumps({'passed':True,'checks':checks,'all_bound_files_match':True,'production_files_verified':len(review['production_files']),
 'source':review['source'],'original_wheel_and32_dependencies_verified':True,'component_attempts_unstarted':True,
 'execution_kind':'first_party_in_memory_substituted_capacity_and_read_only_hash_checks',
 'actual_scanner_calls':0,'actual_installs':0,'actual_docker_calls':0,'actual_grant_amendments':0,'models':0},indent=2))
