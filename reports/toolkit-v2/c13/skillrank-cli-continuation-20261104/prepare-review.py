"""Bind the remaining-only operation; never dispatch or alter the grant."""
import hashlib,json,sqlite3,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OLD=HERE.parent/'workflow-skillrank-20261103'
sys.path.insert(0,str(ROOT/'src'))
from aeep.assessment.models import content_digest
from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import parse_installation
from aeep_toolkit.workflow_runtime import observe

def load(path):return json.loads(Path(path).read_bytes())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
prior=load(OLD/'operation-review.json');prepared=load(OLD/'workflow-preparation.json')
assert sha(OLD/'operation-review.json')=='c0227f6f3e84a950c31bc51b6c9dd542650236b1e00811acbe8830f008c2a5d0'
failed=load(OLD/'runtime-execution/summary.json')
assert not failed['passed'] and not failed['cleanup_uncertain'] and not failed['accounting_uncertain']
assert load(OLD/'package-execution/summary.json')['passed'] and load(OLD/'docs-attempt-1.json')['passed']
assert load(HERE/'driver-controls.json')['passed'] and load(HERE/'boundary-controls.json')['passed']
assert verification_source_digest(ROOT)==verification_source_digest(Path(prior['coordinator_source_snapshot']))==prior['source']
plan=parse_installation(load(OLD/'retained-installation.json'));observation=observe(plan)
assert observation['installed'] is True and not Path(load(OLD/'disposable-installation.json')['destination']).exists()
keys=[key for name in ('document-search','software-show','missing-show','disposable-setup','disposable-conflict','disposable-remove') for key in (name+'-preview',name)]+['retained-shared-removal-preview']
with sqlite3.connect(Path(prepared['original_ledger']).as_uri()+'?mode=ro',uri=True) as db:
 counters=list(db.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(prepared['authorization_id'],)).fetchone())
 assert counters==failed['counters_after'] and counters[0]==24 and counters[1]==0 and counters[3]=='0'
 assert not db.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(prepared['authorization_id'],)).fetchone()
 for key in keys:assert not db.execute('SELECT 1 FROM assessment_operations WHERE id=?',('workflow:'+prepared['request_id']+':'+key,)).fetchone(),key
assets={str(p.resolve()):sha(p) for p in HERE.iterdir() if p.is_file() and p.name!='operation-review.json'}
for name in ('run-workflow.py','source-snapshot.json','operation-review.json','operator-approval.json','workflow-preparation.json','workflow.json','registry.json','policy.json','catalog.json','catalog-runtime.json','accounting.json','manifest.json','retained-installation.json','disposable-installation.json','scope-amendment.json',
 'runtime-execution/summary.json','runtime-execution/boundary-receipt.json','runtime-execution/boundary-result.json','runtime-execution/operation-ledger.json','runtime-execution/driver-operation-ledger.json','runtime-execution/retained-setup.json','runtime-execution/retained-idempotent.json','runtime-execution/document-data-readiness-preview.json','runtime-execution/software-engineering-readiness-preview.json',
 'package-execution/summary.json','docs-attempt-1.json'):
 assets[str((OLD/name).resolve())]=sha(OLD/name)
for entry in plan.files:assets[str(Path(plan.destination)/entry.destination)]=sha(Path(plan.destination)/entry.destination)
for path in load(OLD/'catalog-runtime.json')['executable_dependencies']:assets[path]=sha(path)
config=Path(prepared['runtime'])/'docker-config/config.json';assets[str(config)]=sha(config)
assets[prior['source_checks']]=sha(prior['source_checks'])
review={'purpose':'Run one diagnostic containment/version check, then only unstarted catalog/selective-removal phases. Preserve passed setup, wheel and docs.',
 'parent_review_sha256':sha(OLD/'operation-review.json'),'source':prior['source'],'source_checks':prior['source_checks'],
 'coordinator_source_snapshot':prior['coordinator_source_snapshot'],'expires_at':prior['expires_at'],'assets':assets,
 'counters_before':counters,'original_grant':prepared['authorization_id'],'unstarted_cli_operation_keys':keys,
 'maximum_additional_operations':18,'maximum_additional_reserved_seconds':765,'maximum_new_containers':4,'maximum_catalog_queries':3,
 'maximum_model_turns':0,'cash_authority_usd':'0','actual_cash_measurement':'UNKNOWN',
 'delegated_budget_amendment':{'file':str(HERE/'budget-amendment.json'),'old_operation_ceiling':40,'new_operation_ceiling':42,
  'unchanged_time_ceiling_seconds':4500,'unchanged_model_ceiling':0,'unchanged_cash_ceiling_usd':'0',
  'reason':'Two additional finite first-party probe/driver operations; the old24 operations remain charged. Uses AGENTS.md and docs/ASSESSMENT_TESTING.md standing September25/27 finite-amendment authority. Prepared, not applied.'},
 'source_changes':'Product source, upstream binary, data, image, dependency versions and permission boundaries are unchanged. Only first-party containment classification/diagnostic retention and remaining-phase bookkeeping change.',
 'diagnostics':'The old underlying failure remains UNKNOWN. Retain actual root-write errno, network errno/category, version exit code and at most1024bytes selected public binary stderr; real executor status/error categories and reviewed first-party catalog/probe results. No prompts, credential values or task artifacts.',
 'boundary':'Existing offline worker35dc1bcb; read-only root and binary/AEEP package mounts, no host home/socket/credential mounts, uid65534, zero capabilities, no-new-privileges, resource limits from the unchanged definition. Only owned tmp is writable.',
 'runtime':'Keep the main installed binary/runtime, package runtime, original caches, all images/volumes/backups and unrelated work. Remove only new owned containers by verified ID/image/label, the explicit preservation-control note and unchanged new disposable copy.',
 'storage':{'minimum_free_bytes':50*1024**3,'start_headroom_bytes':64*1024**2},
 'not_authorized':['Models, comparisons, candidate admission or activation','Downloads, pulls, builds, dependencies or package/docs reruns','Credential handling, new destinations/services, cash, publication or release','Existing image/volume/backup/runtime deletion','Reducing the50GiB reserve'],
 'automatic_retry':False,'all_stack_complete':False,'candidate_usefulness':'NOT_ASSESSED','selection_usefulness':'NOT_ASSESSED','comparisons':'PAUSED',
 'approval_reason':'The exact c0227f6f runtime attempt is terminal and cannot cover changed probe bytes or a fresh containment call. The continuation policy reserves untrusted execution/provisioning. The finite two-operation amendment is already delegated and preserves every prior charge; no architecture decision or paid authority is requested.'}
assert not (HERE/'operation-review.json').exists()
(HERE/'operation-review.json').write_text(json.dumps(review,indent=2)+'\n')
print(json.dumps({'prepared':True,'review_sha256':sha(HERE/'operation-review.json'),'assets':len(assets),'product_source_unchanged':True,'old_charges_preserved':counters[0],'maximum_additional_operations':18,'models':0,'execution_started':False}))
