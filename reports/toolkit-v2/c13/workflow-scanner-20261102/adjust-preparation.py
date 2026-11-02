"""Record an inert runtime-budget correction before review or execution."""
import json,uuid
from pathlib import Path
from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.store import ReceiptStore
from aeep_toolkit.workflow_security import ScannerRuntimeDefinition
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.install_runtime import file_digest
root=Path.cwd();here=root/'reports/toolkit-v2/c13/workflow-scanner-20261102';cache=root/'.aeep/workflow-scanner-20261102'
names=['scanner-runtime.json','cli-workflow.json','cli-accounting.json','cli-authority.json','cli-preview.json','cli-preparation.json']
old={name:json.loads((here/name).read_bytes()) for name in names}
with (here/'preparation-v1.json').open('x') as f:json.dump({'reason':'Retain the proven 1 GiB scanner engineering envelope instead of the generic 256 MiB environment default; add a fresh launch-boundary probe. No dispatch or grant occurred.','files':old},f,indent=2)
scan=ScannerRuntimeDefinition.model_validate(old['scanner-runtime.json'])
env=scan.environment.model_copy(update={'memory_mb':1024,'cpu_count':2.0,'process_limit':128})
req=scan.request.model_copy(update={'plan_id':'recipe-'+uuid.uuid4().hex,'environment_digest':content_digest(env),
 'definition_digests':[content_digest(env) if r==scan.request.environment_digest else r for r in scan.request.definition_digests]})
scan=ScannerRuntimeDefinition.model_validate(scan.model_dump()|{'environment':env,'request':req})
(here/'scanner-runtime.json').write_text(scan.model_dump_json(indent=2)+'\n')
with ReceiptStore(cache/'canonical.sqlite3') as store:
 repo=AssessmentRepository(store);repo.put('environment',env.environment_id+'-1g',env)
 repo.put('recipe_materialization_request',req.plan_id,req);repo.put('toolkit_scanner_runtime',content_digest(scan),scan)
workflow=old['cli-workflow.json']
for c in workflow['configurations'].values():c['scanner']['sha256']=file_digest(here/'scanner-runtime.json')
(here/'cli-workflow.json').write_text(json.dumps(workflow,indent=2)+'\n')
accounting=WorkflowAccountingDefinition.model_validate(old['cli-accounting.json']|{'workflow_sha256':file_digest(here/'cli-workflow.json')})
(here/'cli-accounting.json').write_text(accounting.model_dump_json(indent=2)+'\n')
with ReceiptStore(cache/'canonical.sqlite3') as store:
 repo=AssessmentRepository(store);repo.put('toolkit_workflow_accounting',content_digest(accounting),accounting)
authority=old['cli-authority.json']
authority['review_refs']=[content_digest(env) if x==old['scanner-runtime.json']['request']['environment_digest'] else content_digest(scan) if x==content_digest(old['scanner-runtime.json']) else content_digest(accounting) if x==content_digest(old['cli-accounting.json']) else x for x in authority['review_refs']]
for grant in authority['grants']:
 if grant['authorization_id'].startswith('workflow-scanner-scanner-'):
  grant['environment_digests']=[content_digest(env)];grant['limits']['max_operations']=2;grant['limits']['max_elapsed_seconds']=210
(here/'cli-authority.json').write_text(json.dumps(authority,indent=2)+'\n')
