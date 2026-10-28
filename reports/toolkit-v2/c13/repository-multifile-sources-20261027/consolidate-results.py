"""Add only the reproduced Canopen task;retain all rejected control outcomes."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')

def main():
    previous=HERE.parent/'repository-worker-input-20261027/provisional-pool.json';old=json.loads(previous.read_text());old_cases=ROOT/old['cases_file'];assert sha(old_cases)==old['cases_file_sha256']
    audit_path=HERE/'runtime-execution/completion-audit.json';audit=json.loads(audit_path.read_text());assert audit['batch_completed'] and audit['physical_receipt_integrity_passed'] and audit['all_owned_containers_absent']
    assert audit['canonical_receipts_reopened']==audit['terminal_attempts_reopened']==audit['completed_attempts_reopened']==13 and audit['failed_attempts_reopened']==0 and audit['eligible_cases']==['canopen-python__canopen-613-declared-tests']
    build=json.loads((HERE/'build-result.json').read_text());assert build['passed']
    bundle=json.loads((HERE/'bundle-execution-result.json').read_text());assert bundle['all_components_passed'] and bundle['source_unchanged']
    for component in bundle['components']:assert component['passed'] and sha(Path(component['result_file']))==component['result_sha256']
    ledgers=[json.loads((HERE/name).read_text()) for name in ('build-operation-ledger.json','runtime-execution/operation-ledger.json')];operations=[v for ledger in ledgers for v in ledger['operations']];assert len(operations)==16
    with sqlite3.connect('file:/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3?mode=ro',uri=True) as c:
        for o in operations:
            assert c.execute('SELECT state FROM assessment_operations WHERE id=?',(o['operation_id'],)).fetchone()[0]=='complete'
            assert o['elapsed_seconds'] is not None and math.isfinite(o['elapsed_seconds']) and o['elapsed_seconds']>=0
        after=list(c.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    before=build['grant_before'];assert after==audit['grant_after'];seconds=sum(o['elapsed_seconds'] for o in operations)
    assert after[0]-before[0]==16 and after[1]==before[1] and after[3]==before[3] and math.isclose(after[2]-before[2],seconds,abs_tol=1e-7)
    assert json.loads((HERE/'canary-cleanup.json').read_text())['unchanged_owned_canary_removed']
    review=json.loads((HERE/'runtime-review.json').read_text());cases=json.loads(old_cases.read_text());bindings=dict(old['source_runtime_bindings'])
    for case in json.loads((ROOT/review['cases_file']).read_text()):
        identity=case['input']['task_id']
        if identity not in audit['eligible_cases']:continue
        assert identity not in bindings
        cases.append(case);bindings[identity]={'evidence_manifest':str(audit_path.relative_to(ROOT)),'source_digest':review['source_digest'],'image_id':build['image_id'],'image_tag':build['target_tag'],'observer_profile':'Explicit larger-source profile,pytest framing,Hypothesis seed29 and bounded failed-public-log envelope;no automatic campaign qualification','recipe_digest':review['build_request']['recipe_digest']}
    assert len(cases)==len({(c['source_repository'].casefold(),c['source_revision']) for c in cases})==len({c['input']['source_sha256'] for c in cases})==57
    counts=dict(Counter(c['input']['family'] for c in cases));assert counts=={'single-file-repair':22,'contract-audit':15,'multi-file-repair':20}
    out=ROOT/'.aeep/repository-provisional-pool-multifile-20261028';out.mkdir(exist_ok=False);target=out/'cases.json';target.write_text(json.dumps(cases,indent=2)+'\n')
    pool={**old,'cases_file':str(target.relative_to(ROOT)),'cases_file_sha256':sha(target),'case_count':57,'repository_count':len({c['source_repository'].casefold() for c in cases}),'family_counts':counts,'required_reference_identities':sum(len(c['truth']['fail_to_pass'])+len(c['truth']['pass_to_pass']) for c in cases),'source_runtime_bindings':bindings,'inputs':[{'manifest':str(previous.relative_to(ROOT)),'manifest_sha256':sha(previous),'cases_sha256':sha(old_cases)},{'manifest':str(audit_path.relative_to(ROOT)),'manifest_sha256':sha(audit_path),'cases_sha256':sha(ROOT/review['cases_file'])}],'missing_family_counts':{k:47-n for k,n in counts.items()},'latest_grant':after,'batch_operations_including_build':16,'builds_in_this_batch':1,'batch_charged_operation_seconds':seconds,'image_retained':build['image_id'],'new_external_calls_for_consolidation':0,'cases_adopted':0,'stages_frozen':False,'qualification':False,'comparative_usefulness':False,'selection':False}
    assert pool['repository_count']==36 and pool['required_reference_identities']==3067
    save(HERE/'provisional-pool.json',pool);save(HERE/'final-accounting-audit.json',{'passed':True,'canonical_operations_reopened':16,'physical_receipts_and_completed_attempts_reopened':13,'grant_before':before,'grant_after':after,'charged_operation_seconds':seconds,'all_operations_complete':True,'model_turns':0,'cash_delta':0,'canary_removed':True,'all_images_retained':True,'new_calls_for_consolidation':0,'source_digest':review['source_digest']})
    print(json.dumps({k:pool[k] for k in ('case_count','repository_count','family_counts','required_reference_identities','missing_family_counts','latest_grant','batch_charged_operation_seconds')}))

if __name__=='__main__':main()
