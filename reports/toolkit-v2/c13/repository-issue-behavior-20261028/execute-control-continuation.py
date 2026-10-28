"""Execute only the reviewed finite control continuation, then exact unstarted docs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=HERE/'control-continuation'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')

def main():
    assert len(sys.argv)==2 and sys.argv[1]==sha(OUT/'operation-review.json')
    check=json.loads((HERE/'control-correction-check.json').read_text());assert check['passed'] and check['child_review_sha256']==sys.argv[1]
    review=json.loads((OUT/'operation-review.json').read_text());bundle=json.loads((HERE/'approval-bundle.json').read_text());approval=json.loads((HERE/'bundle-operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256']==sha(HERE/'approval-bundle.json')
    for p,h in review['assets'].items():assert sha(Path(p))==h
    save(HERE/'control-execution-started.json',{'review_sha256':sys.argv[1],'parent_approval':approval['review_sha256'],'runner_sha256':sha(Path(__file__)),'automatic_retry':False})
    canary=ROOT/review['host_canary'];assert not canary.exists();marker=b'AEEP reviewed issue-behavior host-only canary; no secret.\n'
    with canary.open('xb') as f:f.write(marker)
    try:
        with(OUT/'run.log').open('x') as log:run=subprocess.run([sys.executable,str(OUT/'run.py'),sys.argv[1]],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=490)
        assert run.returncode==0,'Preserve failed continuation;no retry or independent dispatch until reconciliation'
        with(OUT/'audit.log').open('x') as log:audit=subprocess.run([sys.executable,str(OUT/'audit-execution.py')],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=120)
        assert audit.returncode==0
    finally:
        assert canary.is_file() and not canary.is_symlink() and canary.read_bytes()==marker
        canary.unlink();save(OUT/'canary-cleanup.json',{'unchanged_owned_canary_removed':True})
    result=json.loads((OUT/'completion-audit.json').read_text());assert result['batch_completed'] and result['all_owned_containers_absent'] and result['physical_receipt_integrity_passed']
    docs=bundle['components']['docs'];directory=Path(docs['directory']);assert sha(directory/docs['review_file'])==docs['review_sha256']
    assert not any((directory/n).exists() for n in ('operator-approval.json','execution-started.json','execution-result.json'))
    save(directory/'operator-approval.json',{**approval,'review_sha256':docs['review_sha256'],'parent_review_sha256':approval['review_sha256'],'authority':'Exact unstarted docs component of actual f18daa4a approval,run after reconciled optional dependency failure and completed immutable-payload XS continuation;not a new human response.'})
    with(HERE/'remaining-docs-component.log').open('x') as log:process=subprocess.run([sys.executable,*docs['argv'],docs['review_sha256']],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=docs['maximum_driver_seconds'])
    observed=json.loads((directory/docs['result_file']).read_text());assert process.returncode==0 and observed['passed'] and observed['runtime_removed']
    save(HERE/'remaining-execution-result.json',{'passed':True,'parent_approval':approval['review_sha256'],'original_failed_probe_and_charges_preserved':True,'xs_completion_audit_sha256':sha(OUT/'completion-audit.json'),'xs_cases_reproduced':len(result['eligible_cases']),'xs_contained_calls':result['canonical_receipts_reopened'],'docs_result_sha256':sha(directory/docs['result_file']),'docs_passed':True,'pymdown_not_started':True,'new_models_builds_installs_downloads':0,'no_automatic_retry':True})

if __name__=='__main__':main()
