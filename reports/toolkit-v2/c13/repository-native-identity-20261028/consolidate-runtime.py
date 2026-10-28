"""Retain the new reproduced native task; never duplicate compatibility controls."""
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
    prior=HERE.parent/'repository-pymdown-portable-20261028/provisional-pool.json';old=json.loads(prior.read_text())
    assert sha(ROOT/old['cases_file'])==old['cases_file_sha256']
    audit=json.loads((HERE/'completion-audit.json').read_text());result=json.loads((HERE/'bundle-execution-result.json').read_text())
    assert audit['physical_receipt_integrity_passed'] and audit['all_owned_containers_absent'] and audit['native_collection_verified']
    assert audit['canonical_receipts_reopened']==audit['completed_attempts_reopened']==15 and audit['failed_attempts_reopened']==0
    assert len(audit['eligible_cases'])==3 and result['source_unchanged']
    assert [c['passed'] for c in result['components']]==[True,True,False]
    # The initial docs failure stays a failure; it cannot invalidate observed grading.
    operations=json.loads((HERE/'operation-ledger.json').read_text())['operations'];assert len(operations)==17
    with sqlite3.connect('file:/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3?mode=ro',uri=True) as c:
        for op in operations:
            assert c.execute('SELECT state FROM assessment_operations WHERE id=?',(op['operation_id'],)).fetchone()[0]=='complete'
            assert op['elapsed_seconds'] is not None and math.isfinite(op['elapsed_seconds']) and op['elapsed_seconds']>=0
        after=list(c.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    assert after==audit['grant_after'];before=audit['grant_before'];seconds=sum(op['elapsed_seconds'] for op in operations)
    assert after[0]-before[0]==17 and after[1]==before[1] and after[3]==before[3] and math.isclose(after[2]-before[2],seconds,abs_tol=1e-7)
    assert json.loads((HERE/'canary-cleanup.json').read_text())['unchanged_owned_canary_removed']
    review=json.loads((HERE/'operation-review.json').read_text());meta=json.loads((HERE/'execution-cases.json').read_text())
    current=json.loads((ROOT/review['cases_file']).read_text());cases=json.loads((ROOT/old['cases_file']).read_text());bindings=dict(old['source_runtime_bindings'])
    new=next(c for c in current if c['input']['task_id']==meta['new_case_id']);identity=new['input']['task_id']
    assert identity in audit['eligible_cases'] and identity not in bindings
    for control in current[:-1]:assert control==next(c for c in cases if c['input']['task_id']==control['input']['task_id'])
    cases.append(new);bindings[identity]={'evidence_manifest':str((HERE/'completion-audit.json').relative_to(ROOT)),
        'source_digest':review['source_digest'],'image_id':review['parent_image'],'image_tag':'aeep-toolkit-v2/repository-grader:py313-multifile-20261027',
        'observer_profile':'Explicit casev6/native pytest hooks;frozen915-name mapping confirmed before body trials;reference/original/both partials reproduced. Two legacy controls reproduced. No transfer of old corpus-wide qualification.',
        'operator_program_sha256':sha(HERE/'observer-v6-integrated.py'),'recipe_digest':review['request']['recipe_digest'],
        'identity_map_sha256':sha(HERE/'identity-map.json'),'upstream_assertions_unchanged':True,'earlier899of915_failure_preserved':True}
    assert len(cases)==len({(c['source_repository'].casefold(),c['source_revision']) for c in cases})==len({c['input']['source_sha256'] for c in cases})==63
    counts=dict(Counter(c['input']['family'] for c in cases));assert counts=={'single-file-repair':25,'contract-audit':15,'multi-file-repair':23}
    out=ROOT/'.aeep/repository-provisional-pool-native-20261028';out.mkdir(exist_ok=False);target=out/'cases.json';target.write_text(json.dumps(cases,indent=2)+'\n')
    pool={**old,'cases_file':str(target.relative_to(ROOT)),'cases_file_sha256':sha(target),'case_count':63,'repository_count':len({c['source_repository'].casefold() for c in cases}),
        'family_counts':counts,'required_reference_identities':sum(len(c['truth']['fail_to_pass'])+len(c['truth']['pass_to_pass']) for c in cases),'source_runtime_bindings':bindings,
        'inputs':[{'manifest':str(prior.relative_to(ROOT)),'manifest_sha256':sha(prior),'cases_sha256':old['cases_file_sha256']},{'manifest':str((HERE/'completion-audit.json').relative_to(ROOT)),'manifest_sha256':sha(HERE/'completion-audit.json'),'cases_sha256':sha(ROOT/review['cases_file'])}],
        'missing_family_counts':{k:47-n for k,n in counts.items()},'latest_grant':after,'batch_operations_including_build':17,'builds_in_this_batch':0,'batch_charged_operation_seconds':seconds,
        'new_external_calls_for_consolidation':0,'cases_adopted':0,'stages_frozen':False,'qualification':False,'comparative_usefulness':False,'selection':False,
        'native_observer_scope':'Current source/image/program fresh probes and these3 subjects only. Historical bindings for other62 cases remain;no automatic universal observer or model qualification.',
        'initial_docs_result':'FAILED:one extra STATE.md blank line;link scan unstarted. Failure retained separately from grader/package results.'}
    assert pool['required_reference_identities']==4866 and pool['repository_count']==39
    save(HERE/'provisional-pool.json',pool)
    save(HERE/'final-accounting-audit.json',{'passed':True,'canonical_operations_reopened':17,'physical_receipts_and_completed_attempts_reopened':15,'grant_before':before,'grant_after':after,'charged_operation_seconds':seconds,
        'all_operations_complete':True,'model_turns':0,'cash_delta':0,'all_owned_containers_and_canary_absent':True,'all_images_retained':True,'new_calls_for_consolidation':0,'source_digest':review['source_digest'],
        'initial_docs_failure_preserved':True,'installed_wheel20checks_passed':True,'pool_additions':1,'controls_duplicated':0})
    print(json.dumps({k:pool[k] for k in ('case_count','repository_count','family_counts','required_reference_identities','missing_family_counts','latest_grant','batch_charged_operation_seconds')}))

if __name__=='__main__':main()
