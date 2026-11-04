"""Prepare exact local artifacts/definitions only; no installation or upstream execution."""
from __future__ import annotations
import hashlib,json,shutil,sqlite3,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
SNAPSHOT=json.loads((HERE/'source-snapshot.json').read_bytes());SOURCE=Path(SNAPSHOT['coordinator_source_snapshot'])
sys.path.insert(0,str(SOURCE/'src'))
from aeep.assessment.models import AssessmentAuthorization,AssessmentEnvironment,AssessmentScopeAmendment,RecipeMaterializationRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import Manifest
from aeep.store import ReceiptStore
from aeep_toolkit.file_runtime import RuntimeFile,prepare_files
from aeep_toolkit.installation import PreviewPolicy,manifest_digest,preview
from aeep_toolkit.models import ExtensionManifest,ExtensionRegistry,SourcePin
from aeep_toolkit.workflow import StackWorkflow
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_catalog import CatalogRuntimeDefinition,catalog_preview

def load(path):return json.loads(Path(path).read_bytes())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def ref(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
WORK=ROOT/'.aeep/workflow-skillrank-20261103';WORK.mkdir(mode=0o700)
for name in ('artifacts','control','docker-config'):(WORK/name).mkdir(mode=0o700)
(WORK/'docker-config/config.json').write_text(json.dumps({'auths':{'https://index.docker.io/v1/':{}},'credsStore':'','credHelpers':{}}))
old=HERE.parent/'skillrank-license-correction-20261103'
result=load(old/'runtime-execution/summary.json');assert result['passed'] and not result['cleanup_uncertain'] and not result['accounting_uncertain']
binary=ROOT/'.aeep/skillrank-license-correction-20261103/runtime/work/target/release/skillrank'
assert sha(binary)==result['binary_sha256']
for name,original in [('skillrank',binary),('LICENSE',ROOT/'.aeep/skillrank-core-preparation-20261103/source/LICENSE'),
                      ('dependency-license-records.json',old/'registry-metadata-audit.json')]:
 shutil.copyfile(original,WORK/'artifacts'/name)
assert (WORK/'artifacts/skillrank').stat().st_nlink==1
rights='Private retained MIT SkillRank core binary; locked dependency notices retained. No redistribution clearance or external registry use.'
manifest=ExtensionManifest(extension_id='skillrank',purpose='Retain Linux arm64 SkillRank and query reviewed local metadata only inside the pinned offline Linux worker.',
 role='catalog',source=SourcePin(repository='https://github.com/buildbetter-app/skillrank',revision='5216bae9149b4ff8a7f9e014b6889fb094cee8e1',
 artifact_sha256=result['binary_sha256'],license_expression='MIT',data_rights=rights),hosts=('codex',),platforms=('darwin-arm64',),dependencies=(),
 permissions={'network_destinations':[],'filesystem_scope':'workspace','authentication':'none','financial_exposure':'none'},
 disk_bytes=sum(p.stat().st_size for p in (WORK/'artifacts').iterdir()),memory_bytes=None,
 install_effects=('Copy reviewed Linux binary and license records into a private Mac-owned directory; no host execution or activation.',),
 rollback='Stop owned catalog workers; remove only an unchanged unreferenced installation through its retained journal.',status='experimental')
base=load(HERE.parent/'workflow-scanner-20261102/cli-registry.json')
base['extensions']=[m for m in base['extensions'] if m['extension_id'] in {'aeep-evaluator','skillsbench'}]+[manifest.model_dump(mode='json')]
registry=ExtensionRegistry.model_validate(base)
policy=PreviewPolicy(host='codex',platform='darwin-arm64',allowed_licenses=('MIT','Apache-2.0'),
 allowed_data_rights=tuple(dict.fromkeys([m.source.data_rights for m in registry.extensions]+['First-party engineering catalog only; no benchmark answers or third-party skill distribution.'])),
 allowed_filesystem_scopes=('workspace',),allowed_authentication=('none',),allowed_financial_exposure=('none',),free_disk_bytes=shutil.disk_usage(ROOT).free,
 allow_unknown_memory=True,reviewed_dependency_manifests=tuple(map(manifest_digest,registry.extensions)))
write(HERE/'registry.json',registry.model_dump(mode='json'));write(HERE/'policy.json',policy.model_dump(mode='json'))
files=tuple(RuntimeFile(extension_id='skillrank',source=name,destination=destination,sha256=sha(WORK/'artifacts'/name),
 size_bytes=(WORK/'artifacts'/name).stat().st_size,executable=primary,primary=primary)
 for name,destination,primary in [('skillrank','bin/skillrank',True),('LICENSE','licenses/skillrank-MIT.txt',False),('dependency-license-records.json','licenses/dependencies.json',False)])
selection=preview(ExtensionRegistry(extensions=(manifest,)),('skillrank',),policy,profile='evaluation')
for name in ('retained','disposable'):
 plan=prepare_files(selection,policy,WORK/(name+'-runtime'),WORK/'artifacts',files)
 write(HERE/(name+'-installation.json'),plan.model_dump(mode='json'))
# First-party metadata is explicitly an engineering catalog, not a benchmark task.
catalog=[{'slug':'aeep/document-catalog-control','display_name':'Document/data engineering catalog control','category':'document-data','stacks':['spreadsheet'],
 'summary':'First-party catalog filtering fixture, not task execution or usefulness evidence.','content':'Follow reviewed task instructions; preserve unrelated user work.'},
 {'slug':'aeep/software-catalog-control','display_name':'Software engineering catalog control','category':'software-engineering','stacks':['python'],
 'summary':'First-party catalog filtering fixture, not task execution or usefulness evidence.','content':'Follow reviewed task instructions; preserve unrelated user work.'}]
write(HERE/'catalog.json',catalog)
original_review=load(HERE.parent/'skillrank-build-preparation-20261103/operation-review.json')
ledger=Path(load(old/'operation-review.json')['original_ledger'])
with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
 original=RecipeMaterializationRequest.model_validate_json(db.execute("SELECT payload_json FROM assessment_records WHERE kind='recipe_materialization_request' AND id=?",(load(old/'operation-review.json')['original_request_id'],)).fetchone()[0])
 root_grant=AssessmentAuthorization.model_validate_json(db.execute("SELECT payload_json FROM assessment_records WHERE kind='authorization' AND id=?",(original.authorization_id,)).fetchone()[0])
 counters=list(db.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(original.authorization_id,)).fetchone())
 assert counters==result['counters_after']
 assert db.execute("SELECT count(*) FROM assessment_operations WHERE grant_id=? AND state='reserved'",(original.authorization_id,)).fetchone()[0]==0
