"""Seal separate service/docs components; preparation cannot launch or grant."""
import hashlib,importlib.util,json,shutil,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OLD=HERE.parent/'workflow-telemetry-20261104'
source=Path(json.loads((OLD/'source-snapshot.json').read_bytes())['coordinator_source_snapshot'])
sys.path.insert(0,str(source/'src'))
from aeep_toolkit.install_runtime import snapshot
from aeep.assessment.verification import verification_source_digest
from service_plan import SERVICES

def load(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')

old=load(OLD/'operation-review.json');prepared=load(HERE/'prepared.json')
assert not (HERE/'service-started.json').exists() and not (HERE/'docs-attempt-1.json').exists()
assert load(HERE/'driver-controls.json')['passed'] and load(HERE/'boundary-control.json')['passed']
assert verification_source_digest(source)==old['source']
checks=load(old['source_checks']);assert checks['source_before']==checks['source_after']==old['source'] and len(checks['checks'])==13 and all(c['exit_code']==0 for c in checks['checks'])
assert load(OLD/'package-execution/summary.json')['passed'] and all(x['passed'] for x in load(OLD/'image-audit/summary.json')['images'])
images={x['key']:x['reference'] for x in old['acquisition']['images']}
image_ids={x['key']:x['config_digest'] for x in old['acquisition']['images']}
blueprint=load(HERE/'compose-blueprint.json')
service_ids={name:next(image_ids[k] for k,image in images.items() if image==blueprint['services'][name]['image']) for name in SERVICES}
runtime=Path(old['package']['runtime'])
executables={old['acquisition']['docker']:'a6822407e207ff0b687419ccbe55700ffbf389d77de58ef625b3b1790d88747c',
    '/Applications/Docker.app/Contents/Resources/cli-plugins/docker-compose':'0087dac03e594e665bb432bd406325d9ba3f6e032c08c4f1c50db29167da4333',
    '/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13':'20c9c2144a9f5202177620417e67643fb551aa31586e5d3c1361627b920cadb0',
    '/usr/bin/sandbox-exec':'e3d7a792c58a5d3783d2f7274c82d70062393830d8cb1ded713ca554a470bd2f'}
for p,h in executables.items():assert sha(Path(p).resolve())==h,p
bindings=[];release=ROOT/'.aeep/langfuse-source-preparation-20261104/release'
for name,blob in [('ee-LICENSE','3e78f3e97ac04d255328733b8c479d62bbaebadf'),('web-entrypoint.sh','e2a3204b74cc0ffcf3c1fe719cf6adba6b55d93a'),
                  ('worker-entrypoint.sh','081e8bcf41884bececd5ea34e8feb42e29b0b152'),('observations.yml','fcd59019709dcecf2436e8971f953e49a4360f1b'),
                  ('OtelIngestionProcessor.ts','6b6ac015a3d7d5c541dfaa69cfe362e931227392'),('redis-7.4.12-LICENSE.txt','a60c2460490e107623553fca835781b1f329198c'),
                  ('redis-7.4.12-CONTRIBUTIONS.txt','00c9879c8d8e121c44c400913bfd7a6993cc4a17')]:
    p=release/name;b=p.read_bytes();assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==blob
    bindings.append({'path':str(p),'git_blob':blob,'sha256':sha(p)})
write(HERE/'upstream-source-bindings.json',{'langfuse_revision':'5e4db922e9021083500cd066249b220a414b7dfe','redis_image_declared_version':'7.4.12','files':bindings,
    'metadata_mapping':'Non-Langfuse-SDK spans retain unknown attributes in metadata.attributes. Readback expands only attributes to avoid default truncation.',
    'source_execution':False})
excluded={'operation-review.json','review-preflight.json'}
paths=[p for p in HERE.iterdir() if p.is_file() and p.name not in excluded]
paths += [OLD/'source-snapshot.json',Path(old['source_checks']),OLD/'operation-review.json',OLD/'package-execution/summary.json',
          OLD/'image-audit/summary.json',OLD/'runtime-execution/summary.json',OLD/'service-source-bindings.json',OLD/'RESULTS.md']
config=Path(old['acquisition']['docker_config'])/'config.json'
if config.exists():
    value=load(config)
    assert not value.get('credsStore') and not value.get('credHelpers')
    assert not any(record for record in value.get('auths',{}).values())
    paths.append(config)
paths += list((OLD/'image-audit').glob('*-headers.json'))
paths += [Path(x['path']) for x in bindings]
paths += [release/n for n in ('LICENSE','docker-compose.yml','opentelemetry.yml')]
paths += [ROOT/'.aeep/workflow-telemetry-20261104/image-notices'/str(n+'.json') for n in images]
# Bind transitive metadata used by the ordinary workflow without reading task/answer bodies.
for workflow in ('enabled','disabled'):
    data=load(HERE/(workflow+'-workflow.json'))
    for row in [data['registry'],data['policy'],*[x['benchmark'] for x in data['configurations'].values()]]:
        p=Path(row['path']);assert sha(p)==row['sha256'];paths.append(p)
service_assets={str(p.resolve()):sha(p) for p in paths}
docs=old['docs'];docs_assets={str(ROOT/n):sha(ROOT/n) for n in docs['documents']}
for p in [HERE/'run-docs.py',Path(docs['runtime_record']),ROOT/'Makefile',ROOT/'.markdownlint-cli2.jsonc',ROOT/'.lychee.toml']:
    if p.exists():docs_assets[str(p)]=sha(p)
docs_assets.update(docs['executable_dependencies'])
# Preserve this exact set of checked versions before later state updates.
doc_ref=hashlib.sha256(json.dumps(docs_assets,sort_keys=True).encode()).hexdigest()
archive=ROOT/'.aeep/langfuse-service-20261104'/('docs-inputs-'+doc_ref[:12]);archive.mkdir(mode=0o700,parents=True,exist_ok=True)
for name in docs['documents']:
    dest=archive/name;dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():assert sha(dest)==sha(ROOT/name)
    else:shutil.copyfile(ROOT/name,dest)
review={
    'purpose':'Actual private Langfuse ingestion, canonical receipt/trace/span linkage and export disablement through the already verified installed ordinary CLI; independent corrected cached offline docs. Engineering only.',
    'source':old['source'],'source_checks':old['source_checks'],'coordinator_source_snapshot':str(source),
    'service_assets':service_assets,'docs_assets':docs_assets,'expires_at':old['expires_at'],
    'work':str(ROOT/'.aeep/langfuse-service-20261104'),'ledger':prepared['ledger'],
    'docker':old['acquisition']['docker'],'compose':'/Applications/Docker.app/Contents/Resources/cli-plugins/docker-compose',
    'docker_socket':old['acquisition']['docker_socket'],'docker_config':old['acquisition']['docker_config'],
    'docker_config_sha256':sha(config) if config.exists() else None,'executables':executables,
    'python':str(runtime/'bin/python'),'python_symlink_target':str((runtime/'bin/python').resolve()),
    'installed_runtime':str(runtime),'installed_runtime_snapshot':snapshot(runtime),'installed_source':old['package']['installed_source'],
    'images':images,'image_ids':image_ids,'service_image_ids':service_ids,
    'new_grant':prepared['grant'],'maximum_driver_commands':47,'maximum_operations':63,'maximum_reserved_seconds':3200,'models':0,'cash_authority_usd':'0',
    'bound_derivation':{'noncleanup_driver_commands':28,'cleanup_commands_within_one_reserved_batch':19,'local_health_polls':20,'local_ingestion_polls':8,
        'nested_cli_wrapper_operations':4,'nested_http_transport_operations':1,'driver_overhead_operations':1,'reserved_cleanup_operations':1,
        'maximum_operations':63,'sum_maximum_reserved_seconds':2805,'grant_reserved_seconds':3200},
    'lifecycle':{'new_containers':8,'new_volumes':5,'new_internal_networks':1,'port':'127.0.0.1:39067',
        'upstream':'Pinned upstream Compose services and unmodified entrypoints; private bounded adaptation in compose-blueprint.json and service_plan.py.',
        'secrets':'Only new task-owned local Postgres/Redis/ClickHouse/Minio/NextAuth/project/user keys, generated after approval into private0600 files. No host/provider/operator/Codex credential read or copy.',
        'permissions':'Nonprivileged, no host PID/IPC, no socket or unrelated mounts. Postgres/Redis scoped bootstrap capabilities; one nonrecursive root chown on new Minio volume; ClickHouse nonroot writable new container layer; one task-only writable mc config bind.',
        'external_probe':'One fixed worker Node TCP connect attempt to1.1.1.1:443 must be denied; no application payload or task disclosure. Failure stops before export.',
        'readback':'At most8 local observations queries restricted to exact traceId, core/metadata fields and expanded attributes; retain only matching IDs/hash/verdict, never response bodies.',
        'disablement':'Four ordinary CLI commands: accounted preview/export, then accounted preview/disabled call under the other named configuration, with no auth variable and no extra transport debit.',
        'cleanup':'Budgeted before startup; stop only new containers after labels, image and immutable IDs match. Keep containers, images, volumes, network, local keys and installed runtime. No old-resource removal.'},
    'storage':{'minimum_host_free_bytes':50*1024**3,'free_bytes_at_preparation':shutil.disk_usage(ROOT).free,'docker_usage_record':str(OLD/'RESULTS.md'),
        'service_memory_proposal_mib':4096,'purpose':'Finite one-receipt engineering cap, not production resource acceptance; preserve existing Docker VM settings and all unrelated databases.'},
    'docs':{**docs,'maximum_attempts':1,'maximum_lychee_calls':2,'permitted_correction':'One exact corrected-input attempt; no tool/source repair or automatic retry under this review.'},
    'checked_document_snapshot':str(archive),
    'independence':'Docs and service each allow one component attempt. Run docs first to retain bound current inputs. A settled failure leaves the other eligible. Common unresolved authority/accounting/cleanup stops dispatch. No replay of successful wheel/source/image checks.',
    'remaining_limitations':['Generic v1 HTTPS-only setup metadata cannot express loopback HTTP; separate exact receipt-export/service scope is used, and generic setup readiness stays blocked.',
        'This is not a full SkillsBench workload journey, worker/MCP qualification, candidate usefulness, selection usefulness, production resources or release evidence.'],
    'not_authorized':['Models, comparisons, candidate admission, activation, publication, release or cash spending','Downloads, pulls, builds, dependency installs, new providers or host configuration changes',
        'Reading or copying operator/provider/Codex credentials; only newly generated task-local keys are within scope',
        'Old resource deletion, volume/image removal, Docker restart/resize, relaxed50GiB reserve','Automatic service/CLI replays, application/source repair or changed software under this exact review'],
    'all_stack_complete':False,'candidate_usefulness':'NOT_ASSESSED','selection_usefulness':'NOT_ASSESSED','comparisons':'PAUSED',
    'approval_reason':'The completed d7f05c3f acquisition review explicitly excluded containers, services, volumes, networks and local credential generation. CONTINUATION.md requires applicable provisioning/service/execution authority. This exact bounded review adds those operations and corrected docs; no architecture or paid-access decision is requested.'}
assert review['maximum_operations']==sum(review['bound_derivation'][k] for k in ('noncleanup_driver_commands','local_health_polls','local_ingestion_polls','nested_cli_wrapper_operations','nested_http_transport_operations','driver_overhead_operations','reserved_cleanup_operations'))
write(HERE/'operation-review.json',review)
print(json.dumps({'prepared':True,'execution':False,'review_sha256':sha(HERE/'operation-review.json'),'service_assets':len(service_assets),'docs_assets':len(docs_assets)}))
