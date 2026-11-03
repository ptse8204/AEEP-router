"""Grouped component review. No installation/execution until exact approval."""
from __future__ import annotations
import argparse,asyncio,hashlib,importlib.util,json,os,shlex,shutil,subprocess,sys,time
from datetime import UTC,datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
FROZEN=Path(json.loads((HERE/'source-snapshot.json').read_text())['path'])
sys.path.insert(0,str(FROZEN/'src'))
from aeep.assessment.verification import verification_source_digest
from aeep.assessment.identity import verify_dependencies
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest,ExecutionReceipt,ExecutorSpec,SideEffect,utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import RuntimeInstallation,apply,digest,file_digest,snapshot

GATES=('compileall','schemas','assessment-policy','ruff','mypy','pytest','coverage-tests',
 'coverage-json','coverage-report','critical-coverage','assessment-coverage','toolkit-integration-fixtures','build')

def tools_state(runtime):
 files={}
 for folder in ('bin','node_modules'):
  for p in (runtime/folder).rglob('*'):
   if p.is_file():files[str(p.relative_to(runtime))]=file_digest(p)
 for name in ('operation.json','profile.sb'):files[name]=file_digest(runtime/name)
 return files


def verify():
 review=json.loads((HERE/'operation-review.json').read_bytes())
 for name,expected in review['bound_files'].items():
  if file_digest(ROOT/name)==expected:continue
  attempt=HERE/'docs-attempt-1.json'
  assert (name in review['docs']['normalized_input_hashes'] and attempt.exists()
   and not json.loads(attempt.read_bytes())['passed'] and not (HERE/'docs-complete.json').exists()
   and hashlib.sha256(b''.join((ROOT/name).read_bytes().split())).hexdigest()==review['docs']['normalized_input_hashes'][name]),name
 assert verification_source_digest(FROZEN)==review['source']
 source=json.loads((HERE/'source-snapshot.json').read_bytes())
 for name,expected in source['files'].items():assert file_digest(FROZEN/name)==expected,name
 assert verification_source_digest(ROOT)==review['source'],'Current checkout source changed'
 preparation=json.loads((HERE/'preparation/checks.json').read_bytes())
 assert preparation['source_before']==preparation['source_after']==review['source']
 assert len(preparation['checks'])==6 and all(c['exit_code']==0 for c in preparation['checks'])
 plan=RuntimeInstallation.model_validate_json((HERE/'package-installation.json').read_bytes())
 assert digest(plan)==review['package']['installation_digest']
 assert len(plan.wheels)==33
 assert plan.storage_exception is not None and plan.storage_exception.digest()==review['storage_exception_sha256']
 for wheel in plan.wheels:assert file_digest(Path(plan.wheelhouse)/wheel.filename)==wheel.sha256
 state=json.loads(Path(review['docs']['runtime_record']).read_bytes())
 assert tools_state(Path(state['runtime']))==state['files']
 command=subprocess.run(['/usr/bin/make','-n','docs-check'],cwd=ROOT,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'},capture_output=True,text=True,timeout=10,check=True)
 assert shlex.split(command.stdout.splitlines()[0])==['npx','--yes','markdownlint-cli2@0.23.3','--config','.markdownlint-cli2.jsonc','--no-globs',*review['docs']['documents']]
 assert review['cli_review_sha256']==json.loads((HERE/'cli-preview.json').read_bytes())['review_sha256']
 return review,plan


def storage_guard(review):
 exception=json.loads((HERE/'storage-exception.json').read_bytes())
 now=datetime.now(UTC)
 assert datetime.fromisoformat(exception['issued_at'].replace('Z','+00:00'))<=now<datetime.fromisoformat(exception['expires_at'].replace('Z','+00:00')),'Temporary exception is not current'
 free=shutil.disk_usage(ROOT).free
 assert ROOT.stat().st_dev==exception['filesystem_device']
 assert free>=exception['minimum_free_bytes']+review['dispatch_headroom_bytes'],'Actual capacity is below the reviewed reserve and dispatch headroom'
 baseline=HERE/'host-capacity-start.json'
 if baseline.exists():
  assert json.loads(baseline.read_bytes())['available_free_bytes']-free<=exception['maximum_additional_bytes'],'Whole-bundle net host capacity bound crossed'
 return free


def source_passed(review):
 path=HERE/'verification/checks.json'
 if not path.exists():return False
 gates=json.loads(path.read_bytes())
 return (gates['source_before']==gates['source_after']==review['source']
  and tuple(c['name'] for c in gates['checks'])==GATES
  and all(c['exit_code']==0 for c in gates['checks']))


def verification(review):
 assert not (HERE/'verification-started.json').exists(),'No automatic verification retry'
 with (HERE/'verification-started.json').open('x') as f:json.dump({'review_sha256':review['identity']},f)
 process=subprocess.run([sys.executable,str(HERE/'verify-current-source.py'),'--approved-review',review['identity']],
  cwd=ROOT,env=dict(os.environ,PYTHONPATH=str(FROZEN/'src'),PYTHONDONTWRITEBYTECODE='1'),timeout=3700)
 return {'passed':process.returncode==0 and source_passed(review),'exit_code':process.returncode}


async def package_command(review,name,argv,payload,seconds):
 work=HERE/'package-execution/work';runtime=Path(review['package']['runtime'])
 spec=ExecutorSpec(id='toolkit.installed-'+name,capability='toolkit.upstream-engineering@1',description='Exact installed ordinary-workflow checks; no models/upstream scanner',
  kind='command',side_effect='write',config={'argv':['/usr/bin/sandbox-exec','-f',str(HERE/'package.sb'),str(runtime/'bin/python'),'-I','-B',*argv],
   'argv_literal':True,'inherit_env':False,'stdin_json':True,'cwd':str(work),'timeout_seconds':seconds,'max_output_bytes':1048576,'output':{'type':'json'},
   'env':{'PATH':'/usr/bin:/bin','HOME':str(work/'home'),'TMPDIR':str(work/'tmp'),'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','LC_ALL':'C'}})
 action=ActionRequest(capability=spec.capability,input=payload)
 context=ExecutionContext(request=action,spec=spec,estimate=spec.estimate,attempt=1,approved_side_effect=SideEffect.WRITE)
 executor=CommandExecutor();began=utc_now();raw=None
 try:raw=await(await executor.start(context)).task
 finally:await executor.close()
 receipt=ExecutionReceipt(decision_id='workflow-installed-'+name,action_id=action.action_id,capability=spec.capability,executor_id=spec.id,
  executor_kind=spec.kind,status=raw.status,started_at=began,ended_at=utc_now(),estimated=spec.estimate,actual_resources=raw.resources,
  accounting=raw.accounting,execution_success=raw.status.value=='success',error_type=raw.error_type,metadata={'review_sha256':review['identity'],**raw.metadata})
 with ReceiptStore(HERE/'package-execution/receipts.sqlite3') as store:store.save_receipt(receipt)
 (HERE/'package-execution'/('receipt-'+name+'.json')).write_text(receipt.model_dump_json(indent=2)+'\n')
 (HERE/'package-execution'/('process-'+name+'.json')).write_text(json.dumps({'stdout':(raw.stdout or '')[:8192],'stderr':(raw.stderr or '')[:8192]},indent=2)+'\n')
 if isinstance(raw.output,dict):(HERE/'package-execution'/('result-'+name+'.json')).write_text(json.dumps(raw.output,indent=2)+'\n')
 assert raw.status.value=='success' and raw.output.get('passed'), 'Installed '+name+' failed; retain resources and receipt'
 return raw.output


def package(review,plan):
 if shutil.disk_usage(ROOT).free<plan.storage_exception.minimum_free_bytes+review['minimum_headroom_bytes']:
  return {'passed':False,'status':'SPACE_BLOCKED','execution_started':False,'attempt_consumed':False,'required_free_bytes':plan.storage_exception.minimum_free_bytes+review['minimum_headroom_bytes']}
 with (HERE/'package-started.json').open('x') as f:json.dump({'review_sha256':review['identity']},f)
 work=HERE/'package-execution/work'
 assert snapshot(work)==review['package']['prepared_workspace_sha256'],'Preserve changed preparation workspace'
 clock=time.monotonic();result={'passed':False,'models':0,'runtime_retained':True}
 try:
  state=apply(plan,digest(plan));assert apply(plan,digest(plan))==state
  (HERE/'package-execution/installation.json').write_text(json.dumps(state,indent=2)+'\n')
  baseline=snapshot(Path(plan.destination))
  for name in ('package-check.py','package-boundary.py'):shutil.copyfile(HERE/name,work/name)
  result['boundary']=asyncio.run(package_command(review,'boundary',[str(work/'package-boundary.py')],{
   'outside_canary':str(HERE/'package-check.py'),'workspace':str(work)},20))
  assert snapshot(Path(plan.destination))==baseline
  result['installed']=asyncio.run(package_command(review,'source-cli',[str(work/'package-check.py')],{
   'installed_source':review['package']['installed_source'],
   'scanner_runtime':json.loads((HERE/'scanner-runtime.json').read_bytes())},60))
  assert snapshot(Path(plan.destination))==baseline
  result.update(passed=True,runtime_unchanged=True)
 except BaseException as error:result['error_type']=type(error).__name__
 finally:
  result['wall_seconds']=time.monotonic()-clock
  (HERE/'package-execution/summary.json').write_text(json.dumps(result,indent=2)+'\n')
 return result


def docs(review):
 prior=list(HERE.glob('docs-attempt-*.json'));assert len(prior)<2 and not (HERE/'docs-complete.json').exists()
 number=1+len(prior);path=HERE/f'docs-attempt-{number}.json'
 runtime=Path(review['docs']['runtime']);state=json.loads(Path(review['docs']['runtime_record']).read_bytes())
 assert tools_state(runtime)==state['files']
 result={'review_sha256':review['identity'],'attempt':number,'passed':False,'models':0,'network':False,
  'input_hashes':{name:file_digest(ROOT/name) for name in review['docs']['documents']}}
 with path.open('x') as f:json.dump(result,f,indent=2)
 clock=time.monotonic()
 try:
  env={'PATH':str(runtime/'bin')+':/usr/local/bin:/usr/bin:/bin','HOME':str(runtime/'home'),'TMPDIR':str(runtime/'tmp'),'LC_ALL':'C'}
  with (HERE/f'docs-attempt-{number}.log').open('x') as log:
   completed=subprocess.run(['/usr/bin/make','docs-check','LYCHEE='+str(runtime/'bin/lychee-sandbox')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
  result.update(passed=completed.returncode==0,exit_code=completed.returncode)
  assert tools_state(runtime)==state['files']
  assert all(file_digest(ROOT/name)==value for name,value in result['input_hashes'].items())
  result['tools_unchanged']=True
 except BaseException as error:result.update(passed=False,error_type=type(error).__name__)
 finally:
  result['wall_seconds']=time.monotonic()-clock;path.write_text(json.dumps(result,indent=2)+'\n')
  if result['passed']:(HERE/'docs-complete.json').write_text(json.dumps({'attempt':number,'review_sha256':review['identity']})+'\n')
 return {k:v for k,v in result.items() if k!='input_hashes'}


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--execute-approved');parser.add_argument('--component',choices=('all','verification','scanner','package','docs'),default='all');args=parser.parse_args()
 review,plan=verify();identity=file_digest(HERE/'operation-review.json');review['identity']=identity
 if args.execute_approved is None:
  print(json.dumps({'review_sha256':identity,'execution':False,'source_checks_prepared':6,'full_source_checks_passed':source_passed(review)}));return
 assert args.execute_approved==identity
 approval=json.loads((HERE/'operator-approval.json').read_bytes());assert approval['approved'] is True and approval['review_sha256']==identity
 free=storage_guard(review)
 if not (HERE/'host-capacity-start.json').exists():
  with (HERE/'host-capacity-start.json').open('x') as f:json.dump({'review_sha256':identity,'observed_at':datetime.now(UTC).isoformat(),'available_free_bytes':free},f)
 results={}
 if args.component in ('all','verification'):results['verification']=verification(review)
 source_ok=source_passed(review)
 if args.component in ('all','scanner','package') and not source_ok:
  results['scanner']={'passed':False,'status':'SOURCE_GATES_BLOCKED','execution_started':False}
  results['package']={'passed':False,'status':'SOURCE_GATES_BLOCKED','execution_started':False}
 if source_ok and args.component in ('all','scanner'):
  # Image inspection reads daemon metadata only; never pulls or starts unrelated resources.
  try:
   verify();storage_guard(review);runtime_definition=json.loads((HERE/'scanner-runtime.json').read_text())
   verify_dependencies(runtime_definition['executable_dependencies'])
   environment=runtime_definition['environment']
   usage=subprocess.run([environment['container_runtime'],'--host','unix://'+environment['container_socket'],'system','df','--format','json'],capture_output=True,text=True,timeout=30,check=True)
   (HERE/'docker-before.json').write_text(usage.stdout)
   verify_dependencies(runtime_definition['executable_dependencies'])
   image=subprocess.run([environment['container_runtime'],'--host','unix://'+environment['container_socket'],'image','inspect',environment['container_image']],capture_output=True,text=True,timeout=20,check=True)
   assert json.loads(image.stdout)[0]['Id']==review['scanner_image']
   spec=importlib.util.spec_from_file_location('reviewed_scanner_cli',HERE/'run-cli.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
   results['scanner']=module.run(review,identity)
  except BaseException as error:
   results['scanner']={'passed':False,'error_type':type(error).__name__,'automatic_retry':False}
 uncertain=results.get('scanner',{}).get('accounting_uncertain') or results.get('scanner',{}).get('cleanup_uncertain')
 if uncertain:
  results['common_stop']='Unresolved scanner accounting or cleanup; preserve all components'
 else:
  if source_ok and args.component in ('all','package'):
   verify();storage_guard(review);results['package']=package(review,plan)
  if args.component in ('all','docs'):
   verify();storage_guard(review);results['docs']=docs(review)
 with (HERE/f'run-{time.time_ns()}.json').open('x') as f:json.dump(results,f,indent=2)
 print(json.dumps(results))

if __name__=='__main__':main()
