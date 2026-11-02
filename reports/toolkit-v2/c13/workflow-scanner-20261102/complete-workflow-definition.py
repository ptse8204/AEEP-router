"""Keep both named workflow previews valid; evaluator/task gates remain blocked."""
import json,subprocess,sys
from pathlib import Path
from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.installation import PreviewPolicy,manifest_digest
from aeep_toolkit.models import ExtensionManifest,ExtensionRegistry
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
old={name:json.loads((HERE/name).read_bytes()) for name in ('cli-registry.json','cli-policy.json','cli-workflow.json','cli-accounting.json','cli-authority.json')}
with (HERE/'workflow-definition-v1.json').open('x') as f:json.dump({'reason':'Include explicit evaluator and benchmark components so ordinary workflow plan returns its actual blockers; scanner authority/bytes/image unchanged. No execution or grant.','files':old},f,indent=2)
review=HERE/'operation-review.json';review.rename(HERE/'review-draft-v1.json')
(HERE/'review-draft-v1-withdrawn.json').write_text(json.dumps({'approved':False,'executed':False,'reason':'Finish explicit evaluator/benchmark declarations before requesting approval. Prior inert review is withdrawn.'},indent=2)+'\n')
package=json.loads((HERE/'package-preparation.json').read_bytes());pack=json.loads((ROOT/'reports/toolkit-v2/c13/full-stack-20261030/skillsbench-pack.json').read_bytes())
registry=ExtensionRegistry.model_validate(old['cli-registry.json']);extras=[]
for name,role,pin,reason in [
 ('aeep-evaluator','evaluator',{'repository':'https://github.com/ptse8204/AEEP-router','revision':package['source'],
  'artifact_sha256':file_digest(next((HERE/'verification-final/dist').glob('*.whl'))),'license_expression':'Apache-2.0',
  'data_rights':'First-party code only. No task or provider-disclosure authority granted.'},'Managed worker/service/plan/grader readiness and execution authority remain required.'),
 ('skillsbench','benchmark',pack['source'],'Task-specific asset rights, reviewed runtimes and protected verifier/reference journeys remain required.')]:
 extras.append(ExtensionManifest(extension_id=name,purpose='Explicit selected '+name+' declaration; functional gate remains open.',role=role,
  source=pin,hosts=('codex',),platforms=('darwin-arm64',),dependencies=(),
  permissions={'network_destinations':[],'filesystem_scope':'workspace','authentication':'none','financial_exposure':'none'},
  disk_bytes=0,memory_bytes=None,install_effects=('Declaration only; setup/model/task execution blocked.',),
  rollback='No setup occurred.',status='blocked',blockers=(reason,)))
registry=ExtensionRegistry(extensions=(*registry.extensions,*extras));(HERE/'cli-registry.json').write_text(registry.model_dump_json(indent=2)+'\n')
policy=PreviewPolicy.model_validate(old['cli-policy.json'])
policy.allowed_licenses=tuple(dict.fromkeys((*policy.allowed_licenses,*(m.source.license_expression for m in extras))))
policy.allowed_data_rights=tuple(dict.fromkeys((*policy.allowed_data_rights,*(m.source.data_rights for m in extras))))
policy.reviewed_dependency_manifests=(*policy.reviewed_dependency_manifests,*(manifest_digest(m) for m in extras))
(HERE/'cli-policy.json').write_text(policy.model_dump_json(indent=2)+'\n')
workflow=old['cli-workflow.json'];workflow['registry']['sha256']=file_digest(HERE/'cli-registry.json');workflow['policy']['sha256']=file_digest(HERE/'cli-policy.json')
for config in workflow['configurations'].values():config['components']=['aeep-evaluator','skillsbench','skill-scanner']
(HERE/'cli-workflow.json').write_text(json.dumps(workflow,indent=2)+'\n')
scope=WorkflowAccountingDefinition.model_validate(old['cli-accounting.json']|{'workflow_sha256':file_digest(HERE/'cli-workflow.json')})
(HERE/'cli-accounting.json').write_text(scope.model_dump_json(indent=2)+'\n')
with ReceiptStore(ROOT/'.aeep/workflow-scanner-20261102/canonical.sqlite3') as store:
 repo=AssessmentRepository(store);repo.put('toolkit_workflow_accounting',content_digest(scope),scope)
authority=old['cli-authority.json'];authority['review_refs']=[content_digest(scope) if ref==content_digest(old['cli-accounting.json']) else ref for ref in authority['review_refs']]
(HERE/'cli-authority.json').write_text(json.dumps(authority,indent=2)+'\n')
env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(ROOT/'.aeep/stack-frozen-source-0116d754bc7a/src'),'PYTHONDONTWRITEBYTECODE':'1','LC_ALL':'C'}
rows=[]
for domain in ('document-data','software-engineering'):
 process=subprocess.run([sys.executable,'-m','aeep_toolkit','workflow','plan','--workflow',str(HERE/'cli-workflow.json'),'--configuration',domain],cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
 assert process.returncode==0,process.stderr
 data=json.loads(process.stdout);assert data['blockers'] and len(data['benchmark']['tasks'])==3
 (HERE/('workflow-preview-'+domain+'.json')).write_text(json.dumps(data,indent=2)+'\n')
 rows.append({'configuration':domain,'actual_cli_preview':True,'tasks':3,'blocked':True,'executed':False})
(HERE/'workflow-preview-check.json').write_text(json.dumps({'passed':True,'checks':rows,'model_or_task_execution':False},indent=2)+'\n')
print(json.dumps(rows))
