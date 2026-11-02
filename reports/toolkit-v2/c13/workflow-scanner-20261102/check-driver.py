"""First-party driver substitutes only; no Docker, Cisco or model execution."""
import contextlib,io,importlib.util,json,shutil,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
FROZEN=ROOT/'.aeep/stack-frozen-source-0116d754bc7a'
sys.path[:0]=[str(FROZEN/'src'),str(FROZEN/'tests')]
from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import RawExecution
from aeep.store import ReceiptStore
from aeep_toolkit import workflow_security as security
from aeep_toolkit.cli import main as source_cli
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from test_toolkit_workflow_security import install_fixture
spec=importlib.util.spec_from_file_location('reviewed_cli_driver',HERE/'run-cli.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
rows=[]
for scenario in ('success','boundary-failure','scan-failure'):
 with tempfile.TemporaryDirectory(prefix='aeep-scanner-driver-fixture-') as temp,pytest.MonkeyPatch.context() as monkeypatch:
  work=Path(temp).resolve();fixture=work/'fixture';fixture.mkdir()
  for name in ('cli-authority.json','cli-manifest.json','scanner-runtime.json','cli-accounting.json','cli-workflow.json','boundary-program.py'):
   shutil.copyfile(HERE/name,fixture/name)
  manifest=json.loads((fixture/'cli-manifest.json').read_text());original_db=Path(manifest['database']);manifest['database']=str(fixture/'fixture.sqlite3')
  (fixture/'cli-manifest.json').write_text(json.dumps(manifest))
  import sqlite3
  with sqlite3.connect(original_db) as source,sqlite3.connect(manifest['database']) as target:source.backup(target)
  scope=WorkflowAccountingDefinition.model_validate_json((fixture/'cli-accounting.json').read_bytes())
  old_ref=content_digest(scope)
  scope=scope.model_copy(update={'manifest_path':str(fixture/'cli-manifest.json'),'manifest_sha256':file_digest(fixture/'cli-manifest.json')})
  (fixture/'cli-accounting.json').write_text(scope.model_dump_json())
  authority=json.loads((fixture/'cli-authority.json').read_text());authority['review_refs']=[content_digest(scope) if x==old_ref else x for x in authority['review_refs']]
  (fixture/'cli-authority.json').write_text(json.dumps(authority))
  with ReceiptStore(Path(manifest['database'])) as store:
   # Only unexecuted preparation records are copied. No grant or counters exist to reset.
   assert store._connection.execute('SELECT count(*) FROM assessment_grants').fetchone()[0]==0
   AssessmentRepository(store).put('toolkit_workflow_accounting',content_digest(scope),scope)
  calls=install_fixture(monkeypatch,failure=scenario=='scan-failure')
  fixture_executor=security.ScanContainerExecutor;previous=fixture_executor.execute
  async def execute(self,context):
   if '-c' in context.spec.config['argv']:
    return RawExecution(status='failed' if scenario=='boundary-failure' else 'success',output={'passed':scenario!='boundary-failure'})
   return await previous(self,context)
  monkeypatch.setattr(fixture_executor,'execute',execute)
  monkeypatch.setattr(module,'ScanContainerExecutor',fixture_executor)
  monkeypatch.setattr(module,'HERE',fixture)
  def in_process_cli(args):
   output=io.StringIO()
   with contextlib.redirect_stdout(output):
    assert source_cli(args)==0
   return json.loads(output.getvalue())
  monkeypatch.setattr(module,'cli',in_process_cli) # Explicit substitute for the reviewed subprocess CLI.
  facts=module.cli(['workflow','scan','--workflow',str(fixture/'cli-workflow.json'),'--configuration','document-data'])
  result=module.run({'cli_review_sha256':facts['review_sha256'],'candidate_sha256':facts['candidate']['candidate_sha256']},'first-party-'+scenario)
  assert result['passed']==(scenario=='success'),result
  assert len(calls)==(0 if scenario=='boundary-failure' else 1)
  rows.append({'scenario':scenario,'passed':True,'dispatch_substitute_calls':len(calls)})
(HERE/'first-party-driver.json').write_text(json.dumps({'passed':True,'evidence_kind':'first_party_substitutes','checks':rows,'upstream_executed':False,'models':0},indent=2)+'\n')
print(json.dumps(rows))
