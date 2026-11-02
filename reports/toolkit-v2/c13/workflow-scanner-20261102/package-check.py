"""Installed source and ordinary CLI checks; never launch a backend or scanner."""
import contextlib,io,json,sys
from pathlib import Path
from aeep_toolkit.cli import main
request=json.load(sys.stdin)
from aeep.assessment import verification
assert verification.verification_source_digest(Path(verification.__file__).resolve().parents[3])==request['installed_source']
from aeep_toolkit.workflow import StackConfiguration
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition,WorkflowPlanLink
from aeep_toolkit.workflow_security import ScannerRuntimeDefinition,WorkflowScanRecord
assert 'scanner' in StackConfiguration.model_fields
assert 'execution_evidence_ref' in WorkflowScanRecord.model_fields
assert 'executable_dependencies' in ScannerRuntimeDefinition.model_fields
assert 'component_refs' not in WorkflowPlanLink(operation_id='fixture',assessment_plan_id='fixture',assessment_plan_digest='a'*64).model_dump()
assert WorkflowAccountingDefinition.model_json_schema()['properties']['schema_version']['enum']==[
 'aeep.toolkit.workflow-accounting.v1','aeep.toolkit.workflow-accounting.v2','aeep.toolkit.workflow-accounting.v3']
checks=[]
for argv,required in [(['candidate','--help'],'--stage'),(['workflow','scan','--help'],'--reviewed-digest'),
 (['workflow','define-scanner','--help'],'--manifest'),(['workflow','run','--help'],'--scan-report'),
 (['workflow','report','--help'],'--scan-report')]:
 output=io.StringIO()
 with contextlib.redirect_stdout(output):
  try:main(argv)
  except SystemExit as error:assert error.code==0
  else:raise AssertionError('expected help exit')
 assert required in output.getvalue();checks.append(' '.join(argv[:-1]))
print(json.dumps({'passed':True,'installed_source':request['installed_source'],'cli_help_checks':checks,
 'models':0,'upstream_scanner_executed':False,'task_execution':False}))
