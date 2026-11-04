"""Read-only canonical inspection and inert files; no grant, service or secrets."""
import hashlib,json,os,shutil,sqlite3,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OLD=HERE.parent/'workflow-telemetry-20261104'
SOURCE=Path(json.loads((OLD/'source-snapshot.json').read_bytes())['coordinator_source_snapshot'])
sys.path.insert(0,str(SOURCE/'src'))
from aeep.assessment.models import AssessmentAuthorization,AssessmentLimits,RecipeMaterializationRequest,content_digest
from aeep.models import Manifest,ExecutionReceipt,utc_now
from aeep.telemetry import receipt_otlp_preview
from aeep_toolkit.models import ExtensionManifest,ExtensionRegistry,SourcePin
from aeep_toolkit.workflow import StackWorkflow
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_telemetry import ReceiptExportDefinition
from service_plan import compose,PROJECT,SECRETS
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('review_driver',HERE/'run-service.py');driver=module_from_spec(spec);spec.loader.exec_module(driver)

def load(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
def binding(p):return {'path':str(p.resolve()),'sha256':sha(p)}

assert os.getuid()==501 and os.getgid()==20
work=ROOT/'.aeep/langfuse-service-20261104'
artifact_review=load(OLD/'operation-review.json');images={x['key']:x['reference'] for x in artifact_review['acquisition']['images']}
blueprint=compose(images,work,{k:'REVIEWED_NEW_LOCAL_'+k.upper() for k in SECRETS})
write(HERE/'compose-blueprint.json',blueprint)
scopes={}
for role in ('subject','recipe','mapping','environment','deployment'):
    model=driver.Scope(role=role,source_digest=artifact_review['source'],blueprint_sha256=sha(HERE/'compose-blueprint.json'))
    scopes[content_digest(model)]=model.model_dump(mode='json')
refs=list(scopes)
ledger=Path(artifact_review['acquisition']['canonical_database'])
request=RecipeMaterializationRequest(plan_id='langfuse-service-cli-20261104',authorization_id='langfuse-service-engineering-20261104',
    subject_digest=refs[0],recipe_digest=refs[1],mapping_digest=refs[2],environment_digest=refs[3],definition_digests=refs,seed=0)
grant=AssessmentAuthorization(authorization_id=request.authorization_id,subject_digests=[refs[0]],recipe_digests=[refs[1]],environment_digests=[refs[3]],
    limits=AssessmentLimits(max_operations=63,max_model_turns=0,max_elapsed_seconds=3200,max_cash_usd='0'),
    allowed_destinations=['local'],remote_disclosure=False,automatic_admission=False,issued_at=utc_now(),expires_at=artifact_review['expires_at'])
with sqlite3.connect('file:'+str(ledger)+'?mode=ro',uri=True) as db:
    selected=load(HERE.parent/'skillrank-cli-continuation-20261104/runtime-execution/document-search.json')
    raw=db.execute("SELECT payload_json FROM assessment_records WHERE kind='toolkit_component_receipt' AND digest=?",(selected['receipt_ref'],)).fetchone()
    assert raw is not None
    receipt=ExecutionReceipt.model_validate_json(raw[0]);preview=receipt_otlp_preview(receipt)
    canonical=db.execute('SELECT payload_json FROM receipts WHERE receipt_id=?',(receipt.receipt_id,)).fetchone()
    assert canonical is not None and ExecutionReceipt.model_validate_json(canonical[0])==receipt
    assert db.execute('SELECT 1 FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone() is None
    assert db.execute("SELECT count(*) FROM assessment_operations WHERE state='reserved'").fetchone()[0]==0
    old_counters={row[0]:list(row[1:]) for row in db.execute('SELECT id,operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants')}
write(HERE/'manifest.json',Manifest(database=str(ledger),executors=[]).model_dump(mode='json'))
base=load(HERE.parent/'workflow-skillrank-20261103/workflow.json')
registry=load(HERE.parent/'workflow-skillrank-20261103/registry.json')
registry['extensions']=[x for x in registry['extensions'] if x['extension_id']!='skillrank']
for name,revision,license,rights in [('langfuse','5e4db922e9021083500cd066249b220a414b7dfe','MIT','Core-only private receipt observability; enterprise features off; upstream and image third-party notices retained. No redistribution.'),
                                    ('opentelemetry',artifact_review['source'],'Apache-2.0','Existing AEEP receipt instrumentation; no prompts, artifact contents or provider credentials.')]:
    m=ExtensionManifest(extension_id=name,purpose='Explicit local minimized receipt telemetry; generic v1 HTTPS setup metadata cannot express this local HTTP permission',role='observability',
        source=SourcePin(repository='https://github.com/langfuse/langfuse' if name=='langfuse' else 'https://github.com/ptse8204/AEEP-router',revision=revision,
            artifact_sha256=artifact_review['acquisition']['images'][0]['config_digest'].split(':')[1] if name=='langfuse' else sha(SOURCE/'src/aeep/telemetry.py'),
            license_expression=license,data_rights=rights),
        hosts=('codex',),platforms=('darwin-arm64',),dependencies=(),permissions={'network_destinations':[],'filesystem_scope':'workspace','authentication':'operator_setup','financial_exposure':'none'},
        disk_bytes=None,memory_bytes=None,install_effects=('Separate exact service review and ReceiptExportDefinition bind the loopback HTTP exception; this metadata grants no service or network authority.',),
        rollback='Stop only owned containers; retain data and receipts.',status='blocked',
        blockers=('Generic v1 HTTPS-only setup preview cannot express loopback HTTP; use the separate exact receipt-export/service review. Functional ingestion remains unverified.',))
    registry['extensions'].append(m.model_dump(mode='json'))
write(HERE/'registry.json',ExtensionRegistry.model_validate(registry).model_dump(mode='json'))
runtime=Path(artifact_review['package']['runtime'])
for enabled,name in [(True,'enabled'),(False,'disabled')]:
    definition=ReceiptExportDefinition(request=request,port=39067,enabled=enabled,deployment_review_ref=refs[4])
    write(HERE/(name+'-export.json'),definition.model_dump(mode='json'))
    data=json.loads(json.dumps(base));data['registry']=binding(HERE/'registry.json')
    for config in data['configurations'].values():
        config.pop('catalog',None);config.pop('runtimes',None)
        config['components']=['aeep-evaluator','skillsbench','langfuse','opentelemetry']
        config['telemetry']=binding(HERE/(name+'-export.json'))
    write(HERE/(name+'-workflow.json'),StackWorkflow.model_validate(data).model_dump(mode='json'))
    scope=WorkflowAccountingDefinition(schema_version='aeep.toolkit.workflow-accounting.v4',workflow_sha256=sha(HERE/(name+'-workflow.json')),
        configurations=('document-data','software-engineering'),operations=('report',),source_digest=artifact_review['package']['installed_source'],
        manifest_path=str(HERE/'manifest.json'),manifest_sha256=sha(HERE/'manifest.json'),request=request,maximum_overhead_seconds=30)
    write(HERE/(name+'-accounting.json'),scope.model_dump(mode='json'))
# Bound sandbox: only task JSON, installed runtime, canonical database and local OTLP.
db_files=[ledger,Path(str(ledger)+'-wal'),Path(str(ledger)+'-shm'),Path(str(ledger)+'-journal')]
read=[runtime,HERE,work/'home',work/'tmp'];ancestors={p for f in [*read,*db_files] for p in f.parents if str(p).startswith('/Users/edwintse')}
quote=lambda p:json.dumps(str(p))
profile='(version 1)\n(allow default)\n(deny network*)\n(allow network-outbound (remote ip "localhost:39067"))\n(deny file-write*)\n(allow file-write* (literal "/dev/null"))\n(deny file-read* (subpath "/Users/edwintse"))\n'
profile+='(allow file-read* '+ ' '.join('(subpath '+quote(p)+')' for p in read)+')\n'
profile+='(allow file-read* '+' '.join('(literal '+quote(p)+')' for p in db_files)+')\n'
profile+='(allow file-write* '+' '.join('(literal '+quote(p)+')' for p in db_files)+' '+ ' '.join('(subpath '+quote(p)+')' for p in [work/'home',work/'tmp'])+')\n'
profile+='(allow file-read-metadata '+' '.join('(literal '+quote(p)+')' for p in sorted(ancestors))+')\n'
(HERE/'cli.sb').write_text(profile)
write(HERE/'prepared.json',{'source':artifact_review['source'],'scopes':scopes,'request':request.model_dump(mode='json'),'grant':grant.model_dump(mode='json'),
    'source_receipt_id':receipt.receipt_id,'source_receipt_sha256':preview['receipt_sha256'],'source_receipt_ref':selected['receipt_ref'],
    'old_counters':old_counters,'ledger':str(ledger),'new_grant_applied':False,'models':0,'execution':False})
print(json.dumps({'prepared':True,'execution':False,'new_grant_applied':False,'secret_values_created':False,'source_receipt_sha256':preview['receipt_sha256']}))