# Store inert exact records; do not review the new scope or amend the grant yet.
env=AssessmentEnvironment(environment_id='skillrank-cli-retained-grader',kind='container',identity={},network=False,
 container_image='sha256:35dc1bcb7e8162c2a0cef6cbd30bc4bf276c082b11b6e5fc259b6800e8c5ca04',
 container_runtime='/Applications/Docker.app/Contents/Resources/bin/docker',container_socket='/Users/edwintse/.docker/run/docker.sock',memory_mb=1024,cpu_count=1,process_limit=128)
manifest_path=HERE/'manifest.json';write(manifest_path,Manifest(database=str(ledger),executors=[]).model_dump(mode='json'))
with ReceiptStore(ledger) as store:
 repo=AssessmentRepository(store);env_ref=repo.put('environment',env.environment_id,env)
 request=original.model_copy(update={'plan_id':'skillrank-workflow-'+SNAPSHOT['source'][:12],'environment_digest':env_ref,
  'definition_digests':list(dict.fromkeys([*original.definition_digests,env_ref]))})
 worker=SOURCE/'src/aeep_toolkit/catalog_worker.py'
 definition=CatalogRuntimeDefinition(runtime_id='skillrank-files',environment=env,request=request,catalog=ref(HERE/'catalog.json'),
  catalog_source=SourcePin(repository='https://github.com/ptse8204/AEEP-router',revision=SNAPSHOT['source'],artifact_sha256=sha(HERE/'catalog.json'),
  license_expression='Apache-2.0',data_rights='First-party engineering catalog only; no benchmark answers or third-party skill distribution.'),
  control_root=str(WORK/'control'),worker_sha256=sha(worker),executable_dependencies={str(worker):sha(worker),str(env.container_runtime):sha(env.container_runtime)})
 write(HERE/'catalog-runtime.json',definition.model_dump(mode='json'))
 catalog_ref=repo.put('toolkit_catalog_runtime',content_digest(definition),definition)
 data=load(HERE.parent/'scanner-storage-review-20261103/cli-workflow.json')
 data['registry']=ref(HERE/'registry.json');data['policy']=ref(HERE/'policy.json')
 for name,config in data['configurations'].items():
  config.pop('scanner',None);config['components']=['aeep-evaluator','skillsbench','skillrank']
  config['benchmark']=ref(HERE.parent/'skillsbench-transport-20261103/task-only-pack.json')
  config['catalog']=ref(HERE/'catalog-runtime.json')
  config['runtimes']={'skillrank-files':{'installation':ref(HERE/'retained-installation.json'),'components':{'skillrank':'skillrank'}}}
 data['configurations']['document-data']['runtimes']['disposable-files']={'installation':ref(HERE/'disposable-installation.json'),'components':{'skillrank':'skillrank'}}
 workflow=StackWorkflow.model_validate(data);write(HERE/'workflow.json',workflow.model_dump(mode='json'))
 scope=WorkflowAccountingDefinition(schema_version='aeep.toolkit.workflow-accounting.v4',workflow_sha256=sha(HERE/'workflow.json'),
  configurations=('document-data','software-engineering'),operations=('setup','readiness','remove','catalog'),source_digest=SNAPSHOT['source'],
  manifest_path=str(manifest_path),manifest_sha256=sha(manifest_path),request=request,maximum_overhead_seconds=30)
 write(HERE/'accounting.json',scope.model_dump(mode='json'))
 scope_ref=repo.put('toolkit_workflow_accounting',content_digest(scope),scope)
 amendment=AssessmentScopeAmendment(authorization_id=root_grant.authorization_id,authorization_digest=content_digest(root_grant),
  subject_digests=[request.subject_digest],recipe_digests=[request.recipe_digest],environment_digests=[env_ref],reviewed_digests=[catalog_ref,scope_ref])
 write(HERE/'scope-amendment.json',amendment.model_dump(mode='json'))
 repo.put('recipe_materialization_request',request.plan_id,request)
 for name in ('document-data','software-engineering'):
  facts=catalog_preview(HERE/'workflow.json',name,'search','engineering')[0]
  assert facts['blockers']==['selected catalog runtime is absent, changed or unowned'],facts['blockers']
 write(HERE/'workflow-preparation.json',{'source':SNAPSHOT['source'],'source_snapshot':str(SOURCE),'original_ledger':str(ledger),
  'request_id':request.plan_id,'authorization_id':request.authorization_id,'grant_counters':counters,'grant_original_limits':root_grant.limits.model_dump(mode='json'),
  'new_scope_refs':[env_ref,catalog_ref,scope_ref],'definitions_stored_but_not_reviewed':True,'grant_amendment_applied':False,'binary_sha256':result['binary_sha256'],
  'runtime':str(WORK),'container_image':env.container_image,'current_source_cli_executed':False,'models':0,'comparisons':'PAUSED'})
print(json.dumps({'prepared':True,'actual_execution':False,'newly_reviewed_authority':False,'same_root_grant':request.authorization_id,'counters':counters,'binary':result['binary_sha256']}))
