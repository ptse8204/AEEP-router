"""Installed current-source/CLI checks; no worker, SDK workflow or model execution."""
import contextlib
import io
import json
import sys
from importlib.metadata import version
from pathlib import Path
from aeep.assessment.verification import verification_source_digest
import aeep.assessment.verification as verification
from aeep_toolkit.ase_contract import verify_runtime_source
from aeep_toolkit.cli import main
from aeep_toolkit.workflow import StackConfiguration, WorkflowRuntimeBinding
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition

request=json.load(sys.stdin)
source=verification_source_digest(Path(verification.__file__).resolve().parents[3])
assert source==request['installed_source']
verify_runtime_source()
assert 'runtimes' in StackConfiguration.model_fields
assert 'references' in WorkflowRuntimeBinding.model_fields
schema=WorkflowAccountingDefinition.model_json_schema()
assert schema['properties']['schema_version']['enum']==[
 'aeep.toolkit.workflow-accounting.v1','aeep.toolkit.workflow-accounting.v2']
assert schema['properties']['maximum_overhead_seconds']['maximum']==3600
for name in ('setup','readiness','remove'):
 text=io.StringIO()
 with contextlib.redirect_stdout(text):
  try:main(['workflow',name,'--help'])
  except SystemExit as error:assert error.code==0
  else:raise AssertionError('help did not exit')
 assert '--runtime' in text.getvalue() and '--reviewed-digest' in text.getvalue()
assert version('aeep-agent-router')=='0.8.2'
assert version('agent-framework-core')=='1.21.0'
assert version('agent-skill-eval')=='0.7.0'
print(json.dumps({'passed':True,'source':source,'ase_source_files_verified':16,
 'workflow_lifecycle_help':['setup','readiness','remove'],'models':0,
 'framework_executed_by_this_check':False,'ase_scheduler_executed':False}))
