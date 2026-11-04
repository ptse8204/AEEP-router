"""Freeze image acquisition and independent wheel/docs checks; never execute."""
from __future__ import annotations
import hashlib,json,shutil,subprocess,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'src'))
from aeep.assessment.models import content_digest
from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import RuntimeInstallation,digest,snapshot

def load(path):return json.loads(Path(path).read_bytes())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

source=verification_source_digest(ROOT);checks_path=HERE/'verification/checks.json';checks=load(checks_path)
assert checks['source_before']==checks['source_after']==source
assert len(checks['checks'])==13 and all(r['exit_code']==0 for r in checks['checks'])
frozen=load(HERE/'source-snapshot.json');assert frozen['source']==source
assert verification_source_digest(Path(frozen['coordinator_source_snapshot']))==source
assert not (HERE/'operation-review.json').exists()
assert load(HERE/'acquisition-driver-controls.json')['passed']
assert load(HERE/'package-boundary-preflight.json')['exit_code']==0
plan=RuntimeInstallation.model_validate(load(HERE/'package-installation.json'))
package=load(HERE/'package-preparation.json');assert digest(plan)==package['installation_digest']
acquisition=load(HERE/'image-acquisition-plan.json');assert len(acquisition['images'])==6
prepared=load(HERE/'acquisition-preparation.json');assert prepared['source']==source
assert prepared['artifact_plan_sha256']==content_digest(acquisition)
docker=Path('/Applications/Docker.app/Contents/Resources/bin/docker')
work=ROOT/'.aeep/workflow-telemetry-20261104';config=work/'docker-config'
assert load(config/'config.json')=={'auths':{'https://index.docker.io/v1/':{}},'credsStore':'','credHelpers':{}}
assert shutil.disk_usage(ROOT).free>=56*1024**3
raw=subprocess.check_output([str(docker),'--config',str(config),'system','df','--format','json'],timeout=30)
usage=[json.loads(line) for line in raw.splitlines() if line]
(HERE/'docker-usage.json').write_text(json.dumps({'observed_usage':usage,'resources_changed':False},indent=2)+'\n')
docs=load(HERE.parent/'workflow-skillrank-20261103/operation-review.json')['docs']
document_hashes={name:sha(ROOT/name) for name in docs['documents']}
docs_snapshot=work/('docs-inputs-'+content_digest(document_hashes)[:12]);docs_snapshot.mkdir(mode=0o700)
for name in docs['documents']:
 target=docs_snapshot/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
docs['permitted_correction']='At most two offline attempts on these exact inputs/tools/config; stop after success. No tool/source repair, download or repeated successful check.'
assets={str(p):sha(p) for p in HERE.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md','.sb'}
        and not p.name.startswith(('withdrawn-draft-','draft-withdrawal'))}
for p in (HERE.parent/'langfuse-runtime-preparation-20261104').iterdir():
 if p.is_file():assets[str(p)]=sha(p)
for name in (*docs['documents'],'Makefile','.markdownlint-cli2.jsonc','.lychee.toml'):
 assets[str(ROOT/name)]=sha(ROOT/name)
for name in (str(docker),str(config/'config.json'),str(checks_path),str(Path(sys.executable).resolve())):
 assets[name]=sha(name)
assets[docs['runtime_record']]=sha(docs['runtime_record'])
for wheel in plan.wheels:
 path=Path(plan.wheelhouse)/wheel.filename;assert sha(path)==wheel.sha256;assets[str(path)]=wheel.sha256
for row in load(HERE.parent/'langfuse-runtime-preparation-20261104/verified-source-bindings.json'):
 assert sha(row['cache'])==row['sha256'];assets[row['cache']]=row['sha256']
