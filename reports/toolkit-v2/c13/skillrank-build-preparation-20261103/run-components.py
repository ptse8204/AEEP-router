"""Independent installed-wheel and offline-doc components of the exact review."""
from __future__ import annotations
import argparse,asyncio,hashlib,importlib.util,json,os,shlex,shutil,subprocess,sys,time
from datetime import UTC,datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'src'))
from aeep.assessment.verification import verification_source_digest
from aeep.assessment.identity import verify_dependencies
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest,ExecutionReceipt,ExecutorSpec,SideEffect,utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import RuntimeInstallation,apply,digest,file_digest,snapshot


def tools_state(runtime):
 files={}
 for folder in ('bin','node_modules'):
  for p in (runtime/folder).rglob('*'):
   if p.is_file():files[str(p.relative_to(runtime))]=file_digest(p)
 for name in ('operation.json','profile.sb'):files[name]=file_digest(runtime/name)
 return files


def verify():
 from datetime import datetime, UTC
 review=json.loads((HERE/'operation-review.json').read_bytes())
 for path,target in review.get('executable_links',{}).items():assert str(Path(path).resolve(strict=True))==target
 assert datetime.now(UTC)<datetime.fromisoformat(review['expires_at'].replace('Z','+00:00'))
 for path,expected in review['assets'].items():assert file_digest(Path(path))==expected,path
 assert verification_source_digest(ROOT)==review['source']
 checks=json.loads(Path(review['source_checks']).read_bytes())
 assert checks['source_before']==checks['source_after']==review['source']
 assert len(checks['checks'])==13 and all(row['exit_code']==0 for row in checks['checks'])
 if (HERE/'runtime-started.json').exists():
  summary=HERE/'runtime-execution/summary.json'
  assert summary.exists(),'Started runtime needs reconciliation before independent dispatch'
  result=json.loads(summary.read_bytes())
  assert not result.get('cleanup_uncertain') and not result.get('accounting_uncertain'),'Common uncertainty blocks dispatch'
 assert tools_state(Path(review['docs']['runtime']))==json.loads(Path(review['docs']['runtime_record']).read_bytes())['files']
 verify_dependencies(review['docs']['executable_dependencies'])
 plan=RuntimeInstallation.model_validate_json((HERE/'package-installation.json').read_bytes())
 assert digest(plan)==review['package']['installation_digest'] and len(plan.wheels)==33 and plan.storage_exception is None
 for wheel in plan.wheels:assert file_digest(Path(plan.wheelhouse)/wheel.filename)==wheel.sha256
 return review,plan
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
 if shutil.disk_usage(ROOT).free<50*1024**3+review['package']['required_bytes']:
  return {'passed':False,'status':'SPACE_BLOCKED','execution_started':False,'attempt_consumed':False,'required_free_bytes':50*1024**3+review['package']['required_bytes']}
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
   'installed_source':review['package']['installed_source']},60))
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
 parser=argparse.ArgumentParser();parser.add_argument('--execute-approved');parser.add_argument('--component',choices=('package','docs'),required=True);args=parser.parse_args()
 review,plan=verify();identity=file_digest(HERE/'operation-review.json');review['identity']=identity
 if args.execute_approved is None:
  print(json.dumps({'review_sha256':identity,'execution':False,'component':args.component}));return
 approval=json.loads((HERE/'operator-approval.json').read_bytes())
 assert args.execute_approved==identity==approval['review_sha256'] and approval['approved'] is True
 # A known failed worker check does not consume these independent component attempts.
 result=package(review,plan) if args.component=='package' else docs(review)
 print(json.dumps(result))
 if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
