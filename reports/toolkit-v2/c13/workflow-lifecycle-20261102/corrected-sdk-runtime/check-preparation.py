"""Trusted first-party preparation; no optional package or SDK is executed."""
import asyncio,contextlib,hashlib,importlib.metadata,importlib.util,io,json,os,runpy,shutil,sqlite3,sys
from pathlib import Path
from types import SimpleNamespace
import pytest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/'tests'))
from aeep.assessment.verification import verification_source_digest
from aeep.models import RawExecution
from aeep_toolkit.install_runtime import RuntimeInstallation
import test_toolkit_agent_framework as fixture

stage=ROOT/'.aeep/workflow-lifecycle-preparation-20261102'
stage.mkdir(mode=0o700)
source=verification_source_digest(ROOT)
# Run the unchanged functional program using the strict first-party SDK fixture.
# The five owned numeric subprocesses and canonical accounting are real, but this
# does not exercise upstream Framework and cannot close its functional gate.
work=stage/'functional-program';work.mkdir()
oldcwd=Path.cwd()
original_read=Path.read_bytes
canary=work/'denied-synthetic-canary'
canary.write_text('owned synthetic permission fixture')
def read_bytes(path):
 if path==canary:raise PermissionError('synthetic denied canary')
 return original_read(path)
stream=io.StringIO()
with pytest.MonkeyPatch.context() as patch:
 fixture.sdk_fixture.__wrapped__(patch)
 patch.setattr(importlib.metadata,'version',lambda name:'1.21.0' if name=='agent-framework-core' else (_ for _ in ()).throw(ValueError(name)))
 patch.setattr(Path,'read_bytes',read_bytes)
 patch.setattr(sys,'stdin',io.StringIO(json.dumps({'review_sha256':'b'*64,'installed_source':source,'canary_path':str(canary)})))
 os.chdir(work)
 try:
  with contextlib.redirect_stdout(stream):runpy.run_path(str(HERE/'functional-check.py'),run_name='__main__')
 finally:os.chdir(oldcwd)
program=json.loads(stream.getvalue())
assert program['operations']==5 and len(program['checks'])==5 and all(c['passed'] for c in program['checks'])
(HERE/'first-party-program.json').write_text(json.dumps({'passed':True,'upstream_executed':False,
 'scope':'Strict first-party builder/context substitute; actual owned numeric commands/receipts; not SDK integration evidence.',
 'retained_workspace':str(work),'result':program},indent=2)+'\n')

spec=importlib.util.spec_from_file_location('current_sdk_driver',HERE/'run-review.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
review=json.loads((HERE/'review-draft.json').read_bytes());review['identity']='c'*64
plan=RuntimeInstallation.model_validate_json((HERE/'installation.json').read_bytes())
# Exercise full driver control flow with explicit synthetic executor responses.
# Runtime installation and every optional subprocess are replaced, not invoked.
async def scenario(name,failed=False,uncertain=False):
 test=stage/name;test.mkdir()
 for file in ('functional-check.py','boundary-check.py','package-check.py'):
  shutil.copyfile(HERE/file,test/file)
 calls=[]
 class Executor:
  async def start(self,context):
   assert context.spec.description and context.spec.config['stdin_json'] is True
   key=context.spec.id.rsplit('-',1)[-1]
   is_probe=context.spec.config['argv'][-1].endswith('boundary-check.py')
   calls.append((key,is_probe))
   data={'passed':True} if is_probe else {'passed':True,'source':review['installed_source']}
   if key=='framework' and not is_probe:
    with sqlite3.connect(Path(context.spec.config['cwd'])/'canonical.sqlite3') as connection:
     connection.execute('CREATE TABLE assessment_operations (state TEXT)')
     connection.executemany('INSERT INTO assessment_operations VALUES (?)',[('reserved' if uncertain else 'complete',)]*(0 if failed and not uncertain else 5))
    data={'operations':5,'models':0,'checks':[{'passed':True}]*5}
   async def completed():return RawExecution(status='failed' if failed and key=='framework' and not is_probe else 'success',output=data)
   return SimpleNamespace(task=asyncio.create_task(completed()))
  async def close(self):pass
 with pytest.MonkeyPatch.context() as patch:
  patch.setattr(module,'HERE',test)
  patch.setattr(module,'CommandExecutor',Executor)
  patch.setattr(module,'apply',lambda *_:{'status':'installed'})
  patch.setattr(module,'snapshot',lambda *_:'synthetic-unchanged-tree')
  result=await module.run(review,plan)
 assert result['passed'] is (not failed and not uncertain),result
 assert ('package',False) in calls if not uncertain else ('package',False) not in calls
 assert len(calls)==(3 if uncertain else 4),calls
 return {'case':name,'passed':True,'synthetic_calls':calls,'upstream_executed':False}
scenarios=asyncio.run(scenario('driver-success'))
failed=asyncio.run(scenario('driver-terminal-component-failure',failed=True))
uncertain=asyncio.run(scenario('driver-unsettled-stop',uncertain=True))
(HERE/'first-party-driver.json').write_text(json.dumps({'passed':True,'upstream_executed':False,
 'installation_executed':False,'cases':[scenarios,failed,uncertain],'retained_workspace':str(stage)},indent=2)+'\n')
print(json.dumps({'passed':True,'functional_program_with_strict_first_party_sdk':True,
 'driver_scenarios':3,'upstream_executed':False,'installed':False}))
