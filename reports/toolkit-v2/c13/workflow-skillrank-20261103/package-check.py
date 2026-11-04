"""Installed readiness/help/source check only; no upstream or task execution."""
import contextlib
import io
import json
import sys
from pathlib import Path
from aeep.assessment import verification
from aeep_toolkit.cli import main
from aeep_toolkit.worker_readiness import prepare_readiness
from aeep_toolkit.workflow import EvaluationWorkflow, StackWorkflow
from aeep_toolkit.managed import _report_family_keys

request = json.load(sys.stdin)
assert verification.verification_source_digest(Path(verification.__file__).resolve().parents[3]) == request['installed_source']
assert callable(prepare_readiness)
checks = []
for command, required in [
    (['workflow','prepare-worker-readiness','--help'], '--control-request'),
    (['workflow','run','--help'], '--configuration'),
    (['workflow','scan','--help'], '--reviewed-digest'),
    (['workflow','catalog','--help'], '--accounting'),
    (['workflow','define-catalog','--help'], '--file'),
    (['install-files-plan','--help'], '--artifact-root'),
    (['eval','managed','run','--help'], '--scheduler'),
    (['eval','managed','run','--help'], '--engineering-review'),
]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        try: main(command)
        except SystemExit as error: assert error.code == 0
        else: raise AssertionError('Expected help exit')
    assert required in output.getvalue(), command
    checks.append(' '.join(command[:-1]) + ' ' + required)
assert 'aeep.toolkit.workflow.v1' in json.dumps(EvaluationWorkflow.model_json_schema())
assert 'aeep.toolkit.workflow.v2' in json.dumps(StackWorkflow.model_json_schema())
families = _report_family_keys({'legacy.family:v1', 'https://github.com/example/repository'})
assert families['legacy.family:v1'] == 'legacy.family:v1'
assert families['https://github.com/example/repository'].startswith('source-family:')
assert len(set(families.values())) == 2
checks.append('installed repository-URL task-family normalization')
from aeep_toolkit.file_runtime import FileRuntimeInstallation
from aeep_toolkit.workflow_catalog import CatalogRuntimeDefinition, WorkflowCatalogRecord
from aeep_toolkit.catalog_worker import query
assert query('show','owner/skill') == {'mode':'show','value':'owner/skill'}
for model, contract in [(FileRuntimeInstallation,'file-runtime-installation.v1'),(CatalogRuntimeDefinition,'catalog-runtime.v1'),(WorkflowCatalogRecord,'workflow-catalog.v1')]:
    assert contract in json.dumps(model.model_json_schema())
checks.append('installed file/catalog contracts and inert query validation')
print(json.dumps({'passed':True,'installed_source':request['installed_source'],'checks':checks,
    'legacy_and_current_workflow_schemas':True,'upstream_executed':False,'models':0}))
