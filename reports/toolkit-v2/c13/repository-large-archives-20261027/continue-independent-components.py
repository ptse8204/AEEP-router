"""Run only unstarted approved package/docs checks after known terminal reconciliation."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import digest

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')


def main():
    assert len(sys.argv)==2 and sha(HERE/'approval-bundle.json')==sys.argv[1]
    bundle=json.loads((HERE/'approval-bundle.json').read_text())
    approval=json.loads((HERE/'bundle-operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256']==sys.argv[1]
    assert verification_source_digest(ROOT)==bundle['source_digest']
    assert shutil.disk_usage(ROOT).free>51*1024**3
    for name,expected in bundle['assets'].items():
        path=Path(name);assert path.is_file() and not path.is_symlink() and sha(path)==expected
    save(HERE/'independent-execution-started.json',{'review_sha256':sys.argv[1],'automatic_retry':False})
    proof=json.loads((HERE/'initial-failure-reconciliation.json').read_text())
    assert proof['reconciled'] and proof['uncertain_attempts']==0 and proof['all_owned_containers_absent'] and proof['canary_removed']
    results=[];began=time.perf_counter()
    try:
        for name in ('package','docs'):
            component=bundle['components'][name];directory=Path(component['directory'])
            review=directory/component['review_file'];assert sha(review)==component['review_sha256']
            save(directory/'operator-approval.json',{**approval,'review_sha256':component['review_sha256'],'parent_review_sha256':sys.argv[1],'authority':'Parent actual approval explicitly covers this exact component. Mechanical derivation,not a separate human response.'})
            args=component['argv']
            if name=='package':args=[*args,'--execute-reviewed-digest',digest(json.loads(review.read_text()))]
            else:args=[*args,component['review_sha256']]
            with (HERE/(name+'-component.log')).open('x') as log:
                process=subprocess.run([sys.executable,*args],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=component['maximum_driver_seconds'])
            result_path=directory/component['result_file']
            observed=json.loads(result_path.read_text()) if result_path.exists() else None
            results.append({'component':name,'returncode':process.returncode,'result_file':str(result_path),'result_sha256':sha(result_path) if result_path.exists() else None,'passed':process.returncode==0 and observed is not None and observed.get(component['passed_field']) is True})
            if name=='runtime':
                # A common accounting, authority, identity or cleanup failure blocks all external dispatch.
                assert process.returncode==0 and observed and observed['batch_completed'],'Runtime not reconciled;stop external dispatch'
                audit=json.loads((HERE/'runtime-execution/completion-audit.json').read_text())
                assert audit['all_owned_containers_absent'] and audit['physical_receipt_integrity_passed']
                assert json.loads((HERE/'canary-cleanup.json').read_text())['unchanged_owned_canary_removed']
                assert not (ROOT/bundle['host_canary']).exists()
                # Isolated rejected workloads do not prevent independent package/docs checks.
    finally:
        save(HERE/'independent-execution-result.json',{'review_sha256':sys.argv[1],'components':results,'all_components_passed':len(results)==2 and all(item['passed'] for item in results),'source_unchanged':verification_source_digest(ROOT)==bundle['source_digest'],'driver_wall_seconds':time.perf_counter()-began,'automatic_retry':False,'models':0,'formal_qualification_or_usefulness_or_selection':False})


if __name__=='__main__':main()