common={str(checks_path),str(HERE/'source-snapshot.json'),str(Path(sys.executable).resolve())}
acquisition_names=common|{str(HERE/name) for name in ('run-acquisition.py','image-acquisition-plan.json','acquisition-preparation.json','acquisition-driver-controls.json','check-acquisition-driver.py')}
acquisition_names|={str(docker),str(config/'config.json')}
acquisition_names|={name for name in assets if '/langfuse-runtime-preparation-20261104/' in name or '/langfuse-source-preparation-20261104/' in name}
package_names=common|{str(HERE/name) for name in ('run-components.py','package-installation.json','package-preparation.json','package-check.py','package-boundary.py','package.sb','package-boundary-preflight.json')}
package_names|={str(Path(plan.wheelhouse)/wheel.filename) for wheel in plan.wheels}
docs_names=common|{str(HERE/'run-components.py'),docs['runtime_record']}
docs_names|={str(ROOT/name) for name in (*docs['documents'],'Makefile','.markdownlint-cli2.jsonc','.lychee.toml')}
component_assets={name:{path:assets[path] for path in sorted(names)} for name,names in [('acquisition',acquisition_names),('package',package_names),('docs',docs_names)]}
review={
 'purpose':'Acquire six exact Langfuse/support images for static license/permission inspection before a separate service review. Independently verify the changed installed CLI and current offline docs. No Langfuse or model execution.',
 'source':source,'source_checks':str(checks_path),'coordinator_source_snapshot':frozen['coordinator_source_snapshot'],
 'assets':assets,'component_assets':component_assets,'executable_links':{sys.executable:str(Path(sys.executable).resolve())},'expires_at':'2026-11-08T12:00:00Z',
 'acquisition':{**acquisition,'docker':str(docker),'docker_config':str(config),'docker_socket':'/Users/edwintse/.docker/run/docker.sock','work':str(work),
   'grant':prepared['grant'],'canonical_database':prepared['ledger'],'maximum_total_operations':31,'maximum_model_turns':0,'maximum_reserved_seconds':4200,
   'commands':'At most two quiet image pulls and one RepoDigests inspection per immutable reference. Up to12 subsequent read-only image-save streams for static license/header audits. No disk archive or executable extraction. No Docker container create/run/exec/build, service, volume, network or credential setup.',
   'accounting':'New isolated finite engineering grant in the existing canonical database. Preserve every old grant/counter, including42 settled SkillRank operations. Child wall intervals and exclusive driver overhead recorded separately; network transfer and cash measurement remain UNKNOWN.',
   'downloads':'Six exact ARM64 OCI manifests/configs and their pinned layers only; compressed layer inventory1,164,219,714bytes. Anonymous public registry pull flow with an empty private Docker configuration; no host credentials/helpers or new registry account.',
   'independence':'A settled download/reference-inspection failure leaves other images eligible. Missing terminal evidence, authority/source/accounting/cleanup uncertainty or reserve violation stops dispatch. Each actual image-pull attempt retains its charge.'},
 'package':{**package,'runtime':plan.destination,'prepared_workspace_sha256':snapshot(HERE/'package-execution/work'),
   'executable_dependencies':{name:expected for name,expected in docs['executable_dependencies'].items() if name.endswith('/sandbox-exec') or 'Python.framework/' in name},
   'checks':'Existing owned installer/idempotence and sandbox checks, exact installed-source hash, CLI help including export/define-telemetry, old/new workflow and MCP state/receipt-export contracts; retain unchanged runtime. No HTTP destination, upstream guest program or model is invoked.'},
 'docs':docs,'checked_document_snapshot':str(docs_snapshot),
 'storage':{'minimum_free_bytes':50*1024**3,'acquisition_start_headroom_bytes':6*1024**3,'package_required_bytes':package['required_bytes'],'usage_record':str(HERE/'docker-usage.json'),
   'preserve':'All existing images, containers, volumes, backups, caches, source work and retained runtimes. No pruning, deletion of old resources, Docker restart or memory-setting changes.'},
 'independence':'Acquisition/package/docs are separate component attempts. Independent installed/docs checks continue after a settled acquisition failure; missing accounting/cleanup/authority blocks common dispatch. Acquisition driver one attempt, up to two explicitly allowed idempotent pulls per image; package one attempt; docs up to two, stopping after success.',
 'not_authorized':['Model turns, comparisons, admission, activation or release','Langfuse or other service/container/volume/network startup or creation','Generation, reading, copying or use of operator/provider/Codex credentials','Dependency changes beyond the reviewed AEEP wheel and32 exact cached dependency wheels','Any shell installer, guest executable, image build or paid service','Existing resource deletion, host/global installation, Docker restart/configuration change or reduced storage reserve'],
 'all_stack_complete':False,'langfuse_functional_readiness':'NOT_VERIFIED','candidate_usefulness':'NOT_ASSESSED','selection_usefulness':'NOT_ASSESSED','comparisons':'PAUSED',
 'approval_reason':'Completed1a091b2b covered SkillRank-only runtime continuation and forbade downloads/installations. This binds six different untrusted image artifacts, the changed AEEP wheel and current docs. CONTINUATION.md requires applicable download/installation/execution authority. New finite engineering definitions/budget use standing delegation; no architecture, cash or provider decision is needed.'}
(HERE/'operation-review.json').write_text(json.dumps(review,indent=2)+'\n')
print(json.dumps({'review_sha256':sha(HERE/'operation-review.json'),'assets':len(assets),'source':source,'images':6,'models':0,'execution_started':False}))
