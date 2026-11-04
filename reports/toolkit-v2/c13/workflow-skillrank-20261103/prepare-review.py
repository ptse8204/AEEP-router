"""Freeze a concrete grouped review after source/package preparation; never execute."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import RuntimeInstallation, digest, snapshot as snapshot_tree


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


source = verification_source_digest(ROOT)
checks_path = HERE / 'verification/checks.json'
checks = load(checks_path)
assert checks['source_before'] == checks['source_after'] == source
assert len(checks['checks']) == 13 and all(c['exit_code'] == 0 for c in checks['checks'])
assert not (HERE / 'operation-review.json').exists()
assert shutil.disk_usage(ROOT).free >= 52 * 1024**3
package = load(HERE / 'package-preparation.json')
assert package['source'] == source and package['unchanged_dependencies'] == 32
plan = RuntimeInstallation.model_validate(load(HERE / 'package-installation.json'))
assert digest(plan) == package['installation_digest']
previous = load(HERE.parent / 'integration-snapshot-correction-20261103/operation-review.json')
docs = previous['docs']
docs['permitted_correction'] = 'Up to two offline attempts with these exact inputs/tools/config; stop after success. No source/tool repair or repeated successful check.'
from aeep.assessment.models import content_digest

document_hashes = {name: sha(ROOT / name) for name in docs['documents']}
docs_snapshot = ROOT / ('.aeep/workflow-skillrank-20261103/docs-inputs-' + content_digest(document_hashes)[:12])
docs_snapshot.mkdir(mode=0o700, exist_ok=True)
for name in docs['documents']:
    target = docs_snapshot / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == (ROOT / name).read_bytes()
    else:
        shutil.copyfile(ROOT / name, target)
assets = {}
for p in HERE.iterdir():
    if p.is_file() and p.suffix in {'.py', '.json', '.md', '.rs', '.sb'}:
        assets[str(p)] = sha(p)
for name in docs['documents']:
    assets[str(ROOT / name)] = sha(ROOT / name)
for name in ('Makefile', '.markdownlint-cli2.jsonc', '.lychee.toml'):
    assets[str(ROOT / name)] = sha(ROOT / name)
for name in ('/usr/local/bin/docker', sys.executable):
    assets[str(Path(name).resolve(strict=True))] = sha(name)
assets[str(checks_path)] = sha(checks_path)
prepared=load(HERE/'workflow-preparation.json')
snapshot=load(HERE/'source-snapshot.json')
assert prepared['source']==snapshot['source']==source
config=Path(prepared['runtime'])/'docker-config/config.json'
assert load(config)=={'auths':{'https://index.docker.io/v1/':{}},'credsStore':'','credHelpers':{}}
assets[str(config)]=sha(config)
assert load(HERE/'driver-controls.json')['passed']
from aeep_toolkit.file_runtime import FileRuntimeInstallation
for name in ('retained','disposable'):
    value=FileRuntimeInstallation.model_validate(load(HERE/(name+'-installation.json')))
    for entry in value.files:
        path=Path(value.artifact_root)/entry.source
        assert path.stat().st_nlink==1 and sha(path)==entry.sha256
        assets[str(path)]=entry.sha256
for name in ['skillrank-build-preparation-20261103/run-components.py',
             'skillrank-license-correction-20261103/runtime-execution/summary.json']:
    path=HERE.parent/name
    assets[str(path)]=sha(path)
review={
 'purpose':'Retain the pinned SkillRank binary through ordinary CLI setup/readiness/search/show/selective removal; independently verify current wheel and changed offline docs. Engineering only.',
 'source':source,'source_checks':str(checks_path),'coordinator_source_snapshot':snapshot['coordinator_source_snapshot'],'assets':assets,
 'executable_links':{name:str(Path(name).resolve(strict=True)) for name in ('/usr/local/bin/docker',sys.executable)},
 'expires_at':'2026-11-06T12:00:00Z',
 'workflow':{**prepared,'maximum_additional_operations':24,'maximum_additional_reserved_seconds':945,
   'prepared_docker_config':str(Path(prepared['runtime'])/'docker-config'),
   'cumulative_operation_ceiling':40,'cumulative_time_ceiling_seconds':4500,'maximum_new_containers':4,
   'maximum_catalog_queries':3,'maximum_model_turns':0,'cash_authority_usd':'0','actual_cash_measurement':'UNKNOWN',
   'backend_probe':'One fresh standard-library boundary probe on the retained worker, including installed binary hash, owned writes, denied root/network access and absent host/socket/credential environment.',
   'journey':'Ordinary CLI: setup/idempotence, readiness from both named configurations, upstream search/show/missing-record queries, shared-reference removal refusal, and conflict-preserving removal of one newly owned disposable copy.',
   'accounting':'19 workflow wrapper reservations, three nested catalog operations, one contained boundary operation, one exclusive driver-overhead operation. Original16 charges and grant limits/counters remain. Separate overhead plan identity preserves the settled-plan dispatch barrier; no separate database or grant.',
   'scope_amendment':'Add the exact retained grader environment and current definitions to the existing grant only after approval. No new grant, reset, larger ceiling, destination or expiry expansion.',
   'retained_runtime':'Main owned file runtime stays; copied Linux binary is never invoked directly on macOS. Static dependency/build caches and every pre-existing resource stay.',
   'removal':'Remove only newly owned containers after exact image/label/ID checks and the new disposable runtime through its unchanged journal. Add, hash-check and remove only the explicit first-party preservation-control note.',
   'claims':'Catalog component workflow only. This does not execute SkillsBench tasks or close bounded SkillRank evaluation, either domain journey, or all-stack readiness.'},
 'package':{**package,'runtime':plan.destination,'prepared_workspace_sha256':snapshot_tree(HERE/'package-execution/work'),
   'checks':'Owned installer idempotence, native home/outside-write/network denial, actual installed-source hash, eight CLI-help surfaces, legacy schemas, installed file/catalog contracts, and report family encoding. Retain unchanged private runtime.'},
 'docs':docs,'checked_document_snapshot':str(docs_snapshot),
 'storage':{'minimum_free_bytes':50*1024**3,'start_headroom_bytes':2*1024**3,'package_required_bytes':package['required_bytes'],
   'preflight_docker_usage':str(HERE/'docker-usage.json'),'preserve':'All existing images, containers, volumes, caches, backups, runtimes and unrelated work. No pruning or old-resource removal.'},
 'allowed_disclosure':'No external disclosure. Only reviewed first-party catalog metadata enters the offline worker; no benchmark inputs, model prompts, task outputs or credentials.',
 'retained_resources':'Retain main SkillRank runtime, package runtime, existing offline docs checker and all original resources. Private workspaces and receipts stay.',
 'independence':'Separate workflow/package/docs attempts. A settled failed component leaves independent checks eligible; authority, source, accounting or cleanup uncertainty blocks dispatch. Runtime allows one attempt; no repeated upstream query or changed software under this review. Docs allow at most two offline attempts, stopping after success.',
 'failure_diagnostics':'Retain at most8KiB stdout/stderr from a failed CLI engineering step. Queries/catalog are the explicitly reviewed first-party fixtures only. Never retain task payloads or credentials.',
 'not_authorized':['Model turns, comparisons, candidate admission or activation','Downloads, image pulls/builds, new packages or dependencies',
   'Credential reading/copying, paid services, new destinations or host/global activation','Publication, payment or release','Existing images/volumes/backups/old-runtime deletion','Reducing the50GiB reserve'],
 'automatic_retry':False,'all_stack_complete':False,'candidate_usefulness':'NOT_ASSESSED','selection_usefulness':'NOT_ASSESSED','comparisons':'PAUSED',
 'approval_reason':'Completed6057c786 binds the old source build and direct component search/show. It does not authorize the changed file installer/catalog worker, retained runtime installation or current wheel/docs. The continuation reserves untrusted installation/execution and container provisioning. No architecture or larger-ceiling decision is requested.'}
(HERE/'operation-review.json').write_text(json.dumps(review,indent=2)+'\n')
print(json.dumps({'prepared':True,'review_sha256':sha(HERE/'operation-review.json'),'assets':len(assets),'source':source,'additional_workflow_operations':24,'models':0,'execution_started':False}))
