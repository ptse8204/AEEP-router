"""Driver and protocol checks with explicit first-party subprocess substitutes."""
import asyncio,importlib.util,json,shutil,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
spec=importlib.util.spec_from_file_location('scanner_review_driver',HERE/'run.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
from aeep.models import RawExecution
context=json.loads((HERE/'context.json').read_bytes())
source='e363cfa5ada2201e355b1e4528ff36cb2d05a08fff7423912c6d5e163ea43dfb'
review={'source':source,'output_tag':'aeep-toolkit-v2/scanner:2.2.1-review-20261102','execution_headroom_bytes':2*1024**3}
image={'Id':'sha256:'+'f'*64,'RootFS':{'Layers':['parent','scanner']},'Config':{'User':'65532:65532'}}
parent={'Id':context['parent_id'],'RootFS':{'Layers':['parent']}}
stage=ROOT/'.aeep/scanner-driver-preparation-4-20261102';stage.mkdir()
async def scenario(name,fail_scan=False,ownership_changed=False,existing_name=False,owned_lingering=False):
 folder=stage/name;folder.mkdir();(folder/'operation-review.json').write_text(json.dumps({'synthetic':name}))
 shutil.copyfile(HERE/'boundary.py',folder/'boundary.py')
 shutil.copyfile(HERE/'context.json',folder/'context.json')
 calls=[];inspection_count={};stopped=False
 class Executor:
  async def start(self,execution):
   argv=execution.spec.config['argv'];assert execution.spec.description
   nonlocal stopped
   key=execution.spec.id.removeprefix('toolkit.scanner-');calls.append(key)
   if key=='build':
    assert '--network=none' in argv and '--pull=false' in argv
    value='synthetic image build'
   elif key=='boundary':
    assert '--read-only' in argv and '--cap-drop' in argv and '--network' in argv
    value={'passed':True,'worker_sha256':context['assets']['scanner_worker.py']}
   elif key in ('selected-candidate','static-negative-control'):
    payload=execution.request.input
    value={'candidate_sha256':payload['candidate_sha256'],'candidate_bytes_bound':True,
           'analyzers_executed':1,'safety_verdict':'NOT_ESTABLISHED','findings_count':1 if key=='static-negative-control' else 0}
   elif key=='stop-owned' and owned_lingering:
    stopped=True;value='owned-container-stopped'
   else:raise AssertionError('ownership change must never authorize cleanup')
   async def finish():return RawExecution(status='failed' if fail_scan and key=='selected-candidate' else 'success',output=value,
      metadata={'evidence_kind':'synthetic_driver_fixture'})
   return SimpleNamespace(task=asyncio.create_task(finish()))
  async def close(self):pass
 def readonly(args):
  if args[0:2]==['image','inspect']:return json.dumps([parent if args[2]==context['parent_tag'] else image])
  if args[0:2]==['system','df']:return '[]'
  raise AssertionError(args)
 def subprocess_run(argv,**kwargs):
  assert argv[:len(module.DOCKER)]==module.DOCKER
  assert argv[len(module.DOCKER):len(module.DOCKER)+2]==['container','inspect']
  container_name=argv[-1];inspection_count[container_name]=inspection_count.get(container_name,0)+1
  if owned_lingering and inspection_count[container_name]>1 and not stopped:
   record={'Config':{'Labels':{'aeep.review':'scanner-runtime-20261102'}},'Image':image['Id'],'State':{'Running':True},'Id':'owned-container'}
   return SimpleNamespace(returncode=0,stdout=json.dumps([record]),stderr='')
  if existing_name or ownership_changed and inspection_count[container_name]>1:
   record={'Config':{'Labels':{'aeep.review':'UNRELATED_WORK'}},'Image':image['Id'],'State':{'Running':False},'Id':'unrelated-container'}
   return SimpleNamespace(returncode=0,stdout=json.dumps([record]),stderr='')
  return SimpleNamespace(returncode=1,stdout='',stderr='Error: No such container')
 with pytest.MonkeyPatch.context() as patch:
  patch.setattr(module,'HERE',folder);patch.setattr(module,'CommandExecutor',Executor)
  patch.setattr(module,'readonly',readonly);patch.setattr(module,'subprocess',SimpleNamespace(run=subprocess_run))
  result=await module.execute(review,context)
 assert result['passed'] is not (fail_scan or ownership_changed or existing_name),result
 if not owned_lingering:assert 'stop-owned' not in calls and 'remove-owned' not in calls
 if owned_lingering:assert calls==['build','boundary','selected-candidate','static-negative-control','stop-owned']
 elif fail_scan:assert calls==['build','boundary','selected-candidate']
 elif existing_name:assert calls==['build']
 else:assert calls==['build','boundary','selected-candidate','static-negative-control']
 return {'case':name,'passed':True,'synthetic_calls':calls,'upstream_executed':False,'docker_mutated':False}
results=[asyncio.run(scenario('success')),asyncio.run(scenario('terminal-scan-failure',fail_scan=True)),
 asyncio.run(scenario('unrelated-container-preserved',ownership_changed=True)),asyncio.run(scenario('existing-name-refused',existing_name=True)),asyncio.run(scenario('owned-container-stopped',owned_lingering=True))]
# Exercise actual first-party input/JSON normalization with a labeled scanner
# process substitute. No candidate script or upstream scanner runs.
from aeep_toolkit import scanner_worker
payload=json.loads((HERE/'static-negative-control.json').read_bytes())
work=stage/'protocol';work.mkdir()
fixture={'findings':[{'id':'fixture','rule_id':'fixture','category':'fixture','severity':'HIGH','analyzer':'static'}],
 'findings_count':1,'analyzers_used':['StaticAnalyzer'],'analyzers_failed':[{'analyzer':'fixture-failure','reason':'owned fixture'}]}
with pytest.MonkeyPatch.context() as patch:
 patch.setattr(scanner_worker,'subprocess',SimpleNamespace(DEVNULL=-3,run=lambda *a,**k:SimpleNamespace(returncode=1,stdout=json.dumps(fixture).encode())))
 result=scanner_worker.scan(payload,work)
 assert result['findings_count']==1 and result['failed_analyzers']==1 and result['candidate_bytes_bound']
record={'passed':True,'upstream_executed':False,'docker_mutated':False,'installation':False,
 'driver_cases':results,'normalization_retains_findings_and_failure_hashes':True,
 'scope':'First-party substitutes only; not scanner functionality, security approval or stack-completion evidence.',
 'retained_workspace':str(stage)}
(HERE/'preparation.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
