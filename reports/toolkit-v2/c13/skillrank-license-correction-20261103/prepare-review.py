"""Bind only unstarted runtime work, preserving the existing grant and charges."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
SOURCE=ROOT/'.aeep/stack-frozen-source-e48eec5f3039'
sys.path.insert(0,str(SOURCE/'src'))
from aeep.assessment.models import AssessmentAuthorization,RecipeMaterializationRequest,content_digest
from aeep.assessment.verification import verification_source_digest

def load(path):return json.loads(Path(path).read_bytes())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

OLD=HERE.parent/'skillrank-build-preparation-20261103'
parent=load(OLD/'operation-review.json')
assert sha(OLD/'operation-review.json')=='d6fbbad37ecac25b1900d434a0c6c38fedb1758cb15e1f3fbbbfe0430230cdbd'
assert verification_source_digest(SOURCE)==parent['source']
failed=load(OLD/'runtime-execution/summary.json')
assert not failed['passed'] and not failed['accounting_uncertain'] and not failed['cleanup_uncertain']
assert failed['cleanup']==[] and not (OLD/'runtime-execution/image-binding.json').exists()
assert load(OLD/'package-execution/summary.json')['passed'] and load(OLD/'docs-attempt-1.json')['passed']
metadata=load(HERE/'registry-metadata-audit.json')
assert metadata['passed'] and len(metadata['rows'])==86
ledger=(OLD/'runtime-execution/canonical.sqlite3').resolve()
old_ledger=load(OLD/'runtime-execution/operation-ledger.json')
with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
 request=RecipeMaterializationRequest.model_validate_json(db.execute("SELECT payload_json FROM assessment_records WHERE kind='recipe_materialization_request' AND id=?",(old_ledger['plan_id'],)).fetchone()[0])
 grant=AssessmentAuthorization.model_validate_json(db.execute("SELECT payload_json FROM assessment_records WHERE kind='authorization' AND id=?",(request.authorization_id,)).fetchone()[0])
 counters=list(db.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone())
 assert counters[:2]==[2,0] and counters[3]=='0'
 assert db.execute("SELECT count(*) FROM assessment_operations WHERE grant_id=? AND state='reserved'",(grant.authorization_id,)).fetchone()[0]==0
assets={str(p):sha(p) for p in HERE.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md'} and p.name!='operation-review.json'}
for name in ['operation-review.json','operator-approval.json','runtime-execution/summary.json',
             'runtime-execution/operation-ledger.json','runtime-execution/crate-source-receipt.json',
             'package-execution/summary.json','docs-attempt-1.json']:
 assets[str(OLD/name)]=sha(OLD/name)
for name in parent['executable_links'].values():assets[name]=sha(name)
assets[parent['source_checks']]=sha(parent['source_checks'])
adler=ROOT/'.aeep/skillrank-build-preparation-20261103/runtime/archives/adler2-2.0.1.crate'
lock=load(HERE/'locked-crates.json');expected=next(r['sha256'] for r in lock['files'] if r['name']=='adler2')
assert sha(adler)==expected
assets[str(adler)]=expected
review={k:parent[k] for k in ['source','source_checks','executable_links','expires_at','build_context','build_context_sha256','source_revision','compiler_image','compiler_label','compiler_architecture','compiler_image_compressed_bytes','compiler_pull','storage']}
review.update(purpose='Complete only the unstarted same-source SkillRank runtime after the first-party SPDX guard failure. Package/docs passed and must not rerun.',
 parent_review_sha256=sha(OLD/'operation-review.json'),assets=assets,
 coordinator_source_snapshot=str(SOURCE),runtime=str(ROOT/'.aeep/skillrank-license-correction-20261103/runtime'),
 original_ledger=str(ledger),original_request_id=request.plan_id,original_request_sha256=content_digest(request),
 original_grant_id=grant.authorization_id,original_limits=grant.limits.model_dump(mode='json'),original_counters=counters,
 original_grant_digest=content_digest(grant),cached_archives={adler.name:str(adler)},
 remaining_archive_downloads=85,maximum_archive_http_attempts_each=2,
 maximum_compressed_source_bytes=64*1024**2,maximum_expanded_source_bytes=512*1024**2,
 reviewed_license_expressions=sorted({r['license_expression'] for r in metadata['rows']}),
 license_guard='Match every actual archive checksum and manifest license to the exact86-version inventory before compilation; preserve license files. Private engineering only; no redistribution clearance is claimed.',
 maximum_cumulative_operations=40,maximum_additional_operations=38,maximum_cumulative_reserved_seconds=4500,
 prior_operations_charged=2,prior_elapsed_seconds_charged=counters[2],maximum_model_turns=0,cash_authority_usd='0',
 maximum_image_pulls=1,maximum_builds=1,maximum_new_containers=3,maximum_search_readiness_attempts=5,
 expiry_amendment='Retain the original authorization and limits/counters; record only a finite expiry extension to this review expiry under standing delegation. No new grant.',
 corrections='First-party SPDX inspection and remaining-phase bookkeeping change; upstream source, all86 archive hashes, compiler image, task-independent commands and permissions stay. No repeated started model/task/compile or source repair.',
 independence='Frozen checked coordinator permits independent implementation. This review contains no package/docs attempt and cannot consume or reset their completed evidence.',
 not_authorized=['Models or comparisons','New software versions or dependency/image replacement','Host/global installation, OS packages, credentials, new services outside the owned check','Cash, admission, activation, publication or release','Existing image/volume/runtime/backups deletion','Changing the50GiB reserve'],
 retained_resources='Keep the exact compiler image and built runtime, source/cache, original partial resources and every existing image,volume,runtime,backup and user edit. Remove only new check containers with verified IDs/image/label.',
 automatic_retry=False,all_stack_complete=False,candidate_usefulness='NOT_ASSESSED',selection_usefulness='NOT_ASSESSED',comparisons='PAUSED',
 approval_reason='d6fbbad3 ended at its exact first-party license allowlist. The corrected guard and fresh remaining-phase driver have new bytes and acknowledge the complete locked license inventory, including certificate-data terms. The continuation reserves changed untrusted execution/installation and provisioning authority. No architecture or larger-ceiling decision is needed.')
assert not (HERE/'operation-review.json').exists()
(HERE/'operation-review.json').write_text(json.dumps(review,indent=2)+'\n')
print(json.dumps({'prepared':True,'review_sha256':sha(HERE/'operation-review.json'),'assets':len(assets),'prior_charged_operations':2,'original_grant_preserved':True,'models':0,'execution_started':False}))
