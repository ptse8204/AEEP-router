"""One explicit source-harness continuation; reuse the unstarted reviewed package."""
from __future__ import annotations
import argparse,importlib.util,json,os,shutil,subprocess,sys,time
from datetime import UTC,datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
FROZEN=Path(json.loads((HERE/'source-snapshot.json').read_text())['path'])
sys.path.insert(0,str(FROZEN/'src'))
from aeep.assessment.verification import verification_source_digest
from aeep.assessment.identity import verify_dependencies
from aeep_toolkit.install_runtime import RuntimeInstallation,digest,file_digest,snapshot as tree_snapshot

GATES=('compileall','schemas','assessment-policy','ruff','mypy','pytest','coverage-tests',
 'coverage-json','coverage-report','critical-coverage','assessment-coverage','toolkit-integration-fixtures','build')

def load_module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def verify():
 review=json.loads((HERE/'operation-review.json').read_bytes())
 for name,expected in review['bound_files'].items():assert file_digest(ROOT/name)==expected,name
 assert verification_source_digest(ROOT)==verification_source_digest(FROZEN)==review['source']
 snapshot=json.loads((HERE/'source-snapshot.json').read_bytes())
 for name,expected in snapshot['files'].items():assert file_digest(FROZEN/name)==expected,name
 prepared=json.loads((HERE/'preparation/checks.json').read_bytes())
 assert prepared['source_before']==prepared['source_after']==review['source']
 assert len(prepared['checks'])==6 and all(x['exit_code']==0 for x in prepared['checks'])
 parent=Path(review['parent_directory'])
 plan=RuntimeInstallation.model_validate_json((parent/'package-installation.json').read_bytes())
 assert digest(plan)==review['package']['installation_digest']
 for wheel in plan.wheels:assert file_digest(Path(plan.wheelhouse)/wheel.filename)==wheel.sha256
 for name,expected in review['production_files'].items():assert file_digest(ROOT/name)==expected,name
 old_source=Path(json.loads((parent/'source-snapshot.json').read_bytes())['path'])
 for name,expected in review['production_files'].items():assert file_digest(old_source/name)==expected,name
 assert not (parent/'package-started.json').exists() or (parent/'package-execution/summary.json').exists(),'Inspect interrupted package; never repeat it'
 if not (parent/'package-started.json').exists():
  assert tree_snapshot(parent/'package-execution/work')==review['package']['prepared_workspace_sha256'],'Preserve changed package workspace'
 return review,plan

def storage_guard(review, *, source_only=False):
 exception=json.loads((HERE/'storage-exception.json').read_bytes());now=datetime.now(UTC)
 assert datetime.fromisoformat(exception['issued_at'].replace('Z','+00:00'))<=now<datetime.fromisoformat(exception['expires_at'].replace('Z','+00:00'))
 assert ROOT.stat().st_dev==exception['filesystem_device']
 free=shutil.disk_usage(ROOT).free
 minimum=review['source_minimum_free_bytes'] if source_only else exception['minimum_free_bytes']
 assert free>=minimum+16*1024**2
 start=HERE/'host-capacity-start.json'
 if start.exists():assert json.loads(start.read_bytes())['available_free_bytes']-free<=review['source_capacity_stop_bytes']
 return free

def passed(review):
 path=HERE/'verification/checks.json'
 if not path.exists():return False
 record=json.loads(path.read_bytes())
 return (record['source_before']==record['source_after']==review['source']
  and tuple(x['name'] for x in record['checks'])==GATES and all(x['exit_code']==0 for x in record['checks']))

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--execute-approved');parser.add_argument('--component',choices=('all','verification','scanner','package'),default='all');args=parser.parse_args()
 review,plan=verify();identity=file_digest(HERE/'operation-review.json');review['identity']=identity
 if args.execute_approved is None:
  print(json.dumps({'review_sha256':identity,'execution':False,'source_gates_passed':passed(review),'package_artifact_unchanged':True}));return
 approval=json.loads((HERE/'operator-approval.json').read_bytes())
 assert args.execute_approved==identity and approval['approved'] is True and approval['review_sha256']==identity
 free=storage_guard(review,source_only=args.component in ('all','verification'))
 if not (HERE/'host-capacity-start.json').exists():
  with (HERE/'host-capacity-start.json').open('x') as f:json.dump({'review_sha256':identity,'observed_at':datetime.now(UTC).isoformat(),'available_free_bytes':free,'scope':'Fresh explicitly approved source attempt; old samples and all assessment counters retained.'},f)
 results={}
 if args.component in ('all','verification'):
  with (HERE/'verification-started.json').open('x') as f:json.dump({'review_sha256':identity},f)
  process=subprocess.run([sys.executable,str(HERE/'verify-current-source.py'),'--approved-review',identity],cwd=ROOT,
   env=dict(os.environ,PYTHONPATH=str(FROZEN/'src'),PYTHONDONTWRITEBYTECODE='1'),timeout=3700)
  results['verification']={'passed':process.returncode==0 and passed(review),'exit_code':process.returncode}
 source_ok=passed(review)
 if source_ok and args.component in ('all','scanner'):
  try:
   verify();storage_guard(review)
   runtime=json.loads((HERE/'scanner-runtime.json').read_bytes());verify_dependencies(runtime['executable_dependencies'])
   environment=runtime['environment'];command=[environment['container_runtime'],'--host','unix://'+environment['container_socket']]
   usage=subprocess.run([*command,'system','df','--format','json'],capture_output=True,text=True,timeout=30,check=True)
   (HERE/'docker-before.json').write_text(usage.stdout)
   image=json.loads(subprocess.run([*command,'image','inspect',environment['container_image']],capture_output=True,text=True,timeout=20,check=True).stdout)[0]
   assert image['Id']==review['scanner_image'];verify_dependencies(runtime['executable_dependencies'])
   module=load_module('current_scanner_driver',HERE/'run-cli.py');results['scanner']=module.run(review,identity)
  except BaseException as error:
   results['scanner']={'passed':False,'error_type':type(error).__name__,'automatic_retry':False,
    'accounting_uncertain':(HERE/'cli-started.json').exists() and not (HERE/'cli-execution/summary.json').exists()}
 uncertain=results.get('scanner',{}).get('accounting_uncertain') or results.get('scanner',{}).get('cleanup_uncertain')
 if uncertain:results['common_stop']='Unresolved scanner accounting or ownership'
 elif source_ok and args.component in ('all','package'):
  verify();storage_guard(review)
  parent=Path(review['parent_directory']);assert not (parent/'package-started.json').exists(),'Parent package attempt was consumed; no retry'
  # Exact parent wheel, dependencies, programs, workspace and sandbox remain in use.
  module=load_module('reviewed_parent_package',parent/'run-review.py');results['package']=module.package(review,plan)
 if not source_ok:results['unstarted_components']='SOURCE_GATES_BLOCKED'
 with (HERE/f'run-{time.time_ns()}.json').open('x') as f:json.dump(results,f,indent=2)
 print(json.dumps(results))

if __name__=='__main__':main()
