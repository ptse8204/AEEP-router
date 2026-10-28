"""Add only actually reproduced PyMdown cases and keep private wheel provenance."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')

def main():
    previous=HERE.parent/'repository-issue-behavior-20261028/provisional-pool.json';old=json.loads(previous.read_text());old_cases=ROOT/old['cases_file'];assert sha(old_cases)==old['cases_file_sha256']
    audit_path=HERE/'completion-audit.json';audit=json.loads(audit_path.read_text());assert audit['batch_completed'] and audit['physical_receipt_integrity_passed'] and audit['all_owned_containers_absent']
    assert audit['canonical_receipts_reopened']==audit['completed_attempts_reopened']==5 and audit['failed_attempts_reopened']==0 and len(audit['eligible_cases'])==2
    bundle=json.loads((HERE/'bundle-execution-result.json').read_text());assert bundle['all_components_passed'] and bundle['source_unchanged']
    for item in bundle['components']:assert item['passed'] and sha(Path(item['result_file']))==item['result_sha256']
    operations=json.loads((HERE/'operation-ledger.json').read_text())['operations'];assert len(operations)==7
    with sqlite3.connect('file:/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3?mode=ro',uri=True) as c:
        for item in operations:assert c.execute('SELECT state FROM assessment_operations WHERE id=?',(item['operation_id'],)).fetchone()[0]=='complete' and item['elapsed_seconds'] is not None and math.isfinite(item['elapsed_seconds']) and item['elapsed_seconds']>=0
        after=list(c.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    before=audit['grant_before'];assert after==audit['grant_after'];seconds=sum(x['elapsed_seconds'] for x in operations)
    assert after[0]-before[0]==7 and after[1]==before[1] and after[3]==before[3] and math.isclose(after[2]-before[2],seconds,abs_tol=1e-7)
    assert json.loads((HERE/'canary-cleanup.json').read_text())['unchanged_owned_canary_removed']
    review=json.loads((HERE/'operation-review.json').read_text());cases=json.loads(old_cases.read_text());bindings=dict(old['source_runtime_bindings']);pin=json.loads((HERE/'portable-wheel-review.json').read_text())['pin']
    for case in json.loads((ROOT/review['cases_file']).read_text()):
        identity=case['input']['task_id'];assert identity in audit['eligible_cases'] and identity not in bindings
        cases.append(case);bindings[identity]={'evidence_manifest':str(audit_path.relative_to(ROOT)),'source_digest':review['source_digest'],'image_id':review['parent_image'],'image_tag':'aeep-toolkit-v2/repository-grader:py313-multifile-20261027','per_payload_wheels':[{'project':'Markdown','version':'3.9','sha256':pin['sha256'],'mode':'Private wheel ZIP on grader sys.path;not installed in image or host.'}],'observer_profile':'Reference/original tests with all original assertions;fresh actual ZIP-origin/hash/rendering probe passed. No model qualification or value transfer.','recipe_digest':review['request']['recipe_digest']}
    assert len(cases)==len({(c['source_repository'].casefold(),c['source_revision']) for c in cases})==len({c['input']['source_sha256'] for c in cases})==62
    counts=dict(Counter(c['input']['family'] for c in cases));assert counts=={'single-file-repair':25,'contract-audit':15,'multi-file-repair':22}
    out=ROOT/'.aeep/repository-provisional-pool-pymdown-20261028';out.mkdir(exist_ok=False);target=out/'cases.json';target.write_text(json.dumps(cases,indent=2)+'\n')
    pool={**old,'cases_file':str(target.relative_to(ROOT)),'cases_file_sha256':sha(target),'case_count':62,'repository_count':len({c['source_repository'].casefold() for c in cases}),'family_counts':counts,'required_reference_identities':sum(len(c['truth']['fail_to_pass'])+len(c['truth']['pass_to_pass']) for c in cases),'source_runtime_bindings':bindings,'inputs':[{'manifest':str(previous.relative_to(ROOT)),'manifest_sha256':sha(previous),'cases_sha256':sha(old_cases)},{'manifest':str(audit_path.relative_to(ROOT)),'manifest_sha256':sha(audit_path),'cases_sha256':sha(ROOT/review['cases_file'])}],'missing_family_counts':{k:47-n for k,n in counts.items()},'latest_grant':after,'batch_operations_including_build':7,'builds_in_this_batch':0,'batch_charged_operation_seconds':seconds,'new_external_calls_for_consolidation':0,'cases_adopted':0,'stages_frozen':False,'qualification':False,'comparative_usefulness':False,'selection':False,'optional_pymdown_runtime':'Verified exact Markdown3.9 private ZIP import;not an image installation.','initial_failed_probe_kept':True}
    assert pool['required_reference_identities']==3951 and pool['repository_count']==39
    save(HERE/'provisional-pool.json',pool);save(HERE/'final-accounting-audit.json',{'passed':True,'canonical_operations_reopened':7,'physical_receipts_and_completed_attempts_reopened':5,'grant_before':before,'grant_after':after,'charged_operation_seconds':seconds,'all_operations_complete':True,'model_turns':0,'cash_delta':0,'all_owned_containers_and_canary_absent':True,'all_images_retained':True,'new_calls_for_consolidation':0,'source_digest':review['source_digest'],'private_markdown_zip_import_verified':True,'image_or_host_installations':0})
    print(json.dumps({k:pool[k] for k in ('case_count','repository_count','family_counts','required_reference_identities','missing_family_counts','latest_grant','batch_charged_operation_seconds')}))

if __name__=='__main__':main()
